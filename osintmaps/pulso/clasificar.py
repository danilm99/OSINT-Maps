"""Qué dice un texto y si es de València: reglas sencillas, en castellano y en valenciano.

Es lo que se usa siempre y, si hay IA local (ia.py), lo que se usa mientras ella no ha
leído el texto o cuando no está encendida. Las reglas son palabras clave por categoría; la
IA afina después (entiende la frase, sitúa mejor el lugar y descarta lo que no es de aquí).
"""

from __future__ import annotations

import re

from .zonas import normalizar

# Categoría -> raíces de palabra (sin acentos, en minúscula). El orden importa: gana la primera con más aciertos.
CATEGORIAS: dict[str, tuple[str, ...]] = {
    "emergencia": ("incendi", "fuego", "foc ", "humo", "fum ", "explosi", "derrumb", "desplom", "evacua", "bombero", "bomber",
                   "rescat", "fuga de gas", "inundac", "inundaci", "socavon"),
    "accidente": ("accident", "atropell", "colisi", "choque", "chocan", "herido", "ferit", "fallec", "muere", "mor ", "vuelca",
                  "siniestro", "patinete", "motorista"),
    "seguridad": ("polic", "detenid", "detingut", "robo", "atraco", "apunal", "agresi", "tiroteo", "pelea", "reyerta", "okup",
                  "desaloj", "guardia civil", "operacion", "narco", "droga", "vandal", "hurto"),
    "protesta": ("manifestaci", "concentraci", "protesta", "huelga", "vaga ", "pancarta", "marcha ", "cacerolada", "acampada",
                 "sindicat", "reivindic"),
    "trafico": ("trafico", "transit", "atasco", "retenci", "corte de", "cortad", "tallat", "desvio", "carril", "calzada",
                "circulaci", "semaforo", "zona de bajas emisiones", "zbe"),
    "transporte": ("metro", "metrovalencia", "fgv", "emt", "autobus", "tranvia", "tramvia", "cercanias", "renfe", "valenbisi",
                   "aeropuerto", "taxi", "estacion del nord", "linea "),
    "meteo": ("lluvia", "pluja", "tormenta", "granizo", "viento", "vent ", "aviso amarillo", "aviso naranja", "aviso rojo", "dana",
              "calor", "temperatura", "aemet", "temporal de", "temporal marit", "niebla", "calima", "ola de frio"),
    "evento": ("concierto", "concert", "festival", "partido", "mestalla", "falla", "mascleta", "procesi", "cabalgata", "feria",
               "fiesta", "festa", "maraton", "carrera popular", "exposici", "espectaculo", "roig arena", "verbena", "nit de",
               "cremà", "crema", "ofrenda", "fuegos artificiales", "castillo de fuegos"),
    "vivienda": ("vivienda", "alquiler", "lloguer", "desahucio", "desnonament", "pisos turisticos", "apartamentos turisticos",
                 "habitatge", "inquilin"),
    "urbanismo": ("obras", "urbanism", "reforma", "remodelaci", "licencia", "derribo", "edificio", "solar", "plan general"),
    "sanidad": ("hospital", "urgencias", "sanidad", "sanitat", "centro de salud", "ambulancia", "samu", "brote"),
    "medioambiente": ("contaminaci", "ruido", "soroll", "basura", "residuos", "limpieza", "plaga", "mosquito", "playa", "albufera"),
    "politica": ("alcaldesa", "alcalde", "pleno", "concejal", "regidor", "generalitat", "consell", "corts", "compromis",
                 "psoe", "partido popular", " pp ", " vox ", "eleccion", "presupuesto"),
    "deporte": ("valencia cf", "levante ud", "valencia basket", "futbol", "baloncesto", "liga ", "gol ", "entrenador"),
}
URGENTES = ("muere", "fallec", "mortal", "grave", "incendio", "explosi", "evacua", "herido", "tiroteo", "apunal", "derrumb",
            "atrapad", "desaparec", "rescat", "ultima hora", "urgente")
# Otras Valencias, y cosas que se llaman así pero no son la ciudad.
OTRAS_VALENCIAS = ("venezuela", "carabobo", "valencia de don juan", "valencia de alcantara", "valencia del ventoso",
                   "valencia de las torres", "puerto cabello", "maracay", "cheste", "circuit ricardo tormo", "motogp")
MENCIONES_CIUDAD = ("valencia", "valencian", "vlc", "cap i casal", "ajuntament", "ayuntamiento de valencia", "catalina")


def categoria(texto: str) -> tuple[str, int]:
    """(categoría, urgencia 0..3) por palabras clave."""
    t = " " + normalizar(texto) + " "
    mejor, aciertos = "", 0
    for cat, raices in CATEGORIAS.items():
        n = sum(1 for r in raices if r in t)
        if n > aciertos:
            mejor, aciertos = cat, n
    urgencia = 0
    graves = any(u in t for u in URGENTES)
    if mejor == "emergencia":
        # Hablar de inundaciones o de bomberos no es una emergencia en marcha: hace falta algo que suene a ahora.
        urgencia = 1 + graves + any(u in t for u in ("muere", "fallec", "mortal", "evacua", "atrapad", "explosi"))
    elif mejor in ("accidente", "seguridad"):
        urgencia = 1 + graves + any(u in t for u in ("muere", "fallec", "mortal"))
    elif mejor in ("protesta", "trafico", "transporte", "meteo"):
        urgencia = 1 + (mejor == "meteo" and ("naranja" in t or "rojo" in t))
    return mejor or "otros", min(3, urgencia)


def es_de_valencia(texto: str, hay_lugar: bool) -> bool:
    """¿Habla de la ciudad? Si se ha encontrado un lugar de la ciudad en el texto, sí; si no, hace falta
    que la nombre y que no sea otra Valencia (la de Venezuela, el circuito de Cheste...)."""
    t = " " + normalizar(texto) + " "
    if any(o in t for o in OTRAS_VALENCIAS):
        return hay_lugar and "venezuela" not in t
    return hay_lugar or any(re.search(rf"\b{re.escape(m)}\b", t) for m in MENCIONES_CIUDAD)


def limpiar_html(texto: str) -> str:
    """Texto plano de un trozo de HTML (de un RSS o de Mastodon)."""
    import html as _html
    t = re.sub(r"<br\s*/?>|</p>", " ", str(texto or ""), flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    return re.sub(r"\s+", " ", _html.unescape(t)).strip()
