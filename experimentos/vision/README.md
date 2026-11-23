# Análisis por imagen: qué se puede detectar (pruebas del 22 y 23/11/2026)

Experimentos, no producto: nada de esta carpeta se instala con el paquete. Los apartados 1 a 3
son la prueba de viabilidad; el 4, el detector entrenado en la tarjeta gráfica, cuyo resultado
ya lee el visor (bloque «Visto desde el aire» de la ficha). De lo que hace `detectar.py` con la
salida de la red hay una prueba en `tests/test_vision_experimento.py`.

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

## 4. El detector entrenado (23/11/2026)

Lo que la prueba 2 no sacaba con reglas a mano se intenta con una red entrenada en la
tarjeta gráfica del PC. La idea: OpenStreetMap ya tiene dibujados miles de caminos,
sendas, muros y vallas de la provincia; se recorta la foto de 15 cm donde los hay y la
red aprende a encontrarlos en el resto.

| Paso | Guion | Qué hace |
|---|---|---|
| 1 | `preparar.py` | Baja el extracto de OSM (Geofabrik), se queda con las vías que interesan, elige teselas de 77 m repartidas por clase, baja cada una en color y en infrarrojo y pinta las etiquetas. `--ampliar N` añade más. |
| 2 | `entrenar.py` | Una U-Net (ResNet-34) con cuatro canales de entrada (color e infrarrojo cercano) y ocho de salida: camino, senda, carretera, muro, valla, seto, acequia y edificio. Si se corta, al relanzarlo sigue donde iba. |
| 3 | `calibrar.py` | Elige para cada clase a partir de qué probabilidad se da algo por detectado, y mide con ese corte cuánto acierta y cuánto encuentra. |
| 4 | `ver.py` | Hojas con la foto, lo de OSM y lo que marca la red, para juzgar a ojo. |
| 5 | `detectar.py` | Pasa la red por una ventana de 307 m alrededor de cada candidato, convierte las manchas en líneas, mide cierre y accesos, añade altura y vegetación (apartado 1) y deja un JSON por sitio. Con `--empaquetar`, lo que lee el visor. |

Todo corre en el PC, dentro de `cache/_vision` (entorno, fotos, modelos y resultados):

    set HF_HOME=cache\_vision\hf
    python experimentos/vision/preparar.py --carpeta cache/_vision --datos datos
    python experimentos/vision/entrenar.py --carpeta cache/_vision --nombre lineas-v2 --vueltas 16 --lote 12
    python experimentos/vision/calibrar.py --carpeta cache/_vision --modelo lineas-v2
    python experimentos/vision/ver.py --carpeta cache/_vision --modelo lineas-v2
    python experimentos/vision/detectar.py --carpeta cache/_vision --datos datos --modelo lineas-v2

### Lo que se guarda y cuándo hay que rehacerlo

- `cache/_vision/resultados/<foto>/<modelo>/<id>.json`: lo detectado en cada sitio. Va ligado
  a la foto (`IMAGEN` en `preparar.py`, hoy `0202_2025PVAL0015`) y al modelo. **Mientras el
  ICV no publique otro vuelo no hay que recalcular nada**; cuando lo haga, se cambian `IMAGEN`,
  `WMS` y `CAPAS` y se vuelve a pasar `detectar.py`.
- `cache/_vision/ventanas/<foto>/`: las fotos de cada sitio (unos 3 MB por sitio). Sirven para
  pasar un modelo mejor sin volver a bajarlas. Se pueden borrar.
- `cache/_vision/alturas/`: la altura de cada contorno según la maqueta 3D.
- `datos/revision.json` y `datos/vision/<id>.json`: lo que publica la web (`osintmaps publicar`).

### Lo aprendido hasta ahora

- **OSM no es la verdad, es lo que alguien ha dibujado.** De los muros y vallas falta la
  mayoría, y casi todo lo dibujado está en los pueblos. Mirando las hojas de `ver.py`, la red
  marca tapias de chalés que existen y no están en OSM: en las cifras eso cuenta como fallo, y
  al entrenar se le estaba enseñando a no marcarlas. Por eso ahora marcar un cierre donde OSM
  calla se castiga poco (y menos aún en teselas donde nadie ha dibujado ninguno).
- **Las sendas de OSM son trazas de GPS**: van a varios metros de la senda que se ve, o por
  debajo de los pinos, donde no se ve nada. La red casi no aprende a nombrarlas. Lo que sí hace
  es verlas como un camino estrecho, así que al trazar las líneas una franja de tierra de menos
  de 1,8 m de ancho se da por senda.
- **Muro o valla, desde arriba, a menudo no se distingue.** Se trazan juntos y cada tramo se
  queda con lo que más pesa; `calibrar.py` mide también el acierto en «hay un cierre», sin
  distinguir cuál.
- Una de cada cuatro teselas pedidas cae fuera de la foto (el recuadro de la provincia coge
  trozos de Alicante y Castellón). Se descartan solas.
- El portátil en modo «equilibrado» deja la gráfica en unos 30 W: una vuelta de entrenamiento
  con 2.700 teselas son 2 minutos y medio.

### Cifras del primer modelo (`lineas-v1`)

Entrenado con 2.950 teselas, 24 vueltas, 58 minutos con la gráfica a 30 W. Examinado con
510 teselas apartadas (ninguna vista al entrenar), comparando con OSM con 1,2 m de manga y
con el corte que elige `calibrar.py`:

| Clase | De lo que marca, coincide con OSM | De lo que hay en OSM, encuentra |
|---|---|---|
| Carretera | 89 % | 88 % |
| Edificio | 74 % | 92 % |
| Camino | 59 % | 62 % |
| Seto | 60 % | 60 % |
| Muro | 54 % | 66 % |
| Senda | 41 % | 34 % |
| Valla | 25 % | 37 % |
| Acequia | 16 % | 21 % |
| **Cierre** (muro, valla o seto, sin distinguir) | 62 % | 70 % |

Cómo leerlas:

- Son contra OSM, que está incompleto: lo que el modelo ve y nadie ha dibujado cuenta como
  fallo. La primera columna es un suelo, no la cifra real.
- **Valla sale mal y «cierre» sale bien**: encuentra la barrera y falla al decir cuál es.
- Mover el corte apenas cambia nada (el modelo responde casi siempre cerca de 0 o de 1): lo
  que limita son las etiquetas, no el umbral.

### Lo visto a ojo en sitios de verdad

Con `ver_sitios.py`, sobre la foto de cada candidato:

- **Caminos**: los traza bien y enteros; es lo más fiable. Las carreteras asfaltadas no se
  pintan (salen por otra clase).
- **Muros y vallas**: marca los cierres de naves, desguaces y corrales, a trozos. Muro y
  valla se intercambian a menudo. Los quitamiedos de las autovías salen como valla. En casco
  urbano marca muchos tramos cortos.
- **Sendas**: pocas, salvo en monte bajo abierto (dunas, matorral), donde sí las sigue.
- **«Casi nada en pie»** (menos del 15 % de la planta por encima de 2,5 m): de 12 mirados,
  11 eran solares o losas vacías y 1 conservaba muros bajos sin techo. Es lo más sólido.
- **Tapado por vegetación**: un contorno bajo un pinar salía como «en pie al 92 %» porque la
  maqueta mide las copas. Con el 70 % o más de vegetación se dice que no se ve qué hay.
- **«Con vegetación dentro»** se pasa de listo: una masía con patio ajardinado y tejados
  enteros sale así. Hace falta medir la vegetación solo en lo que levanta del suelo.

### Tiempos y tamaños (portátil con RTX 4060 a 30 W)

- Entrenar: 2 min 23 s por vuelta con 2.664 teselas.
- Detectar: entre 0,9 y 1,6 s por sitio (dos fotos, la altura y la red); los 4.314, hora y media.
- Fotos guardadas: 1 MB por sitio. Líneas publicadas: unos 2 KB por sitio.

### Tropiezos de la primera pasada (ya arreglados)

- Con una «ó» en la cabecera `User-Agent`, el servidor de la maqueta 3D contesta con un 500:
  todo salía sin altura y el fallo se tragaba en silencio.
- Los sitios de provincias vecinas (OSM y Wikidata se buscan por rectángulo) reciben una
  imagen en blanco: ahora se apuntan y no se vuelven a pedir.
- El PC se reinició de madrugada por una actualización de Windows. No se perdió nada, pero
  desde entonces el entrenamiento y el detector retoman donde iban.

### Siguiente modelo

`entrenar.py` ya no castiga marcar un cierre donde OSM calla ni marcar camino junto a una
senda, y hay 4.981 teselas en vez de 2.950 (un 30 % junto a los candidatos). Está sin
entrenar: `cadena.py --modelo lineas-v2` lo hace todo seguido. Las fotos ya están guardadas,
así que volver a pasar el detector cuesta solo el tiempo de gráfica.

## Cómo se hicieron las pruebas de los apartados 1 y 2

Los recortes se pidieron al WMS desde el PC (300 m de lado, 2.000 píxeles) y se
analizaron con OpenCV y scikit-image. `lineas.py` y `estado_imagen.py` esperan los
recortes en `in/` con nombres `sNN_rgb.jpg`, `sNN_irg.jpg` y `t_sNN_*.jpg`; están
tal cual se usaron, sin pulir. `malla.py` sí funciona solo:

    python experimentos/vision/malla.py --primeros 20
