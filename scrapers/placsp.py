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

Ejecutar directamente para lanzar la extracción y guardar el crudo (desde
la carpeta licitaciones_marketing/):
    python scrapers/placsp.py
"""

from __future__ import annotations

import io
import json
import sys
import zipfile
from datetime import datetime, timezone
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
# mensual con la misma estructura: un fichero histórico completo (partido en
# varios .atom) más varios ficheros incrementales con timestamp real en el
# nombre. Da igual cuál de los dos, ni cuándo se ejecute dentro del mes: el
# histórico completo va dentro de CADA ZIP mensual, así que un solo mes basta
# (verificado con datos reales: el ZIP de septiembre trae expedientes con
# fecha de actualización desde 2021). "Sumar solo el fichero sin sufijo de
# fecha" fue un bug real de una versión anterior (ver README): ese fichero es
# una muestra pequeña, no "el acumulado" — hay que iterar TODOS los ficheros
# del ZIP y deduplicar por expediente.
# ---------------------------------------------------------------------------
FEED_GENERAL_ZIP = (
    "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_643/"
    "licitacionesPerfilesContratanteCompleto3_{anio_mes}.zip"
)
FEED_MENORES_ZIP = (
    "https://contrataciondelsectorpublico.gob.es/sindicacion/sindicacion_1143/"
    "contratosMenoresPerfilesContratantes_{anio_mes}.zip"
)


def _extraer_zip_mensual(url_template: str) -> list[dict]:
    anio_mes = datetime.now(timezone.utc).strftime("%Y%m")
    url = url_template.format(anio_mes=anio_mes)
    # timeout alto: el ZIP de licitaciones generales ronda los 180 MB.
    resp = requests.get(url, timeout=300, headers={"User-Agent": "licitaciones-marketing-radar/1.0"})
    resp.raise_for_status()

    resultados = []
    vistos = set()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        for nombre in z.namelist():
            with z.open(nombre) as f:
                try:
                    root = ET.fromstring(f.read())
                except ET.ParseError:
                    continue
            for entry in root.findall("atom:entry", NS):
                item = _parsear_entry(entry)
                clave = item["expediente"] or item["enlace"]
                if clave in vistos:
                    continue
                vistos.add(clave)
                resultados.append(item)
    return resultados


def extraer() -> list[dict]:
    return _extraer_zip_mensual(FEED_GENERAL_ZIP)


def extraer_contratos_menores() -> list[dict]:
    return _extraer_zip_mensual(FEED_MENORES_ZIP)


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
    try:
        items = extraer()
    except (requests.RequestException, ET.ParseError) as exc:
        print(f"[placsp] ERROR al consultar el feed de PLACSP: {exc}", file=sys.stderr)
        _guardar_error("placsp", exc)
        sys.exit(1)

    ruta = guardar_crudo(items, "placsp")
    print(f"[placsp] {len(items)} licitaciones guardadas en {ruta}")

    try:
        menores = extraer_contratos_menores()
    except (requests.RequestException, ET.ParseError, KeyError) as exc:
        print(f"[placsp] ERROR al consultar contratos menores: {exc}", file=sys.stderr)
        _guardar_error("placsp_menores", exc)
        return

    ruta_menores = guardar_crudo(menores, "placsp_menores")
    print(f"[placsp] {len(menores)} contratos menores guardados en {ruta_menores}")


if __name__ == "__main__":
    main()
