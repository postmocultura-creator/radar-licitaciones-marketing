# -*- coding: utf-8 -*-
"""
Aviso temprano de licitaciones del Estado leyendo el BUSCADOR WEB de PLACSP
(contrataciondelestado.es), no el feed de sindicación.

Por qué existe (verificado con datos reales el 2026-09-30, ver README,
"Desfase de PLACSP: de dónde sale de verdad"): el feed de sindicación -tanto
el ATOM como el ZIP mensual que usa scrapers/placsp.py- sale de lotes de
exportación que PLACSP genera hacia las 20:15, pero NO todos los días
laborables. En septiembre de 2026, lo publicado del 9 al 11 no llegó al
feed hasta el 14, y lo del 23 al 25 hasta el 28: ese es el "retraso de
5 días". El buscador web lee de la base de datos de la plataforma y muestra
lo publicado en el mismo día (291 expedientes de servicios publicados el
30/09 visibles a las 16:00 de ese día, sin lote exportado todavía).

Qué hace: busca, día a día, los expedientes de tipo "Servicios" en estado
"Publicada" de los últimos DIAS_ATRAS días, y extrae de cada fila del
listado expediente, título, tipo, importe, fecha límite, órgano y el enlace
permanente (deeplink idEvl, el mismo formato que usa el feed).

Una vez a la semana hace además dos búsquedas sin fecha de publicación para
traer las convocatorias de plazo largo (sistemas dinámicos de adquisición,
homologaciones...), que no salen por ninguna otra vía: ver
_buscar_plazo_largo.

El buscador solo cubre días recientes, pero una licitación sigue abierta
semanas: el resultado se ACUMULA en data/placsp_web_acumulado.json
(commiteado por el workflow) y cada registro se conserva hasta que vence su
plazo. Sin esto, lo que solo existe en la web -el buscador incluye también
las plataformas autonómicas agregadas en PLACSP (Cataluña, Madrid...), que
no están en el feed sindicacion_643- desaparecería del radar a los 2 días.

Cuando la misma licitación llega después por el feed, normalizar.py se
queda con la versión del feed (trae CPV) y la fusiona con esta: mismo id
(expediente + título) y mismo título/organismo.

Es la vía más frágil del radar: el buscador es una aplicación JSF con
estado de sesión, sin API. Si PLACSP cambia la página, este scraper falla,
guarda su _error.json y el resto del radar sigue con el feed como antes.

Requiere Playwright con Chromium:
    pip install playwright && python -m playwright install chromium

Ejecutar (desde licitaciones_marketing/):
    python scrapers/placsp_web.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

FUENTE = "Estado"
URL_BUSCADOR = "https://contrataciondelestado.es/wps/portal/plataforma/buscadores/busqueda/"
# Hoy, ayer y anteayer: el workflow corre a las 00:47 hora española, así que
# "ayer" es el día completo que interesa; los otros dos cubren una
# ejecución fallida o saltada sin perder nada.
DIAS_ATRAS = 2
MAX_PAGINAS_POR_DIA = 60  # ~20 filas/página; un día laborable normal son ~15
# Sin plazo publicado (sistemas dinámicos, etc.) se conserva como mucho
# este número de días desde su publicación, igual que la ventana general.
DIAS_CONSERVAR_SIN_PLAZO = 30

BASE = Path(__file__).resolve().parent.parent
ACUMULADO = BASE / "data" / "placsp_web_acumulado.json"
RAW_DIR = BASE / "data" / "raw"

SEL = lambda sufijo: f'[id$=":form1:{sufijo}"]'  # noqa: E731  (ids JSF con prefijo de portlet variable)


def _hoy_madrid() -> date:
    return datetime.now(ZoneInfo("Europe/Madrid")).date()


def _fecha_es(texto: str) -> str | None:
    """'23/10/2026' -> '2026-10-23'."""
    m = re.match(r"\s*(\d{2})/(\d{2})/(\d{4})", texto or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def _importe_es(texto: str) -> str | None:
    """'656.040,53' -> '656040.53' (como string, igual que el feed)."""
    limpio = (texto or "").strip().replace(".", "").replace(",", ".")
    return limpio if re.fullmatch(r"\d+(\.\d+)?", limpio) else None


_JS_FILAS = """
() => Array.from(document.querySelectorAll('#myTablaBusquedaCustom tbody tr')).map(tr => {
  const td = tr.querySelectorAll(':scope > td');
  if (td.length < 6) return null;
  const deeplink = td[0].querySelector('a[href*="idEvl"]');
  const exp = td[0].querySelector('span[id*="textoEnlace"]');
  const divs = td[0].querySelectorAll(':scope > div');
  const tipo = td[1].querySelectorAll('div');
  const organo = td[5].querySelector('a');
  return {
    expediente: exp ? exp.textContent.trim() : null,
    titulo: divs.length > 1 ? divs[divs.length - 1].textContent.trim() : null,
    enlace: deeplink ? deeplink.href : null,
    tipo: tipo[0] ? tipo[0].textContent.trim() : null,
    subtipo: tipo[1] ? tipo[1].textContent.trim() : null,
    estado: td[2].textContent.trim(),
    importe: td[3].textContent.trim(),
    presentacion: td[4].textContent.trim(),
    organismo: td[5].textContent.trim(),
    perfil_url: organo ? organo.href : null,
  };
}).filter(Boolean)
"""


ESPERA_MS = 180_000  # PLACSP puede tardar más de un minuto por página de madrugada
# Esperas sucesivas a que cargue la página siguiente tras pulsar "Siguiente".
# Si la primera se agota y la página sigue siendo la misma, el clic no hizo
# nada (pasa cuando llega antes de que la página termine de inicializarse) y
# se repite. Antes era una sola espera de ESPERA_MS: cada clic perdido
# costaba tres minutos.
ESPERAS_PAGINA_MS = (45_000, 90_000, ESPERA_MS)
# El listado trae alguna fila que no es un expediente (la búsqueda de plazo
# largo dio 155 de 156 y 138 de 139): se da por entera con este margen.
MINIMO_FILAS_SOBRE_TOTAL = 0.97

# Estado de la página de resultados, o null mientras no esté cargada entera.
# Hay que esperar a document.readyState === "complete": la tabla se pinta a
# trozos, y leerla en cuanto aparecía la primera fila devolvía páginas a
# medias (17, 0 y 12 filas en vez de 20, medido el 2026-10-02) sin dar
# ningún error. "marca" identifica la página: su número y su primera fila.
_JS_ESTADO = """
(anterior) => {
  if (!document.body || document.readyState !== 'complete') return null;
  const texto = s => { const e = document.querySelector('[id$=":form1:' + s + '"]'); return e ? e.textContent.trim() : ''; };
  const primera = document.querySelector('#myTablaBusquedaCustom tbody tr');
  if (!primera) return document.body.innerText.includes('No se han encontrado resultados') ? {vacio: true} : null;
  const marca = texto('textfooterInfoNumPagMAQ') + '|' + primera.innerText;
  if (anterior !== null && marca === anterior) return null;
  return {vacio: false, marca: marca, total: texto('textfooterTotalTotalMAQ')};
}
"""


def _buscar(page, etiqueta: str, criterios: dict[str, str]) -> tuple[list[dict], bool]:
    """(filas, completa). Devuelve lo leído aunque falle a mitad: mejor 10
    páginas de 15 que nada (pasó en la primera ejecución en GitHub Actions:
    la página 5 del 29/09 no cargó en 60 s y se perdieron también los otros
    dos días). "completa" dice si se llegó a la última página y las filas
    leídas cuadran con el total que anuncia el buscador."""
    filas: list[dict] = []
    try:
        total = _recorrer_resultados(page, criterios, filas)
    except Exception as exc:  # Playwright lanza varios tipos de timeout/error
        print(f"[placsp_web] AVISO {etiqueta}: búsqueda interrumpida tras {len(filas)} filas ({exc})",
              file=sys.stderr)
        return filas, False
    if total is not None and len(filas) < total * MINIMO_FILAS_SOBRE_TOTAL:
        print(f"[placsp_web] AVISO {etiqueta}: leídas {len(filas)} filas de las {total} que anuncia el buscador",
              file=sys.stderr)
        return filas, False
    return filas, True


def _buscar_dia(page, dia: date) -> list[dict]:
    texto_dia = dia.strftime("%d-%m-%Y")
    filas, _ = _buscar(page, dia.isoformat(), {"textMinFecAnuncioMAQ2": texto_dia, "textMaxFecAnuncioMAQ": texto_dia})
    for f in filas:
        f["fecha_publicacion"] = dia.isoformat()
    return filas


# ---------------------------------------------------------------------------
# Convocatorias de plazo largo: sistemas dinámicos de adquisición,
# homologaciones de proveedores y acuerdos marco que admiten solicitudes
# durante meses o años. Se publicaron hace mucho, así que la búsqueda día a
# día no las ve nunca, y no se actualizan, así que tampoco vienen en el ZIP
# mensual del feed. Comparando con un servicio comercial de alertas, eran la
# mitad de lo que le faltaba al radar entre lo abierto.
#
# Dos búsquedas sin fecha de publicación, medidas el 2026-10-02:
#   - todo lo publicado con más de DIAS_PLAZO_LARGO días de plazo por delante
#     (155 expedientes de servicios, 8 páginas);
#   - los "Establecimiento del Sistema Dinámico de Adquisición" publicados,
#     tengan el plazo que tengan (139, de los que 31 no salían en la primera).
# De los 186, 7 encajan con la taxonomía. Cambian poco: se leen una vez a la
# semana y el acumulado las conserva hasta que vence su plazo.
#
# Como ese plazo puede ser 2030, una convocatoria anulada se quedaría años en
# el radar. Por eso, cuando las dos búsquedas se leen enteras, acumular()
# retira las de plazo largo que el buscador ya no devuelve. Si alguna se
# interrumpe, esa semana no se retira nada.
#
# El listado no da la fecha de publicación: se guardan sin ella.
# ---------------------------------------------------------------------------
DIAS_PLAZO_LARGO = 60
DIA_SEMANA_PLAZO_LARGO = 0  # lunes
SISTEMA_DINAMICO = "2"  # "Establecimiento del Sistema Dinámico de Adquisición"


def _toca_plazo_largo() -> bool:
    """Los lunes, y siempre que el acumulado todavía no tenga ninguna (la
    primera ejecución tras añadir esta búsqueda, o si se borra el fichero)."""
    if _hoy_madrid().weekday() == DIA_SEMANA_PLAZO_LARGO:
        return True
    try:
        return not any(r.get("plazo_largo") for r in json.loads(ACUMULADO.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return True


def _buscar_plazo_largo(page) -> tuple[list[dict], bool]:
    """(filas, completa): completa solo si las dos búsquedas llegaron a su
    última página y devolvieron algo."""
    desde = (_hoy_madrid() + timedelta(days=DIAS_PLAZO_LARGO)).strftime("%d-%m-%Y")
    por_enlace: dict[str, dict] = {}
    completa = True
    for etiqueta, criterios in (
        ("plazo largo", {"textMinFecLimite": desde}),
        ("sistemas dinámicos", {"tipoSistemaContratacion": SISTEMA_DINAMICO}),
    ):
        filas, entera = _buscar(page, etiqueta, criterios)
        print(f"[placsp_web] {etiqueta}: {len(filas)} expedientes de servicios publicados")
        completa = completa and entera and bool(filas)
        for f in filas:
            if f.get("enlace"):
                por_enlace.setdefault(f["enlace"], f)
    for f in por_enlace.values():
        f["fecha_publicacion"] = None
        f["plazo_largo"] = True
    return list(por_enlace.values()), completa


CAMPOS_DESPLEGABLES = {"tipoSistemaContratacion"}


def _recorrer_resultados(page, criterios: dict[str, str], filas: list[dict]) -> int | None:
    """Rellena el formulario, recorre todas las páginas de resultados
    añadiendo sus filas a `filas` y devuelve el total que anuncia el
    buscador (None si no lo muestra)."""
    page.goto(URL_BUSCADOR, wait_until="domcontentloaded", timeout=ESPERA_MS)
    page.click(SEL("linkFormularioBusqueda"))
    page.wait_for_selector(SEL("combo1MAQ"), timeout=ESPERA_MS)

    page.select_option(SEL("combo1MAQ"), "2")  # Servicios
    page.select_option(SEL("estadoLici"), "PUB")  # Publicada
    for campo, valor in criterios.items():
        if campo in CAMPOS_DESPLEGABLES:
            page.select_option(SEL(campo), valor)
        else:
            page.fill(SEL(campo), valor)
    page.click(SEL("button1"))

    # Un día sin resultados (domingo, o el día en curso de madrugada) muestra
    # "No se han encontrado resultados" y no pinta la tabla. Hay que esperar a
    # una de las dos cosas: antes, agotar la espera se tomaba por "no hay
    # resultados" y un día lento se quedaba en 0 sin avisar (pasó el
    # 2026-10-01 por la tarde: 0 filas donde por la mañana había 78). Si no
    # llega ninguna, es un fallo y salta como tal. (document.body es null
    # mientras la página navega tras pulsar "Buscar": _JS_ESTADO lo
    # comprueba; sin eso la espera reventaba con un TypeError y el día se
    # quedaba en 0, como pasó en la primera ejecución en Actions.)
    estado = page.wait_for_function(_JS_ESTADO, arg=None, timeout=ESPERA_MS).json_value()
    if estado["vacio"]:
        return 0
    total = int(estado["total"]) if estado["total"].isdigit() else None

    boton_siguiente = 'input[id*=":form1:bt_"][value^="Siguiente"]'
    for _ in range(MAX_PAGINAS_POR_DIA):
        filas.extend(page.evaluate(_JS_FILAS))
        siguiente = page.locator(boton_siguiente)
        if siguiente.count() == 0 or not siguiente.first.is_enabled():
            return total
        # La navegación JSF recarga la página entera, sin evento fiable que
        # esperar: se espera a que la página cargada sea otra (_JS_ESTADO).
        marca = estado["marca"]
        siguiente.first.click()
        for intento, espera in enumerate(ESPERAS_PAGINA_MS):
            try:
                estado = page.wait_for_function(_JS_ESTADO, arg=marca, timeout=espera).json_value()
                break
            except Exception:
                if intento == len(ESPERAS_PAGINA_MS) - 1:
                    raise
                # Solo se repite el clic si seguimos en la misma página ya
                # cargada. Si está navegando o la nueva está a medio pintar,
                # otro clic se saltaría una página: se sigue esperando.
                try:
                    misma = page.evaluate(_JS_ESTADO, None)
                except Exception:
                    misma = None
                if misma and misma.get("marca") == marca:
                    page.locator(boton_siguiente).first.click()
    return total


def _limpiar_filas(resultados: list[dict]) -> list[dict]:
    for r in resultados:
        r["fecha_limite"] = _fecha_es(r.pop("presentacion", ""))
        r["presupuesto"] = _importe_es(r.pop("importe", ""))
        r["moneda"] = "EUR"
    return [r for r in resultados if r.get("enlace") and r.get("titulo")]


def extraer() -> list[dict]:
    """Lo publicado hoy, ayer y anteayer."""
    from playwright.sync_api import sync_playwright

    hoy = _hoy_madrid()
    resultados: list[dict] = []
    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(locale="es-ES")
        for atras in range(DIAS_ATRAS, -1, -1):
            dia = hoy - timedelta(days=atras)
            filas = _buscar_dia(page, dia)
            print(f"[placsp_web] {dia.isoformat()}: {len(filas)} expedientes de servicios publicados")
            resultados.extend(filas)
        navegador.close()
    return _limpiar_filas(resultados)


def extraer_plazo_largo() -> tuple[list[dict], bool]:
    """(convocatorias de plazo largo, completa): ver _buscar_plazo_largo."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        page = navegador.new_page(locale="es-ES")
        filas, completa = _buscar_plazo_largo(page)
        navegador.close()
    return _limpiar_filas(filas), completa


def acumular(nuevos: list[dict], plazo_largo_completo: bool = False) -> list[dict]:
    """Une lo de hoy con lo acumulado de días anteriores (clave: deeplink) y
    poda lo que ya no puede ser una oportunidad abierta.

    Con plazo_largo_completo (la pasada semanal se leyó entera), retira
    además las convocatorias de plazo largo que el buscador ya no devuelve
    aunque su plazo siga lejos: se anularon o se cerraron. Las que salen de
    la búsqueda solo porque ya les quedan menos de DIAS_PLAZO_LARGO días
    siguen abiertas y se conservan hasta que venzan."""
    previos: dict[str, dict] = {}
    if ACUMULADO.exists():
        try:
            previos = {r["enlace"]: r for r in json.loads(ACUMULADO.read_text(encoding="utf-8"))}
        except (json.JSONDecodeError, OSError, KeyError):
            previos = {}

    if plazo_largo_completo:
        devueltas = {r["enlace"] for r in nuevos if r.get("plazo_largo")}
        lejos = (_hoy_madrid() + timedelta(days=DIAS_PLAZO_LARGO)).isoformat()
        retiradas = [
            enlace for enlace, r in previos.items()
            if r.get("plazo_largo") and enlace not in devueltas and (r.get("fecha_limite") or "") > lejos
        ]
        for enlace in retiradas:
            del previos[enlace]
        if retiradas:
            print(f"[placsp_web] {len(retiradas)} convocatorias de plazo largo retiradas: el buscador ya no las devuelve")

    for r in nuevos:
        anterior = previos.get(r["enlace"])
        # Conserva la fecha de publicación más antigua vista (una misma
        # licitación puede reaparecer otro día si se publica un anuncio nuevo
        # sobre ella, p. ej. una rectificación). Las de plazo largo llegan
        # sin fecha: si ya se conocía por la búsqueda diaria, se mantiene.
        if anterior:
            fechas = [f for f in (anterior.get("fecha_publicacion"), r.get("fecha_publicacion")) if f]
            r["fecha_publicacion"] = min(fechas) if fechas else None
            if anterior.get("plazo_largo"):
                r["plazo_largo"] = True
        previos[r["enlace"]] = r

    hoy = _hoy_madrid().isoformat()
    corte_sin_plazo = (_hoy_madrid() - timedelta(days=DIAS_CONSERVAR_SIN_PLAZO)).isoformat()
    vigentes = [
        r for r in previos.values()
        if (r.get("fecha_limite") and r["fecha_limite"] >= hoy)
        or (not r.get("fecha_limite") and (r.get("fecha_publicacion") or "") >= corte_sin_plazo)
    ]
    ACUMULADO.parent.mkdir(parents=True, exist_ok=True)
    ACUMULADO.write_text(json.dumps(vigentes, ensure_ascii=False, indent=2), encoding="utf-8")
    return vigentes


def _guardar(nombre: str, payload: dict) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ruta = RAW_DIR / nombre
    ruta.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


def main() -> None:
    ahora = datetime.now(timezone.utc)
    sello = ahora.strftime("%Y%m%dT%H%M%SZ")
    try:
        nuevos = extraer()
    except Exception as exc:  # Playwright lanza varios tipos; cualquiera invalida la pasada
        print(f"[placsp_web] ERROR al leer el buscador web de PLACSP: {exc}", file=sys.stderr)
        _guardar(f"placsp_web_{sello}_error.json", {"fuente": FUENTE, "timestamp": ahora.isoformat(), "error": str(exc)})
        sys.exit(1)

    vigentes = acumular(nuevos)
    ruta = _guardar(
        f"placsp_web_{sello}.json",
        {"fuente": FUENTE, "timestamp": ahora.isoformat(), "num_resultados": len(vigentes), "resultados": vigentes},
    )
    print(f"[placsp_web] {len(nuevos)} leídos hoy, {len(vigentes)} vigentes acumulados -> {ruta}")

    # La pasada de plazo largo va después y por separado: lo diario ya está
    # guardado, así que si esta falla o el workflow la corta por tiempo no se
    # pierde nada (se reintenta al día siguiente mientras el acumulado no
    # tenga ninguna). Sobrescribe el mismo crudo con el acumulado ampliado.
    if not _toca_plazo_largo():
        return
    try:
        largas, completa = extraer_plazo_largo()
    except Exception as exc:
        print(f"[placsp_web] AVISO: sin pasada de plazo largo hoy ({exc})", file=sys.stderr)
        return
    vigentes = acumular(largas, completa)
    _guardar(
        f"placsp_web_{sello}.json",
        {"fuente": FUENTE, "timestamp": ahora.isoformat(), "num_resultados": len(vigentes), "resultados": vigentes},
    )
    print(f"[placsp_web] plazo largo: {len(largas)} leídas ({'entera' if completa else 'incompleta'}), {len(vigentes)} vigentes acumulados")


if __name__ == "__main__":
    main()
