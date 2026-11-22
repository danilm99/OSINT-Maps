"""Datos de prueba.

Las pruebas no tocan internet: fabrican respuestas con la misma forma que
devuelven los servicios reales. El GML imita, etiqueta por etiqueta, un fichero
real de edificios de Catastro.
"""

from __future__ import annotations

import io
import zipfile

import pytest

# Todo es inventado: un municipio ficticio en coordenadas UTM 30N (EPSG:25830).
X0, Y0 = 700_000.0, 4_380_000.0

CABECERA = """<?xml version="1.0" encoding="ISO-8859-1"?>
<!--Edificios de la D.G. del Catastro.-->
<gml:FeatureCollection gml:id="ES.SDGC.BU" xmlns:base="urn:x-inspire:specification:gmlas:BaseTypes:3.2" xmlns:bu-core2d="http://inspire.jrc.ec.europa.eu/schemas/bu-core2d/2.0" xmlns:bu-ext2d="http://inspire.jrc.ec.europa.eu/schemas/bu-ext2d/2.0" xmlns:gml="http://www.opengis.net/gml/3.2" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
"""

EDIFICIO = """  <gml:featureMember>
    <bu-ext2d:Building gml:id="ES.SDGC.BU.{refcat}">
    <gml:boundedBy>
      <gml:Envelope srsName="urn:ogc:def:crs:EPSG::25830">
         <gml:lowerCorner>{x0} {y0}</gml:lowerCorner>
         <gml:upperCorner>{x1} {y1}</gml:upperCorner>
      </gml:Envelope>
    </gml:boundedBy>
      <bu-core2d:beginLifespanVersion>2015-11-24T00:00:00</bu-core2d:beginLifespanVersion>
      <bu-core2d:conditionOfConstruction>{estado}</bu-core2d:conditionOfConstruction>
      <bu-core2d:dateOfConstruction>
        <bu-core2d:DateOfEvent>
          <bu-core2d:beginning>{anio}-01-01T00:00:00</bu-core2d:beginning>
          <bu-core2d:end>{anio}-01-01T00:00:00</bu-core2d:end>
        </bu-core2d:DateOfEvent>
      </bu-core2d:dateOfConstruction>
      <bu-core2d:externalReference>
        <bu-core2d:ExternalReference>
          <bu-core2d:informationSystem><![CDATA[https://www1.sedecatastro.gob.es/CYCBienInmueble/OVCListaBienes.aspx?rc1={rc1}&rc2={rc2}]]></bu-core2d:informationSystem>
          <bu-core2d:informationSystemName>{nombre_sistema}</bu-core2d:informationSystemName>
          <bu-core2d:reference>{refcat}</bu-core2d:reference>
        </bu-core2d:ExternalReference>
      </bu-core2d:externalReference>
      <bu-core2d:inspireId>
        <base:Identifier>
          <base:localId>{refcat}</base:localId>
          <base:namespace>ES.SDGC.BU</base:namespace>
        </base:Identifier>
      </bu-core2d:inspireId>
      <bu-core2d:addresses xlink:href="http://ovc.catastro.meh.es/INSPIRE/wfsAD.aspx?service=wfs&amp;refcat={refcat}"></bu-core2d:addresses>
      <bu-ext2d:geometry>
       <bu-core2d:BuildingGeometry>
        <bu-core2d:geometry>
         <gml:Surface gml:id="Surface_ES.SDGC.BU.{refcat}" srsName="urn:ogc:def:crs:EPSG::25830">
           <gml:patches>
                <gml:PolygonPatch>
                <gml:exterior>
                    <gml:LinearRing>
                      <gml:posList srsDimension="2" count="5"> {x0} {y0} {x1} {y0} {x1} {y1} {x0} {y1} {x0} {y0}</gml:posList>
                    </gml:LinearRing>
                  </gml:exterior>{hueco}
                </gml:PolygonPatch>
           </gml:patches>
         </gml:Surface>
        </bu-core2d:geometry>
       </bu-core2d:BuildingGeometry>
      </bu-ext2d:geometry>
        <bu-ext2d:currentUse>{uso}</bu-ext2d:currentUse>
      <bu-ext2d:numberOfBuildingUnits>1</bu-ext2d:numberOfBuildingUnits>
      <bu-ext2d:officialArea>
         <bu-ext2d:OfficialArea>
          <bu-ext2d:officialAreaReference>grossFloorArea</bu-ext2d:officialAreaReference>
          <bu-ext2d:value uom="m2">{construida}</bu-ext2d:value>
         </bu-ext2d:OfficialArea>
      </bu-ext2d:officialArea>
    </bu-ext2d:Building>
  </gml:featureMember>
"""

HUECO = """
                  <gml:interior>
                    <gml:LinearRing>
                      <gml:posList srsDimension="2" count="5"> {x0} {y0} {x1} {y0} {x1} {y1} {x0} {y1} {x0} {y0}</gml:posList>
                    </gml:LinearRing>
                  </gml:interior>"""


def edificio(refcat, dx, dy, ancho, alto, estado="functional", uso="1_residential", anio=1960,
             nombre_sistema="", hueco=False) -> str:
    x0, y0 = X0 + dx, Y0 + dy
    x1, y1 = x0 + ancho, y0 + alto
    texto_hueco = ""
    if hueco:  # patio interior de 10 x 10 m
        texto_hueco = HUECO.format(x0=x0 + 5, y0=y0 + 5, x1=x0 + 15, y1=y0 + 15)
    return EDIFICIO.format(refcat=refcat, rc1=refcat[:7], rc2=refcat[7:], x0=x0, y0=y0, x1=x1, y1=y1,
                           estado=estado, uso=uso, anio=anio, construida=int(ancho * alto),
                           nombre_sistema=nombre_sistema, hueco=texto_hueco)


def gml_municipio() -> bytes:
    """Municipio ficticio con una fábrica en ruinas, una casa suelta y un corral."""
    partes = [
        # Fábrica: dos naves ruinosas a 10 m una de otra -> deben formar un conjunto.
        edificio("0000001YJ0000A", 0, 0, 50, 40, "ruin", "3_industrial", 1925, hueco=True),
        edificio("0000002YJ0000B", 60, 0, 20, 20, "ruin", "3_industrial", 1931),
        # Casa deficiente de 100 m², lejos: por debajo del mínimo de 150 m².
        edificio("0000003YJ0000C", 600, 0, 10, 10, "declined", "1_residential", 1950),
        # Corral ruinoso a 2 km con tres casas en uso al lado. Lleva un "&" suelto,
        # como pasa en ficheros reales, y una letra acentuada.
        edificio("0000004YJ0000D", 2000, 0, 15, 12, "ruin", "2_agriculture", 1900,
                 nombre_sistema="Explotación Pérez & Hijos"),
        edificio("0000005YJ0000E", 2030, 0, 10, 10),
        edificio("0000006YJ0000F", 2030, 30, 10, 10),
        edificio("0000007YJ0000G", 2000, 40, 10, 10),
        # Casa en uso muy lejos: no cuenta como vecina de nadie.
        edificio("0000008YJ0000H", 5000, 5000, 10, 10),
    ]
    texto = CABECERA + "".join(partes) + "</gml:FeatureCollection>\n"
    return texto.encode("iso-8859-1")


FEED = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:georss="http://www.georss.org/georss" xml:lang="en">
<title>Download Office Valencia</title>
<entry>
<title> 46900-VILLA DE PRUEBA buildings</title>
<id>http://www.catastro.hacienda.gob.es/INSPIRE/Buildings/46/46900-VILLA DE  PRUEBA/A.ES.SDGC.BU.46900.zip</id>
<link rel="enclosure" href="http://www.catastro.hacienda.gob.es/INSPIRE/Buildings/46/46900-VILLA DE  PRUEBA/A.ES.SDGC.BU.46900.zip" type="application/zip"/>
<georss:polygon>39.50 -0.75 39.50 -0.55 39.62 -0.55 39.62 -0.75 39.50 -0.75</georss:polygon>
</entry>
<entry>
<title> 46001-OTRO PUEBLO buildings</title>
<link rel="enclosure" href="http://www.catastro.hacienda.gob.es/INSPIRE/Buildings/46/46001-OTRO PUEBLO/A.ES.SDGC.BU.46001.zip" type="application/zip"/>
<georss:polygon>38.90 -0.60 38.90 -0.50 39.00 -0.50 39.00 -0.60 38.90 -0.60</georss:polygon>
</entry>
</feed>
"""


@pytest.fixture
def gml() -> bytes:
    return gml_municipio()


@pytest.fixture
def zip_municipio(tmp_path, gml):
    ruta = tmp_path / "46900.zip"
    with zipfile.ZipFile(ruta, "w") as zf:
        zf.writestr("A.ES.SDGC.BU.46900.building.gml", gml)
        zf.writestr("A.ES.SDGC.BU.46900.buildingpart.gml", b"<x/>")
    return ruta


@pytest.fixture
def gml_fh(gml):
    return io.BytesIO(gml)
