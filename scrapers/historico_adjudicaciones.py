# -*- coding: utf-8 -*-
"""
Histórico de adjudicaciones (2021 en adelante) para la vista "Histórico de
adjudicaciones" del dashboard: qué empresas ganan contratos de servicios de
agencia, por cuánto, de qué tipo y a qué organismos.

Ámbito (decidido con el usuario): Estado + Euskadi + licitaciones españolas
que solo llegan por TED, incluidos contratos menores.

Fuentes (verificadas en vivo el 2026-09-30):
    - PLACSP perfiles propios (sindicacion_643): ZIP anual 2021-2025
      (605 MB a 2,2 GB cada uno) y mensual para el año en curso.
    - Plataformas autonómicas agregadas en PLACSP (sindicacion_1044,
      Euskadi, Cataluña, Madrid, Andalucía...): ZIP anual/mensual, 75-140 MB.
    - Contratos menores de PLACSP (sindicacion_1143): ZIP anual/mensual,
      155-300 MB.
    - TED, avisos de resultado de organismos españoles (API de búsqueda).
El ZIP mensual NO es una foto completa del histórico (el de septiembre de
2026 trae ~41.000 expedientes, el 85% de las adjudicaciones de 2026): hacen
falta los anuales.

Cada expediente puede tener varios lotes con adjudicatarios distintos: se
guardan TODOS (cac:TenderResult repetido), con NIF -para agrupar empresas
cuyo nombre se escribe de varias formas-, fecha, importe sin IVA, número de
ofertas recibidas y si la ganadora es pyme. Solo entran expedientes cuyo
título encaja con la taxonomía de servicios de agencia (clasificar_texto, la
misma de todo el radar) y con al menos un lote adjudicado.

Uso (desde licitaciones_marketing/):
    # una pieza (lo que hace cada trabajo en paralelo del workflow):
    python scrapers/historico_adjudicaciones.py pieza --feed agregadas --periodo 2021 --salida parcial.json
    python scrapers/historico_adjudicaciones.py pieza --feed ted --periodo 2021 --salida parcial.json
    # unir piezas con lo ya publicado en dashboard/historico-data.js:
    python scrapers/historico_adjudicaciones.py combinar "parciales/*.json"
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import html
import json
import re
import sys
import tempfile
import time
import zipfile
from datetime import date, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

BASE = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE))
sys.path.append(str(BASE / "scrapers"))
import config  # noqa: E402
import territorio  # noqa: E402
from nif import enmascarado as nif_enmascarado, es_relleno, limpiar as limpiar_nif, ocultar_en_texto  # noqa: E402
from clasificar import clasificar_texto, _normalizar_texto, _titulo_ted  # noqa: E402
import peticiones  # noqa: E402
from placsp import NS, _fecha_anuncio, _texto, limpiar_enlace, limpiar_texto  # noqa: E402

SALIDA = BASE / "data" / "historico_adjudicaciones.json"
SALIDA_DETALLE = BASE / "dashboard" / "historico-detalle"
FRAGMENTOS = 32
SALIDA_DASHBOARD = BASE / "dashboard" / "historico-data.js"

URL_SINDICACION = "https://contrataciondelsectorpublico.gob.es/sindicacion/"
FEEDS = {
    "licitaciones": "sindicacion_643/licitacionesPerfilesContratanteCompleto3_{periodo}.zip",
    "agregadas": "sindicacion_1044/PlataformasAgregadasSinMenores_{periodo}.zip",
    "menores": "sindicacion_1143/contratosMenoresPerfilesContratantes_{periodo}.zip",
}
ANIO_INICIO = 2021

# Listas oficiales de códigos (leídas del formulario del buscador de PLACSP).
TIPOS_CONTRATO = {
    "1": "Suministros", "2": "Servicios", "3": "Obras", "7": "Administrativo especial",
    "8": "Privado", "21": "Gestión de servicios públicos", "22": "Concesión de servicios",
    "31": "Concesión de obras públicas", "32": "Concesión de obras",
    "40": "Colaboración público-privada", "50": "Patrimonial",
}
PROCEDIMIENTOS = {
    "1": "Abierto", "9": "Abierto simplificado", "10": "Asociación para la innovación",
    "7": "Basado en acuerdo marco", "12": "Basado en sistema dinámico",
    "8": "Concurso de proyectos", "11": "Derivado de asociación para la innovación",
    "5": "Diálogo competitivo", "13": "Licitación con negociación",
    "4": "Negociado con publicidad", "3": "Negociado sin publicidad",
    "100": "Normas internas", "999": "Otros", "2": "Restringido",
}
# Provincias de la CAPV por código postal: Álava 01, Gipuzkoa 20, Bizkaia 48.
CP_EUSKADI = ("01", "20", "48")


def _importe(texto: str | None) -> float | None:
    """0 en PLACSP significa "no publicado", no "gratis" (mismo criterio que
    normalizar._parsear_presupuesto)."""
    try:
        valor = float(texto) if texto else None
    except ValueError:
        return None
    return valor if valor else None


def _id(*partes: str | None) -> str:
    return hashlib.sha1("|".join(p or "" for p in partes).encode("utf-8")).hexdigest()[:16]


def _es_euskadi(cp: str, nuts_ejecucion: str, enlace: str | None) -> bool:
    """Organismo vasco: código postal de Álava/Gipuzkoa/Bizkaia (perfiles
    propios de PLACSP), o -en las plataformas agregadas, que no dan
    dirección- lugar de ejecución en la CAPV (NUTS ES21x) o anuncio alojado
    en la plataforma de contratación de Euskadi."""
    return (cp[:2] in CP_EUSKADI or nuts_ejecucion.startswith("ES21")
            or "contratacion.euskadi.eus" in (enlace or ""))


# Duración planeada en PLACSP (DAY/MON/ANN): MON y ANN se aproximan a 30 y
# 365 días, igual que normalizar._fecha_fin_estimada_placsp. Basta para
# decidir "está a punto de terminar".
_DIAS_POR_UNIDAD = {"DAY": 1, "MON": 30, "ANN": 365}


def _fin_contrato(proyecto, lotes: list[dict]) -> tuple[str | None, bool | None]:
    """(fecha de fin estimada, si prevé prórroga) de un expediente de PLACSP.
    La fecha de fin publicada si la hay; si no, el inicio (o, si falta, la
    fecha de adjudicación más reciente) más la duración. Medido en las
    adjudicaciones de agencia de septiembre de 2026: 90 % con duración y 40 %
    con prórroga prevista (cac:ContractExtension), que puede alargarlo."""
    if proyecto is None:
        return None, None
    prorroga = proyecto.find("cac:ContractExtension", NS) is not None
    periodo = proyecto.find("cac:PlannedPeriod", NS)
    if periodo is None:
        return None, prorroga
    fin = (_texto(periodo, "cbc:EndDate") or "")[:10]
    if fin:
        return fin, prorroga
    nodo = periodo.find("cbc:DurationMeasure", NS)
    if nodo is None or not nodo.text or nodo.attrib.get("unitCode") not in _DIAS_POR_UNIDAD:
        return None, prorroga
    inicio = (_texto(periodo, "cbc:StartDate") or "")[:10] or max((l["fecha"] or "" for l in lotes), default="")
    try:
        dias = int(float(nodo.text)) * _DIAS_POR_UNIDAD[nodo.attrib["unitCode"]]
        return (date.fromisoformat(inicio) + timedelta(days=dias)).isoformat(), prorroga
    except (ValueError, OverflowError):
        return None, prorroga


def _parsear_entry(entry, es_menor: bool) -> dict | None:
    cfs = entry.find("cac-place-ext:ContractFolderStatus", NS)
    if cfs is None:
        return None
    # Último recurso: fecha de la última actualización del expediente.
    fecha_anuncio_adj = _fecha_anuncio(cfs, ("DOC_CAN_ADJ", "DOC_FORM")) or (_texto(entry, "atom:updated") or "")[:10] or None

    lotes = []
    for tr in cfs.findall("cac:TenderResult", NS):
        empresa = _texto(tr, "cac:WinningParty/cac:PartyName/cbc:Name")
        if not empresa:
            continue  # desierto, desistido... sin ganador
        importe = _importe(_texto(tr, "cac:AwardedTenderedProject/cac:LegalMonetaryTotal/cbc:TaxExclusiveAmount"))
        if importe is None:
            importe = _importe(_texto(tr, "cac:AwardedTenderedProject/cac:LegalMonetaryTotal/cbc:PayableAmount"))
        ofertas = _texto(tr, "cbc:ReceivedTenderQuantity")
        pyme = _texto(tr, "cbc:SMEAwardedIndicator")
        lotes.append({
            "empresa": empresa,
            "nif": limpiar_nif(_texto(tr, "cac:WinningParty/cac:PartyIdentification/cbc:ID")),
            "fecha": (_texto(tr, "cbc:AwardDate") or "")[:10] or fecha_anuncio_adj,
            "importe": importe,
            "ofertas": int(ofertas) if ofertas and ofertas.isdigit() else None,
            "pyme": {"true": True, "false": False}.get(pyme or ""),
            "lote": _texto(tr, "cac:AwardedTenderedProject/cbc:ProcurementProjectLotID"),
        })
    if not lotes:
        return None

    # Acuerdos marco con varias adjudicatarias: PLACSP repite el importe
    # TOTAL del acuerdo en cada ganadora (verificado: Ingenio Media e Imaxe
    # Intermedia, 6,9 M€ cada una del mismo acuerdo de Turismo de Galicia).
    # Sumado por empresa, eso multiplica el importe real. Se reparte a
    # partes iguales entre las que comparten lote e importe.
    grupos: dict[tuple, list[dict]] = {}
    for l in lotes:
        if l["importe"]:
            grupos.setdefault((l["lote"], l["importe"]), []).append(l)
    for grupo in grupos.values():
        if len(grupo) > 1:
            for l in grupo:
                l["importe"] = round(l["importe"] / len(grupo), 2)

    proyecto = cfs.find("cac:ProcurementProject", NS)
    titulo = _texto(proyecto, "cbc:Name") or _texto(entry, "atom:title") or ""
    clasif = clasificar_texto(titulo)
    if not clasif["incluir"]:
        return None

    parte = "cac-place-ext:LocatedContractingParty/cac:Party/"
    cp = _texto(cfs, parte + "cac:PostalAddress/cbc:PostalZone") or ""
    link = entry.find("atom:link", NS)
    enlace = link.attrib.get("href") if link is not None else None
    organismo = _texto(cfs, parte + "cac:PartyName/cbc:Name") or "no publicado"
    expediente = _texto(cfs, "cbc:ContractFolderID")
    nuts = _texto(proyecto, "cac:RealizedLocation/cbc:CountrySubentityCode") or ""
    # Mismo criterio que el radar (normalizar._lugar): lugar de ejecución y,
    # si no lo hay, código postal del organismo.
    provincia, comunidad = territorio.lugar(nuts, None, cp)
    fin, prorroga = _fin_contrato(proyecto, lotes)

    return {
        "id": _id(enlace or expediente, organismo),
        "expediente": expediente,
        "titulo": titulo,
        "organismo": organismo,
        "organismo_nif": _texto(cfs, parte + "cac:PartyIdentification/cbc:ID"),
        "ambito": "Euskadi" if _es_euskadi(cp, nuts, enlace) else "Estado",
        "provincia": provincia,
        "comunidad": comunidad,
        "tipo_contrato": TIPOS_CONTRATO.get(_texto(proyecto, "cbc:TypeCode") or "", "no publicado"),
        "procedimiento": "Contrato menor" if es_menor else PROCEDIMIENTOS.get(
            _texto(cfs, "cac:TenderingProcess/cbc:ProcedureCode") or "", "no publicado"),
        "menor": es_menor,
        "presupuesto": _importe(_texto(proyecto, "cac:BudgetAmount/cbc:TaxExclusiveAmount")),
        "cpv": [c.text.strip() for c in (proyecto.findall(
            "cac:RequiredCommodityClassification/cbc:ItemClassificationCode", NS) if proyecto is not None else []) if c.text],
        "categorias": clasif["categorias"],
        "enlace": enlace,
        "fuente": "PLACSP",
        "actualizado": (_texto(entry, "atom:updated") or "")[:19],
        "fin": fin,
        "prorroga": prorroga,
        "lotes": lotes,
    }


def _descargar(url: str, destino: Path) -> bool:
    ultimo = None
    for intento in range(4):
        try:
            with requests.get(url, stream=True, timeout=120,
                              headers={"User-Agent": "licitaciones-marketing-radar/1.0"}) as resp:
                if resp.status_code == 404:
                    # El ZIP del mes en curso no existe los primeros días
                    # (pasó el 2026-10-01): no es un error, aún no hay datos.
                    return False
                resp.raise_for_status()
                with destino.open("wb") as f:
                    for trozo in resp.iter_content(chunk_size=1 << 20):
                        f.write(trozo)
            return True
        except requests.RequestException as exc:
            ultimo = exc
            time.sleep(30 * (intento + 1))
    raise ultimo


# Prefiltro sobre el texto en bruto. Parsear todo el XML y clasificar cada
# título palabra clave a palabra clave tardaba 7 min con el mensual de
# 294 MB (ahora ~1,5). Ojo: esto NO es lo que hacía que los anuales no
# cupieran en 3 h de GitHub Actions; eso es la descarga de PLACSP (~0,8 MB/s
# en total), ver el timeout del workflow. El 98% de los expedientes no interesa, así que
# antes de parsear nada se descarta lo que no tiene adjudicatario y lo que
# no contiene NINGUNA palabra clave de la taxonomía (una sola búsqueda con
# todas las palabras, misma semántica de palabra completa que
# clasificar._contiene_keyword). clasificar_texto decide después con las
# reglas completas (exclusiones, servicios no ofrecidos...).
_ALGUNA_KEYWORD = re.compile(
    r"\b(?:" + "|".join(
        re.escape(kw) for kw in sorted({k for kws in config.CATEGORIAS.values() for k in kws}, key=len, reverse=True)
    ) + r")\b"
)
_TITULOS_VISTOS: dict[str, bool] = {}
_RE_TITULOS =re.compile(r"<title>(.*?)</title>|<cac:ProcurementProject>\s*<cbc:Name>(.*?)</cbc:Name>", re.S)


def _entries(texto: str):
    """Trocea un .atom en sus <entry>...</entry> con búsquedas directas (una
    expresión regular perezosa sobre 15 MB era lo más lento del proceso)."""
    pos = texto.find("<entry")
    while pos != -1:
        fin = texto.find("</entry>", pos)
        if fin == -1:
            return
        yield texto[pos:fin + 8]
        pos = texto.find("<entry", fin)


def _puede_interesar(entry_xml: str) -> bool:
    if "<cac:WinningParty>" not in entry_xml:
        return False
    for m in _RE_TITULOS.finditer(entry_xml):
        titulo = m.group(1) or m.group(2) or ""
        # El mismo expediente se repite con cada cambio de estado.
        relevante = _TITULOS_VISTOS.get(titulo)
        if relevante is None:
            relevante = bool(_ALGUNA_KEYWORD.search(_normalizar_texto(html.unescape(titulo))))
            _TITULOS_VISTOS[titulo] = relevante
        if relevante:
            return True
    return False


def procesar_zip(ruta: Path, es_menor: bool) -> dict[str, dict]:
    """Recorre todos los .atom del ZIP y se queda con la versión más reciente
    de cada expediente (un mismo expediente aparece una vez por cada cambio
    de estado a lo largo del año)."""
    registros: dict[str, dict] = {}
    with zipfile.ZipFile(ruta) as z:
        for nombre in z.namelist():
            texto = z.read(nombre).decode("utf-8", "replace")
            apertura = re.search(r"<feed[^>]*>", texto)
            if apertura is None:
                continue
            for entry_xml in _entries(texto):
                if not _puede_interesar(entry_xml):
                    continue
                try:
                    # La apertura de <feed> lleva las declaraciones de namespaces.
                    entry = ET.fromstring(apertura.group(0) + entry_xml + "</feed>").find("atom:entry", NS)
                except ET.ParseError:
                    continue
                r = _parsear_entry(entry, es_menor)
                if r is None:
                    continue
                previo = registros.get(r["id"])
                if previo is None or r["actualizado"] >= previo["actualizado"]:
                    registros[r["id"]] = r
    return registros


def pieza_placsp(feed: str, periodo: str) -> list[dict]:
    url = URL_SINDICACION + FEEDS[feed].format(periodo=periodo)
    with tempfile.TemporaryDirectory() as tmp:
        destino = Path(tmp) / "feed.zip"
        if not _descargar(url, destino):
            print(f"[historico] {feed} {periodo}: el fichero todavía no existe en PLACSP, sin datos")
            return []
        try:
            return list(procesar_zip(destino, es_menor=(feed == "menores")).values())
        except zipfile.BadZipFile:
            print(f"[historico] {feed} {periodo}: PLACSP no ha devuelto un ZIP válido, sin datos", file=sys.stderr)
            return []


URL_EUSKADI_CONTRATOS = "https://api.euskadi.eus/procurements/contracts"


def pieza_euskadi_menores(periodo: str) -> list[dict]:
    """Contratos menores de organismos vascos, desde la API de contratación
    de Euskadi. Hacen falta aparte: los organismos vascos publican sus
    menores en su propia plataforma, no en PLACSP (el feed de menores de
    PLACSP solo traía 896 expedientes vascos en 5 años, de la UPV/EHU y la
    Autoridad Portuaria, frente a ~84.000 menores al año en esta API), y el
    feed de plataformas agregadas excluye los menores por definición.

    'minor-contract=true' filtra en el servidor (verificado: 93.033 -> 83.760
    en 2025). El tamaño de página máximo es 50 (100 devuelve 400)."""
    import euskadi  # noqa: E402  (resuelve y cachea el nombre del organismo)

    desde, hasta = euskadi.rango_mes_api(periodo)
    salida: dict[str, dict] = {}
    pagina, total_paginas = 1, 1
    while pagina <= total_paginas:
        params = {"minor-contract": "true", "award-date.gt": desde, "award-date.lt": hasta,
                  "itemsOfPage": 50, "currentPage": pagina}
        try:
            datos = peticiones.pedir("GET", URL_EUSKADI_CONTRATOS, intentos=4, espera=10, params=params,
                                     timeout=60, headers={"Accept": "application/json"}).json()
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError(f"La API de Euskadi no responde (página {pagina} de {periodo})") from exc
        total_paginas = datos.get("totalPages", 1)
        for item in datos.get("items", []):
            titulo = item.get("object") or ""
            empresa = item.get("socialReason")
            if not empresa or not _ALGUNA_KEYWORD.search(_normalizar_texto(titulo)):
                continue
            clasif = clasificar_texto(titulo)
            if not clasif["incluir"]:
                continue
            href = (item.get("_links") or {}).get("contractingAuthority", {}).get("href")
            fecha = (item.get("awardDate") or "")[:10]
            identificador = str(item.get("id") or "")
            organismo = euskadi._resolver_organismo(href) or "no publicado"
            # _resolver_organismo deja en caché la región del organismo.
            provincia, _ = territorio.lugar(None, euskadi._CACHE_NUTS.get(href))
            salida[identificador] = {
                "id": _id("EUSKADI", identificador),
                "expediente": identificador,
                "titulo": titulo,
                "organismo": organismo,
                "organismo_nif": None,
                "ambito": "Euskadi",
                "provincia": provincia,
                "comunidad": "País Vasco",
                "tipo_contrato": (item.get("contractType") or {}).get("name") or "no publicado",
                "procedimiento": "Contrato menor",
                "menor": True,
                "presupuesto": None,
                "cpv": [],
                "categorias": clasif["categorias"],
                "enlace": item.get("mainEntityOfPage"),
                "fuente": "Euskadi",
                "actualizado": fecha,
                "lotes": [{
                    "empresa": empresa,
                    "nif": limpiar_nif(item.get("CIF")),
                    "fecha": fecha or None,
                    "importe": _importe(str(item.get("awardAmountWithoutVAT") or item.get("awardAmount") or "")),
                    "ofertas": None, "pyme": None, "lote": None,
                }],
            }
        pagina += 1
        time.sleep(0.3)
    return list(salida.values())


def pieza_ted(anio: str) -> list[dict]:
    """Avisos de resultado de TED de organismos españoles, mismos rangos CPV
    que el radar. Casi todos están también en PLACSP; combinar() descarta
    los que coinciden por título y organismo y deja solo los que no."""
    import ted  # noqa: E402  (mismo cliente que el radar diario)

    query = (f"({ted.consulta_cpv()}) AND buyer-country=ESP AND form-type=result "
             f"AND publication-date>={anio}0101 AND publication-date<={anio}1231")
    campos = ["publication-number", "notice-title", "buyer-name", "buyer-country-sub",
              "publication-date", "winner-name", "winner-identifier", "winner-country", "result-value-lot",
              "result-value-cur-lot", "classification-cpv", "received-submissions-type-val",
              "contract-duration-end-date-lot"]
    salida = []
    for n in ted._consultar(query, campos, limite_paginas=200, scope="ALL"):
        titulo = _titulo_ted(n)
        clasif = clasificar_texto(titulo, ted=True)  # mismo criterio que el radar diario
        if not clasif["incluir"]:
            continue
        nombres = next(iter((n.get("buyer-name") or {}).values()), None) or ["no publicado"]
        ganadores = next(iter((n.get("winner-name") or {}).values()), None) or []
        if not ganadores:
            continue
        nifs = n.get("winner-identifier") or []
        paises = n.get("winner-country") or []
        importes = n.get("result-value-lot") or []
        region = (n.get("buyer-country-sub") or [""])[0]
        fecha = (n.get("publication-date") or "")[:10]
        numero = n.get("publication-number", "")
        provincia, comunidad = territorio.lugar(None, region)
        salida.append({
            "id": _id("TED", numero),
            "expediente": None,
            "titulo": titulo,
            "organismo": nombres[0],
            "organismo_nif": None,
            "ambito": "Euskadi" if region.startswith("ES21") else "Estado",
            "provincia": provincia,
            "comunidad": comunidad,
            "tipo_contrato": "no publicado",
            "procedimiento": "no publicado",
            "menor": False,
            "presupuesto": None,
            "cpv": n.get("classification-cpv") or [],
            "categorias": clasif["categorias"],
            "enlace": f"https://ted.europa.eu/es/notice/-/detail/{numero}",
            "fuente": "TED",
            "actualizado": fecha,
            # La fecha de fin que publica TED (la más tardía si hay lotes).
            "fin": max((str(f)[:10] for f in n.get("contract-duration-end-date-lot") or [] if f), default=None),
            "prorroga": None,
            "lotes": [{
                "empresa": g,
                "nif": limpiar_nif(nifs[i]) if i < len(nifs) else None,
                "fecha": fecha or None,
                "importe": _importe(str(importes[i])) if i < len(importes) else None,
                "ofertas": None, "pyme": None, "lote": None,
                "pais": paises[i] if i < len(paises) else None,
            } for i, g in enumerate(ganadores)],
        })
    return salida


def _clave_titulo(r: dict) -> str:
    from normalizar import _normalizar_clave, _titulo_ted_sin_prefijo
    titulo = _titulo_ted_sin_prefijo(r["titulo"]) if r["fuente"] == "TED" else r["titulo"]
    # Recortado: lo ya publicado guarda el título a MAX_TITULO caracteres, y
    # sin recortar aquí un título largo dejaba de coincidir con su copia.
    return _normalizar_clave(titulo)[:100]


# ---------------------------------------------------------------------------
# Formato compacto. Con 5 años y los contratos menores (~20.000 al año) son
# más de 110.000 expedientes: como lista de objetos serían ~100 MB. Por
# columnas, con diccionarios para lo que se repite (empresas, organismos...),
# máscara de bits para las categorías, título recortado y solo el
# identificador del enlace de PLACSP, el completo se queda en ~31 MB; lo que
# viaja al navegador es bastante menos (ver _publicar).
# ---------------------------------------------------------------------------
PREFIJO_DEEPLINK = "https://contrataciondelestado.es/wps/poc?uri=deeplink:detalle_licitacion&idEvl="
MAX_TITULO = 160
CATEGORIAS = list(config.CATEGORIAS)  # orden fijo = bit de la máscara
CABECERA_JS = "window.HISTORICO = "


def _clave_empresa(nif: str | None, nombre: str) -> str:
    """Agrupa por NIF (el nombre se escribe de varias formas: "S.L.", "SL",
    "SOCIEDAD LIMITADA"...); sin NIF, por nombre normalizado.

    Un NIF enmascarado ("***9688**", "XXXXX155F") solo enseña tres o cuatro
    cifras: no basta para agrupar, porque junta a personas distintas. Con
    esos se exige además el mismo nombre, comparado sin tildes, sin
    puntuación y sin importar el orden ("GARCÍA LÓPEZ, ANA" = "Ana García
    López"). Los DNI completos ya llegan enmascarados (nif.limpiar), así que
    las personas físicas siempre se agrupan de esta forma."""
    from normalizar import _normalizar_clave

    nif = _nif_empresa(nif)
    if nif and nif_enmascarado(nif):
        return nif + "~" + " ".join(sorted(_normalizar_clave(nombre).split()))
    return nif or "~" + " ".join(nombre.upper().split())


def _nif_empresa(nif: str | None) -> str | None:
    """NIF tal como se guarda y se compara (nif.limpiar), sin los de relleno
    (nif.es_relleno). Sin NIF, la empresa se agrupa por nombre."""
    return None if es_relleno(nif) else limpiar_nif(nif)


def _publicable(texto: str | None) -> str | None:
    """Nombres y títulos sin DNI pegados (nif.ocultar_en_texto) ni el
    "&' || '" de Navarra (placsp.limpiar_texto). Se aplica también a lo ya
    publicado, al volver a compactarlo."""
    return ocultar_en_texto(limpiar_texto(texto))


def _compactar(registros: list[dict], dic_previo: dict | None = None) -> dict:
    """dic_previo: diccionarios de lo ya publicado. Se parte de ellos para que
    cada empresa/organismo conserve su índice (ver combinar_registros).

    Empresas fusionadas: si dos fichas ya publicadas resultan ser la misma
    empresa (el mismo NIF escrito con y sin prefijo "ES"), se queda la
    primera y la otra NO se borra: borrarla correría una posición los
    índices de todas las siguientes, y con ellos los enlaces a fichas que el
    radar ya tiene calculados. Se deja en su sitio como [None, nombre,
    índice_de_la_buena]; el dashboard redirige a la buena."""
    dic = {"empresa": [], "organismo": [], "tipo": [], "procedimiento": [], "lugar": []}
    indices: dict[str, dict] = {k: {} for k in dic}
    nombres_empresa: dict[str, dict[str, int]] = {}
    if dic_previo:
        for valor in dic_previo.get("empresa", []):
            valor = [valor[0], _publicable(valor[1]), *valor[2:]]
            if len(valor) > 2:  # ya fusionada en una pasada anterior
                dic["empresa"].append(valor)
                continue
            clave = _clave_empresa(valor[0], valor[1])
            if clave in indices["empresa"]:
                dic["empresa"].append([None, valor[1], indices["empresa"][clave]])
                continue
            indices["empresa"][clave] = len(dic["empresa"])
            dic["empresa"].append([_nif_empresa(valor[0]), valor[1]])
        for tabla in ("organismo", "tipo", "procedimiento", "lugar"):
            for valor in dic_previo.get(tabla, []):
                if tabla == "organismo":
                    valor = _publicable(valor)
                clave = tuple(valor) if tabla == "lugar" else valor
                if clave not in indices[tabla]:
                    indices[tabla][clave] = len(dic[tabla])
                    dic[tabla].append(valor)

    def idx(tabla: str, clave, valor=None) -> int:
        if clave not in indices[tabla]:
            indices[tabla][clave] = len(dic[tabla])
            dic[tabla].append(valor if valor is not None else clave)
        return indices[tabla][clave]

    exp, lotes = [], []
    for r in registros:
        enlace = limpiar_enlace(r["enlace"]) or ""
        mascara = sum(1 << CATEGORIAS.index(c) for c in r["categorias"] if c in CATEGORIAS)
        lugar = (r.get("provincia"), r.get("comunidad"))
        exp.append([
            r["id"], _publicable(r["titulo"])[:MAX_TITULO].strip(), idx("organismo", _publicable(r["organismo"])),
            1 if r["ambito"] == "Euskadi" else 0, idx("tipo", r["tipo_contrato"]),
            idx("procedimiento", r["procedimiento"]), 1 if r["menor"] else 0, mascara,
            enlace[len(PREFIJO_DEEPLINK):] if enlace.startswith(PREFIJO_DEEPLINK) else enlace,
            1 if r["fuente"] == "TED" else 0, r["actualizado"][:10], r["presupuesto"],
            # [provincia, comunidad]; [None, None] = la fuente no publica el
            # lugar, o el expediente es anterior a que se recogiera.
            idx("lugar", lugar, list(lugar)),
            # Fecha de fin estimada del contrato y si prevé prórroga (1/0);
            # None si la fuente no lo dice o es anterior a octubre de 2026.
            r.get("fin"), None if r.get("prorroga") is None else int(r["prorroga"]),
        ])
        for l in r["lotes"]:
            nombre = _publicable(l["empresa"])
            clave = _clave_empresa(l["nif"], nombre)
            nombres_empresa.setdefault(clave, {}).setdefault(nombre, 0)
            nombres_empresa[clave][nombre] += 1
            lotes.append([len(exp) - 1, idx("empresa", clave, [_nif_empresa(l["nif"]), ""]), l["fecha"],
                          round(l["importe"]) if l["importe"] else None, l["ofertas"],
                          None if l["pyme"] is None else int(l["pyme"])])
    # Nombre mostrado de cada empresa: la grafía más frecuente.
    for clave, i in indices["empresa"].items():
        if clave in nombres_empresa:  # las heredadas sin lotes ahora conservan su nombre
            dic["empresa"][i][1] = max(nombres_empresa[clave].items(), key=lambda kv: kv[1])[0]
    return {"v": 1, "actualizado": date.today().isoformat(), "categorias": CATEGORIAS,
            "prefijo_enlace": PREFIJO_DEEPLINK, "dic": dic, "exp": exp, "lotes": lotes}


def _expandir(c: dict) -> list[dict]:
    """Inversa de _compactar, para añadir piezas nuevas sobre lo publicado."""
    d = c["dic"]
    registros = []
    for e in c["exp"]:
        enlace = e[8] if e[8].startswith("http") or not e[8] else c["prefijo_enlace"] + e[8]
        # Lo publicado antes de octubre de 2026 no tiene la columna de lugar.
        provincia, comunidad = d["lugar"][e[12]] if len(e) > 12 else (None, None)
        registros.append({
            "id": e[0], "expediente": None, "titulo": e[1], "organismo": d["organismo"][e[2]],
            "organismo_nif": None, "ambito": "Euskadi" if e[3] else "Estado",
            "provincia": provincia, "comunidad": comunidad,
            "tipo_contrato": d["tipo"][e[4]], "procedimiento": d["procedimiento"][e[5]],
            "menor": bool(e[6]), "presupuesto": e[11],
            "categorias": [cat for i, cat in enumerate(c["categorias"]) if e[7] >> i & 1],
            "enlace": enlace, "fuente": "TED" if e[9] else "PLACSP", "actualizado": e[10], "lotes": [],
            # Lo publicado antes de octubre de 2026 no tiene fin ni prórroga.
            "fin": e[13] if len(e) > 13 else None,
            "prorroga": None if len(e) <= 14 or e[14] is None else bool(e[14]),
        })
    for l in c["lotes"]:
        nif, nombre = d["empresa"][l[1]][:2]
        registros[l[0]]["lotes"].append({"empresa": nombre, "nif": nif, "fecha": l[2], "importe": l[3],
                                         "ofertas": l[4], "pyme": None if l[5] is None else bool(l[5])})
    return registros


def _leer_publicado() -> tuple[list[dict], dict | None]:
    """Registros ya publicados y sus diccionarios (para conservar índices)."""
    if not SALIDA.exists():
        return [], None
    compacto = json.loads(SALIDA.read_text(encoding="utf-8"))
    return _expandir(compacto), compacto["dic"]


def _publicar(c: dict) -> None:
    """Escribe el fichero completo (data/, no se sirve al navegador: lo usa
    la siguiente actualización) y lo que lee el dashboard, partido en dos
    porque el completo pesa >30 MB y el 75% son títulos y enlaces, que solo
    hacen falta al abrir la ficha de una empresa (medido el 2026-10-01):

    - historico-data.js: diccionarios, atributos por expediente y lotes. Lo
      que necesitan los gráficos y los filtros (~7 MB, ~2 MB comprimido).
    - historico-detalle/NN.js: título y enlace de cada expediente, repartidos
      en FRAGMENTOS ficheros según la empresa adjudicataria. La ficha de una
      empresa descarga solo su fragmento."""
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(c, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    nucleo = {k: c[k] for k in ("v", "actualizado", "categorias", "prefijo_enlace", "dic", "lotes")}
    nucleo["fragmentos"] = FRAGMENTOS
    # [organismo, euskadi, tipo, procedimiento, menor, mascara_categorias,
    # lugar, presupuesto sin IVA en euros enteros (para la rebaja)]
    nucleo["exp"] = [e[2:8] + [e[12], round(e[11]) if e[11] else None] for e in c["exp"]]
    SALIDA_DASHBOARD.write_text(
        "// Generado por scrapers/historico_adjudicaciones.py (ver _publicar). No editar a mano.\n"
        + CABECERA_JS + json.dumps(nucleo, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )

    fragmentos: list[dict] = [{} for _ in range(FRAGMENTOS)]
    for l in c["lotes"]:
        e = c["exp"][l[0]]
        fragmentos[l[1] % FRAGMENTOS][l[0]] = [e[1], e[8]]
    SALIDA_DETALLE.mkdir(parents=True, exist_ok=True)
    for n, contenido in enumerate(fragmentos):
        (SALIDA_DETALLE / f"{n:02d}.js").write_text(
            f"(window.HISTORICO_DETALLE=window.HISTORICO_DETALLE||{{}})[{n}]="
            + json.dumps(contenido, ensure_ascii=False, separators=(",", ":")) + ";\n",
            encoding="utf-8",
        )


def combinar(rutas: list[str]) -> None:
    nuevos = [r for ruta in rutas for r in json.loads(Path(ruta).read_text(encoding="utf-8"))]
    combinar_registros(nuevos)


def combinar_registros(nuevos: list[dict]) -> None:
    """Suma registros nuevos a lo ya publicado y lo vuelve a publicar.

    El orden es estable a propósito: lo publicado conserva su posición (un
    expediente actualizado se sustituye en su sitio) y lo nuevo va al final.
    Los ficheros guardan índices (expediente, empresa, organismo); si cada
    día se reordenara todo, cambiarían enteros y git tendría que guardar
    ~60 MB nuevos por ejecución en vez de las pocas líneas añadidas."""
    from normalizar import _normalizar_clave, _organismos_compatibles, es_empresa_espanola

    # Solo lotes ganados por empresas españolas (vascas incluidas): la
    # agencia quiere ver a sus competidores, no a una empresa extranjera.
    # Misma regla que el radar diario (normalizar.es_empresa_espanola). Se
    # aplica SOLO a lo que entra nuevo: lo publicado ya la pasó, y al
    # guardarlo se pierde el país del adjudicatario que da TED, así que
    # volver a aplicarla descartaba cada día alguna empresa española con un
    # identificador poco habitual (comprobado: 17 expedientes en una pasada).
    lotes_extranjeros = 0
    for r in nuevos:
        antes = len(r["lotes"])
        r["lotes"] = [l for l in r["lotes"]
                      if es_empresa_espanola(l["nif"], [l["pais"]] if l.get("pais") else None, comprador_espanol=True)]
        lotes_extranjeros += antes - len(r["lotes"])
    nuevos = [r for r in nuevos if r["lotes"]]
    print(f"[historico] {lotes_extranjeros} lotes nuevos descartados por ser de empresas no españolas")

    publicados, dic_previo = _leer_publicado()
    registros: dict[str, dict] = {r["id"]: r for r in publicados}
    for r in nuevos:
        previo = registros.get(r["id"])
        if previo is None or r["actualizado"] >= previo["actualizado"]:
            registros[r["id"]] = r

    # TED: solo lo que no está ya en PLACSP (título exacto + organismo
    # compatible). Se revisa también lo de TED ya publicado: puede que PLACSP
    # lo haya publicado después.
    indice: dict[str, list[str]] = {}
    for r in registros.values():
        if r["fuente"] != "TED":
            indice.setdefault(_clave_titulo(r), []).append(_normalizar_clave(r["organismo"]))
    solo_ted = 0
    for r in [r for r in registros.values() if r["fuente"] == "TED"]:
        orgs = indice.get(_clave_titulo(r), [])
        if any(_organismos_compatibles(o, _normalizar_clave(r["organismo"])) for o in orgs):
            del registros[r["id"]]
        else:
            solo_ted += 1

    finales = [r for r in registros.values()
               if any((l["fecha"] or "") >= f"{ANIO_INICIO}-01-01" for l in r["lotes"])]

    _publicar(_compactar(finales, dic_previo))
    n_lotes = sum(len(r["lotes"]) for r in finales)
    print(f"[historico] {len(finales)} expedientes, {n_lotes} lotes adjudicados ({solo_ted} solo en TED) -> "
          f"{SALIDA} ({SALIDA.stat().st_size / 1e6:.1f} MB), {SALIDA_DASHBOARD.name} "
          f"({SALIDA_DASHBOARD.stat().st_size / 1e6:.1f} MB) + {FRAGMENTOS} fragmentos de detalle")


MESES_ROTACION_EUSKADI = 6


def diario() -> None:
    """Alimenta el histórico desde el pipeline diario, sin descargar nada que
    este no haya bajado ya (salvo lo pequeño):

    - PLACSP licitaciones y contratos menores: los ZIP que scrapers/placsp.py
      acaba de dejar en data/raw/zips/ (mes en curso, y el anterior los
      primeros días del mes).
    - Plataformas agregadas: ZIP mensual propio, ~10 MB.
    - TED: avisos de resultado españoles del año en curso (2-3 peticiones).
    - Contratos menores de Euskadi: se publican con meses de retraso y la API
      se consulta por fecha de adjudicación, así que cada día se repasa UNO
      de los últimos 6 meses, en rotación (~4 min). Cada mes se revisa cada 6
      días.

    Cada fuente va por separado: si una falla, las demás se suman igual."""
    import placsp  # noqa: E402

    hoy = date.today()
    nuevos: list[dict] = []

    def sumar(nombre: str, funcion) -> None:
        try:
            registros = funcion()
        except Exception as exc:  # una fuente caída no debe tumbar las demás
            print(f"[historico] AVISO: {nombre} no disponible hoy ({exc})", file=sys.stderr)
            return
        print(f"[historico] {nombre}: {len(registros)} expedientes con adjudicación")
        nuevos.extend(registros)

    for ruta in sorted(placsp.DIR_ZIPS.glob("*.zip")):
        es_menor = ruta.name.startswith("menores")
        sumar(f"PLACSP {ruta.stem}", lambda: list(procesar_zip(ruta, es_menor).values()))
    for mes in placsp._meses_a_leer():
        # Desde octubre de 2026 placsp.py también descarga este ZIP para las
        # licitaciones abiertas: si está en disco, ya se ha leído arriba.
        if (placsp.DIR_ZIPS / f"agregadas_{mes}.zip").exists():
            continue
        sumar(f"agregadas {mes}", lambda: pieza_placsp("agregadas", mes))
    sumar(f"TED {hoy.year}", lambda: pieza_ted(str(hoy.year)))
    indice_mes = hoy.year * 12 + hoy.month - 1 - hoy.toordinal() % MESES_ROTACION_EUSKADI
    mes_euskadi = f"{indice_mes // 12}{indice_mes % 12 + 1:02d}"
    sumar(f"menores de Euskadi {mes_euskadi}", lambda: pieza_euskadi_menores(mes_euskadi))

    if not nuevos and not SALIDA.exists():
        print("[historico] Sin datos nuevos y sin histórico previo: no se publica nada.", file=sys.stderr)
        return
    combinar_registros(nuevos)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="accion", required=True)
    sub.add_parser("diario")
    p = sub.add_parser("pieza")
    p.add_argument("--feed", choices=[*FEEDS, "ted", "euskadi_menores"], required=True)
    p.add_argument("--periodo", required=True, help="AAAA (anual) o AAAAMM (mensual; TED solo AAAA)")
    p.add_argument("--zip", help="ZIP ya descargado (pruebas locales)")
    p.add_argument("--salida", required=True)
    c = sub.add_parser("combinar")
    c.add_argument("parciales", nargs="+")
    args = parser.parse_args()

    if args.accion == "diario":
        diario()
        return
    if args.accion == "combinar":
        rutas = [r for patron in args.parciales for r in glob.glob(patron)]
        combinar(rutas)
        return

    if args.feed == "ted":
        registros = pieza_ted(args.periodo[:4])
    elif args.feed == "euskadi_menores":
        registros = pieza_euskadi_menores(args.periodo)
    elif args.zip:
        registros = list(procesar_zip(Path(args.zip), es_menor=(args.feed == "menores")).values())
    else:
        registros = pieza_placsp(args.feed, args.periodo)
    Path(args.salida).write_text(json.dumps(registros, ensure_ascii=False), encoding="utf-8")
    n_lotes = sum(len(r["lotes"]) for r in registros)
    print(f"[historico] {args.feed} {args.periodo}: {len(registros)} expedientes, {n_lotes} lotes -> {args.salida}")


if __name__ == "__main__":
    main()
