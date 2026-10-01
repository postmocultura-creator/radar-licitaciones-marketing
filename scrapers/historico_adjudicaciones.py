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
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

BASE = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE))
sys.path.append(str(BASE / "scrapers"))
import config  # noqa: E402
from clasificar import clasificar_texto, _normalizar_texto, _titulo_ted  # noqa: E402
from placsp import NS  # noqa: E402

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


def _texto(el, path) -> str | None:
    if el is None:
        return None
    nodo = el.find(path, NS)
    return nodo.text.strip() if nodo is not None and nodo.text and nodo.text.strip() else None


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


def _fecha_anuncio(cfs, tipos: tuple[str, ...]) -> str | None:
    """Fecha del primer anuncio publicado de alguno de estos tipos
    (DOC_CAN_ADJ = adjudicación, DOC_FORM = formalización). Las plataformas
    agregadas -verificado con la de Euskadi- no rellenan AwardDate en el
    lote, pero sí publican el anuncio de adjudicación con su fecha."""
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


def _es_euskadi(cp: str, nuts_ejecucion: str, enlace: str | None) -> bool:
    """Organismo vasco: código postal de Álava/Gipuzkoa/Bizkaia (perfiles
    propios de PLACSP), o -en las plataformas agregadas, que no dan
    dirección- lugar de ejecución en la CAPV (NUTS ES21x) o anuncio alojado
    en la plataforma de contratación de Euskadi."""
    return (cp[:2] in CP_EUSKADI or nuts_ejecucion.startswith("ES21")
            or "contratacion.euskadi.eus" in (enlace or ""))


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
            "nif": (_texto(tr, "cac:WinningParty/cac:PartyIdentification/cbc:ID") or "").upper().replace("-", "").replace(" ", "") or None,
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
    clasif = clasificar_texto(titulo, [])
    if not clasif["incluir"]:
        return None

    parte = "cac-place-ext:LocatedContractingParty/cac:Party/"
    cp = _texto(cfs, parte + "cac:PostalAddress/cbc:PostalZone") or ""
    link = entry.find("atom:link", NS)
    enlace = link.attrib.get("href") if link is not None else None
    organismo = _texto(cfs, parte + "cac:PartyName/cbc:Name") or "no publicado"
    expediente = _texto(cfs, "cbc:ContractFolderID")

    return {
        "id": _id(enlace or expediente, organismo),
        "expediente": expediente,
        "titulo": titulo,
        "organismo": organismo,
        "organismo_nif": _texto(cfs, parte + "cac:PartyIdentification/cbc:ID"),
        "ambito": "Euskadi" if _es_euskadi(
            cp, _texto(proyecto, "cac:RealizedLocation/cbc:CountrySubentityCode") or "", enlace) else "Estado",
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
# título palabra clave a palabra clave tardaba ~2 min por cada 10 MB de ZIP
# (medido: 7 min el mensual de 294 MB; los anuales de 1,7-2,2 GB no cabían
# en 3 h de GitHub Actions). El 98% de los expedientes no interesa, así que
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


def pieza_ted(anio: str) -> list[dict]:
    """Avisos de resultado de TED de organismos españoles, mismos rangos CPV
    que el radar. Casi todos están también en PLACSP; combinar() descarta
    los que coinciden por título y organismo y deja solo los que no."""
    import ted  # noqa: E402  (mismo cliente que el radar diario)

    partes_cpv = [f"classification-cpv={g:05d}*" for lo, hi, _ in config.CPV_RANGOS
                  for g in range(lo // 1000, hi // 1000 + 1)]
    query = (f"({' OR '.join(partes_cpv)}) AND buyer-country=ESP AND form-type=result "
             f"AND publication-date>={anio}0101 AND publication-date<={anio}1231")
    campos = ["publication-number", "notice-title", "buyer-name", "buyer-country-sub",
              "publication-date", "winner-name", "winner-identifier", "winner-country", "result-value-lot",
              "result-value-cur-lot", "classification-cpv", "received-submissions-type-val"]
    salida = []
    for n in ted._consultar(query, campos, limite_paginas=200, scope="ALL"):
        titulo = _titulo_ted(n)
        clasif = clasificar_texto(titulo, [])
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
        salida.append({
            "id": _id("TED", numero),
            "expediente": None,
            "titulo": titulo,
            "organismo": nombres[0],
            "organismo_nif": None,
            "ambito": "Euskadi" if region.startswith("ES21") else "Estado",
            "tipo_contrato": "no publicado",
            "procedimiento": "no publicado",
            "menor": False,
            "presupuesto": None,
            "cpv": n.get("classification-cpv") or [],
            "categorias": clasif["categorias"],
            "enlace": f"https://ted.europa.eu/es/notice/-/detail/{numero}",
            "fuente": "TED",
            "actualizado": fecha,
            "lotes": [{
                "empresa": g,
                "nif": (nifs[i] if i < len(nifs) else None),
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


def _compactar(registros: list[dict]) -> dict:
    dic = {"empresa": [], "organismo": [], "tipo": [], "procedimiento": []}
    indices: dict[str, dict] = {k: {} for k in dic}
    nombres_empresa: dict[str, dict[str, int]] = {}

    def idx(tabla: str, clave, valor=None) -> int:
        if clave not in indices[tabla]:
            indices[tabla][clave] = len(dic[tabla])
            dic[tabla].append(valor if valor is not None else clave)
        return indices[tabla][clave]

    exp, lotes = [], []
    for r in registros:
        enlace = r["enlace"] or ""
        mascara = sum(1 << CATEGORIAS.index(c) for c in r["categorias"] if c in CATEGORIAS)
        exp.append([
            r["id"], r["titulo"][:MAX_TITULO].strip(), idx("organismo", r["organismo"]),
            1 if r["ambito"] == "Euskadi" else 0, idx("tipo", r["tipo_contrato"]),
            idx("procedimiento", r["procedimiento"]), 1 if r["menor"] else 0, mascara,
            enlace[len(PREFIJO_DEEPLINK):] if enlace.startswith(PREFIJO_DEEPLINK) else enlace,
            1 if r["fuente"] == "TED" else 0, r["actualizado"][:10], r["presupuesto"],
        ])
        for l in r["lotes"]:
            # Agrupa por NIF (el nombre se escribe de varias formas: "S.L.",
            # "SL", "SOCIEDAD LIMITADA"...); sin NIF, por nombre normalizado.
            clave = l["nif"] or "~" + " ".join(l["empresa"].upper().split())
            nombres_empresa.setdefault(clave, {}).setdefault(l["empresa"], 0)
            nombres_empresa[clave][l["empresa"]] += 1
            lotes.append([len(exp) - 1, idx("empresa", clave, [l["nif"], ""]), l["fecha"],
                          round(l["importe"]) if l["importe"] else None, l["ofertas"],
                          None if l["pyme"] is None else int(l["pyme"])])
    # Nombre mostrado de cada empresa: la grafía más frecuente.
    for clave, i in indices["empresa"].items():
        dic["empresa"][i][1] = max(nombres_empresa[clave].items(), key=lambda kv: kv[1])[0]
    return {"v": 1, "actualizado": date.today().isoformat(), "categorias": CATEGORIAS,
            "prefijo_enlace": PREFIJO_DEEPLINK, "dic": dic, "exp": exp, "lotes": lotes}


def _expandir(c: dict) -> list[dict]:
    """Inversa de _compactar, para añadir piezas nuevas sobre lo publicado."""
    d = c["dic"]
    registros = []
    for e in c["exp"]:
        enlace = e[8] if e[8].startswith("http") or not e[8] else c["prefijo_enlace"] + e[8]
        registros.append({
            "id": e[0], "expediente": None, "titulo": e[1], "organismo": d["organismo"][e[2]],
            "organismo_nif": None, "ambito": "Euskadi" if e[3] else "Estado",
            "tipo_contrato": d["tipo"][e[4]], "procedimiento": d["procedimiento"][e[5]],
            "menor": bool(e[6]), "presupuesto": e[11],
            "categorias": [cat for i, cat in enumerate(c["categorias"]) if e[7] >> i & 1],
            "enlace": enlace, "fuente": "TED" if e[9] else "PLACSP", "actualizado": e[10], "lotes": [],
        })
    for l in c["lotes"]:
        nif, nombre = d["empresa"][l[1]]
        registros[l[0]]["lotes"].append({"empresa": nombre, "nif": nif, "fecha": l[2], "importe": l[3],
                                         "ofertas": l[4], "pyme": None if l[5] is None else bool(l[5])})
    return registros


def _leer_publicado() -> list[dict]:
    if not SALIDA.exists():
        return []
    return _expandir(json.loads(SALIDA.read_text(encoding="utf-8")))


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
    # [organismo, euskadi, tipo, procedimiento, menor, mascara_categorias]
    nucleo["exp"] = [e[2:8] for e in c["exp"]]
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
    from normalizar import _normalizar_clave, _organismos_compatibles, es_empresa_espanola

    registros: dict[str, dict] = {}
    ted: list[dict] = []
    # La actualización semanal añade sobre lo que ya hay. Lo de TED ya
    # publicado vuelve a pasar por el filtro de abajo: puede que PLACSP lo
    # haya publicado después.
    for r in _leer_publicado():
        if r["fuente"] == "TED":
            ted.append(r)
        else:
            registros[r["id"]] = r
    for ruta in rutas:
        for r in json.loads(Path(ruta).read_text(encoding="utf-8")):
            if r["fuente"] == "TED":
                ted.append(r)
                continue
            previo = registros.get(r["id"])
            if previo is None or r["actualizado"] >= previo["actualizado"]:
                registros[r["id"]] = r

    # TED: solo lo que no está ya en PLACSP (título exacto + organismo compatible).
    indice: dict[str, list[str]] = {}
    for r in registros.values():
        if r["fuente"] != "TED":
            indice.setdefault(_clave_titulo(r), []).append(_normalizar_clave(r["organismo"]))
    ids_solo_ted = set()
    for r in ted:
        orgs = indice.get(_clave_titulo(r), [])
        if any(_organismos_compatibles(o, _normalizar_clave(r["organismo"])) for o in orgs):
            continue
        registros[r["id"]] = r
        ids_solo_ted.add(r["id"])
    solo_ted = len(ids_solo_ted)

    # Solo lotes ganados por empresas españolas (vascas incluidas): la
    # agencia quiere ver a sus competidores, no a una empresa extranjera.
    # Misma regla que el radar diario (normalizar.es_empresa_espanola). Se
    # aplica también a lo ya publicado, así una actualización la impone
    # sobre datos generados antes de existir la regla.
    lotes_extranjeros = 0
    for r in registros.values():
        antes = len(r["lotes"])
        r["lotes"] = [l for l in r["lotes"]
                      if es_empresa_espanola(l["nif"], [l["pais"]] if l.get("pais") else None, comprador_espanol=True)]
        lotes_extranjeros += antes - len(r["lotes"])
    print(f"[historico] {lotes_extranjeros} lotes descartados por ser de empresas no españolas")

    finales = [r for r in registros.values()
               if any((l["fecha"] or "") >= f"{ANIO_INICIO}-01-01" for l in r["lotes"])]
    finales.sort(key=lambda r: max(l["fecha"] or "" for l in r["lotes"]), reverse=True)

    _publicar(_compactar(finales))
    n_lotes = sum(len(r["lotes"]) for r in finales)
    print(f"[historico] {len(finales)} expedientes, {n_lotes} lotes adjudicados ({solo_ted} solo en TED) -> "
          f"{SALIDA} ({SALIDA.stat().st_size / 1e6:.1f} MB), {SALIDA_DASHBOARD.name} "
          f"({SALIDA_DASHBOARD.stat().st_size / 1e6:.1f} MB) + {FRAGMENTOS} fragmentos de detalle")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="accion", required=True)
    p = sub.add_parser("pieza")
    p.add_argument("--feed", choices=[*FEEDS, "ted"], required=True)
    p.add_argument("--periodo", required=True, help="AAAA (anual) o AAAAMM (mensual; TED solo AAAA)")
    p.add_argument("--zip", help="ZIP ya descargado (pruebas locales)")
    p.add_argument("--salida", required=True)
    c = sub.add_parser("combinar")
    c.add_argument("parciales", nargs="+")
    args = parser.parse_args()

    if args.accion == "combinar":
        rutas = [r for patron in args.parciales for r in glob.glob(patron)]
        combinar(rutas)
        return

    if args.feed == "ted":
        registros = pieza_ted(args.periodo[:4])
    elif args.zip:
        registros = list(procesar_zip(Path(args.zip), es_menor=(args.feed == "menores")).values())
    else:
        registros = pieza_placsp(args.feed, args.periodo)
    Path(args.salida).write_text(json.dumps(registros, ensure_ascii=False), encoding="utf-8")
    n_lotes = sum(len(r["lotes"]) for r in registros)
    print(f"[historico] {args.feed} {args.periodo}: {len(registros)} expedientes, {n_lotes} lotes -> {args.salida}")


if __name__ == "__main__":
    main()
