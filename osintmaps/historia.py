"""La historia en la prensa: noticias de los sitios que tienen nombre.

El visor monta la historia de cada sitio preguntando él mismo a Wikidata, Wikipedia, los
nomenclátores y Catastro, que admiten preguntas de una página web. Google Noticias no: solo
contesta a un programa. De eso se encarga este módulo, de dos maneras:

- «osintmaps historia» recorre los sitios con nombre, busca cada uno en Google Noticias y deja
  lo encontrado en datos/historia.json. Ese fichero viaja con la web publicada, así que las
  noticias se ven también desde el móvil.
- «osintmaps servir» busca al momento cuando el visor se lo pide (/vivo/noticias).

Google Noticias se consulta por su canal RSS (la lista de titulares que ofrece a los lectores de
noticias): de cada noticia se guarda el titular, el medio, la fecha y el enlace, nunca el texto.
Se pregunta despacio y, si Google contesta que son demasiadas peticiones, se para: lo ya buscado
queda guardado y la misma orden, más tarde, sigue donde lo dejó.

Dos cosas hacen falta para que la búsqueda sirva de algo:

- El municipio. «Casa Alta» a secas devuelve noticias de medio mundo; «Casa Alta» + «la Pobla del
  Duc», no. Los sitios de Catastro lo traen; para los demás se pregunta a Photon (el buscador de
  OpenStreetMap) en qué municipio cae el punto.
- Saber si la noticia va del sitio. Google no busca la frase exacta aunque vaya entre comillas:
  devuelve también noticias del pueblo que no tienen nada que ver. Por eso cada noticia lleva
  «nombra»: si el titular contiene el nombre. Las que no lo nombran solo se guardan (tres como
  mucho) cuando el nombre tiene alguna palabra propia y el titular habla de patrimonio, ruinas,
  abandono o del mismo tipo de edificio. Las palabras del municipio no cuentan como propias:
  «Estación de Quart de Poblet» no la nombra cualquier noticia de Quart de Poblet.

Todo apunta a LUGARES: se busca el nombre del sitio, nunca el de una persona.
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
import unicodedata
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlencode
from xml.etree import ElementTree

import requests

from .modelos import Candidato
from .red import pedir

log = logging.getLogger(__name__)

URL_NOTICIAS = "https://news.google.com/rss/search"
URL_PHOTON = "https://photon.komoot.io/reverse"
FUENTE = "Google Noticias (RSS)"
MAX_NOTICIAS = 8
FICHERO = "historia.json"


class Bloqueado(RuntimeError):
    """Google ha contestado «demasiadas peticiones» (429) o «ahora no» (503): toca parar."""


# Artículos y preposiciones: no cuentan como palabras del nombre.
_HUECAS = frozenset("de del la las el los els les l d y i en a al dels sa es un una".split())
# Formas valencianas llevadas a las castellanas, para que «Castell del Borró» y «Castillo de Borró» coincidan.
_FORMA_COMUN = {"castell": "castillo", "moli": "molino", "esglesia": "iglesia", "estacio": "estacion", "pont": "puente",
                "convent": "convento", "monestir": "monasterio", "font": "fuente", "cova": "cueva", "masia": "mas",
                "forn": "horno", "pou": "pozo", "creu": "cruz", "sant": "san", "palau": "palacio", "antic": "antigua",
                "antiga": "antigua", "antiguo": "antigua", "vell": "vieja", "vella": "vieja", "viejo": "vieja"}
# Palabras que por sí solas no distinguen un sitio de otro: tipos de edificio, adjetivos, accidentes
# del terreno y los apellidos y santos más repetidos en los nombres de casas y corrales.
# Adjetivos y otras palabras corrientes que no dicen de qué tipo es el edificio.
_ADJETIVOS = frozenset("""antigua vieja nueva nuevo alta alto baja bajo blanca blanco roja rojo negra negro verde grande gran pequena
    mayor menor larga largo redonda quemada quemado hundida caida rota viejas nuevas altas bajas arriba abajo medio
    norte sur este oeste""".split())
_CORRIENTES = frozenset("""
    casa casas caseta casetas casilla casillas corral corrales corralon molino molinos mas masos alqueria venta ventas
    ermita torre torres castillo iglesia convento monasterio palacio fabrica estacion apeadero cementerio hospital
    sanatorio cuartel balneario nevera aljibe refugio poblado aldea cortijo granja finca huerto huerta horta villa
    chalet chalets nave naves almacen bodega horno pozo puente fuente cueva cuevas cruz mina minas cantera colegio
    escuela escuelas hotel motel fonda posada teatro cine deposito central presa tunel
    antigua vieja nueva nuevo alta alto baja bajo blanca blanco roja rojo negra negro verde grande gran pequena
    mayor menor larga largo redonda quemada quemado hundida caida rota viejas nuevas altas bajas
    san santa santo santos virgen cristo pedro juan jose maria antonio miguel vicente francisco rafael roque jaime
    pere joan josep antoni miquel vicent francesc jaume roc
    mora moro moros rey reina conde duque marques cura fraile frailes monjas tio tia abuelo señor senor don
    beata beato purisima rosario pilar carmen dolores esperanza salud remedios paz luz consuelo angel angeles rosa
    paloma calvario trinidad concepcion asuncion salvador
    rio barranco rambla monte montes pena penas loma lomas llano llanos plana vega hoya cerro cabezo collado puntal
    camino carretera calle plaza arriba abajo medio norte sur este oeste sol luna agua aguas pino pinos olivo higuera
""".split())


def _plano(texto: str) -> str:
    """Minúsculas, sin acentos y sin más signos que letras y cifras: para comparar textos."""
    sin = "".join(c for c in unicodedata.normalize("NFD", str(texto or "")) if not unicodedata.combining(c)).lower()
    return "".join(c if c.isalnum() else " " for c in sin)


def palabras(texto: str) -> list[str]:
    """Las palabras que cuentan de un nombre o de un titular, en su forma común."""
    return [_FORMA_COMUN.get(p, p) for p in _plano(texto).split() if len(p) > 1 and p not in _HUECAS]


# De qué habla un titular que puede interesar aunque no nombre el sitio.
_PISTAS = re.compile(r"patrimoni|abandon|ruina|derrumb|derrib|lista roja|rehabilit|restaur|monument|historic|despobla|arqueol|yacimient"
                     r"|en riesgo|olvid|recupera|proteg|bien de interes|centenari|vestigi|antigu|antic|fantasma|se cae")


def _propias(nombre: str, municipio: str | None = None) -> list[str]:
    """Las palabras del nombre que lo distinguen: ni corrientes, ni cifras, ni las del municipio."""
    del_municipio = set(palabras(municipio or ""))
    return [p for p in dict.fromkeys(palabras(nombre)) if len(p) >= 4 and not p.isdigit() and p not in _CORRIENTES and p not in del_municipio]


def es_distintivo(nombre: str, municipio: str | None = None) -> bool:
    """¿Tiene el nombre alguna palabra propia, que no sea corriente ni del municipio?"""
    return bool(_propias(nombre, municipio))


def se_puede_buscar(nombre: str, municipio: str | None = None) -> bool:
    """Un nombre que es el del municipio y nada más («Camporrobles», en Camporrobles) solo
    devolvería las noticias del pueblo: no merece la pregunta. Tampoco uno de palabras corrientes
    sin municipio que lo acote."""
    del_nombre = set(palabras(nombre))
    if not del_nombre or del_nombre <= set(palabras(municipio or "")):
        return False
    return bool(municipio) or es_distintivo(nombre)


def nombra(titular: str, nombre: str, municipio: str | None = None) -> bool:
    """¿Habla el titular de este sitio? Si el nombre tiene alguna palabra propia, el titular tiene
    que traer esa (o una de ellas) y la mayoría de las demás. Si no tiene ninguna («Casa Alta», «La
    Beata»), tiene que traerlas todas y, además, el municipio: casas altas hay en todas partes."""
    del_nombre = list(dict.fromkeys(palabras(nombre)))
    if not del_nombre:
        return False
    del_titular = set(palabras(titular))
    presentes = [p for p in del_nombre if p in del_titular]
    propias = _propias(nombre, municipio)
    if not propias:
        return len(presentes) == len(del_nombre) and set(palabras(municipio_corto(municipio))) <= del_titular
    return len(presentes) >= math.ceil(0.6 * len(del_nombre)) and any(p in del_titular for p in propias)


def cribar(noticias: list[dict], nombre: str, municipio: str | None = None, tope: int = MAX_NOTICIAS) -> list[dict]:
    """Deja las noticias que merecen enseñarse, en orden: primero las que nombran el sitio y, dentro
    de cada grupo, las más recientes. De las que no lo nombran se quedan tres como mucho, y solo si
    el nombre tiene alguna palabra propia y el titular habla de patrimonio, de abandono o del mismo
    tipo de edificio («molino», «estación»). Sirve también para repasar lo ya guardado."""
    distintivo = es_distintivo(nombre, municipio)
    de_tipo = {p for p in palabras(nombre) if len(p) >= 4 and p in _CORRIENTES and p not in _ADJETIVOS}
    buenas, flojas = [], []
    for n in noticias:
        n = dict(n, nombra=nombra(n.get("titulo", ""), nombre, municipio))
        if n["nombra"]:
            buenas.append(n)
        elif distintivo and (_PISTAS.search(_plano(n["titulo"])) or de_tipo & set(palabras(n["titulo"]))):
            flojas.append(n)
    reciente = lambda n: -int(str(n.get("fecha", "")).replace("-", "") or 0)      # noqa: E731
    return (sorted(buenas, key=reciente) + sorted(flojas, key=reciente)[:3])[:tope]


def nombre_de_busqueda(nombre: str, wikipedia: str | None = None) -> str:
    """Con qué nombre preguntar. Si el sitio tiene artículo de Wikipedia y su título es más corto
    que el nombre, se usa el título: los nombres oficiales largos («Estación de Ferrocarril de X en
    la Línea Y») no los escribe ningún periódico. El título tiene que tener al menos dos palabras
    y una propia, para no cambiar un nombre bueno por uno corriente."""
    nombre = " ".join(str(nombre or "").split())
    if wikipedia and ":" in wikipedia:
        titulo = " ".join(wikipedia.split(":", 1)[1].split("(")[0].replace("_", " ").split())
        if titulo and len(titulo) < len(nombre) and len(palabras(titulo)) >= 2 and es_distintivo(titulo):
            return titulo
    return nombre


def municipio_corto(municipio: str | None) -> str:
    """«Sagunt / Sagunto» → «Sagunt»: los nombres dobles se buscan por el primero."""
    return str(municipio or "").split(" / ")[0].strip()


def consulta_de(nombre: str, municipio: str | None = None) -> str:
    """Lo que se le escribe al buscador: el nombre y el municipio, cada uno entre comillas."""
    limpio = " ".join(str(nombre).replace('"', " ").split())
    lugar = " ".join(municipio_corto(municipio).replace('"', " ").split())
    return f'"{limpio}"' + (f' "{lugar}"' if lugar else "")


def direccion(nombre: str, municipio: str | None = None) -> str:
    """La dirección del canal de titulares para esa búsqueda, en castellano y de España."""
    return URL_NOTICIAS + "?" + urlencode({"q": consulta_de(nombre, municipio), "hl": "es", "gl": "ES", "ceid": "ES:es"})


def leer_rss(contenido: bytes, nombre: str, municipio: str | None = None, tope: int = MAX_NOTICIAS) -> list[dict]:
    """Las noticias de un canal RSS de Google Noticias, ya cribadas y ordenadas (ver `cribar`)."""
    try:
        raiz = ElementTree.fromstring(contenido)
    except ElementTree.ParseError:
        return []
    noticias, vistos = [], set()
    for item in raiz.iter("item"):
        medio = " ".join((item.findtext("source") or "").split())
        titular = " ".join((item.findtext("title") or "").split())
        if medio and titular.endswith(f" - {medio}"):      # Google añade el medio al final del titular
            titular = titular[: -len(medio) - 3].rstrip()
        enlace = (item.findtext("link") or "").strip()
        if not titular or not enlace.startswith("https://") or _plano(titular) in vistos:
            continue
        vistos.add(_plano(titular))
        try:
            fecha = parsedate_to_datetime(item.findtext("pubDate") or "").date().isoformat()
        except (TypeError, ValueError):
            fecha = ""
        noticias.append({"titulo": titular[:300], "medio": medio[:80], "fecha": fecha, "url": enlace})
    return cribar(noticias, nombre, municipio, tope)


def buscar_noticias(sesion: requests.Session, nombre: str, municipio: str | None = None, tope: int = MAX_NOTICIAS) -> list[dict]:
    """Pregunta a Google Noticias por un sitio. Una sola petición, sin reintentos: si Google dice
    que son demasiadas, insistir solo lo empeora."""
    resp = sesion.get(direccion(nombre, municipio), timeout=30)
    if resp.status_code in (429, 503):
        raise Bloqueado(f"Google Noticias ha contestado {resp.status_code}")
    resp.raise_for_status()
    return leer_rss(resp.content, nombre, municipio, tope)


def municipio_de(sesion: requests.Session, lat: float, lon: float) -> str | None:
    """El municipio en el que cae un punto, según OpenStreetMap (Photon). None si no se sabe."""
    try:
        resp = pedir(sesion, "GET", URL_PHOTON, reintentos=2, espera=3.0, timeout=20, params={"lat": lat, "lon": lon, "limit": 3})
        for f in resp.json().get("features", []):
            p = f.get("properties") or {}
            municipio = p.get("city") or p.get("town") or p.get("village")
            if municipio:
                return str(municipio)
    except (requests.RequestException, ValueError) as exc:
        log.warning("Photon no ha dicho el municipio de %.5f, %.5f: %s", lat, lon, exc)
    return None


def leer(ruta: Path) -> dict:
    """Lo guardado en datos/historia.json, o un fichero nuevo si no existe o está estropeado."""
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        if isinstance(datos, dict) and isinstance(datos.get("sitios"), dict):
            return datos
    except (OSError, ValueError):
        pass
    return {"sitios": {}}


def guardar(ruta: Path, datos: dict) -> None:
    """Escribe el fichero entero en otro nombre y luego lo cambia de golpe: si el programa se
    corta a mitad, el fichero bueno sigue siendo el anterior."""
    datos["generado"] = datetime.now().isoformat(timespec="seconds")
    datos["fuente"] = FUENTE
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_suffix(ruta.suffix + ".parcial")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporal.replace(ruta)


def _reciente(entrada: dict | None, dias: int, hoy: date) -> bool:
    try:
        return entrada is not None and (hoy - date.fromisoformat(entrada["consultado"])).days < dias
    except (KeyError, TypeError, ValueError):
        return False


def repasar(sesion: requests.Session, candidatos: Iterable[Candidato], ruta: Path, *, maximo: int | None = None,
            pausa: float = 5.0, dias: int = 30, rehacer: bool = False, decir: Callable[[str], None] = print,
            dormir: Callable[[float], None] = time.sleep, hoy: date | None = None) -> dict:
    """Busca noticias de los sitios con nombre y las deja en `ruta`. Se puede cortar y repetir.

    - Empieza por los de mejor nota: si se corta, lo buscado es lo que más interesa.
    - Lo consultado hace menos de `dias` días no se repite (salvo `rehacer`).
    - Entre una pregunta a Google y la siguiente espera `pausa` segundos.
    - Si Google bloquea, guarda lo que lleva y para.

    Devuelve cuántos ha consultado, cuántos tienen noticias, cuántos quedan y si se paró por bloqueo.
    """
    hoy = hoy or date.today()
    candidatos = list(candidatos)
    datos = leer(ruta)
    sitios = datos["sitios"]
    # Lo ya guardado se vuelve a cribar con las reglas de hoy: si han cambiado, el fichero no se queda con las de ayer.
    for entrada in sitios.values():
        if entrada.get("noticias"):
            entrada["noticias"] = cribar(entrada["noticias"], entrada.get("nombre", ""), entrada.get("municipio")) if se_puede_buscar(entrada.get("nombre", ""), entrada.get("municipio")) else []
    con_nombre = sorted((c for c in candidatos if c.nombre and c.nombre.strip()), key=lambda c: -c.puntuacion)
    pendientes = [c for c in con_nombre if rehacer or not _reciente(sitios.get(c.id), dias, hoy)]
    tanda = pendientes if maximo is None else pendientes[:max(0, maximo)]
    hechos = fallos = 0
    bloqueado = False
    # Varios sitios pueden llamarse igual y estar en el mismo municipio (los tramos de una vía abandonada):
    # la misma pregunta no se hace dos veces, ni en esta tanda ni si ya se hizo hace poco.
    ya_preguntado = {e["consulta"]: e["noticias"] for e in sitios.values() if e.get("consulta") and _reciente(e, dias, hoy) and not rehacer}
    for c in tanda:
        nombre = nombre_de_busqueda(c.nombre, c.wikipedia)
        municipio = c.municipio or (sitios.get(c.id) or {}).get("municipio") or municipio_de(sesion, c.lat, c.lon) or ""
        entrada = {"nombre": nombre, "municipio": municipio, "consulta": "", "consultado": hoy.isoformat(), "noticias": []}
        # Un nombre de palabras corrientes y sin municipio que lo acote, o que es el del municipio, no merece la pregunta.
        if se_puede_buscar(nombre, municipio):
            entrada["consulta"] = consulta_de(nombre, municipio)
            if entrada["consulta"] in ya_preguntado:
                entrada["noticias"] = [dict(n) for n in ya_preguntado[entrada["consulta"]]]
                sitios[c.id] = entrada
                hechos += 1
                continue
            try:
                entrada["noticias"] = buscar_noticias(sesion, nombre, municipio)
            except Bloqueado as exc:
                decir(f"{exc}: se para aquí. Repite la orden dentro de un rato y seguirá donde lo ha dejado.")
                bloqueado = True
                break
            except requests.RequestException as exc:
                # Un fallo suelto de red no se apunta como «sin noticias»: ese sitio se reintentará otro día.
                log.warning("No se han podido buscar noticias de %s: %s", nombre, exc)
                fallos += 1
                if fallos >= 5:
                    decir("Demasiados fallos de red seguidos: se para aquí.")
                    break
                dormir(pausa)
                continue
            fallos = 0
            ya_preguntado[entrada["consulta"]] = entrada["noticias"]
            dormir(pausa)
        sitios[c.id] = entrada
        hechos += 1
        if hechos % 20 == 0:
            guardar(ruta, datos)
            decir(f"  {hechos} de {len(tanda)} sitios consultados…")
    # Fuera lo de sitios que ya no están en la lista.
    vivos = {c.id for c in candidatos}
    datos["sitios"] = {k: v for k, v in sitios.items() if k in vivos}
    guardar(ruta, datos)
    return {"consultados": hechos, "con_noticias": sum(1 for v in datos["sitios"].values() if v.get("noticias")),
            "guardados": len(datos["sitios"]), "pendientes": len(pendientes) - hechos, "bloqueado": bloqueado}
