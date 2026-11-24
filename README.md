# OSINT Maps

Un mapa para cruzar fuentes abiertas sobre el terreno, en España: se elige qué
capas ver, se busca en todas a la vez y cualquier cosa del mapa abre su ficha
con datos e imágenes sin salir de la página.

- **Buscador como el de un mapa de calle**: negocios, direcciones con su
  portal, lugares, coordenadas y referencias catastrales, y «farmacias (o
  gasolineras, cajeros, aseos...) cerca de aquí» con lo más próximo primero.
- **Cómo llegar**: a pie, en coche, en bici y en transporte público, con
  alternativas, pasos uno a uno, líneas y transbordos.
- **Sitios abandonados**, sacados de Catastro, OpenStreetMap y Wikidata y
  ordenados por interés.
- **Más de 120 capas de datos**: cámaras (OpenStreetMap, DGT y València),
  radares, patrimonio en riesgo, inmuebles en subasta, solares, descampados,
  ferrocarril, túneles, energía, antenas, industria, agua, farolas, arte
  urbano, edificios de Catastro con su estado y su año, Wikipedia y fotos;
  lo de cada día (restaurantes, tiendas, farmacias, bancos, aparcamientos,
  paradas con sus próximos pasos, gasolineras con el precio de hoy); 35
  capas del Ayuntamiento de València (Valenbisi, aparcamientos y tráfico al
  momento, obras, arbolado, mupis, hidrantes...); y en vivo, aviones, trenes
  de Cercanías, terremotos y sensores de aire.
- **La foto aérea más nítida de cada sitio** (6 cm en València ciudad, 15 cm
  en la provincia, 25 cm en el resto de España) y **vista en 3D** con relieve
  y edificios.
- **Medición** de distancias sobre el mapa.
- **Imágenes dentro de la página**: ortofoto de cada año desde 1956, Street
  View, fotos a pie de calle de Panoramax, fotos de Wikimedia Commons, las
  últimas pasadas del satélite Sentinel-2 y cámaras de tráfico en directo.
- **Ficha de cualquier punto**: dirección, parcela catastral y su uso, altitud,
  tiempo, sol y luna, y qué hay alrededor.
- **La historia de cada sitio**: de cuándo es, qué fue, si está protegido y
  cuándo cerró, el arranque de su artículo, los nombres que le da el mapa,
  fotos con su año y noticias; cada dato, con su fuente.
- **Marcadores propios** con nota, y **parcelas, vallas y caminos** para leer
  el terreno.

Funciona de dos maneras: en tu ordenador (`osintmaps servir`) o publicado como
página web (`osintmaps publicar`), que se abre desde el móvil y se puede
instalar como una aplicación. Todo lo que usa es gratuito y no pide cuenta ni
clave.

## Estado

Probado de principio a fin con la provincia de Valencia (noviembre de 2026):

| | |
|---|---|
| Municipios procesados | 266 |
| Primera ejecución (descargando) | unos 5 minutos, 150 MB de caché |
| Ejecuciones siguientes | unos 2 minutos y medio |
| Candidatos | 4.297 |
| Con nota de 40 o más | 331 |

Todas las fuentes responden y el mapa funciona con datos reales. Hay 142
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
osintmaps historia                             # busca en la prensa los sitios con nombre
osintmaps publicar --con-notas                 # lo sube a GitHub Pages, para el móvil
osintmaps servir --pulso --publicar-datos      # el mapa, el histórico de la ciudad y la web al día
```

El buscador, las rutas, la mayoría de las capas y el 3D no necesitan `buscar`:
funcionan nada más abrir el mapa, en cualquier sitio. `buscar` es lo que
rellena la lista de sitios abandonados de una provincia.

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
- **Qué se ve**: en *Capas* (y en la tira de arriba del mapa) se encienden y
  apagan por separado los sitios, las cámaras y tus marcadores.
- **Revisión rápida** con el teclado: `→` siguiente, `←` anterior, `F`
  favorito, `V` visitado, `X` descartar (pasa solo al siguiente), `Esc` lista.

### Capas de datos

En *Capas* se enciende lo que se quiera ver. Cada capa se carga sola para la
zona que hay en pantalla; las que tienen muchos elementos esperan a que se
acerque el mapa, y lo dicen.

| Grupo | Capas | De dónde salen |
|---|---|---|
| Vigilancia | Cámaras, cámaras de tráfico de la DGT y de València, radares de velocidad, policía, barreras y controles de paso, prisiones | OpenStreetMap, DGT, Ajuntament de València |
| Abandono y patrimonio | Lista Roja, Verde y Negra; inmuebles en subasta; abandonado en OSM; descampados y obras; solares y edificios a rehabilitar; BIC y BRL; refugios antiaéreos; militar; lugares históricos | Hispania Nostra, BOE, OpenStreetMap, Ajuntament de València |
| Infraestructura | Ferrocarril (en magenta lo que está en desuso), túneles y puentes, muros, energía, antenas, industria, canteras, minas y cuevas, agua, farolas, centros de datos y armarios de calle, tapas de registro, granjas e invernaderos | OpenStreetMap |
| A pie de calle | Arte urbano y murales, miradores, publicidad (vallas, mupis, pantallas), skateparks, escaleras y ascensores | OpenStreetMap |
| Transporte | Paradas con sus próximos pasos, estaciones, taxis, bicis de alquiler, aparcabicis, carriles bici, gasolineras con el precio de hoy, recarga eléctrica, aparcamientos, talleres, aeropuertos, puertos | Transitous, Ministerio para la Transición Ecológica, OpenStreetMap |
| Comer y beber, Compras, Servicios, Ocio, Naturaleza | Restaurantes, bares, cafeterías; supermercados, panaderías, pintura y ferretería, todas las tiendas; farmacias, hospitales, bancos y cajeros, correos, oficinas públicas, emergencias, colegios, aseos, fuentes, wifi; hoteles, museos y cines, deporte; parques, picos, playas, manantiales, camping y refugios | OpenStreetMap |
| València: movilidad | Valenbisi, aparcamientos y tráfico al momento; metro y bocas, EMT, taxis, carril bici, zona azul, plazas reservadas, obras y cortes, bolardos, semáforos, aforos, paneles, vados | Ajuntament de València |
| València: ciudad | Calidad del aire y estaciones meteorológicas al momento, sonómetros, fuentes, aseos, jardines, los 158.000 árboles, contenedores, wifi municipal, monumentos, excavaciones arqueológicas, fallas, hidrantes, mupis, quioscos, vivienda protegida, equipamientos | Ajuntament de València |
| Fotos y artículos | Wikipedia, fotos de Commons, fotos a pie de calle | Wikimedia, Panoramax |
| Catastro | Edificios con su estado (en uso, deficiente, ruina), año y uso | Catastro |
| En vivo | Aviones en vuelo y trenes de Cercanías (solo con `osintmaps servir`); terremotos del último mes y sensores de partículas | adsb.fi y adsb.lol, Renfe, EMSC, sensor.community |

Los grupos del panel se pliegan y dicen cuántas capas tienen encendidas, y el
buscador de capas del propio panel encuentra una por su nombre.

Lo que cambia cada pocos minutos (Valenbisi, aparcamientos, tráfico, aire) no
se guarda: se vuelve a pedir lo que se ve, cada uno a su ritmo. Las
gasolineras se colorean por tercios de precio dentro de su provincia (verde
lo barato, rojo lo caro).

**Imágenes para poner encima** (en *Capas*, bajo el mapa de fondo): nombres
de calles, red ferroviaria, mapa de 1915-1960, relieve LiDAR, radar de lluvia,
zonas inundables (ríos a 100 y 500 años y temporales de mar), restricciones
para drones de ENAIRE, límites municipales, senderos y rutas ciclistas
señalizadas, señales del mar y focos de calor vistos desde satélite. De
València: mapa de ruido, calificación urbanística (PGOU), distritos y barrios
(los municipales y los policiales), secciones censales, zona de bajas
emisiones y zonas acústicamente saturadas. Con una de estas zonas encendida,
la ficha de cualquier punto dice además qué le toca (su calificación, su
barrio policial, su nivel de ruido).

Tres de ellas no se piden al momento, sino que se descargan a la carpeta de
datos: la Lista Roja, las cámaras de la DGT y las subastas. Lo hace `osintmaps
buscar`, y `osintmaps capas --provincia 46` las refresca sin repetir la
búsqueda (las subastas cambian cada semana).

De las subastas sale lo único que hay abierto sobre si algo está en venta y
ocupado: cada ficha trae el valor, la fecha de cierre y la «situación
posesoria» cuando el juzgado la indica.

### Cómo se lee el mapa

Cada punto es una ficha con su icono, la misma que aparece junto al nombre de
la capa en el panel *Capas*:

| Forma | Qué es |
|---|---|
| Cuadrado | Sitio abandonado de la búsqueda; el color es su nota |
| Rombo | Abandono y patrimonio: Lista Roja, subastas, solares, BIC, refugios, militar |
| Círculo | Todo lo demás: rojo, vigilancia; azul y gris, infraestructura; verde azulado, fotos |
| Chincheta | Tus marcadores |

De lejos las fichas se quedan en un punto de color y el icono aparece al
acercar. Las líneas (vías, túneles, muros, tendidos) llevan un borde oscuro
para que se vean igual sobre una foto clara que sobre una oscura; la vía en
desuso va en magenta.

El botón de la luna, junto al título, cambia entre modo claro y oscuro. La
primera vez se sigue el del sistema. En modo oscuro los mapas dibujados
(callejero, topográfico, OpenStreetMap) se invierten; las fotos no se tocan.

Arriba del mapa hay una **tira con las capas encendidas**: cada ficha lleva el
símbolo de la capa, su nombre y cuántos elementos tiene cargados, así que hace
de leyenda. Pulsar una ficha oculta esa capa y pulsarla otra vez la vuelve a
mostrar (se queda en la tira, atenuada), que es la forma rápida de despejar el
mapa cuando hay muchas cosas encima. Mientras una capa carga, su ficha gira; si
pone «acerca», esa capa solo se pide más de cerca; un «!» es que su servicio
no ha contestado, y el aviso de abajo trae un botón para reintentar.

En el ordenador, el asa del borde izquierdo del mapa esconde el panel y deja
todo el ancho al mapa; al abrir cualquier ficha el panel vuelve solo. En el
panel *Capas* se puede buscar una capa por su nombre. La tecla `/` lleva al
buscador.

### Velocidad: lo que se descarga se guarda

Los servicios de fuera son lentos y no hay forma de acelerarlos: Catastro tarda
entre 10 y 30 segundos por cada trozo de mapa y OpenStreetMap, a ratos, un
minuto. Lo que sí se puede es no esperar dos veces por lo mismo:

- **Memoria en el navegador.** Las parcelas, los edificios, las vallas y todo
  lo que traen las capas se guarda por trozos de mapa en el navegador
  (IndexedDB). Al volver a una zona, o al recargar la página, sale al
  momento sin preguntar a nadie. Cada dato caduca solo: una semana lo de
  OpenStreetMap, Wikipedia y Commons; tres días lo municipal y Panoramax; un
  mes las parcelas y dos los edificios. Al final del panel *Capas* se ve
  cuánto hay guardado y hay un botón para vaciarlo y pedirlo todo de nuevo.
- **Solo se pide lo que se está mirando.** Si mueves el mapa mientras hay
  peticiones en cola, las de la zona que ya no ves se tiran y pasan delante
  las de la zona nueva.
- **OpenStreetMap, con carrera entre servidores.** Se pregunta al servidor
  que mejor respondió la última vez; si a los 8 segundos sigue callado se
  pregunta también al siguiente y vale la primera respuesta.
- **Mover el mapa no rehace los puntos.** Los miles de sitios y las parcelas
  ya dibujadas se conservan al mover; solo se añade lo que entra en pantalla.
- **Datos comprimidos y sin repetir.** `osintmaps servir` manda los ficheros
  de datos comprimidos (ocupan la sexta parte, se nota desde el móvil por la
  wifi) y, al recargar, el navegador solo pregunta si han cambiado.

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
- **Buscador**: una sola caja para todo. Mientras se escribe propone negocios
  y lugares (Photon) y portales de España (CartoCiudad); con Intro, o al dejar
  de escribir, pregunta además a Nominatim, que entiende frases enteras
  («mercadona ruzafa»). También busca en los sitios, en lo cargado de las
  capas y en tus marcadores, y entiende coordenadas (`39.47, -0.37`) y
  referencias catastrales. El mapa no se mueve solo mientras se escribe: los
  resultados se ordenan por cercanía a lo que se está mirando.
- **Cerca de aquí**: al entrar en la caja vacía salen dieciséis búsquedas
  rápidas (restaurantes, súper, farmacias, gasolineras, cajeros, parking,
  paradas, aseos, fuentes...), y escribir «farmacia» o «gasolinera» ofrece lo
  mismo. La lista sale por distancia al centro del mapa, con «abierto» o
  «cerrado» cuando OpenStreetMap trae el horario; *Buscar en esta zona* la
  repite donde se haya movido el mapa y *Dejar la capa encendida* la convierte
  en una capa normal.
- **Ficha de un negocio**: si está abierto y cuándo cierra, el horario de la
  semana, la dirección, el teléfono (para llamar con un toque) y la web. Los
  datos son los de OpenStreetMap; el horario no sabe de festivos.
- **Fondos**: ortofoto del IGN, satélite de Esri (otra fecha), Sentinel-2,
  callejero, mapas oscuro y claro de Esri, relieve LiDAR (se ven edificios y
  muros bajo los árboles), luces nocturnas desde satélite y los mapas de 1870
  a 1960. Encima se pueden poner los nombres de las calles, la red
  ferroviaria, el mapa antiguo translúcido o el radar de lluvia del momento.
- **Pestañas del panel**: *Sitios* es la lista de siempre; *En el mapa*
  enumera lo que hay de las capas encendidas en lo que se ve, de más cerca a
  más lejos, y lo guarda como GeoJSON; *Marcadores* es la lista de los tuyos.
- **Cómo llegar**: el botón de cualquier ficha (o botón derecho, *Ruta desde
  aquí* y *Ruta hasta aquí*) abre las cuatro maneras de ir, cada una con lo
  que tarda: a pie, en transporte público, en coche y en bici. El origen es
  tu posición si el navegador la da; si no, se escribe o se toca en el mapa.
  A pie, en coche y en bici (OSRM) salen hasta tres caminos, que se eligen en
  la lista o tocándolos en el mapa, con las maniobras una a una. En
  transporte público (Transitous) salen varios viajes con sus líneas en su
  color, los transbordos, las paradas intermedias y si el vehículo va ya
  comunicando su posición; se puede pedir para otra hora o «llegar a las».
  Si la ruta sale de tu posición y te mueves, dice cuánto queda, la vuelve a
  calcular cuando te sales de ella y pide al móvil que no apague la pantalla.
- **Medir**: botón derecho, *Medir distancia desde aquí*, y cada clic añade
  un tramo. Escape termina.
- La ficha de un punto enseña la **foto de fachada de Catastro** cuando la
  parcela la tiene, y las de Hispania Nostra traen su foto y su resumen.
- La dirección de la página guarda dónde se está mirando: se puede copiar y
  volver al mismo sitio.

### La historia de cada sitio

La ficha de un sitio, y la de cualquier edificio o punto del mapa, lleva un
bloque **Historia**. Enseña al momento lo que ya está en los datos: el año de
Catastro, qué fue según OpenStreetMap, si tiene al lado una ficha de la Lista
Roja o sale a subasta, entre qué años deja de verse el tejado y las noticias
guardadas. Al pulsar **Buscar su historia** pregunta, además, a los servicios
abiertos que dejan que una página web les pregunte:

| Fuente | Qué aporta |
|---|---|
| Wikidata | La ficha del sitio: fechas de construcción, inauguración y cierre, protección (BIC, BRL), estado de uso y de conservación, estilo, y el enlace a la ficha de patrimonio de la Generalitat cuando la tiene. Y qué hay catalogado a 400 m |
| Wikipedia, en castellano o en valenciano | El arranque del artículo |
| Wikimedia Commons | Fotos de alrededor, ordenadas por el año en que se hicieron |
| Nomenclátor del IGN, Nomenclàtor Toponímic Valencià (ICV) y OpenStreetMap | Los nombres del mapa: el del edificio si lo tiene, la partida, el paraje y el municipio |
| Catastro | Dirección o paraje y para qué consta cada construcción |

Con eso monta un resumen (qué es, de cuándo, si está protegido, cuándo cerró,
cómo está hoy), una cronología y una fila de enlaces con la búsqueda ya escrita
en Google Noticias, Google Libros, la Biblioteca Virtual de Prensa Histórica,
la Biblioteca Valenciana Digital, el BOE y el DOGV, Dialnet, Europeana e
Internet Archive. Lo encontrado se guarda dos semanas en el navegador, y una
casilla hace que se busque solo al abrir cada ficha.

**Las noticias** van aparte, porque Google Noticias solo contesta a un
programa, no a una página:

```bash
osintmaps historia            # busca los sitios con nombre y lo deja en datos/historia.json
osintmaps historia --max 50   # solo los 50 mejores que falten
```

Ese fichero viaja con la web publicada, así que las noticias se ven también
desde el móvil. Con `osintmaps servir` abierto, además, la ficha las busca al
momento. Se pregunta despacio (una vez cada 5 segundos) y, si Google contesta
que son demasiadas peticiones, se para: repetir la orden más tarde sigue donde
lo dejó. De cada noticia se guarda el titular, el medio, la fecha y el enlace.

Lo que hay que saber antes de fiarse:

- **Sin nombre no hay prensa ni archivos.** En la provincia de València tienen
  nombre unos 700 sitios de 4.300. Para el resto, el bloque propone el nombre
  del mapa más cercano («puede ser el suyo») y busca con ese, avisándolo.
- **Casi nunca consta cuándo se abandonó.** Lo traen algunas fichas de Wikidata
  (estaciones, sobre todo) y la capa de tejados. Cuando no, el bloque dice que
  no consta y remite a las fotos por años.
- Un sitio sin ficha de Wikidata se empareja por el nombre. Si tampoco tiene
  nombre, con lo que Wikidata sitúe encima, y entonces va aparte y con el aviso
  de que puede no ser el mismo sitio.
- Google no busca la frase exacta aunque vaya entre comillas: devuelve también
  noticias del pueblo que no tienen que ver. Se guardan las que nombran el sitio
  en el titular y, atenuadas, hasta tres que no lo nombran pero hablan de
  patrimonio, de abandono o del mismo tipo de edificio. Si el nombre está hecho
  de palabras corrientes («Casa Alta»), solo valen las que traen además el
  municipio. Aun así se cuela alguna.
- El resumen son frases hechas sobre los datos encontrados: no lo redacta
  nadie ni lo inventa ningún modelo. Lo que no está en una fuente, no sale.
- No se busca ni se guarda nada sobre propietarios.

### La foto y el 3D

- **La foto más nítida de cada sitio**: el fondo por defecto elige solo, para
  cada trozo de mapa, la mejor foto aérea que hay: la del Ayuntamiento en
  València ciudad (unos 6 cm por punto), la del ICV de 2025 en la provincia
  (15 cm) y la del PNOA en el resto de España (25 cm). Se puede acercar hasta
  el zoom 22, y en pantallas densas (móviles, portátiles modernos) se pide el
  doble de detalle. En *Capas → Ajustar la foto* hay brillo, contraste, color
  y enfoque.
- **Otros fondos**: infrarrojo del ICV (la vegetación sale en rojo), satélite
  de Google y de Esri (otras fechas), el satélite de ayer de todo el planeta
  (250 m, para ver humo, riadas o nieve), y en València ciudad los vuelos
  desde 1956 y los planos desde 1738 para comparar con cortina.
- **Año a año desde 2017**: en la Comunitat Valenciana, la tira de fotos de
  cada ficha y la lista de *foto antigua* ofrecen los vuelos anuales del ICV
  (2017 a 2024, 25 cm). Es la manera más rápida de ver cuándo se cayó un
  tejado o desde cuándo crece la maleza.
- **3D**: el botón *3D* cambia el mapa por una vista en perspectiva. Encima
  siguen los sitios, tus marcadores, lo cargado de las capas, la ruta y tu
  posición, y al tocar un punto se abre su ficha. Se gira y se inclina con el
  botón derecho (o con dos dedos). La biblioteca que lo dibuja (MapLibre) pesa
  un megabyte y solo se descarga la primera vez que se pulsa el botón.
- **3D real, en la provincia de València**: dentro del 3D, el botón *Real*
  (encendido de entrada) pone la maqueta fotográfica del ICV, hecha con el
  vuelo de 2025: edificios, árboles y taludes con su forma de verdad, como en
  Google Earth. Es el mismo servicio público que usa el «Visor 3D GVA» y se
  lee directamente, sin clave. Cada trozo que se ve son entre 0,3 y 2 MB:
  con datos móviles conviene apagarla. Sin ella, o fuera de la provincia,
  queda el relieve con la foto pegada y cada edificio como un prisma con la
  altura que consta en OpenStreetMap.

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

### Visto desde el aire: lo que un programa detecta en la foto

OpenStreetMap solo tiene las vallas y sendas que alguien ha dibujado. Para lo
demás hay un detector que mira la foto de 15 cm de 2025 (color e infrarrojo) y
la maqueta 3D alrededor de cada sitio. Cuando se ha pasado, la ficha gana un
bloque **Visto desde el aire** con:

- si queda algo en pie y cuánta vegetación hay dentro (altura de la maqueta 3D
  e infrarrojo);
- cuánto del contorno está cerrado por muro, valla o seto, y cuántos caminos o
  sendas llegan a menos de 20 m;
- los metros de muro, valla, seto, camino y senda detectados a 150 m a la
  redonda, y el botón *Verlo sobre el mapa*, que los pinta encima de la foto
  (también en 3D): muros en naranja, vallas en amarillo a trazos, setos en
  verde, caminos en blanco y sendas en azul claro a puntos.

En la lista, cada sitio dice lo que se ve («casi nada en pie», «en pie, con
vegetación»...) y en *Filtros y orden* aparece **Desde el aire**, que permite
ocultar lo que ya no está en pie.

Esto no lo hace `osintmaps buscar`: necesita una tarjeta gráfica y es un
experimento aparte (`experimentos/vision/`, con su README). Deja en `datos/` un
`revision.json` y una carpeta `vision/`, y `osintmaps publicar` los sube con lo
demás. Los resultados van ligados a la foto usada: mientras el ICV no publique
otro vuelo, no hay que recalcular nada.

Cuánto fiarse: **es una pista, no un dato.** El detector aprende de lo dibujado
en OpenStreetMap, que es incompleto.

- Los **caminos** son lo que mejor saca.
- De los **cierres** acierta dónde hay uno bastante más que cuál es: confunde a
  menudo muro con valla, y los quitamiedos de las autovías le salen como vallas.
- **Sendas** encuentra pocas (mejor en monte bajo abierto), y bajo los árboles no
  ve nada.
- **«Casi nada en pie»** sale de la altura de la maqueta 3D y es lo más sólido:
  de doce sitios así mirados uno a uno, once eran solares o losas vacías y uno
  conservaba muros bajos.
- Los demás veredictos («con cubierta», «con vegetación dentro») son más toscos:
  un patio con plantas cuenta como vegetación dentro y un árbol cuenta como algo
  en pie.

La propia ficha enseña lo que acertó el detector al examinarlo, clase por clase.
Solo cubre la provincia de València (la foto y la maqueta son del ICV); los
sitios de provincias vecinas se quedan sin este bloque.

### Edificios que han perdido el tejado: comparar las fotos de varios años (en pruebas)

Otro experimento (`experimentos/vision/cambios.py` y `tejado.py`) mira los
edificios que Catastro da **por buenos** y compara cada uno consigo mismo en
las fotos de 2017 a 2025. Un detector entrenado con todos los años dice quién
tenía tejado y ha dejado de tenerlo, y la maqueta 3D de 2025 confirma si de
verdad ya no está en pie. El resultado es la capa **Han perdido el tejado**, en
*Abandono y patrimonio*, que solo aparece si existe
`datos/capa-posibles.geojson`. Cada ficha dice entre qué dos años dejó de verse
el tejado.

En las dos zonas de prueba (Godella y los alrededores de Bétera) acierta casi
siempre en que ahí ha cambiado algo, pero **casi todo lo que encuentra son
derribos**: de once casos, diez lo eran y uno era una nave que perdió la
cubierta y conserva los muros. Los derribados no van al mapa salvo que se pidan.
Un edificio cerrado con el tejado entero no se distingue desde arriba de uno
habitado, así que esto no encuentra abandonos recientes: encuentra lo que se ha
caído o han tirado.

`osintmaps publicar` **no sube la capa** salvo que se pida con
`--con-posibles`: son sospechas sin comprobar sobre el terreno.

### En el móvil, sin el ordenador

- **Publicado como página web**: `osintmaps publicar` sube el mapa a GitHub
  Pages (la rama `gh-pages` del repositorio) y queda en una dirección del
  tipo `https://usuario.github.io/OSINT-Maps/`, que se abre desde cualquier
  sitio. Lleva los sitios, las cámaras y las capas descargadas; con
  `--con-notas`, también tus marcas y marcadores (quedan a la vista de quien
  tenga la dirección). `osintmaps sitio` crea la misma página en una carpeta,
  para alojarla donde se quiera. El repositorio tiene que ser público, o la
  cuenta de pago, para que GitHub sirva la página.
- **Como una aplicación**: en el navegador del móvil, *Añadir a la pantalla
  de inicio*. Se abre a pantalla completa y arranca aunque no haya cobertura
  (lo ya visto sale de la memoria).
- **Pensado para el dedo**: el buscador flota sobre el mapa y el panel es una
  hoja que sube desde abajo, con tres alturas; se arrastra por el asa. El
  botón de la posición pone un punto azul que sigue al aparato mientras la
  página está abierta.
- En la versión web las notas que se hagan se quedan en ese navegador (no hay
  un programa detrás que las guarde), y los aviones y los trenes en vivo no
  salen: sus servicios no dejan que una página les pregunte directamente.
- **En casa, por la wifi**: `osintmaps servir --red` (o `abrir-mapa.bat
  --red`) muestra una dirección del tipo `http://192.168.1.20:8000/` para
  abrir en el móvil. Las marcas y los marcadores se comparten con el
  ordenador. Mientras esté abierto, cualquiera en esa wifi puede ver el mapa.
  Así el navegador no da la posición: solo la da en páginas seguras (https).
- **Un solo fichero**: `osintmaps paquete` crea `datos/mapa.html`, con el
  mapa y los datos dentro, para pasarlo al móvil y abrirlo sin servidor.
- **Google Earth**: `datos/candidatos.kml` se abre tal cual.

### Pulso: la ciudad a lo largo del tiempo

Las capas «en vivo» enseñan lo que pasa ahora. El pulso lo va apuntando para
poder volver atrás: una consola sobre el mapa (botón **Pulso**) con una línea
de tiempo que se arrastra o se reproduce, los indicadores de toda la ciudad
comparados con lo normal a esa hora y, en el mapa, lo que marcaba cada
estación de Valenbisi, cada aparcamiento y cada tramo de calle en ese momento,
con el rastro de los aviones y los trenes.

```bash
osintmaps servir --pulso                    # el mapa, y además va guardando el histórico
osintmaps servir --pulso --publicar-datos   # y sube el resumen a la web al arrancar y cada 15 minutos
```

`abrir-mapa.bat` arranca así, con las dos cosas.

Qué se guarda, mientras el programa está abierto:

| Qué | Cada cuánto | De dónde |
|---|---|---|
| Bicis ancladas en cada estación de Valenbisi | 2 min | Ajuntament de València |
| Plazas libres en cada aparcamiento público | 5 min | Ajuntament de València |
| Estado de cada tramo de calle (fluido, denso, congestionado, cortado) | 3 min | Ajuntament de València |
| Vehículos y bicis por hora en las espiras de aforo | 10 min | Ajuntament de València |
| NO₂, partículas y ozono por estación; temperatura, viento y lluvia | 15 min | Ajuntament de València |
| Aviones a menos de 75 km | 30 s | adsb.fi (y adsb.lol si falla) |
| Trenes de Cercanías del área de València | 30 s | Renfe |

Todo va a `datos/pulso.sqlite`. Los valores punto a punto se guardan solo
cuando cambian y se conservan 90 días (`--guardar-dias`); los indicadores de
la ciudad, siempre. Con el programa abierto todo el día salen entre 5 y 10 MB
diarios (medido una noche con datos reales: unas 190.000 filas al día; de día
se mueve más).

**Solo hay histórico de los ratos en que el programa ha estado abierto.** Los
huecos se guardan como huecos y la línea de tiempo los enseña rayados: nunca
se rellena lo que no se vio.

**Lo normal y lo que se sale.** Cada indicador se compara con lo que marcó a
esa misma hora en las semanas anteriores (hasta ocho; mientras no hay tres
semanas, con los días anteriores del mismo tipo, laborable o fin de semana).
La línea de puntos de la gráfica es esa referencia. Cuando lo de ahora se
separa mucho de ella queda apuntado como **suceso** y la ficha del indicador
se pone en magenta. No dice por qué: un partido, una manifestación, lluvia o
un sensor estropeado dan la misma señal. Dice dónde mirar. Hacen falta al
menos cuatro días comparables para que opine.

**Las dos versiones.**

| | Con el programa (`osintmaps servir`) | Web publicada |
|---|---|---|
| Histórico | Todo lo guardado: 6 h, 24 h, 48 h, 7 días, 30 días o un día concreto | Las últimas 48 h de indicadores y 24 h punto a punto, tal como las subió el ordenador |
| Ahora mismo | Todo, cada minuto | Bicis, aparcamientos y tráfico (el navegador los pide al Ayuntamiento); lo demás, con la hora del último dato |
| Aviones y trenes | Rastro completo | Los de las 3 h anteriores a la última subida |
| Historia de un punto | La última semana | Las últimas 24 h |

La web no puede preguntar a los servicios de aviones ni a Renfe (no dejan que una página les
pregunte), ni guardar nada entre visitas: por eso su histórico es el que
publica el ordenador. `--publicar-datos` cambia en la web **solo**
`datos/pulso.json` (unos 600 KB, que viajan comprimidos en menos de 100): no
toca el visor ni el resto de los datos,
así que da igual qué versión del visor haya publicada. Si mientras tanto
alguien publica la web entera, la subida se rechaza sola y se repite a la
siguiente vuelta. La primera vez hay que haber publicado la web con
`osintmaps publicar`.

`https://.../?pulso` abre la web con la consola ya desplegada, para un acceso
directo en el móvil.

Los aviones salen de adsb.fi y, si no contesta, de adsb.lol. Todas las peticiones (las del
recolector y las de la capa en vivo) pasan por `osintmaps/aviones.py`: dejan al menos dos
segundos entre una y otra al mismo servicio y, si uno contesta «demasiadas peticiones», no se
le vuelve a preguntar en lo que pida (diez minutos si no lo dice).

Lo que **no** hay, por ahora: el ruido (el Ayuntamiento solo publica medias
diarias, con semanas de retraso) y las posiciones de los autobuses de la EMT.
Y lo que no habrá: nada de esto sigue a personas; son recuentos de sensores
públicos.

### La sala de control

`sala.html` (enlace **Sala de control ↗** en la consola del pulso) es una pantalla
para ver València de un vistazo: qué barrios están fuera de lo normal y por qué,
los sucesos en marcha, las cifras de la ciudad, lo que se publica y lo previsto
para hoy. Con el programa abierto (`osintmaps servir --pulso`) se pide al
ordenador cada medio minuto; en la web, el ordenador sube cada cuarto de hora
`datos/sala.json` y la pantalla lo lee.

**Fuentes nuevas** (se recogen con `--pulso`, además de las del pulso):

| Qué | Cada cuánto | De dónde |
|---|---|---|
| Titulares de prensa local, situados en su calle o barrio | 10 min | Las Provincias, Valencia Plaza, elDiario.es, Europa Press, 20minutos, El Mundo |
| Publicaciones que hablan de València | 5-10 min | Bluesky (búsqueda pública), Mastodon (etiquetas) |
| Incidencias de tráfico del área metropolitana | 10 min | DGT (DATEX II) |
| Avisos meteorológicos | 15 min | AEMET vía Meteoalarm |
| Retrasos y avisos de Cercanías | 30 s | Renfe |
| Salidas de metro en la próxima media hora, por estación | 10 min | FGV, geoportal municipal |
| Ocupación prevista de la zona azul | 15 min | Ajuntament de València |
| Obras, ocupaciones de la vía, mudanzas y festejos | 3 h | Ajuntament de València |
| Partidos en casa (Valencia, Levante, Valencia Basket) | 12 h | TheSportsDB |
| Festivos y fiestas (Fallas, San Vicente Ferrer...) | 1 día | calendario laboral |
| Ruido de día y de noche en Russafa (de ayer) | 6 h | sonómetros del Ajuntament |
| Barrios, calles, patrimonio, registro de solares, vivienda protegida, zonas saturadas, vulnerabilidad, quejas, accidentes | al arrancar, si han caducado | geoportal y portal de datos abiertos del Ajuntament |
| Viajes entre distritos hora a hora (un lunes, un sábado y un domingo) | una vez | Ministerio de Transportes (MITMA), estudio de movilidad con big data |

**El cruce** (`pulso/cruce.py`). Cada diez minutos todo se lleva a los 87
barrios y se convierte en rasgos: tráfico, tramos cortados, vehículos por
hora, bicis que llegan y salen, aparcamientos, metro, publicaciones, noticias,
incidencias, textos urgentes, minutos de helicóptero encima. Cada rasgo se
compara con lo normal **para ese barrio a esa media hora de la semana** (las
ocho semanas anteriores; mientras no las hay, los días del mismo tipo, y nunca
lo de hoy). Lo que se mueve en toda la ciudad a la vez, como la lluvia, se
quita de cada barrio y se cuenta aparte, como suceso de la ciudad.

Un **suceso** necesita señales de fuentes distintas a la vez: Valenbisi sola
(un camión que reparte bicis) no basta; Valenbisi y los aparcamientos llenos,
sí. Tipos: afluencia, salida de gente, posible incidente (helicóptero encima,
textos urgentes, incidencias), congestión, posible corte, metro sin servicio y
«se habla de». Los barrios vecinos con el mismo tipo son un solo suceso, que
se sigue mientras dura (y si se mueve, como una manifestación, sigue siendo el
mismo). Para cada uno se busca la causa: algo previsto en la zona (un partido,
un festejo, una obra), la lluvia o lo que se publica de allí. Si no hay
ninguna, queda **sin causa conocida**. Durante las primeras cuatro semanas la
sala está aprendiendo: solo salta lo muy claro.

**Las fichas.** Cada suceso: por qué (causas con su peso), las señales en el
momento más fuerte, la evolución de cada una frente a lo normal, lo publicado
y los helicópteros que pasaron por la zona. Cada barrio: sus cifras de ahora,
su nivel en 24 horas, vulnerabilidad, quejas del último año por tema,
accidentes, sucesos del mes, obras y lo publicado. Cada punto (clic derecho
en el mapa o **⌖ Investigar**): la calle y el número, la parcela del Catastro
(uso, superficie, año de construcción, tipo de construcción), patrimonio,
registro de solares y edificios a rehabilitar, vivienda protegida, zona
acústicamente saturada, accidentes de esa esquina, obras registradas allí y
noticias. Solo datos de inmuebles: nada sobre quién vive o es propietario.

**Comparar** pone dos días uno al lado del otro (laborable, sábado, festivo
o una fecha) para cualquier rasgo, con el mapa de la diferencia a cada hora.
**Movilidad** enseña dónde llegan y de dónde salen las bicis y, con los datos
del MITMA, los viajes entre distritos de un lunes, un sábado y un domingo.
**Histórico** abre la máquina del tiempo del pulso.

**IA local, opcional.** Si hay [Ollama](https://ollama.com) con un modelo
(por ejemplo `ollama pull qwen3:8b`), la sala lo usa para afinar la
categoría y el sitio de las noticias, resumir cada suceso y escribir el parte.
Solo recibe cifras de conjunto y titulares públicos. El modelo sale de la
memoria de la gráfica tras cinco minutos sin trabajo. Sin Ollama, o con
`--sin-ia`, todo funciona con reglas.

**Lo que no hace.** No sigue a nadie: son recuentos de sensores públicos,
titulares y avisos oficiales. De las redes se guarda el texto público, la fecha
y el enlace de cada publicación, nunca quién la escribió, y nada se junta por
persona. Los textos de redes no se publican en la web (solo cuántos hay) y se
borran del ordenador a los 30 días. No lee matrículas, caras, wifi ni
bluetooth.

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
| `revision.json`, `vision/` | Lo visto desde el aire en cada sitio y las líneas detectadas (los escribe `experimentos/vision/detectar.py`, no `buscar`) |
| `capa-posibles.geojson` | Edificios que han perdido el tejado entre 2017 y 2025 (lo escribe `experimentos/vision/cambios.py`; no se publica salvo con `--con-posibles`) |
| `historia.json` | Noticias de los sitios con nombre: titular, medio, fecha y enlace (lo escribe `osintmaps historia`) |
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

- La detección «por imagen» (caminos, muros, vallas, si queda algo en pie) es un
  experimento aparte que necesita tarjeta gráfica y solo cubre la provincia de
  València. Acierta a medias y no está validado con una muestra grande: la
  comprobación sigue siendo tuya, en la ficha.
- Comparar fotos de varios años encuentra, sobre todo, derribos: lo que ha
  perdido el tejado. No distingue un edificio cerrado de uno habitado. Solo se
  ha probado en dos municipios.
- La historia de un sitio depende de que alguien la haya escrito: de una nave
  o una caseta sin nombre sale, como mucho, el año de Catastro, la partida y lo
  que haya catalogado cerca. Las hemerotecas (la de la BNE, la prensa histórica
  del Ministerio) no dejan preguntar desde un programa: solo se enlazan.
- Las noticias salen del canal de titulares de Google Noticias, que cubre unos
  pocos años y no busca la frase exacta: puede faltar lo viejo y colarse algo
  que no tiene que ver. Si Google cambia o cierra ese canal, dejarán de salir.
- Catastro no cubre País Vasco ni Navarra; ahí solo funcionan OSM y Wikidata.
- Wikidata se consulta por rectángulo, así que en una búsqueda por provincia
  pueden colarse sitios de provincias vecinas cerca del límite.
- El servidor principal de Overpass (OSM) a veces responde con un error por
  saturación; el programa reintenta y prueba otros servidores.
- OpenStreetMap contesta despacio cuando hay varias capas encendidas: la
  primera vez que se ve una zona puede tardar medio minuto. La segunda sale
  de la memoria del navegador.
- Los edificios de Catastro solo se cargan muy de cerca (zoom 18) y en el
  centro de una ciudad cada trozo tarda de 15 a 25 segundos; las parcelas,
  de 10 a 30. El servicio es así de lento y solo se nota la primera vez.
- La memoria del navegador es de cada navegador: el móvil y el ordenador
  guardan cada uno lo suyo, y en una ventana privada no se guarda nada.
- Las subastas y la Lista Roja se leen de sus webs, que no tienen API: si
  cambian el diseño, esas dos capas dejarán de actualizarse hasta adaptarlas.
- Street View va incrustado con una dirección que Google no documenta; puede
  dejar de funcionar sin aviso. Las imágenes de Sentinel-2 dependen de un
  servidor de demostración (titiler.xyz).
- Las capas de València solo cubren el término municipal.
- Los aviones y los trenes en vivo solo funcionan con `osintmaps servir`: ni
  en la versión web ni en el `mapa.html` autónomo.
- Las rutas en coche no cuentan el tráfico, y no hay navegación hablada: se
  ve cuánto queda y el paso siguiente hay que mirarlo.
- El transporte público es lo que las empresas publican y Transitous reúne:
  en València están EMT, Metrovalencia, MetroBus y Renfe; en otros sitios
  puede faltar alguna empresa.
- Los negocios y sus horarios son los de OpenStreetMap: lo que nadie ha
  apuntado no sale, y un horario puede estar anticuado.
- Los buscadores, las rutas y OpenStreetMap son servidores públicos
  mantenidos por voluntarios: a ratos tardan o no contestan, y no están
  pensados para un uso masivo.
- La maqueta 3D real solo existe en la provincia de València y sale de un
  vuelo vertical: las fachadas son aproximadas y lo que queda bajo un árbol o
  un voladizo no se ve. Depende de un servidor del ICV que no promete nada:
  si lo cambian, esa vista deja de salir y queda la de prismas. En el móvil
  está sin probar a fondo. Fuera de la provincia, la altura de un edificio es
  la que consta en OpenStreetMap, que a veces falta.

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
  historia.py       noticias de los sitios con nombre (Google Noticias), para la ficha
  imagen/
    pnoa.py         URL y descarga de ortofotos del IGN
    sentinel.py     vegetación con Sentinel-2 (experimental)
  exportar.py       GeoJSON, CSV, KML
  red.py, geo.py    utilidades de red y de coordenadas
  web/iconos.js     iconos, símbolos del mapa y cambio de tema
  web/index.html    el mapa: sitios, fichas, marcas, marcadores, accesos y la memoria de lo descargado
  web/capas.js      fondos, capas de datos, ficha general, visor, buscador y menú
  web/herramientas.js  pestañas del panel, medición, exportación, tira de capas y hoja del móvil
  web/rutas.js      cómo llegar: a pie, en coche, en bici y en transporte público
  web/vision.js     lo visto desde el aire: bloque de la ficha, líneas sobre el mapa y filtro
  web/historia.js   la historia de un sitio: resumen, fechas, nombres del mapa, fotos con año y prensa
  web/tresd.js      la vista en 3D
  web/pulso.js      la consola del pulso: línea de tiempo, indicadores y capas en el tiempo
  web/sala.html, web/sala.js  la sala de control
  pulso/
    fuentes.py      qué se pregunta a cada servicio y cómo se lee
    almacen.py      el histórico (SQLite): valores, indicadores, rastros y huecos
    recolector.py   quién pregunta, cada cuánto y qué hace si un servicio falla
    anomalias.py    lo normal a cada hora y lo que se sale
    resumen.py      el trozo de histórico que pide el visor o que se publica
    publicar.py     sube a la web solo los datos
    servidor.py     las direcciones /vivo/pulso/...
    catalogo.py     todas las fuentes del pulso y de la sala, en una lista
    textos.py       prensa, Bluesky, Mastodon, avisos de AEMET e incidencias de la DGT
    agenda.py       lo previsto: obras, ocupaciones, festejos, partidos, festivos; y el ruido
    clasificar.py   de qué habla un texto y si es de València (reglas)
    contexto.py     las capas de la ciudad que cambian poco (barrios, calles, patrimonio...)
    zonas.py        barrios, vecinos y nomenclátor: de un texto o una dirección a un punto
    cruce.py        el cruce: rasgos por barrio, lo normal, sucesos, su causa y su seguimiento
    fichas.py       la ficha de un barrio y la de un inmueble (con el Catastro)
    movilidad.py    los viajes entre distritos del MITMA
    ia.py           la IA local opcional (Ollama)
    sala.py         la sala en marcha y las direcciones /vivo/sala/...
  web/sw.js, manifest.webmanifest  lo que hace falta para instalarlo como aplicación
tests/              pruebas; `pip install -e ".[dev]"` y luego `pytest`
pruebas_navegador/  pruebas del visor en un navegador de verdad (ver su README)
experimentos/vision/  el detector por imagen: preparar datos, entrenar, calibrar y pasar por los sitios;
                      y cambios.py y tejado.py, el repaso por años en busca de lo que ha perdido el tejado
```

## Fuentes y licencias de los datos

- Edificios: Dirección General del Catastro, servicio INSPIRE.
- OpenStreetMap: © colaboradores de OpenStreetMap, licencia ODbL.
- Wikidata: CC0. Fotos: Wikimedia Commons, cada una con su licencia.
- Ortofotos: PNOA, CC BY 4.0 scne.es; Institut Cartogràfic Valencià (vuelos de
  2017 a 2025 y maqueta 3D), CC BY 4.0. Sentinel-2: Copernicus, vía Earth Search.
- Mapas antiguos, relieve y callejero: IGN, CC BY 4.0. Satélite alternativo: Esri.
- Cámaras de tráfico: DGT y Ajuntament de València. Solares y patrimonio de
  València: geoportal municipal. Subastas: Portal de Subastas del BOE.
- Historia de cada sitio: Wikidata (CC0); Wikipedia (CC BY-SA: se cita el
  arranque del artículo con su enlace); Nomenclátor Geográfico Básico de España
  (IGN, CC BY 4.0); Nomenclàtor Toponímic Valencià (ICV y Acadèmia Valenciana de
  la Llengua, CC BY 4.0); Photon. Noticias: titulares de Google Noticias,
  enlazados a su medio.
- Iconos: Material Design Icons (Pictogrammers), Apache 2.0.
- Patrimonio en riesgo: Hispania Nostra. Fotos de calle: Panoramax. Aviones:
  adsb.fi y adsb.lol. Trenes: Renfe. Tiempo, altitud y aire: Open-Meteo. Lluvia:
  RainViewer. Mapas oscuro y claro: Esri. Luces nocturnas: NASA Black Marble.
- Buscador: Photon (Komoot), CartoCiudad (IGN) y Nominatim, sobre datos de
  OpenStreetMap. Rutas: OSRM en los servidores de FOSSGIS. Transporte
  público: Transitous, con los horarios que publican las empresas.
- Fotos aéreas de detalle: Ajuntament de València e Institut Cartogràfic
  Valencià (CC BY 4.0). Capas y zonas de València: geoportal de datos
  abiertos del Ajuntament.
- Gasolineras: Ministerio para la Transición Ecológica. Terremotos: EMSC.
  Sensores de aire: sensor.community. Zonas inundables: SNCZI (MITECO), vía
  IDEE. Drones: ENAIRE. Senderos: Waymarked Trails. Mar: OpenSeaMap. Satélite
  diario y focos de calor: NASA GIBS.
- Sala de control: prensa local (titulares enlazados a cada medio), Bluesky y
  Mastodon (publicaciones públicas, enlazadas), DGT (DATEX II), AEMET vía
  Meteoalarm, Renfe, FGV, TheSportsDB, Catastro (Sede Electrónica, datos no
  protegidos), Ministerio de Transportes (estudio de movilidad con big data) y
  portal de datos abiertos del Ajuntament de València (quejas y sugerencias,
  accidentes, vulnerabilidad, obras y ocupaciones).
- 3D: MapLibre GL (BSD); edificios y nombres de OpenFreeMap (OpenMapTiles,
  datos de OpenStreetMap); relieve de las teselas Terrarium (Mapzen, con
  datos SRTM y otros).

`datos/` y `cache/` no se suben al repositorio.
