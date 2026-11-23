"""Pulso: la ciudad a lo largo del tiempo.

El visor ya enseña lo que pasa ahora (Valenbisi, aparcamientos, tráfico, aviones). Este
paquete lo va apuntando mientras el programa está abierto, para poder volver atrás:

    fuentes.py      qué se pregunta a cada servicio y cómo se lee la respuesta
    almacen.py      dónde se guarda (un fichero SQLite en la carpeta de datos)
    recolector.py   quién pregunta, cada cuánto, y qué hace cuando un servicio falla
    anomalias.py    qué es lo normal a cada hora y cuándo algo se sale de ello
    resumen.py      el trozo de histórico que pide el visor (o que se publica en la web)
    publicar.py     sube ese resumen a la web sin tocar nada más de ella
    servidor.py     las direcciones /vivo/pulso/... de «osintmaps servir»

Solo hay histórico de los ratos en que el programa ha estado abierto: los huecos se
guardan como huecos y el visor los enseña como tales.
"""

from __future__ import annotations

FICHERO_HISTORICO = "pulso.sqlite"      # en la carpeta de datos; no se publica
FICHERO_RESUMEN = "pulso.json"          # lo que sí se publica: las últimas horas, resumidas
