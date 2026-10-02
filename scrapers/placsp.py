# -*- coding: utf-8 -*-
"""
Cliente del feed de sindicación de PLACSP (Plataforma de Contratación del
Sector Público, Estado español).

Método de acceso: PLACSP NO tiene una API REST pública documentada como la
de TED. Lo que publica es un feed ATOM con extensión CODICE 2.07,
confirmado navegando el XML real. Namespaces reales verificados:

    cbc:          urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2
    cac:          urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2
    cac-place-ext: urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2
    cbc-place-ext: urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonBasicComponents-2

HISTORIAL — de ATOM paginado a ZIP mensual (el cambio importante de este
módulo). La primera versión leía el feed ATOM paginable
(.../sindicacion_643/licitacionesPerfilesContratanteCompleto3.atom) siguiendo
<link rel="next">. Se verificó en vivo (curl + cache-busting en peticiones
separadas por >15 minutos) que la página 1 de ese ATOM es un ancla FIJA que
no avanza sola, y que en la práctica iba entre 18 y 21 días por detrás del
reloj real -de ahí que una licitación con plazo corto pudiera llegarnos con
menos días de los que en realidad tenía, o directamente ya cerrada-. Subir
`MAX_PAGINAS` no arreglaba esto: `rel="next"` retrocede en el tiempo desde
esa ancla desfasada, así que por muchas páginas que se pidieran nunca se
llegaba a nada más reciente que el ancla.

La solución, descubierta por analogía con el ZIP de contratos menores de
más abajo: sindicacion_643 TAMBIÉN publica un ZIP mensual con el mismo
patrón de URL que sindicacion_1143
(.../sindicacion_643/licitacionesPerfilesContratanteCompleto3_{AAAAMM}.zip),
no documentado en ningún sitio de prosa pero confirmado en vivo (HTTP 200,
content-type application/zip). Cada ZIP mensual trae un fichero histórico
completo (partido en varios .atom, con expedientes desde 2021) MÁS varios
ficheros incrementales con timestamp real en el nombre
(licitacionesPerfilesContratanteCompleto3_20260923_211008_9.atom, etc.).
Verificado con datos reales del mes en curso: la entrada más reciente del
ZIP llegaba a 5 días de retraso frente a los 18-21 días del ATOM paginado, y
el número de licitaciones "PUB" con plazo todavía genuinamente abierto hoy
pasó de 998 a 3.202 sobre el mismo universo de datos -exactamente el
problema que preocupaba: menos días reales para preparar la documentación
de una licitación con plazo corto-. Por eso `extraer()` usa ahora el mismo
mecanismo de ZIP mensual que `extraer_contratos_menores()` (ver
`_extraer_zip_mensual()`, compartida por ambas).

Segundo feed, sindicacion_1143, para CONTRATOS MENORES (adjudicación
directa): se probó, se quitó (un contrato menor se publica SIEMPRE ya
adjudicado, nunca es una oportunidad a la que presentarse) y se ha vuelto
a añadir con otro objetivo -prospección comercial sobre contratos que
vencen pronto, ver extraer_contratos_menores() y el README-.

Tercer feed, sindicacion_1044, con las PLATAFORMAS AUTONÓMICAS agregadas en
PLACSP (ver FEED_AGREGADAS_ZIP): licitaciones y adjudicaciones de los
organismos que publican en la plataforma de su comunidad y no en PLACSP.

Ejecutar directamente para lanzar la extracción y guardar el crudo (desde
la carpeta licitaciones_marketing/):
    python scrapers/placsp.py
"""

from __future__ import annotations

import json
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

FUENTE = "Estado"

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "cbc": "urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2",
    "cac-place-ext": "urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonAggregateComponents-2",
    "cbc-place-ext": "urn:dgpe:names:draft:codice-place-ext:schema:xsd:CommonBasicComponents-2",
}


def _texto(el, path) -> str | None:
    nodo = el.find(path, NS)
    return nodo.text.strip() if nodo is not None and nodo.text else None


def _fecha_anuncio(cfs, tipos: tuple[str, ...]) -> str | None:
    """Fecha del primer anuncio publicado de alguno de estos tipos
    (DOC_CAN_ADJ = adjudicación, DOC_FORM = formalización). Misma lógica que
    scrapers/historico_adjudicaciones._fecha_anuncio."""
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

    enlace = None
    link_nodo = entry.find("atom:link", NS)
    if link_nodo is not None:
        enlace = link_nodo.attrib.get("href")

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
            empresa_adjudicataria = nombre_ganador.text.strip()
        # NIF del ganador: para quedarse solo con empresas españolas (ver
        # normalizar.es_empresa_espanola).
        empresa_nif = _texto(tender_result, "cac:WinningParty/cac:PartyIdentification/cbc:ID")
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
        "titulo": objeto or _texto(entry, "atom:title"),
        "organismo": organismo,
        "lugar_nuts": lugar_nuts,
        "lugar_nombre": lugar_nombre,
        "organismo_cp": organismo_cp,
        "cpv": cpvs,
        "presupuesto": importe,
        "moneda": moneda,
        "fecha_actualizacion": _texto(entry, "atom:updated"),
        "fecha_limite": fecha_limite,
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
    ahora = datetime.now(timezone.utc)
    raw_dir = Path(__file__).resolve().parent.parent / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    nombre = f"{prefijo}_{ahora.strftime('%Y%m%dT%H%M%SZ')}.json"
    ruta = raw_dir / nombre

    payload = {
        "fuente": FUENTE,
        "timestamp": ahora.isoformat(),
        "num_resultados": len(items),
        "resultados": items,
    }
    ruta.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


def _guardar_error(prefijo: str, exc: Exception) -> None:
    ahora = datetime.now(timezone.utc)
    raw_dir = Path(__file__).resolve().parent.parent / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    ruta = raw_dir / f"{prefijo}_{ahora.strftime('%Y%m%dT%H%M%SZ')}_error.json"
    ruta.write_text(
        json.dumps({"fuente": FUENTE, "timestamp": ahora.isoformat(), "error": str(exc)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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
