# OSINT Maps

Un mapa para cruzar fuentes abiertas sobre el terreno, en España: se elige qué
capas ver, se busca en todas a la vez y cualquier cosa del mapa abre su ficha
con datos e imágenes sin salir de la página.

- **Sitios abandonados**, sacados de Catastro, OpenStreetMap y Wikidata y
  ordenados por interés.
- **Más de veinte capas de datos**: cámaras (OpenStreetMap, DGT y València),
  patrimonio en riesgo, inmuebles en subasta, solares, ferrocarril, túneles,
  energía, antenas, industria, farolas, edificios de Catastro con su estado y
  su año, artículos de Wikipedia, fotos, aviones en vuelo.
- **Imágenes dentro de la página**: ortofoto de cada año desde 1956, Street
  View, fotos a pie de calle de Panoramax, fotos de Wikimedia Commons, las
  últimas pasadas del satélite Sentinel-2 y cámaras de tráfico en directo.
- **Ficha de cualquier punto**: dirección, parcela catastral y su uso, altitud,
  tiempo, sol y luna, y qué hay alrededor.
- **Marcadores propios** con nota, y **parcelas, vallas y caminos** para leer
  el terreno.

Herramienta personal: funciona en tu ordenador y los datos se quedan en él.
Todo lo que usa es gratuito y no pide cuenta ni clave.

## Estado

Probado de principio a fin con la provincia de Valencia (noviembre de 2026):

| | |
|---|---|
| Municipios procesados | 266 |
| Primera ejecución (descargando) | unos 5 minutos, 150 MB de caché |
| Ejecuciones siguientes | unos 2 minutos y medio |
| Candidatos | 4.297 |
| Con nota de 40 o más | 331 |

Todas las fuentes responden y el mapa funciona con datos reales. Hay 84
pruebas automáticas (`pytest`) que no necesitan internet.

Recuentos reales de esa misma prueba: 390 cámaras en OpenStreetMap, 1.980
cámaras de la DGT (toda España), 1.969 fichas de Hispania Nostra (toda
España) y 49 inmuebles en subasta en la provincia.

Lo que hay que saber antes de fiarse de los resultados:

- **La nota ordena, no certifica.** Los primeros puestos (ruinas con nombre,
  despoblados, molinos, estaciones cerradas) son fiables. Entre los candidatos
  que solo salen de Catastro hay naves y granjas abandonadas de verdad, pero
  también solares donde el edificio ya se derribó: Catastro tarda en enterarse.
  La ortofoto actual de la ficha lo aclara en un segundo.
- **Los pesos están ajustados con Valencia.** En otra provincia puede hacer
  falta retocarlos (ver [Puntuación](#puntuación)).
- **El análisis de vegetación (`--ndvi`) es experimental**: funciona, pero no
  está comprobado cuánto ayuda.

## Cómo funciona

1. **Catastro** publica todos los edificios de cada municipio con su estado de
   conservación. El programa se queda con los *ruinosos* y *deficientes*, junta
   los que están pegados (una fábrica o una aldea son muchos edificios) y
   cuenta cuántos edificios en uso tienen alrededor.
2. **OpenStreetMap** aporta lo marcado como abandonado, en desuso o en ruinas,
   con nombre y tipo concreto (cuartel, estación, molino, mina, despoblado).
3. **Wikidata** aporta sitios con artículo: despoblados, estaciones cerradas,
   monasterios en ruinas.
4. **Cámaras**: las de OpenStreetMap (`man_made=surveillance`) de la misma
   zona. Van a una capa aparte, no se mezclan con los sitios.
5. **Fusión**: lo que cae en el mismo sitio se convierte en un solo candidato,
   que gana puntos por estar confirmado por varias fuentes.
6. **Puntuación** de 0 a 100 y **enlaces de comprobación** para cada candidato.
7. **Mapa** para verlo todo junto y anotar encima.

## Instalación

Hace falta Python 3.10 o posterior. En una terminal, dentro de la carpeta del
repositorio:

```bash
python -m venv .venv            # crea un entorno aislado para este proyecto
.venv\Scripts\activate          # en Linux o Mac: source .venv/bin/activate
pip install -e .                # instala el programa y sus dependencias
```

`pip install -e .` deja disponible la orden `osintmaps`. La `-e` hace que
los cambios que hagas en el código se apliquen sin reinstalar.

## Uso

```bash
osintmaps buscar --provincia 46 --fotos 200    # genera los datos en datos/
osintmaps servir                               # abre el mapa en el navegador
osintmaps capas --provincia 46                 # refresca Lista Roja, DGT y subastas
```

En Windows, el mapa también se abre con doble clic en `abrir-mapa.bat`.

Para probar con un solo municipio:

```bash
osintmaps municipios 46                 # lista los de Valencia con su código
osintmaps buscar --municipios 46001 -v  # Ademuz
```

Los códigos de municipio son los de **Catastro**, que no coinciden con los del
INE; por eso existe la orden `municipios`.

Opciones útiles de `buscar`:

| Opción | Para qué |
|---|---|
| `--caja oeste,sur,este,norte` | Recorta la zona a un rectángulo en grados |
| `--min-superficie 150` | Superficie mínima en planta de un conjunto (m²) |
| `--dist-agrupar 25` | Distancia para juntar edificios en un conjunto (m) |
| `--min-puntuacion 40` | Descarta los candidatos flojos |
| `--limite 2000` | Se queda con los N mejores |
| `--fotos N` | Busca fotos cercanas en Wikimedia Commons para los N mejores |
| `--ndvi N` | Experimental: avance de vegetación (Sentinel-2) en los N mejores |
| `--sin-catastro`, `--sin-osm`, `--sin-wikidata` | Apaga una fuente |
| `--refrescar` | Ignora la caché de OSM y Wikidata |
| `-v` | Muestra el avance municipio a municipio |

`--ndvi` necesita además `pip install -e ".[satelite]"` y tarda alrededor de
medio minuto por sitio.

### El mapa

- **Lista y filtros**: nota mínima, superficie, categorías, texto, solo lo
  confirmado por varias fuentes o solo lo que se ve en el mapa. Se ordena por
  nota, superficie o cercanía.
- **Ficha**: la ortofoto del sitio año a año (desde el vuelo de 1956), foto de
  fachada de Catastro si existe, desglose de la nota y enlaces a Street View,
  ficha catastral, prensa y demás.
- **Comparar en el mapa**: elige un año en la ficha y pulsa *Comparar*; aparece
  una cortina que se arrastra, con hoy a la izquierda y ese año a la derecha.
- **Marcas**: favorito, visitado, descartado y notas. Se guardan en
  `datos/marcas.json`, así que sobreviven a repetir la búsqueda.
- **Qué se ve**: en *Capas del mapa* se encienden y apagan por separado los
  sitios, las cámaras y tus marcadores.
- **Revisión rápida** con el teclado: `→` siguiente, `←` anterior, `F`
  favorito, `V` visitado, `X` descartar (pasa solo al siguiente), `Esc` lista.

### Capas de datos

En *Capas* se enciende lo que se quiera ver. Cada capa se carga sola para la
zona que hay en pantalla; las que tienen muchos elementos esperan a que se
acerque el mapa, y lo dicen.

| Grupo | Capas | De dónde salen |
|---|---|---|
| Vigilancia | Cámaras, cámaras de tráfico de la DGT y de València, policía | OpenStreetMap, DGT, Ajuntament de València |
| Abandono y patrimonio | Lista Roja, Verde y Negra; inmuebles en subasta; abandonado en OSM; solares y edificios a rehabilitar; BIC y BRL; refugios antiaéreos; militar; lugares históricos | Hispania Nostra, BOE, OpenStreetMap, Ajuntament de València |
| Infraestructura | Ferrocarril (en magenta lo que está en desuso), túneles y puentes, muros, energía, antenas, industria, canteras, farolas | OpenStreetMap |
| Fotos y artículos | Wikipedia, fotos de Commons, fotos a pie de calle | Wikimedia, Panoramax |
| Catastro | Edificios con su estado (en uso, deficiente, ruina), año y uso | Catastro |
| En vivo | Aviones en vuelo, cada 10 segundos | adsb.lol, a través de `osintmaps servir` |

Tres de ellas no se piden al momento, sino que se descargan a la carpeta de
datos: la Lista Roja, las cámaras de la DGT y las subastas. Lo hace `osintmaps
buscar`, y `osintmaps capas --provincia 46` las refresca sin repetir la
búsqueda (las subastas cambian cada semana).

De las subastas sale lo único que hay abierto sobre si algo está en venta y
ocupado: cada ficha trae el valor, la fecha de cierre y la «situación
posesoria» cuando el juzgado la indica.

### Ficha, visor y buscador

- **Ficha**: al tocar cualquier elemento, o con botón derecho y *¿Qué hay
  aquí?* en cualquier punto. Trae los datos del elemento y, del punto, la
  dirección, la parcela catastral con su uso y año, la altitud, el tiempo, la
  hora de salida y puesta de sol y la luna. *Analizar 200 m alrededor* cuenta
  cámaras, farolas, vallas, puertas y la comisaría más cercana.
- **Visor**: los botones *Por años*, *A pie de calle*, *Fotos cerca* y
  *Satélite* abren las imágenes a pantalla completa. La ortofoto se pide al
  IGN a la máxima resolución que tiene (15 a 50 cm por píxel según la zona y
  el año). Sentinel-2 son 10 m por píxel: vale para ver si algo ha cambiado
  este mes, no para ver detalle.
- **Buscador**: una sola caja para los sitios, lo cargado en las capas, tus
  marcadores, calles y lugares (Nominatim), coordenadas (`39.47, -0.37`) y
  referencias catastrales.
- **Fondos**: ortofoto del IGN, satélite de Esri (otra fecha), Sentinel-2,
  callejero, relieve LiDAR (se ven edificios y muros bajo los árboles) y los
  mapas de 1870 a 1960. Encima se pueden poner los nombres de las calles, la
  red ferroviaria o el mapa antiguo translúcido.
- La dirección de la página guarda dónde se está mirando: se puede copiar y
  volver al mismo sitio.

### Cámaras

Círculos rojos. Al acercar el mapa, las que tienen la orientación anotada
enseñan un abanico hacia donde miran. Su ficha dice lo que OpenStreetMap sabe
de ella (tipo, qué vigila, zona, montaje, orientación, operador) y permite
guardarla entre tus marcadores. Las de tráfico de la DGT y de València enseñan
además la imagen en directo.

`osintmaps buscar` descarga las de la zona buscada a `datos/camaras.geojson`
(`--sin-camaras` lo evita). Fuera de esa zona se cargan solas al acercar el
mapa.

Es un dato colaborativo y muy incompleto: en la mayoría de los pueblos no hay
ninguna dibujada. Sirve como punto de partida, y lo que veas tú se añade con
un marcador propio de tipo cámara.

### Marcadores propios

Rombos de color. Se crean con el botón *Añadir marcador* y un clic en el
sitio, con *Añadir un marcador aquí* del menú del botón derecho (en el móvil,
mantener pulsado), o con *Guardar como marcador* desde cualquier ficha.

Cada uno tiene un tipo (sitio, cámara, acceso, aviso, nota) y una nota de
hasta 500 caracteres. Con su ficha abierta se arrastra para moverlo. Borrar
pide dos pulsaciones.

Se guardan en `datos/marcadores.json` y se comparten entre el ordenador y el
móvil igual que las marcas. *Guardar copia de marcas y marcadores* baja un
fichero con todo; *Recuperar una copia* admite ese fichero y también las
copias de GraffMap, que usa el mismo formato de marcador.

### Parcelas, vallas y caminos

En *Capas del mapa* hay un grupo para leer el terreno:

| Capa | Qué enseña | De dónde sale |
|---|---|---|
| Parcelas y suelo público | Cada parcela, y en verde las de dominio público: caminos, cauces y vías | Catastro |
| Vallas, puertas y caminos | Vallas, muros, puertas, sendas y caminos de paso restringido | OpenStreetMap |
| Vías pecuarias y senderos | Vías pecuarias y senderos GR, PR y SL | ICV (solo C. Valenciana) |
| Montes y fincas públicas | Montes gestionados por la Generalitat y fincas patrimoniales | ICV (solo C. Valenciana) |

Las parcelas aparecen al acercar el mapa. Al tocar una se consulta a Catastro
su uso, su aprovechamiento (pastos, pinar, algarrobo, improductivo...) y si
tiene construcciones.

Lo que estos datos **no** dicen, y conviene no suponer:

- **Quién es el dueño.** Catastro no lo publica. Una parcela rústica puede ser
  de un particular o de un ayuntamiento; el verde solo marca lo que Catastro
  numera como dominio público.
- **Si está ocupada, vigilada o en venta.** No existe una fuente abierta para eso.
- **Si hay valla.** OpenStreetMap solo tiene las que alguien ha dibujado. Que no
  salga ninguna no significa que no la haya.

Las vallas y caminos pueden tardar hasta un minuto en cargar: el servicio de
OpenStreetMap es gratuito y compartido.

### En el móvil

- **En casa, por la wifi**: `osintmaps servir --red` (o `abrir-mapa.bat
  --red`) muestra una dirección del tipo `http://192.168.1.20:8000/` para
  abrir en el móvil. Las marcas y los marcadores se comparten con el ordenador. Mientras esté
  abierto, cualquiera en esa wifi puede ver el mapa.
- **Fuera de casa**: `osintmaps paquete` crea `datos/mapa.html`, un único
  fichero con el mapa y los datos dentro. Pásalo al móvil y ábrelo; solo
  necesita internet para las ortofotos. En este modo lo que anotes se queda
  en el navegador del móvil; pásalo al ordenador con una copia.
- **Google Earth**: `datos/candidatos.kml` se abre tal cual.

El botón *Cerca de mí* necesita que el navegador dé la posición, y los
navegadores solo la dan en el propio ordenador o en páginas seguras: por la
wifi de casa no funcionará.

### Qué genera

Todo queda en la carpeta `datos/`, que no se sube a git:

| Fichero | Contenido |
|---|---|
| `candidatos.geojson` | Un punto por sitio con todos sus datos. Lo lee el mapa |
| `huellas.geojson` | Contornos de los edificios |
| `candidatos.csv` | Tabla para hoja de cálculo (separador `;`) |
| `candidatos.kml` | Para Google Earth, con una carpeta por categoría |
| `resumen.json` | Fecha, parámetros y recuentos de la ejecución |
| `camaras.geojson` | Cámaras de OpenStreetMap de la zona buscada |
| `capa-listaroja.geojson` | Lista Roja, Verde y Negra de Hispania Nostra |
| `capa-dgt.geojson` | Cámaras de tráfico de la DGT |
| `capa-subastas.geojson` | Inmuebles en subasta de la provincia |
| `marcas.json` | Tus marcas y notas sobre los sitios (lo escribe el mapa) |
| `marcadores.json` | Tus marcadores propios (lo escribe el mapa) |
| `mapa.html` | El mapa autónomo (lo escribe `osintmaps paquete`) |

Otras órdenes: `osintmaps miniaturas --top 50` baja a disco las ortofotos
(hoy, 2006 y 1956) de los 50 mejores.

### Sin ordenador: desde GitHub

El repositorio incluye una acción manual. En GitHub: pestaña **Actions →
Buscar → Run workflow**, indica provincia o municipios y, al terminar, descarga
el artefacto `datos`. Los artefactos de un repositorio privado solo los ve
quien tiene acceso al repositorio.

## Puntuación

La nota es una suma de factores, definidos en `osintmaps/puntuacion.py`:

| Factor | Máx. | Qué premia |
|---|---|---|
| Tamaño | 20 | Superficie en planta, en escala logarítmica |
| Estado | 16 | Ruina o abandonado frente a deficiente o en desuso |
| Tipo de sitio | 15 | Sanatorio, cuartel o despoblado frente a cobertizo agrícola |
| Varias fuentes | 15 | Confirmado por 2 o 3 fuentes independientes |
| Aislamiento | 12 | Pocos edificios en uso a 150 m, o mayoría de ruinas |
| Conjunto | 8 | Varios edificios deteriorados juntos |
| Nombre y artículo | 5 | Tiene nombre propio o entrada en Wikipedia/Wikidata |
| Antigüedad | 4 | Construido antes de 1940 o de 1975 |
| Vegetación | 5 | Solo con `--ndvi` |

En la práctica las notas se mueven entre 15 y 70: llegar a 100 exigiría un
sitio enorme, aislado y confirmado por las tres fuentes. Por eso el mapa pinta
en magenta desde 60, en naranja desde 50 y en amarillo desde 40.

Decisiones que salieron de mirar los resultados reales:

- **Cascos de pueblo**. Un grupo de edificios deteriorados solo cuenta como
  conjunto si son mayoría en su entorno. Sin esto, los cascos antiguos de
  pueblos habitados salían como «aldeas abandonadas».
- **Catastro importado a OSM**. En muchos municipios cada edificio ruinoso de
  Catastro está copiado en OSM sin nombre ni tipo. Eso no cuenta como segunda
  fuente.
- **«Industrial» según Catastro** incluye pajares y almacenes de pueblo. Si
  ninguna otra fuente confirma el tipo, solo puntúa entero cuando el edificio
  principal tiene tamaño de nave (400 m²).

Para ajustarla, cambia los diccionarios `PESO_ESTADO` y `PESO_CATEGORIA` y las
funciones cortas que hay debajo, y vuelve a ejecutar `buscar`.

## Limitaciones conocidas

- No detecta nada «por imagen». Reconocer tejados hundidos o solares vacíos en
  la ortofoto con un modelo de visión es el siguiente paso natural y no está
  hecho; hoy esa comprobación la haces tú en la ficha.
- Catastro no cubre País Vasco ni Navarra; ahí solo funcionan OSM y Wikidata.
- Wikidata se consulta por rectángulo, así que en una búsqueda por provincia
  pueden colarse sitios de provincias vecinas cerca del límite.
- El servidor principal de Overpass (OSM) a veces responde con un error por
  saturación; el programa reintenta y prueba otros servidores.
- OpenStreetMap contesta despacio cuando hay varias capas encendidas: la
  primera carga de una zona puede tardar medio minuto.
- Las subastas y la Lista Roja se leen de sus webs, que no tienen API: si
  cambian el diseño, esas dos capas dejarán de actualizarse hasta adaptarlas.
- Street View va incrustado con una dirección que Google no documenta; puede
  dejar de funcionar sin aviso. Las imágenes de Sentinel-2 dependen de un
  servidor de demostración (titiler.xyz).
- Las capas de València solo cubren el término municipal.
- Los aviones y las imágenes en directo no funcionan en el `mapa.html`
  autónomo: necesitan `osintmaps servir`.

## Estructura del código

```
osintmaps/
  cli.py            órdenes de terminal, servidor del mapa y orquestación
  modelos.py        la estructura Candidato, común a todo
  fuentes/
    catastro.py     índice de municipios, lectura del GML, agrupación
    osm.py          consulta Overpass y clasificación de etiquetas
    camaras.py      cámaras de vigilancia de OpenStreetMap
    listaroja.py    patrimonio en riesgo (Hispania Nostra)
    dgt.py          cámaras de tráfico de la DGT
    subastas.py     inmuebles en subasta (BOE)
    wikidata.py     consulta SPARQL
  fusion.py         une candidatos que son el mismo sitio
  puntuacion.py     la nota y sus pesos
  osint.py          enlaces de comprobación y fotos de Commons
  imagen/
    pnoa.py         URL y descarga de ortofotos del IGN
    sentinel.py     vegetación con Sentinel-2 (experimental)
  exportar.py       GeoJSON, CSV, KML
  red.py, geo.py    utilidades de red y de coordenadas
  web/index.html    el mapa: sitios, fichas, marcas, marcadores y accesos
  web/capas.js      capas de datos, ficha general, visor, buscador y menú
tests/              pruebas; `pip install -e ".[dev]"` y luego `pytest`
```

## Fuentes y licencias de los datos

- Edificios: Dirección General del Catastro, servicio INSPIRE.
- OpenStreetMap: © colaboradores de OpenStreetMap, licencia ODbL.
- Wikidata: CC0. Fotos: Wikimedia Commons, cada una con su licencia.
- Ortofotos: PNOA, CC BY 4.0 scne.es. Sentinel-2: Copernicus, vía Earth Search.
- Mapas antiguos, relieve y callejero: IGN, CC BY 4.0. Satélite alternativo: Esri.
- Cámaras de tráfico: DGT y Ajuntament de València. Solares y patrimonio de
  València: geoportal municipal. Subastas: Portal de Subastas del BOE.
- Patrimonio en riesgo: Hispania Nostra. Fotos de calle: Panoramax. Aviones:
  adsb.lol. Tiempo y altitud: Open-Meteo. Direcciones: CartoCiudad y Nominatim.

`datos/` y `cache/` no se suben al repositorio.
