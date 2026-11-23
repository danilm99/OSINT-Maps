# Pruebas del visor en un navegador de verdad

Abren el mapa en Chromium sin ventana (Playwright), con **todos los servicios de internet simulados**:
no hace falta red ni se molesta a nadie. Comprueban lo que `pytest` no puede: que el visor carga, que
el buscador, las rutas, las capas, el 3D y la hoja del móvil se comportan, y que no salen errores en
la consola.

## Preparar (una vez)

    pip install playwright pillow
    playwright install chromium
    cd pruebas_navegador
    npm install

## Ejecutar

Siempre desde esta carpeta. Cada fichero es una prueba suelta y acaba con `ERRORES: ninguno` o con la lista:

    python foto8.py      # la de siempre, completa: ficha, visor de fotos, marcas, medición, capas
    python humo9.py      # arranque y capas nuevas
    python busca9.py     # buscador
    python ruta9.py      # cómo llegar (admite `escritorio` o `movil`)
    python cerca9.py     # «cerca de aquí»
    python sup9.py       # imágenes superpuestas e identificar
    python tresd9.py     # vista 3D
    python malla9.py     # maqueta 3D del ICV, con un servicio I3S simulado
    python vision9.py    # lo visto desde el aire: bloque de la ficha, líneas en 2D y 3D, filtro
    python posibles9.py  # la capa opcional de edificios que han perdido el tejado y los vuelos anuales del ICV (2017 a 2024)
    python estatico.py   # la versión web publicada (`osintmaps sitio`)

## Cómo están hechas

`foto8.py` arranca el servidor del programa con los datos de `datos.zip` y define los servicios simulados
de la primera tanda; `maps9.py` reutiliza todo eso y añade los del buscador, las rutas y el 3D; cada
prueba `*9.py` empieza ejecutando `maps9.py`. Son guiones largos y poco pulidos: sirven para comprobar,
no como ejemplo de código.
