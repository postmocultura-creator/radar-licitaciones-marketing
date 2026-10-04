# -*- coding: utf-8 -*-
"""
Cliente de los ZIP de sindicación de PLACSP (Plataforma de Contratación del
Sector Público, Estado español). PLACSP no tiene API REST: publica ficheros
ATOM con extensión CODICE 2.07, empaquetados en un ZIP por mes, con estos
namespaces (verificados contra el XML real):

    cbc:          urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2
    cac:          urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2
    cac-place-ext: urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2
    cbc-place-ext: urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonBasicComponents-2

Tres feeds, los tres como ZIP mensual con varios .atom (lotes con la hora
en el nombre):

- sindicacion_643: organismos con perfil propio en PLACSP. Licitaciones y,
  en el mismo feed, adjudicaciones con sus documentos (actas, informes de
  valoración).
- sindicacion_1044: plataformas autonómicas agregadas (Cataluña, Euskadi,
  Andalucía, Madrid, Galicia, Navarra, La Rioja).
- sindicacion_1143: contratos menores, para los que vencen pronto.

Cada ZIP trae los expedientes ACTUALIZADOS ese mes, no una foto completa:
por eso clasificar.py acumula el resultado entre ejecuciones. Hay que leer
todos los ficheros del ZIP y quedarse con la versión más reciente de cada
expediente. Por qué ZIP y no el ATOM paginado (iba ~3 semanas por detrás):
ver docs/DECISIONES.md.

Ejecutar desde licitaciones_marketing/:
    python scrapers/placsp.py
"""

from __future__ import annotations

import re
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

import comun

sys.path.append(str(Path(__file__).resolve().parent.parent))
from nif import limpiar as limpiar_nif, ocultar_en_texto  # noqa: E402

FUENTE = "Estado"

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "cbc": "urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2",
    "cac-place-ext": "urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2",
    "cbc-place-ext": "urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonBasicComponents-2",
}


def _texto(el, path) -> str | None:
    """Texto de un nodo CODICE, o None si falta el elemento, el nodo o el
    texto (también si solo son espacios). Lo comparte el histórico."""
    if el is None:
        return None
    nodo = el.find(path, NS)
    return nodo.text.strip() if nodo is not None and nodo.text and nodo.text.strip() else None


def limpiar_texto(texto: str | None) -> str | None:
    """La plataforma de Navarra cambia "&" por "&' || '" (un trozo de su
    propio código): en las direcciones ("...cod=8071&' || 'Ticket=...", que
    así no abren la ficha; sin ese trozo sí, comprobado el 2026-10-04) y en
    los nombres ("CULTURE &' || ' SPORT")."""
    return re.sub(r"'\s*\|\|\s*'", "", texto) if texto else texto


limpiar_enlace = limpiar_texto


def _fecha_anuncio(cfs, tipos: tuple[str, ...]) -> str | None:
    """Fecha del primer anuncio publicado de alguno de estos tipos
    (DOC_CAN_ADJ = adjudicación, DOC_FORM = formalización). Las plataformas
    agregadas -verificado con la de Euskadi- no rellenan AwardDate en el
    lote, pero sí publican el anuncio de adjudicación con su fecha. Lo
    comparte el histórico."""
    for tipo in tipos:
        for info in cfs.findall("cac-place-ext:ValidNoticeInfo", NS):
            if _texto(info, "cbc-place-ext:NoticeTypeCode") != tipo:
                continue
            fechas = [n.text.strip() for n in info.findall(
                "cac-place-ext:AdditionalPublicationStatus/cac-place-ext:AdditionalPublicationDocumentReference/cbc:IssueDate", NS)
                if n.text]
            if fechas:
                return min(fechas)[:10]
    return None


# Documentos de la adjudicación que se enlazan desde la tarjeta: los que
# dicen qué se valoró y cómo. Códigos de la lista oficial
# GeneralContractDocuments-2.08 de PLACSP (codice/cl/2.08/).
DOCUMENTOS_ADJUDICACION = {
    "13": "informe_valoracion",   # Informe de valoración de los criterios ... juicio de valor
    "12": "acta",                 # Acta del órgano de asistencia (la mesa de contratación)
    "14": "informe_anormales",    # Informe sobre las ofertas incursas en presunción de anormalidad
    "1": "apertura",              # Actos públicos informativos o de apertura de ofertas
}
# "Otros documentos" (ZZZ): solo los que, por su nombre, son del resultado.
_RE_OTROS_ADJUDICACION = re.compile(
    r"resoluci[oó]n de adjudicaci|resultado de las ofertas|informe de valoraci|propuesta de adjudicaci"
    r"|informe t[eé]cnico|acta", re.I)
MAX_DOCUMENTOS_ADJUDICACION = 10


def _documentos_adjudicacion(cfs) -> list[dict]:
    """Actas de la mesa, informes de valoración y resolución de adjudicación
    de un expediente adjudicado, con su dirección de descarga directa (PDF).
    Medido con el ZIP de septiembre de 2026: de 443 adjudicaciones de
    servicios de agencia de perfiles propios, 173 traen acta o informe de
    valoración y 236 algún documento de este tipo. Las plataformas
    autonómicas agregadas y los contratos menores no publican ninguno."""
    documentos = []
    for doc in cfs.findall("cac-place-ext:GeneralDocument/cac-place-ext:GeneralDocumentDocumentReference", NS):
        url = _texto(doc, "cac:Attachment/cac:ExternalReference/cbc:URI")
        if not url:
            continue
        nombre = _texto(doc, "cac:Attachment/cac:ExternalReference/cbc:FileName") or ""
        codigo = _texto(doc, "cbc:DocumentTypeCode") or ""
        tipo = DOCUMENTOS_ADJUDICACION.get(codigo)
        # Algunos expedientes llegan sin código: se reconocen por el nombre
        # oficial del tipo, que PLACSP pone como nombre del fichero.
        if tipo is None and not codigo:
            if re.match(r"acta\b", nombre, re.I):  # "Acta del órgano...", "acta", "Acta 2"
                tipo = "acta"
            elif nombre.startswith("Informe de valoración"):
                tipo = "informe_valoracion"
        if tipo is None and _RE_OTROS_ADJUDICACION.search(nombre):
            tipo = "otro"
        if tipo:
            documentos.append({"tipo": tipo, "nombre": nombre, "url": url})
    # Primero lo que más dice sobre la valoración.
    orden = ["informe_valoracion", "acta", "otro", "informe_anormales", "apertura"]
    documentos.sort(key=lambda d: orden.index(d["tipo"]))
    return documentos[:MAX_DOCUMENTOS_ADJUDICACION]


def _parsear_entry(entry) -> dict:
    cfs = entry.find("cac-place-ext:ContractFolderStatus", NS)

    expediente = _texto(cfs, "cbc:ContractFolderID") if cfs is not None else None
    estado = None
    if cfs is not None:
        nodo_estado = cfs.find("cbc-place-ext:ContractFolderStatusCode", NS)
        estado = nodo_estado.text.strip() if nodo_estado is not None and nodo_estado.text else None

    proyecto = cfs.find("cac:ProcurementProject", NS) if cfs is not None else None
    objeto = _texto(proyecto, "cbc:Name") if proyecto is not None else None

    cpvs = []
    importe = None
    moneda = None
    if proyecto is not None:
        for clasif in proyecto.findall("cac:RequiredCommodityClassification/cbc:ItemClassificationCode", NS):
            if clasif.text:
                cpvs.append(clasif.text.strip())
        importe_nodo = proyecto.find("cac:BudgetAmount/cbc:EstimatedOverallContractAmount", NS)
        if importe_nodo is not None and importe_nodo.text:
            importe = importe_nodo.text.strip()
            moneda = importe_nodo.attrib.get("currencyID")

    organismo = None
    party_nodo = cfs.find(
        "cac-place-ext:LocatedContractingParty/cac:Party/cac:PartyName/cbc:Name", NS
    ) if cfs is not None else None
    if party_nodo is not None and party_nodo.text:
        organismo = party_nodo.text.strip()

    # Lugar: código NUTS y nombre del lugar de ejecución del contrato, y
    # código postal del organismo como respaldo (territorio.py los traduce
    # a provincia y comunidad). Las plataformas agregadas no publican la
    # dirección del organismo, solo el lugar de ejecución.
    lugar_nuts = _texto(proyecto, "cac:RealizedLocation/cbc:CountrySubentityCode") if proyecto is not None else None
    lugar_nombre = _texto(proyecto, "cac:RealizedLocation/cbc:CountrySubentity") if proyecto is not None else None
    organismo_cp = _texto(
        cfs, "cac-place-ext:LocatedContractingParty/cac:Party/cac:PostalAddress/cbc:PostalZone"
    ) if cfs is not None else None

    fecha_limite = None
    if cfs is not None:
        deadline_nodo = cfs.find(
            "cac:TenderingProcess/cac:TenderSubmissionDeadlinePeriod/cbc:EndDate", NS
        )
        if deadline_nodo is not None and deadline_nodo.text:
            fecha_limite = deadline_nodo.text.strip()

    # Hora a la que cierra el plazo (hora peninsular) y pliegos. Medido con
    # los ZIP de septiembre de 2026: la hora viene en todas las licitaciones
    # abiertas de los dos feeds (la mitad cierra a las 23:59, el resto a las
    # 14:00, 12:00, 13:00...), y los pliegos en el 98% de los perfiles
    # propios y el 80% de las plataformas agregadas, con dirección de
    # descarga directa. Los pliegos solo se guardan de lo que está en plazo:
    # el feed trae decenas de miles de expedientes ya cerrados.
    hora_limite = None
    pliegos = []
    if cfs is not None:
        hora_limite = _texto(cfs, "cac:TenderingProcess/cac:TenderSubmissionDeadlinePeriod/cbc:EndTime")
        if estado == "PUB":
            for etiqueta, tipo in (("cac:LegalDocumentReference", "administrativo"),
                                   ("cac:TechnicalDocumentReference", "tecnico")):
                for doc in cfs.findall(etiqueta, NS):
                    url = _texto(doc, "cac:Attachment/cac:ExternalReference/cbc:URI")
                    if url:
                        pliegos.append({"tipo": tipo, "nombre": _texto(doc, "cbc:ID"), "url": url})

    enlace = None
    link_nodo = entry.find("atom:link", NS)
    if link_nodo is not None:
        enlace = limpiar_enlace(link_nodo.attrib.get("href"))

    # Bloque de resultado/adjudicación: presente en el mismo feed general
    # para expedientes en estado ADJ/RES (confirmado con datos reales, no
    # hace falta un feed aparte). Se parsea siempre -es inofensivo, viene
    # vacío en PUB/EV/PRE- para que clasificar.py pueda construir la
    # categoría "adjudicaciones" sin volver a tocar este scraper.
    empresa_adjudicataria = None
    empresa_nif = None
    fecha_adjudicacion = None
    importe_adjudicado = None
    tender_result = cfs.find("cac:TenderResult", NS) if cfs is not None else None
    if tender_result is not None:
        nombre_ganador = tender_result.find("cac:WinningParty/cac:PartyName/cbc:Name", NS)
        if nombre_ganador is not None and nombre_ganador.text:
            empresa_adjudicataria = ocultar_en_texto(limpiar_texto(nombre_ganador.text.strip()))
        # NIF del ganador: para quedarse solo con empresas españolas (ver
        # nif.es_espanola). El DNI de una persona física se enmascara ya
        # aquí: el crudo acaba en cachés que se versionan.
        empresa_nif = limpiar_nif(_texto(tender_result, "cac:WinningParty/cac:PartyIdentification/cbc:ID"))
        fecha_adjudicacion = _texto(tender_result, "cbc:AwardDate")
        importe_nodo = tender_result.find(
            "cac:AwardedTenderedProject/cac:LegalMonetaryTotal/cbc:PayableAmount", NS
        )
        if importe_nodo is not None and importe_nodo.text:
            importe_adjudicado = importe_nodo.text.strip()
        # Las plataformas agregadas (sindicacion_1044) no rellenan ni la
        # fecha ni el importe anteriores: publican el anuncio de adjudicación
        # con su fecha y el importe sin impuestos. Se usan solo como respaldo.
        if not fecha_adjudicacion:
            fecha_adjudicacion = _fecha_anuncio(cfs, ("DOC_CAN_ADJ", "DOC_FORM"))
        if not importe_adjudicado:
            importe_adjudicado = _texto(
                tender_result, "cac:AwardedTenderedProject/cac:LegalMonetaryTotal/cbc:TaxExclusiveAmount")

    # Duración PLANEADA del contrato (no fecha fin directa: hay que sumarla
    # a fecha_adjudicacion). Solo relevante para contratos menores -única
    # forma de estimar cuándo vencen, ver extraer_contratos_menores()-, pero
    # se parsea siempre porque es el mismo campo en el mismo sitio del
    # esquema CODICE en ambos feeds (general y de menores).
    duracion_valor = None
    duracion_unidad = None
    if proyecto is not None:
        duracion_nodo = proyecto.find("cac:PlannedPeriod/cbc:DurationMeasure", NS)
        if duracion_nodo is not None and duracion_nodo.text:
            duracion_valor = duracion_nodo.text.strip()
            duracion_unidad = duracion_nodo.attrib.get("unitCode")

    return {
        "expediente": expediente,
        "estado": estado,
        "titulo": limpiar_texto(objeto or _texto(entry, "atom:title")),
        "organismo": limpiar_texto(organismo),
        "lugar_nuts": lugar_nuts,
        "lugar_nombre": lugar_nombre,
        "organismo_cp": organismo_cp,
        "cpv": cpvs,
        "presupuesto": importe,
        "moneda": moneda,
        "fecha_actualizacion": _texto(entry, "atom:updated"),
        "fecha_limite": fecha_limite,
        "hora_limite": hora_limite,
        "pliegos": pliegos,
        "documentos_adjudicacion": _documentos_adjudicacion(cfs) if cfs is not None and estado in ("ADJ", "RES") else [],
        "enlace": enlace,
        "resumen_feed": _texto(entry, "atom:summary"),
        "empresa_adjudicataria": empresa_adjudicataria,
        "empresa_nif": empresa_nif,
        "fecha_adjudicacion": fecha_adjudicacion,
        "importe_adjudicado": importe_adjudicado,
        "duracion_valor": duracion_valor,
        "duracion_unidad": duracion_unidad,
    }


# ---------------------------------------------------------------------------
# Ambos feeds (licitaciones general y contratos menores) se sirven como ZIP
# mensual con la misma estructura: varios .atom, la mayoría lotes
# incrementales con la hora real en el nombre. OJO, corregido el 2026-10-01:
# el ZIP mensual NO es el histórico completo, trae los expedientes
# ACTUALIZADOS ese mes (el de septiembre de 2026, ~41.000 expedientes, el 85%
# de sus adjudicaciones de 2026). Por eso clasificar.py acumula el resultado
# entre ejecuciones (FUENTES_ACUMULATIVAS) y el histórico de adjudicaciones
# se construyó con los ZIP anuales. "Sumar solo el fichero sin sufijo de
# fecha" fue un bug real de una versión anterior (ver README): hay que
# iterar TODOS los ficheros del ZIP y quedarse con la última versión de cada
# expediente.
# ---------------------------------------------------------------------------
FEED_GENERAL_ZIP = (
    "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/"
    "licitacionesPerfilesContratanteCompleto3_{anio_mes}.zip"
)
FEED_MENORES_ZIP = (
    "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_1143/"
    "contratosMenoresPerfilesContratantes_{anio_mes}.zip"
)
# Plataformas autonómicas agregadas en PLACSP (Cataluña, Euskadi, Andalucía,
# Madrid, Galicia, Navarra, La Rioja): no están en sindicacion_643, que solo
# trae los organismos con perfil propio en PLACSP. Hasta octubre de 2026 el
# radar solo las veía por el buscador web, y solo lo publicado en los tres
# últimos días. Medido con el ZIP de septiembre de 2026 (19 MB, 15.000
# expedientes): 49 licitaciones de marketing con plazo abierto, de las que
# el radar no tenía 40. Mismo esquema CODICE que el feed general, salvo la
# fecha y el importe de adjudicación (ver _parsear_entry).
FEED_AGREGADAS_ZIP = (
    "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_1044/"
    "PlataformasAgregadasSinMenores_{anio_mes}.zip"
)


# Los ZIP descargados se quedan en disco (data/raw/ no se versiona) para que
# el histórico de adjudicaciones los reutilice en la misma ejecución sin
# volver a bajarlos (scrapers/historico_adjudicaciones.py, modo "diario").
DIR_ZIPS = Path(__file__).resolve().parent.parent / "data" / "raw" / "zips"
# Los primeros días del mes se lee también el ZIP del mes anterior: el cron
# corre a las 22:47 UTC pero GitHub lo retrasa horas, así que la ejecución
# del último día del mes cae ya en el mes siguiente y, leyendo solo el "mes
# en curso", el último lote del mes (el del día 30/31 a las 20:15) no se
# leía nunca. Además esos días el ZIP del mes nuevo puede no existir aún.
DIAS_LEER_MES_ANTERIOR = 3
# OJO: no releer meses pasados dentro del pipeline diario para rellenar un
# campo nuevo. Se probó la noche del 2026-10-03 (agosto y septiembre, para la
# provincia, la hora de cierre y los pliegos): triplicó la descarga, PLACSP
# servía lento esa noche, el paso tardó 68 minutos y el día se quedó sin
# publicar. Además el mes en curso se lee el último, así que si el paso se
# corta, lo que se pierde es justo lo más reciente. Si hace falta rellenar
# lo acumulado, mejor una ejecución aparte.


def _meses_a_leer() -> list[str]:
    hoy = datetime.now(timezone.utc).date()
    meses = [hoy.strftime("%Y%m")]
    if hoy.day <= DIAS_LEER_MES_ANTERIOR:
        anterior = hoy.replace(day=1) - timedelta(days=1)
        meses.insert(0, anterior.strftime("%Y%m"))
    return meses


def _descargar_zip(url: str, destino: Path) -> None:
    # En streaming a disco: el ZIP de licitaciones ronda los 300 MB.
    with requests.get(url, stream=True, timeout=300,
                      headers={"User-Agent": "licitaciones-marketing-radar/1.0"}) as resp:
        resp.raise_for_status()
        with destino.open("wb") as f:
            for trozo in resp.iter_content(chunk_size=1 << 20):
                f.write(trozo)


def _extraer_zip_mensual(url_template: str, nombre: str) -> list[dict]:
    DIR_ZIPS.mkdir(parents=True, exist_ok=True)
    # Versión más reciente de cada expediente (aparece una vez por cada
    # cambio de estado). Antes se guardaba la primera que salía en el ZIP.
    mejores: dict[str, dict] = {}
    ultimo_error: Exception | None = None
    leidos = 0
    for anio_mes in _meses_a_leer():
        destino = DIR_ZIPS / f"{nombre}_{anio_mes}.zip"
        try:
            _descargar_zip(url_template.format(anio_mes=anio_mes), destino)
            with zipfile.ZipFile(destino) as z:
                for fichero in z.namelist():
                    try:
                        root = ET.fromstring(z.read(fichero))
                    except ET.ParseError:
                        continue
                    for entry in root.findall("atom:entry", NS):
                        item = _parsear_entry(entry)
                        clave = item["expediente"] or item["enlace"]
                        previo = mejores.get(clave)
                        if previo is None or (item["fecha_actualizacion"] or "") >= (previo["fecha_actualizacion"] or ""):
                            mejores[clave] = item
            leidos += 1
        except (requests.RequestException, zipfile.BadZipFile) as exc:
            # El del mes en curso puede no existir todavía los primeros días.
            print(f"[placsp] AVISO: {nombre} {anio_mes} no disponible ({exc})", file=sys.stderr)
            destino.unlink(missing_ok=True)
            ultimo_error = exc
    if not leidos:
        raise ultimo_error
    return list(mejores.values())


def extraer() -> list[dict]:
    return _extraer_zip_mensual(FEED_GENERAL_ZIP, "licitaciones")


def extraer_contratos_menores() -> list[dict]:
    return _extraer_zip_mensual(FEED_MENORES_ZIP, "menores")


def extraer_agregadas() -> list[dict]:
    return _extraer_zip_mensual(FEED_AGREGADAS_ZIP, "agregadas")


def guardar_crudo(items: list[dict], prefijo: str = "placsp") -> Path:
    return comun.guardar_crudo(FUENTE, prefijo, items)


def _guardar_error(prefijo: str, exc: Exception) -> None:
    comun.guardar_error(FUENTE, prefijo, exc)


def main() -> None:
    # zipfile.BadZipFile: los primeros días de cada mes el ZIP del mes en
    # curso todavía no existe y PLACSP responde con algo que no es un ZIP
    # (pasó el 2026-10-01). No es un fallo del scraper: sin crudo nuevo,
    # clasificar.py sigue con lo acumulado (ver FUENTES_ACUMULATIVAS) y el
    # buscador web cubre lo publicado esos días. Los dos feeds se intentan
    # por separado: que falte uno no impide el otro.
    fallo = False
    try:
        items = extraer()
        ruta = guardar_crudo(items, "placsp")
        print(f"[placsp] {len(items)} licitaciones guardadas en {ruta}")
    except (requests.RequestException, ET.ParseError, zipfile.BadZipFile) as exc:
        print(f"[placsp] ERROR al consultar el feed de PLACSP: {exc}", file=sys.stderr)
        _guardar_error("placsp", exc)
        fallo = True

    try:
        agregadas = extraer_agregadas()
        ruta = guardar_crudo(agregadas, "placsp_agregadas")
        print(f"[placsp] {len(agregadas)} expedientes de plataformas agregadas guardados en {ruta}")
    except (requests.RequestException, ET.ParseError, zipfile.BadZipFile) as exc:
        print(f"[placsp] ERROR al consultar las plataformas agregadas: {exc}", file=sys.stderr)
        _guardar_error("placsp_agregadas", exc)
        fallo = True

    try:
        menores = extraer_contratos_menores()
    except (requests.RequestException, ET.ParseError, KeyError, zipfile.BadZipFile) as exc:
        print(f"[placsp] ERROR al consultar contratos menores: {exc}", file=sys.stderr)
        _guardar_error("placsp_menores", exc)
        sys.exit(1)

    ruta_menores = guardar_crudo(menores, "placsp_menores")
    print(f"[placsp] {len(menores)} contratos menores guardados en {ruta_menores}")
    if fallo:
        sys.exit(1)


if __name__ == "__main__":
    main()
