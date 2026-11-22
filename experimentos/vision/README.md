# Análisis por imagen: qué se puede detectar (prueba del 22/11/2026)

Experimentos, no producto: nada de esta carpeta se instala con el paquete ni lo
usan las pruebas. Sirve para decidir qué merece la pena construir.

## De dónde salen los datos

| Dato | Servicio | Notas |
|---|---|---|
| Foto de 15 cm, color | WMS `https://terramapas.icv.gva.es/0202_2025PVAL0015`, capa `2025PVAL0015_RGB` | Vuelo de primavera de 2025. Admite peticiones desde cualquier web. |
| Foto de 15 cm, infrarrojo | El mismo WMS, capa `2025PVAL0015_IRG` | Canales: infrarrojo, rojo, verde. Con ella sale el NDVI de verdad. Ya es un fondo del visor. |
| Malla 3D de la provincia | I3S en `https://gvagis.icv.gva.es/server/rest/services/Malla3D_{Sur,Centro,Norte,Ademuz}/SceneServer/layers/0` | Es la del «Visor 3D GVA» (`https://visor.gva.es/visor3d/`). Pública, sin clave, y contesta a peticiones desde `danilm99.github.io`. Texturas JPEG y KTX2. Lleva los vértices también sin comprimir, así que se lee con numpy. |
| LiDAR de 5 puntos/m² (IGN, vuelo 2023-24) y su modelo de superficies de 0,5 m | Solo en el Centro de Descargas del CNIG | El formulario de descarga lleva protección contra programas: **no se automatiza**. Hay que bajar los ficheros a mano (unos 100 MB por km²). |

Lo que no existe como servicio: el modelo de superficies del IGN por WCS (solo da
el del terreno, y a 5 m) y la nube de puntos del vuelo de 2025 del ICV.

## 1. ¿Ruina, edificio en uso o solar? (`malla.py` y `estado_imagen.py`)

Para cada huella de Catastro se miden dos cosas:

- **Altura** sobre el terreno de alrededor, leyendo la malla 3D (`malla.py`).
- **Vegetación** dentro de la huella, con el infrarrojo (`estado_imagen.py`).

Ocho candidatos mirados uno a uno:

| Sitio | Altura mediana | % por encima de 2,5 m | Vegetación | A ojo |
|---|---|---|---|---|
| Industrial en Alfafar (solo Catastro) | 1,3 m | 2 | 1 % | Solar: el edificio ya no está |
| Agrario (solo Catastro) | 4,5 m | 65 | 4 % | Casi todo sin tejado |
| Casa del Moral | 2,2 m | 44 | 37 % | Ruina a medias |
| Recinto de Berfull | 5,6 m | 90 | 64 % | Ruina con árboles dentro |
| Benacatázara (huella principal) | 11,4 m | 100 | 7 % | Tejados enteros |
| Tres naves (solo Catastro) | 7,2 a 7,8 m | 79 a 100 | 0 a 2 % | Con tejado |

La regla que sale de ahí: menos del 15 % en pie es un solar; con mucha vegetación
dentro, ruina invadida; casi todo en pie y liso, edificio con tejado; lo demás,
ruina sin tejado o a medias.

Lo que hay que saber:

- **Son ocho sitios y la regla se ajustó con ellos mismos.** No es una validación:
  falta probarla con unos doscientos y contar aciertos.
- Solo con la foto, un solar y una nave lisa no se distinguen. La altura es lo que
  lo resuelve.
- La vegetación de un patio cuenta como «dentro»: un edificio con patios ajardinados
  sale como ruina invadida. Se arregla usando las partes de edificio de Catastro en
  vez del contorno.
- La malla sale de un vuelo vertical: un árbol tapa lo que tiene debajo y los muros
  finos no están.
- Cada sitio tarda de 2 a 5 segundos. Los 4.300 serían unas cuatro horas.

## 2. Caminos, muros y vallas en la foto (`lineas.py`)

- **Caminos y pistas de tierra**: salen bien (franja clara, sin vegetación, larga).
  Se cuelan bordes de bancal y escombros claros.
- **Muros**: a medias. Se ven los trazos rectos con sombra (tapias, corrales, restos
  de paredes), pero también acequias, bordillos y lindes de cultivo.
- **Vallas de malla**: no. A 15 cm por píxel no se ven; como mucho, su sombra.

Para muros y vallas en serio hace falta altura fina: el LiDAR de 5 puntos/m² del
IGN, que hay que bajar a mano.

## 3. 3D realista

La misma malla sirve para verla: es fotogramétrica (la foto pegada sobre el relieve
real de edificios y árboles) y cubre la provincia entera. Las hojas miden unos
200 m de lado y tienen pocos miles de triángulos, así que es ligera. Falta probar
con qué biblioteca se pinta mejor en el visor y cómo va en el móvil.

## Cómo se hicieron las pruebas

Los recortes se pidieron al WMS desde el PC (300 m de lado, 2.000 píxeles) y se
analizaron con OpenCV y scikit-image. `lineas.py` y `estado_imagen.py` esperan los
recortes en `in/` con nombres `sNN_rgb.jpg`, `sNN_irg.jpg` y `t_sNN_*.jpg`; están
tal cual se usaron, sin pulir. `malla.py` sí funciona solo:

    python experimentos/vision/malla.py --primeros 20
