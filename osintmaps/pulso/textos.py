"""Lo que se dice de la ciudad: prensa local, Bluesky, Mastodon, avisos meteorológicos e
incidencias de tráfico de la DGT.

Cada fuente devuelve `Item`s en bruto. Antes de guardarlos, `enriquecer` los sitúa en el mapa
con el nomenclátor (zonas.py), les pone categoría y urgencia (clasificar.py) y tira lo que no
es de València. La IA local, si está, los vuelve a leer después y afina (ia.py).

De las redes sociales se guarda el texto público, la fecha y el enlace a la publicación; no se
guarda quién la escribió ni se junta nada por persona: lo que interesa es cuánto se habla de
un sitio y de qué, no de quién.
"""

from __future__ import annotations

import email.utils
import hashlib
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

from . import clasificar
from .fuentes import Fuente, Item, Toma

PRENSA: dict[str, str] = {
    "Las Provincias": "https://www.lasprovincias.es/rss/2.0/?section=valencia-ciudad",
    "Las Provincias (última hora)": "https://www.lasprovincias.es/rss/2.0/?section=ultima-hora",
    "Valencia Plaza": "https://valenciaplaza.com/rss",
    "elDiario.es CV": "https://www.eldiario.es/rss/comunitat-valenciana/",
    "Europa Press CV": "https://www.europapress.es/rss/rss.aspx?ch=00192",
    "20minutos Valencia": "https://www.20minutos.es/rss/valencia/",
    "El Mundo CV": "https://e00-elmundo.uecdn.es/elmundo/rss/valencia.xml",
}
# Idiomas de lo que se lee en redes (lo que viene marcado en otro idioma no es de aquí: anuncios de la marca
# «Valencia» en portugués, la Valencia de Venezuela en inglés...). Lo que no dice idioma se queda.
IDIOMAS_DE_AQUI = {"es", "ca", "va", "en"}
_VACIAS = set("de la el en y a los las del un una por con para que se al es su lo como más o sus le ya pero sin sobre este esta entre "
              "cuando muy tras ante hasta desde son ha han fue ser hay tiene valencia valència valenciano valenciana hoy ayer".split())


def palabras_clave(titulo: str) -> frozenset[str]:
    """Las palabras con contenido de un titular (sin tildes, sin las vacías y sin las de menos de cuatro letras)."""
    limpio = "".join(c for c in unicodedata.normalize("NFD", (titulo or "").lower()) if unicodedata.category(c) != "Mn")
    return frozenset(p for p in re.findall(r"[a-z0-9]{4,}", limpio) if p not in _VACIAS)


def hilos(textos: list[dict], horas: float = 18.0) -> list[dict]:
    """Junta las noticias que cuentan el mismo hecho: titulares con la mitad de las palabras clave en común (y al
    menos tres) publicados con menos de `horas` de diferencia. Devuelve una entrada por hilo, la más reciente, con
    «mas»: los otros medios que lo cuentan ({medio, titulo, url, t}). El orden de entrada se respeta."""
    grupos: list[tuple[frozenset[str], dict]] = []
    for tx in textos:
        claves = palabras_clave(tx.get("titulo") or "")
        puesto = False
        if len(claves) >= 3 and tx.get("fuente") == "prensa":
            for claves_g, cabeza in grupos:
                comun = len(claves & claves_g)
                if cabeza.get("fuente") == "prensa" and comun >= 3 and comun >= 0.5 * min(len(claves), len(claves_g)) \
                        and abs((cabeza.get("t") or 0) - (tx.get("t") or 0)) <= horas * 3600:
                    cabeza.setdefault("mas", []).append({k: tx.get(k) for k in ("medio", "titulo", "url", "t")})
                    # Lo que uno sitúa o da por urgente vale para el hilo.
                    for k in ("lat", "lon", "barrio", "lugar"):
                        if cabeza.get(k) is None and tx.get(k) is not None:
                            cabeza[k] = tx[k]
                    cabeza["urgencia"] = max(cabeza.get("urgencia") or 0, tx.get("urgencia") or 0)
                    puesto = True
                    break
        if not puesto:
            grupos.append((claves, dict(tx)))
    return [cabeza for _, cabeza in grupos]
# Secciones que son solo de la ciudad: lo que publican es de aquí aunque no nombre València.
PRENSA_DE_LA_CIUDAD = {"Las Provincias"}
BLUESKY = "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts"
BLUESKY_BUSQUEDAS = (("València", None), ("Valencia", "es"), ("Valencia", "ca"))
MASTODON = ("mastodon.social", "masto.es", "mastodon.uno", "tkz.one")
MASTODON_ETIQUETAS = ("valencia", "vlc")
METEOALARM = "https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-spain"
DGT = "https://nap.dgt.es/datex2/v3/dgt/SituationPublication/datex2_v36.xml"
CAJA_AREA = (-0.62, 39.30, -0.20, 39.62)          # oeste, sur, este, norte: València y su área metropolitana
MAX_TEXTO = 1000


def _id(*partes: str) -> str:
    return hashlib.sha1("|".join(partes).encode("utf-8")).hexdigest()[:16]


def _segundos(fecha: str | None) -> int | None:
    if not fecha:
        return None
    try:
        return int(email.utils.parsedate_to_datetime(fecha).timestamp())
    except (TypeError, ValueError):
        pass
    try:
        return int(datetime.fromisoformat(fecha.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _local(etiqueta: str) -> str:
    return etiqueta.rsplit("}", 1)[-1]


# --------------------------------------------------------------------------
# Prensa
# --------------------------------------------------------------------------

def leer_rss(contenido: bytes, medio: str) -> list[Item]:
    """Noticias de un RSS 2.0 o Atom."""
    raiz = ET.fromstring(contenido)
    items = []
    for nodo in raiz.iter():
        if _local(nodo.tag) not in ("item", "entry"):
            continue
        campos: dict[str, str] = {}
        for hijo in nodo:
            nombre = _local(hijo.tag)
            if nombre == "link" and hijo.get("href"):
                campos.setdefault("link", hijo.get("href"))
            elif hijo.text and nombre not in campos:
                campos[nombre] = hijo.text.strip()
        titulo = clasificar.limpiar_html(campos.get("title", ""))
        enlace = campos.get("link") or campos.get("guid") or ""
        if not titulo or not enlace.startswith("http"):
            continue
        t = _segundos(campos.get("pubDate") or campos.get("published") or campos.get("updated") or campos.get("date")) or int(time.time())
        resumen = clasificar.limpiar_html(campos.get("description") or campos.get("summary") or campos.get("encoded") or "")
        items.append(Item(f"prensa:{_id(enlace)}", "prensa", t, titulo[:300], resumen[:MAX_TEXTO], enlace, extra={"medio": medio}))
    return items


def tomar_prensa(sesion: requests.Session, geometria: bool = True) -> Toma:
    items, fallos = [], 0
    for medio, url in PRENSA.items():
        try:
            resp = sesion.get(url, timeout=20, headers={"Accept": "application/rss+xml, application/xml, text/xml, */*"})
            resp.raise_for_status()
            items.extend(leer_rss(resp.content, medio))
        except Exception:  # noqa: BLE001  (un medio caído no tumba los demás)
            fallos += 1
    if fallos == len(PRENSA):
        raise RuntimeError("ningún medio ha contestado")
    return Toma(items=items)


# --------------------------------------------------------------------------
# Redes abiertas
# --------------------------------------------------------------------------

def leer_bluesky(datos: dict) -> list[Item]:
    items = []
    for post in datos.get("posts") or []:
        registro = post.get("record") or {}
        texto = str(registro.get("text") or "").strip()
        uri = str(post.get("uri") or "")
        m = re.match(r"at://(did:[^/]+)/app\.bsky\.feed\.post/(\w+)", uri)
        if not texto or not m:
            continue
        t = _segundos(registro.get("createdAt")) or int(time.time())
        idiomas = registro.get("langs") or []
        if idiomas and not any(str(i).split("-")[0].lower() in IDIOMAS_DE_AQUI for i in idiomas):
            continue
        items.append(Item(f"bsky:{m.group(2)}:{_id(m.group(1))}", "bluesky", t, texto[:200], texto[:MAX_TEXTO],
                          f"https://bsky.app/profile/{m.group(1)}/post/{m.group(2)}", idioma=idiomas[0] if idiomas else "",
                          extra={"me_gusta": post.get("likeCount") or 0, "compartido": post.get("repostCount") or 0}))
    return items


def tomar_bluesky(sesion: requests.Session, geometria: bool = True) -> Toma:
    items, ok = [], 0
    for consulta, idioma in BLUESKY_BUSQUEDAS:
        parametros = {"q": consulta, "limit": 100, "sort": "latest"}
        if idioma:
            parametros["lang"] = idioma
        try:
            resp = sesion.get(BLUESKY, params=parametros, timeout=20)
            resp.raise_for_status()
            items.extend(leer_bluesky(resp.json()))
            ok += 1
        except Exception:  # noqa: BLE001
            continue
        time.sleep(1)
    if not ok:
        raise RuntimeError("Bluesky no ha contestado")
    return Toma(items=items)


def leer_mastodon(datos: list, instancia: str) -> list[Item]:
    items = []
    for estado in datos or []:
        if estado.get("reblog"):
            continue
        texto = clasificar.limpiar_html(estado.get("content") or "")
        url = estado.get("url") or estado.get("uri") or ""
        if not texto or not url:
            continue
        t = _segundos(estado.get("created_at")) or int(time.time())
        items.append(Item(f"masto:{_id(estado.get('uri') or url)}", "mastodon", t, texto[:200], texto[:MAX_TEXTO], url,
                          idioma=estado.get("language") or "", extra={"instancia": instancia}))
    return items


def tomar_mastodon(sesion: requests.Session, geometria: bool = True) -> Toma:
    items, ok = [], 0
    for instancia in MASTODON:
        for etiqueta in MASTODON_ETIQUETAS:
            try:
                resp = sesion.get(f"https://{instancia}/api/v1/timelines/tag/{etiqueta}", params={"limit": 40}, timeout=20)
                resp.raise_for_status()
                items.extend(leer_mastodon(resp.json(), instancia))
                ok += 1
            except Exception:  # noqa: BLE001
                continue
    if not ok:
        raise RuntimeError("ninguna instancia de Mastodon ha contestado")
    return Toma(items=items)


# --------------------------------------------------------------------------
# Avisos
# --------------------------------------------------------------------------

FENOMENOS = {"coastalevent": "fenómenos costeros", "coastal": "fenómenos costeros", "wind": "viento", "rain": "lluvia",
             "thunderstorm": "tormentas", "snow": "nieve", "ice": "hielo", "fog": "niebla", "high-temperature": "calor",
             "low-temperature": "frío", "forest-fire": "incendios forestales", "avalanche": "aludes", "flood": "inundaciones",
             "rain-flood": "lluvias e inundaciones"}


def aviso_en_castellano(evento: str, severidad: str) -> str:
    """«Moderate coastalevent warning» -> «Aviso amarillo por fenómenos costeros»."""
    color = {"Moderate": "amarillo", "Severe": "naranja", "Extreme": "rojo"}.get(severidad, "")
    t = evento.lower()
    fenomeno = next((v for k, v in sorted(FENOMENOS.items(), key=lambda x: -len(x[0])) if k in t), "")
    if not fenomeno:
        return evento or "Aviso meteorológico"
    return f"Aviso {color + ' ' if color else ''}por {fenomeno}"


def leer_meteoalarm(contenido: bytes, ahora: float | None = None) -> list[Item]:
    """Avisos meteorológicos de AEMET (vía Meteoalarm) de las zonas del litoral de Valencia, vigentes."""
    ahora = ahora or time.time()
    raiz = ET.fromstring(contenido)
    items = []
    for entrada in raiz.iter():
        if _local(entrada.tag) != "entry":
            continue
        c = {_local(h.tag): (h.text or "").strip() for h in entrada}
        zona = c.get("areaDesc", "")
        if "valencia" not in clasificar.normalizar(zona) or "litoral" not in clasificar.normalizar(zona):
            continue
        fin = _segundos(c.get("expires"))
        if fin and fin < ahora:
            continue
        inicio = _segundos(c.get("onset") or c.get("effective") or c.get("sent")) or int(ahora)
        severidad = c.get("severity", "")
        urgencia = {"Moderate": 1, "Severe": 2, "Extreme": 3}.get(severidad, 1)
        titulo = f"{aviso_en_castellano(c.get('event') or c.get('title') or '', severidad)} ({zona})"
        enlace = next((h.get("href") for h in entrada if _local(h.tag) == "link" and h.get("href")), "https://www.aemet.es/es/eltiempo/prediccion/avisos")
        items.append(Item(f"meteo:{_id(c.get('id', ''), titulo, str(inicio))}", "meteoalarm", inicio, titulo[:200],
                          f"{c.get('event', '')}. Nivel: {severidad}. Hasta: {time.strftime('%d/%m %H:%M', time.localtime(fin)) if fin else '¿?'}.",
                          enlace, categoria="meteo", urgencia=urgencia, lugar=zona, extra={"hasta": fin}))
    return items


def tomar_meteoalarm(sesion: requests.Session, geometria: bool = True) -> Toma:
    resp = sesion.get(METEOALARM, timeout=30)
    resp.raise_for_status()
    return Toma(items=leer_meteoalarm(resp.content))


# Tipos de incidencia de la DGT (DATEX II) en castellano.
TIPOS_DGT = {
    "Accident": ("Accidente", "accidente", 2), "VehicleObstruction": ("Vehículo detenido", "trafico", 1),
    "AbnormalTraffic": ("Tráfico anormal (retenciones)", "trafico", 1), "MaintenanceWorks": ("Obras", "trafico", 0),
    "RoadOrCarriagewayOrLaneManagement": ("Corte o restricción de carril", "trafico", 1), "ConstructionWorks": ("Obras", "trafico", 0),
    "PoorEnvironmentConditions": ("Condiciones meteorológicas adversas", "meteo", 1), "GeneralObstruction": ("Obstáculo en la vía", "trafico", 1),
    "AnimalPresenceObstruction": ("Animales en la vía", "trafico", 1), "EnvironmentalObstruction": ("Obstáculo (inundación, desprendimiento...)", "emergencia", 2),
    "InfrastructureDamageObstruction": ("Daños en la infraestructura", "trafico", 1), "PublicEvent": ("Acto público", "evento", 1),
    "DisturbanceActivity": ("Alteración del orden", "seguridad", 2), "ReroutingManagement": ("Desvío", "trafico", 1),
    "SpeedManagement": ("Limitación de velocidad", "trafico", 0), "WinterDrivingManagement": ("Restricción por nieve o hielo", "meteo", 1),
}


def leer_dgt(contenido: bytes, caja: tuple[float, float, float, float] = CAJA_AREA) -> list[Item]:
    """Incidencias de tráfico de la DGT dentro de la caja. El fichero es de toda España (varios MB):
    se lee por partes, sin cargarlo entero."""
    import io
    oeste, sur, este, norte = caja
    items = []
    for _, nodo in ET.iterparse(io.BytesIO(contenido), events=("end",)):
        if _local(nodo.tag) != "situationRecord":
            continue
        tipo = (nodo.get("{http://www.w3.org/2001/XMLSchema-instance}type") or "").split(":")[-1]
        lat = lon = None
        textos, carretera, inicio, sentido = [], "", None, ""
        for h in nodo.iter():
            nombre = _local(h.tag)
            if nombre == "latitude" and lat is None:
                lat = float(h.text)
            elif nombre == "longitude" and lon is None:
                lon = float(h.text)
            elif nombre == "roadName" and not carretera:
                carretera = " ".join(x.text for x in h.iter() if _local(x.tag) == "value" and x.text)
            elif nombre == "overallStartTime" and inicio is None:
                inicio = _segundos(h.text)
            elif nombre in ("comment", "generalPublicComment") and h is not None:
                textos.extend(x.text.strip() for x in h.iter() if _local(x.tag) == "value" and x.text)
            elif nombre == "directionRelativeOnLinearSection" and h.text:
                sentido = h.text
        ident = nodo.get("id") or ""
        nodo.clear()
        if lat is None or lon is None or not (sur <= lat <= norte and oeste <= lon <= este):
            continue
        etiqueta, cat, urgencia = TIPOS_DGT.get(tipo, ("Incidencia", "trafico", 1))
        titulo = f"{etiqueta}{' en ' + carretera if carretera else ''}"
        items.append(Item(f"dgt:{ident}", "dgt", inicio or int(time.time()), titulo[:200], " ".join(textos)[:MAX_TEXTO],
                          "https://infocar.dgt.es/etraffic/", round(lat, 5), round(lon, 5), categoria=cat, urgencia=urgencia,
                          lugar=carretera, extra={"tipo": tipo, "sentido": sentido}))
    return items


def tomar_dgt(sesion: requests.Session, geometria: bool = True) -> Toma:
    resp = sesion.get(DGT, timeout=60)
    resp.raise_for_status()
    return Toma(items=leer_dgt(resp.content))


# --------------------------------------------------------------------------
# Situar y clasificar
# --------------------------------------------------------------------------

def enriquecer(items: list[Item], zonas) -> list[Item]:
    """Sitúa cada texto, le pone categoría y tira lo que no es de la ciudad. Los avisos que ya traen
    sitio (DGT) o que son de toda la ciudad (meteo, Renfe) se quedan como vienen. Sin nomenclátor
    (los primeros minutos tras arrancar) no se sitúa nada, pero lo que no es de València se tira igual."""
    hay_mapa = zonas is not None and zonas.hay
    salida = []
    for it in items:
        texto = f"{it.titulo}. {it.texto}"
        situado = False
        if it.lat is None and it.fuente not in ("meteoalarm", "renfe") and hay_mapa:
            en_ciudad = [l for l in zonas.buscar(texto) if l.barrio]
            if en_ciudad:
                l = en_ciudad[0]
                it.lat, it.lon, it.barrio, it.lugar = l.lat, l.lon, l.barrio, l.nombre
                it.extra["confianza_lugar"] = l.confianza
                situado = True
        elif it.lat is not None and hay_mapa and not it.barrio:
            it.barrio = zonas.barrio_de(it.lat, it.lon)
        if it.fuente in ("prensa", "bluesky", "mastodon"):
            de_la_ciudad = it.extra.get("medio") in PRENSA_DE_LA_CIUDAD and not any(o in texto.lower() for o in clasificar.OTRAS_VALENCIAS)
            if not (de_la_ciudad or clasificar.es_de_valencia(texto, situado)):
                continue
        if not it.categoria:
            it.categoria, it.urgencia = clasificar.categoria(texto)
        salida.append(it)
    return salida


FUENTES: tuple[Fuente, ...] = (
    Fuente("prensa", "Prensa local", 600, tomar_prensa, grupo="textos", origen="Las Provincias, Valencia Plaza, elDiario.es, Europa Press, 20minutos, El Mundo"),
    Fuente("bluesky", "Bluesky", 300, tomar_bluesky, grupo="redes", origen="Bluesky (búsqueda pública)"),
    Fuente("mastodon", "Mastodon", 600, tomar_mastodon, grupo="redes", origen="mastodon.social, masto.es, mastodon.uno, tkz.one"),
    Fuente("meteoalarm", "Avisos meteorológicos", 900, tomar_meteoalarm, grupo="textos", origen="AEMET vía Meteoalarm"),
    Fuente("dgt", "Incidencias DGT", 600, tomar_dgt, grupo="textos", origen="DGT (DATEX II)"),
)
INDICADORES: dict[str, dict] = {}
