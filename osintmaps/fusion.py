"""Fusión de candidatos de distintas fuentes.

El mismo sitio puede salir tres veces: como edificio ruinoso en Catastro, como
objeto abandonado en OSM y como elemento de Wikidata. Aquí se juntan en uno
solo, que además gana puntos por estar confirmado por varias fuentes.

Reglas:
1. Un punto de OSM/Wikidata que cae sobre (o muy cerca de) un contorno de
   Catastro se incorpora a ese candidato.
2. Los puntos que sobran se agrupan entre sí si están cerca, o si OSM y
   Wikidata se enlazan explícitamente (etiqueta wikidata=Q...).
"""

from __future__ import annotations

from collections import defaultdict

import shapely
from shapely.strtree import STRtree

from .geo import ProyeccionLocal
from .modelos import ESTADOS, Candidato

# Categorías "de relleno": si otra fuente da una más concreta, se prefiere esa.
_GENERICAS = {"otro", "residencial", "agrario", "equipamiento", "oficinas", "comercial", "patrimonio"}


def _absorber(principal: Candidato, otro: Candidato) -> None:
    """Vuelca en `principal` lo que `otro` aporta."""
    principal.osm_ids += [x for x in otro.osm_ids if x not in principal.osm_ids]
    for clave, valor in otro.etiquetas.items():
        principal.etiquetas.setdefault(clave, valor)
    if otro.debil and not principal.debil:
        return   # un eco de Catastro deja su enlace a OSM, pero no cuenta como confirmación
    for fuente in otro.fuentes:
        if fuente not in principal.fuentes:
            principal.fuentes.append(fuente)
    principal.nombre = principal.nombre or otro.nombre
    principal.wikidata = principal.wikidata or otro.wikidata
    principal.wikipedia = principal.wikipedia or otro.wikipedia
    principal.municipio = principal.municipio or otro.municipio
    principal.refcats += [x for x in otro.refcats if x not in principal.refcats]
    # Manda la categoría de quien describe el sitio (OSM con tipo, Wikidata) sobre
    # el uso genérico de Catastro; entre iguales, la concreta sobre la de relleno.
    if otro.tipo_confirmado and not principal.tipo_confirmado:
        principal.categoria, principal.tipo_confirmado = otro.categoria, True
    elif (otro.tipo_confirmado == principal.tipo_confirmado
          and principal.categoria in _GENERICAS and otro.categoria not in _GENERICAS):
        principal.categoria = otro.categoria
    # Se conserva el estado más grave de los dos.
    if otro.estado and (principal.estado is None
                        or ESTADOS.index(otro.estado) < ESTADOS.index(principal.estado)):
        principal.estado = otro.estado


def fusionar(
    catastro: list[Candidato],
    puntos: list[Candidato],
    *,
    dist_contorno: float = 30.0,
    dist_puntos: float = 50.0,
    cobertura: list[tuple[float, float, float, float]] | None = None,
) -> list[Candidato]:
    """Devuelve la lista única de candidatos.

    `cobertura` son las cajas (oeste, sur, este, norte) de los municipios que
    Catastro procesó bien. Dentro de ellas, los edificios sueltos de OSM sin
    nombre ni tipo que no caen sobre ningún candidato de Catastro se tiran: son
    ruinas que ya quedaron por debajo del tamaño mínimo. Fuera (municipio que
    falló, País Vasco, Navarra) se conservan, porque ahí OSM es lo único que hay.
    """
    todos = catastro + puntos
    if not todos:
        return []
    proy = ProyeccionLocal(
        sum(c.lat for c in todos) / len(todos),
        sum(c.lon for c in todos) / len(todos),
    )
    xy = [shapely.Point(proy.punto(c.lat, c.lon)) for c in puntos]

    # 1) Puntos sobre contornos de Catastro.
    sueltos = list(range(len(puntos)))
    if catastro and puntos:
        contornos = [
            proy.geometria(c.huella) if c.huella is not None
            else shapely.Point(proy.punto(c.lat, c.lon))
            for c in catastro
        ]
        arbol = STRtree(contornos)
        sueltos = []
        for i, punto in enumerate(xy):
            cerca = arbol.query(punto, predicate="dwithin", distance=dist_contorno)
            if len(cerca):
                mejor = min(cerca.tolist(), key=lambda j: contornos[j].distance(punto))
                _absorber(catastro[mejor], puntos[i])
            else:
                sueltos.append(i)
    if cobertura:
        def cubierto(c: Candidato) -> bool:
            return any(o <= c.lon <= e and s <= c.lat <= n for o, s, e, n in cobertura)
        sueltos = [i for i in sueltos if not (puntos[i].debil and cubierto(puntos[i]))]

    # 2) Agrupar los puntos sueltos entre sí (union-find).
    padre = {i: i for i in sueltos}

    def raiz(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    def unir(i: int, j: int) -> None:
        ri, rj = raiz(i), raiz(j)
        if ri != rj:
            padre[ri] = rj

    if sueltos:
        geoms = [xy[i] for i in sueltos]
        arbol = STRtree(geoms)
        a, b = arbol.query(geoms, predicate="dwithin", distance=dist_puntos)
        for i, j in zip(a.tolist(), b.tolist()):
            unir(sueltos[i], sueltos[j])
        # Enlace explícito OSM -> Wikidata, siempre que no estén absurdamente lejos.
        por_qid: dict[str, list[int]] = defaultdict(list)
        for i in sueltos:
            if puntos[i].wikidata:
                por_qid[puntos[i].wikidata].append(i)
        for indices in por_qid.values():
            for j in indices[1:]:
                if xy[indices[0]].distance(xy[j]) < 2000:
                    unir(indices[0], j)

    grupos: dict[int, list[int]] = defaultdict(list)
    for i in sueltos:
        grupos[raiz(i)].append(i)

    resultado = list(catastro)
    for indices in grupos.values():
        # El representante es el de OSM (posición más fiable) con nombre, si lo hay.
        indices.sort(key=lambda i: (puntos[i].debil, "osm" not in puntos[i].fuentes,
                                    puntos[i].nombre is None, puntos[i].id))
        principal = puntos[indices[0]]
        for i in indices[1:]:
            _absorber(principal, puntos[i])
        principal.debil = all(puntos[i].debil for i in indices)
        # Varios objetos de OSM pegados (las casas de una aldea) cuentan como conjunto.
        principal.n_edificios = max(1, sum(1 for i in indices if "osm" in puntos[i].fuentes))
        resultado.append(principal)
    return resultado
