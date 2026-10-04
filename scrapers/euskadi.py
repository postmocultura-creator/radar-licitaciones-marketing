# -*- coding: utf-8 -*-
"""
Cliente de la API REST pública de contratación de Euskadi (KontratazioA).

Método de acceso: SÍ existe una API REST real y pública, sin autenticación
(confirmado con una llamada en vivo): https://api.euskadi.eus/procurements/contracting-notices
Documentación: https://opendata.euskadi.eus/api-procurements/?api=procurements

Limitación importante verificada contra el esquema real (no en la
documentación de prosa, sino contra el JSON Schema real de la API): esta
API NO expone código CPV en ningún campo. Solo ofrece un "contract-type-id"
genérico (1 Obras, 2 Servicios, 3 Suministros...). Por tanto la capa 1 (CPV)
no aplica a esta fuente: aquí el filtrado real lo hace por completo la capa
2 (texto) de clasificar.py sobre el campo "object" (objeto del contrato).
Para acotar el volumen se pide solo contract-type-id=2 (Servicios), que es
el tipo bajo el que caen los servicios de una agencia de marketing.

También se ha verificado en vivo que "contract-procedure-status-id" no es
fiable como filtro de "en plazo" (se han visto expedientes con estado
"Abierto" y fecha límite de años atrás), así que el estado "en plazo" se
recalcula siempre a partir de deadlineDate en clasificar.py/normalizar.py,
nunca a partir del código de estado del organismo.

Ejecutar directamente para lanzar la extracción y guardar el crudo (desde
la carpeta licitaciones_marketing/):
    python scrapers/euskadi.py
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

import comun
import peticiones

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from nif import limpiar as limpiar_nif, ocultar_en_texto  # noqa: E402

FUENTE = "Euskadi"
BASE_URL = "https://api.euskadi.eus/procurements/contracting-notices"
CONTRACT_TYPE_SERVICIOS = 2
ITEMS_POR_PAGINA = 50
MAX_PAGINAS = 150  # tope defensivo (50*150 = 7500 expedientes de servicios como mucho por ejecución;
# en pruebas reales, 30 días de "Servicios" en todo el sector público vasco ronda las 4-5k entradas)
PETICIONES_POR_SEGUNDO = 1


def extraer() -> list[dict]:
    resultados = []
    pagina = 1
    fecha_desde = config.fecha_corte().isoformat()

    while pagina <= MAX_PAGINAS:
        params = {
            "contract-type-id": CONTRACT_TYPE_SERVICIOS,
            "publication-date.gt": fecha_desde,
            "itemsOfPage": ITEMS_POR_PAGINA,
            "currentPage": pagina,
            "orderBy": "lastPublicationDate",
            "orderType": "DESC",
            "lang": "SPANISH",
        }
        datos = peticiones.pedir("GET", BASE_URL, params=params, headers={"Accept": "application/json"}).json()

        items = datos.get("items", [])
        resultados.extend(items)

        total_paginas = datos.get("totalPages", 1)
        if pagina >= total_paginas or not items:
            break
        pagina += 1
        time.sleep(1 / PETICIONES_POR_SEGUNDO)

    return resultados


# Endpoint separado del de avisos (/contracting-notices): /contracts da los
# contratos YA ADJUDICADOS -confirmado en vivo contra el esquema real, no
# documentado en la página de prosa de la API-. A diferencia del endpoint de
# avisos, este SÍ expone CPV, y da directamente socialReason/CIF (empresa
# adjudicataria), awardDate, awardAmount, contractEndDate (fecha fin ya
# calculada por la propia fuente, no hay que estimarla) y el flag
# minorContract. Sirve tanto para "adjudicaciones" como -filtrando
# minorContract=true- para "contratos menores por vencer".
BASE_URL_CONTRATOS = "https://api.euskadi.eus/procurements/contracts"

_CACHE_ORGANISMO: dict[str, str] = {}
_CACHE_NUTS: dict[str, str | None] = {}


def _resolver_organismo(href: str | None) -> str | None:
    """/procurements/contracts no trae el nombre del organismo inline, solo
    un href al recurso de la autoridad contratante (verificado en vivo
    contra la respuesta real). Se resuelve con una petición aparte, cacheada
    por href: en la práctica hay muchas menos autoridades únicas que
    contratos (96 autoridades para 603 contratos en una muestra real)."""
    if not href:
        return None
    if href in _CACHE_ORGANISMO:
        return _CACHE_ORGANISMO[href]
    # Se comprobó en vivo que, tras las ~100 páginas de extraer() en la
    # misma ejecución, estas peticiones a un endpoint distinto fallaban
    # TODAS de golpe (aislado funcionan 603/603): de ahí los reintentos. Si
    # aun así falla, el contrato sale con el organismo "no publicado".
    nombre = None
    nuts = None
    try:
        autoridad = peticiones.pedir("GET", href, espera=2, timeout=15,
                                     headers={"Accept": "application/json"}).json()
        nombre = autoridad.get("name")
        # Región del organismo ("ES213" = Bizkaia): la misma respuesta la
        # trae, y es el único dato de lugar de un contrato vasco.
        nuts = autoridad.get("codNUTS")
    except (requests.RequestException, ValueError):
        pass
    _CACHE_ORGANISMO[href] = nombre
    _CACHE_NUTS[href] = nuts
    time.sleep(1 / PETICIONES_POR_SEGUNDO)
    return nombre


def extraer_contratos(dias_atras: int) -> list[dict]:
    """Contratos de servicios adjudicados en los últimos `dias_atras` días."""
    resultados = []
    pagina = 1
    fecha_desde = (datetime.now(timezone.utc).date() - timedelta(days=dias_atras)).isoformat()

    while pagina <= MAX_PAGINAS:
        params = {
            "contract-type": CONTRACT_TYPE_SERVICIOS,
            "award-date.gt": fecha_desde,
            "itemsOfPage": ITEMS_POR_PAGINA,
            "currentPage": pagina,
        }
        datos = peticiones.pedir("GET", BASE_URL_CONTRATOS, params=params, headers={"Accept": "application/json"}).json()

        items = datos.get("items", [])
        resultados.extend(items)

        total_paginas = datos.get("totalPages", 1)
        if pagina >= total_paginas or not items:
            break
        pagina += 1
        time.sleep(1 / PETICIONES_POR_SEGUNDO)

    # El organismo (una petición por organismo) solo se resuelve para las que
    # encajan con la taxonomía, en anadir_fichas(): con todas, el paso de
    # Euskadi tardó 16,5 de sus 20 minutos (2026-10-04).
    for item in resultados:
        _sin_datos_personales(item)
    return resultados


def _sin_datos_personales(item: dict) -> None:
    # Euskadi suele enmascarar a las personas físicas (XXXXX155F); por si
    # alguna llega entera, no se guarda (ver nif.limpiar).
    item["CIF"] = limpiar_nif(item.get("CIF"))
    item["socialReason"] = ocultar_en_texto(item.get("socialReason"))


def _completar_contrato(item: dict) -> None:
    """NIF limpio y organismo (nombre y región), que /contracts no trae."""
    _sin_datos_personales(item)
    href = (item.get("_links") or {}).get("contractingAuthority", {}).get("href")
    item["organismo_resuelto"] = _resolver_organismo(href)
    item["organismo_nuts"] = _CACHE_NUTS.get(href)


# ---------------------------------------------------------------------------
# Contratos menores por vencer. Un menor dura hasta un año, así que para ver
# los que vencen en los próximos 3 meses hay que mirar unos 15 meses atrás:
# unos 75.000 menores de servicios (1.500 páginas, 25 minutos a una petición
# por segundo). Hasta octubre de 2026 se pedían todos los contratos de
# servicios de esos 15 meses (85.000, 1.700 páginas), se cortaba en 150
# páginas y solo se veían los adjudicados en los últimos 3-4 meses: justo
# faltaban los que vencen ahora. La API no deja filtrar por fecha de fin
# (probado), pero sí por menor y por mes de adjudicación.
#
# Ahora se pide por meses y se acumula entre noches (ACUMULADO_MENORES), solo
# lo que encaja con la taxonomía (unos cientos): cada noche el mes en curso y
# el anterior (se publican con retraso), y además los meses que no se han
# leído nunca (hasta MESES_NUEVOS_POR_NOCHE) o, si ya están todos, uno en
# rotación. Unas 300 páginas por noche.
# ---------------------------------------------------------------------------
MESES_MENORES = config.DIAS_HISTORIAL_CONTRATO_MENOR // 30  # 15
# Dos: con tres, la primera noche el paso de Euskadi tardó 16,5 de sus 20
# minutos (2026-10-04). Así la ventana se completa en unas 7 noches.
MESES_NUEVOS_POR_NOCHE = 2
ACUMULADO_MENORES = Path(__file__).resolve().parent.parent / "data" / "euskadi_menores_acumulado.json"


def _ventana_menores(hoy) -> list[str]:
    """Meses de adjudicación que interesan, 'AAAAMM', del más reciente al más antiguo."""
    indice = hoy.year * 12 + hoy.month - 1
    return [f"{(indice - i) // 12}{(indice - i) % 12 + 1:02d}" for i in range(MESES_MENORES)]


def _meses_a_leer_menores(hoy, leidos: dict[str, str]) -> list[str]:
    ventana = _ventana_menores(hoy)
    fijos, resto = ventana[:2], ventana[2:]
    nunca = [m for m in resto if m not in leidos]
    if nunca:
        return fijos + nunca[:MESES_NUEVOS_POR_NOCHE]
    return fijos + [resto[hoy.toordinal() % len(resto)]]


def rango_mes_api(periodo: str) -> tuple[str, str]:
    """award-date.gt y award-date.lt para pedir un mes ('AAAAMM') o un año
    ('AAAA') entero. Comprobado el 2026-10-04: .gt excluye su día y .lt
    incluye el suyo. Pedir gt=día 1 dejaba fuera los contratos del día 1 de
    cada mes (27 de 595 en septiembre de 2026)."""
    anio = int(periodo[:4])
    if len(periodo) == 4:
        return f"{anio - 1}-12-31", f"{anio}-12-31"
    mes = int(periodo[4:6])
    primero = datetime(anio, mes, 1).date()
    siguiente = datetime(anio + (mes == 12), mes % 12 + 1, 1).date()
    return (primero - timedelta(days=1)).isoformat(), (siguiente - timedelta(days=1)).isoformat()


def _menores_del_mes(periodo: str) -> list[dict]:
    """Menores de servicios adjudicados ese mes que encajan con la taxonomía
    y tienen fecha de fin, con su organismo resuelto."""
    from clasificar import clasificar_texto  # noqa: E402

    desde, hasta = rango_mes_api(periodo)
    relevantes = []
    pagina, total_paginas = 1, 1
    while pagina <= total_paginas:
        params = {"contract-type": CONTRACT_TYPE_SERVICIOS, "minor-contract": "true",
                  "award-date.gt": desde, "award-date.lt": hasta,
                  "itemsOfPage": ITEMS_POR_PAGINA, "currentPage": pagina}
        datos = peticiones.pedir("GET", BASE_URL_CONTRATOS, params=params, headers={"Accept": "application/json"}).json()
        items = datos.get("items", [])
        for item in items:
            if item.get("contractEndDate") and clasificar_texto(item.get("object") or "")["incluir"]:
                relevantes.append(item)
        total_paginas = datos.get("totalPages", 1)
        if not items:
            break
        pagina += 1
        time.sleep(1 / PETICIONES_POR_SEGUNDO)
    for item in relevantes:
        _completar_contrato(item)
    return relevantes


def actualizar_menores(hoy=None) -> list[dict]:
    """Lee los meses que tocan, los sustituye en el acumulado (un menor
    anulado desaparece al releer su mes) y poda lo vencido o fuera de la
    ventana. Devuelve los contratos vigentes."""
    hoy = hoy or datetime.now(timezone.utc).date()
    try:
        acumulado = json.loads(ACUMULADO_MENORES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        acumulado = {}
    contratos = {str(c["id"]): c for c in acumulado.get("contratos", [])}
    leidos: dict[str, str] = acumulado.get("meses_leidos", {})

    for mes in _meses_a_leer_menores(hoy, leidos):
        try:
            nuevos = _menores_del_mes(mes)
        except (requests.RequestException, ValueError) as exc:
            # Ese mes se queda como estaba y se reintenta otra noche.
            print(f"[euskadi] AVISO: menores de {mes} no disponibles hoy ({exc})", file=sys.stderr)
            continue
        contratos = {k: c for k, c in contratos.items() if _mes(c) != mes}
        contratos.update({str(c["id"]): c for c in nuevos})
        leidos[mes] = hoy.isoformat()
        print(f"[euskadi] menores de {mes}: {len(nuevos)} de agencia con fecha de fin")
        # Se guarda tras cada mes: si el paso se corta por tiempo, lo leído
        # no se pierde y la noche siguiente sigue por donde iba.
        _guardar_menores(contratos, leidos, hoy)
    return _guardar_menores(contratos, leidos, hoy)


def _guardar_menores(contratos: dict[str, dict], leidos: dict[str, str], hoy) -> list[dict]:
    """Poda lo vencido y lo que sale de la ventana, guarda y devuelve los vigentes."""
    ventana = set(_ventana_menores(hoy))
    vigentes = sorted((c for c in contratos.values()
                       if _mes(c) in ventana and (c.get("contractEndDate") or "")[:10] >= hoy.isoformat()),
                      key=lambda c: c["contractEndDate"])
    ACUMULADO_MENORES.parent.mkdir(parents=True, exist_ok=True)
    ACUMULADO_MENORES.write_text(json.dumps(
        {"meses_leidos": {m: f for m, f in leidos.items() if m in ventana}, "contratos": vigentes},
        ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return vigentes


def _mes(contrato: dict) -> str:
    return (contrato.get("awardDate") or "")[:7].replace("-", "")


# ---------------------------------------------------------------------------
# Ficha del expediente en el portal (mainEntityOfPage). La API no da ni los
# documentos ni quién se presentó, pero la página pública de cada expediente
# sí, en HTML normal: pestañas "Ficheros", "Tablón Anuncios" (acuerdos de la
# mesa), "Gestión Ofertas" (empresas licitadoras) y "Resolución". Medido el
# 2026-10-04 con 63 adjudicaciones de servicios desde julio: 34 traen acta
# de la mesa o informe de valoración, 59 algún documento de la adjudicación,
# y todas la lista de licitadoras (208 empresas, ~3 por contrato). Cada
# fichero se descarga con una dirección directa, sin sesión.
#
# Es leer una página, no una API: si Euskadi cambia el diseño, las fichas
# vuelven vacías (la tarjeta sale igual, sin esos bloques) y main() lo avisa.
# ---------------------------------------------------------------------------
URL_DESCARGA_FICHERO = ("https://www.contratacion.euskadi.eus/ac70cPublicidadWar/downloadDokusiREST/"
                        "descargaFicheroPorIdFichero?idFichero={}&R01HNoPortal=true")
MAX_DOCUMENTOS_FICHA = 10
_RE_PESTANA = re.compile(r'<a[^>]+href="#(tabs-\d+)"[^>]*>(.*?)</a>', re.S)
_RE_FILA = re.compile(
    r'<div class="col-xs-12 col-sm-12 col-md-12[^"]*">(?P<titulo>.*?)</div>'
    r'|<div class="col-xs-12 col-sm-4 col-md-4">(?P<etiqueta>.*?)</div>\s*<div class="col-xs-6 col-md-8">(?P<valor>.*?)</div>'
    r'|(?P<fin><div class="row last">)', re.S)
_RE_FICHERO = re.compile(r"descargarFichero\('(\d+)'\)")


def _limpio(fragmento: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragmento or ""))).strip()


def _plano(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").lower()


def _pestanas(pagina: str) -> dict[str, str]:
    """Nombre de la pestaña ("Ficheros", "Resolución"...) -> su HTML."""
    salida = {}
    for ident, nombre in _RE_PESTANA.findall(pagina):
        inicio = pagina.find(f'<div id="{ident}">')
        if inicio == -1:
            continue
        fin = pagina.find('<div id="tabs-', inicio + 10)
        salida[_limpio(nombre)] = pagina[inicio:fin if fin != -1 else len(pagina)]
    return salida


def _tipo_documento(texto: str, de_la_mesa: bool) -> str | None:
    """Mismos tipos que PLACSP (placsp._documentos_adjudicacion) más
    "resolucion". Pliegos, DEUC, memorias y demás preparatorios: None."""
    t = _plano(texto)
    # Documentos preparatorios que a veces se cuelgan en la pestaña de
    # resolución ("Autorizacion gasto_025.pdf"): no dicen nada de la
    # valoración.
    if re.search(r"autorizacion|gasto|aprobacion del expediente|pliego|deuc|memoria|insuficiencia|composicion", t):
        return None
    if re.search(r"valoraci|juicio|puntuaci|baremaci", t):
        return "informe_valoracion"
    if re.search(r"resolucion definitiva|resolucion de adjudicacion|informe de adjudicacion|propuesta de adjudicacion", t):
        return "resolucion"
    if re.search(r"\bacta", t) or de_la_mesa:
        return "acta"
    return None


def leer_ficha(url: str) -> dict:
    """{documentos: [{tipo, nombre, detalle, url}], licitadores: [{nombre,
    nif, pyme, provincia}]} de la página pública de un expediente. Solo el
    nombre, NIF, si es pyme y la provincia de cada licitadora: la página
    publica también teléfonos y correos, que no se guardan."""
    resp = peticiones.pedir("GET", url, timeout=60)
    pestanas = _pestanas(resp.content.decode("utf-8", "replace"))
    documentos: dict[str, dict] = {}
    for nombre_pestana in ("Ficheros", "Tablón Anuncios", "Resolución"):
        seccion, concepto, tipo_fichero = "", "", ""
        filas = list(_RE_FILA.finditer(pestanas.get(nombre_pestana, "")))
        for i, m in enumerate(filas):
            if m.group("titulo") is not None:
                seccion = _limpio(m.group("titulo"))
                continue
            if m.group("fin"):
                concepto = ""
                continue
            etiqueta, valor = _limpio(m.group("etiqueta")), m.group("valor")
            if etiqueta == "Concepto":
                concepto = _limpio(valor)
                continue
            fichero = _RE_FICHERO.search(valor)
            if not fichero or etiqueta not in ("Nombre del fichero", "Fichero"):
                continue
            nombre_fichero = _limpio(valor)
            tipo_fichero = ""
            if i + 1 < len(filas) and filas[i + 1].group("etiqueta") is not None \
                    and _limpio(filas[i + 1].group("etiqueta")) == "Tipo de fichero":
                tipo_fichero = _limpio(filas[i + 1].group("valor"))
            de_la_mesa = nombre_pestana == "Tablón Anuncios" and "mesa" in _plano(seccion)
            if nombre_pestana == "Tablón Anuncios" and not de_la_mesa:
                continue  # avisos a licitadores, consultas...
            tipo = _tipo_documento(" ".join((tipo_fichero, concepto, nombre_fichero)), de_la_mesa)
            # En la pestaña Resolución, un fichero cuyo tipo es "Resolución"
            # cuenta como tal aunque el nombre no lo diga.
            if (nombre_pestana == "Resolución" and tipo is None
                    and _tipo_documento(nombre_fichero, False) is None
                    and "resolucion" in _plano(tipo_fichero)
                    and not re.search(r"autorizacion|gasto", _plano(nombre_fichero))):
                tipo = "resolucion"
            if tipo and fichero.group(1) not in documentos:
                documentos[fichero.group(1)] = {
                    "tipo": tipo,
                    "nombre": nombre_fichero,
                    # Lo que el organismo dice que es ("Apertura sobre B",
                    # "Valoración técnica"); si no, el nombre del fichero.
                    "detalle": concepto or nombre_fichero,
                    "url": URL_DESCARGA_FICHERO.format(fichero.group(1)),
                }

    licitadores: list[dict] = []
    for m in _RE_FILA.finditer(pestanas.get("Gestión Ofertas", "")):
        if m.group("etiqueta") is None:
            continue
        etiqueta, valor = _limpio(m.group("etiqueta")), _limpio(m.group("valor"))
        if etiqueta == "Razón Social":
            licitadores.append({"nombre": ocultar_en_texto(valor), "nif": None, "pyme": None, "provincia": None})
        elif licitadores and etiqueta == "CIF":
            licitadores[-1]["nif"] = limpiar_nif(valor)
        elif licitadores and etiqueta == "Es Pyme":
            licitadores[-1]["pyme"] = {"si": True, "no": False}.get(_plano(valor))
        elif licitadores and etiqueta == "Provincia":
            licitadores[-1]["provincia"] = valor or None

    orden = ["informe_valoracion", "acta", "resolucion"]
    docs = sorted(documentos.values(), key=lambda d: orden.index(d["tipo"]))
    return {"documentos": docs[:MAX_DOCUMENTOS_FICHA], "licitadores": licitadores}


def anadir_fichas(items: list[dict]) -> None:
    """Organismo y ficha solo de las adjudicaciones que el radar va a enseñar
    (las que encajan con la taxonomía, ~10-20 al mes): hacerlo con todas
    serían cientos de peticiones cada noche."""
    from clasificar import clasificar_texto  # noqa: E402

    leidas = vacias = 0
    for item in items:
        if not clasificar_texto(item.get("object") or "")["incluir"]:
            continue
        _completar_contrato(item)
        url = item.get("mainEntityOfPage")
        if not url:
            continue
        try:
            item["ficha"] = leer_ficha(url)
        except requests.RequestException as exc:
            print(f"[euskadi] AVISO: no se pudo leer la ficha {url} ({exc})", file=sys.stderr)
            continue
        leidas += 1
        vacias += not item["ficha"]["documentos"] and not item["ficha"]["licitadores"]
        time.sleep(1 / PETICIONES_POR_SEGUNDO)
    print(f"[euskadi] fichas de expediente leídas: {leidas}")
    if leidas and vacias == leidas:
        # Todas vacías: lo más probable es que haya cambiado el diseño del
        # portal, no que ningún expediente tenga documentos ni licitadoras.
        print("[euskadi] AVISO: ninguna ficha trae documentos ni licitadoras; revisar leer_ficha()", file=sys.stderr)


def guardar_crudo(items: list[dict], prefijo: str = "euskadi") -> Path:
    return comun.guardar_crudo(FUENTE, prefijo, items)


def _guardar_error(prefijo: str, exc: Exception) -> None:
    comun.guardar_error(FUENTE, prefijo, exc)


def main() -> None:
    try:
        items = extraer()
    except requests.RequestException as exc:
        print(f"[euskadi] ERROR al consultar la API de Euskadi: {exc}", file=sys.stderr)
        _guardar_error("euskadi", exc)
        sys.exit(1)

    ruta = guardar_crudo(items, "euskadi")
    print(f"[euskadi] {len(items)} expedientes guardados en {ruta}")

    try:
        adjudicaciones = extraer_contratos(dias_atras=config.DIAS_ANTIGUEDAD_MAXIMA)
    except requests.RequestException as exc:
        print(f"[euskadi] ERROR al consultar adjudicaciones en la API de Euskadi: {exc}", file=sys.stderr)
        _guardar_error("euskadi_adjudicaciones", exc)
        return
    anadir_fichas(adjudicaciones)
    ruta_adj = guardar_crudo(adjudicaciones, "euskadi_adjudicaciones")
    print(f"[euskadi] {len(adjudicaciones)} adjudicaciones guardadas en {ruta_adj}")

    # Ventana distinta a la de arriba a propósito: "adjudicado hace poco"
    # (30 días) no tiene nada que ver con "vence pronto" -un contrato de
    # hace 10 meses con 1 año de duración vence pronto igual-. Ver
    # actualizar_menores().
    try:
        menores = actualizar_menores()
    except requests.RequestException as exc:
        print(f"[euskadi] ERROR al consultar contratos menores en la API de Euskadi: {exc}", file=sys.stderr)
        _guardar_error("euskadi_menores", exc)
        return
    ruta_menores = guardar_crudo(menores, "euskadi_menores")
    print(f"[euskadi] {len(menores)} contratos menores guardados en {ruta_menores}")


if __name__ == "__main__":
    main()
