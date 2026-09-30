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


def _buscar_dia(page, dia: date) -> list[dict]:
    page.goto(URL_BUSCADOR, wait_until="domcontentloaded", timeout=90_000)
    page.click(SEL("linkFormularioBusqueda"))
    page.wait_for_selector(SEL("combo1MAQ"), timeout=60_000)

    texto_dia = dia.strftime("%d-%m-%Y")
    page.select_option(SEL("combo1MAQ"), "2")  # Servicios
    page.select_option(SEL("estadoLici"), "PUB")  # Publicada
    page.fill(SEL("textMinFecAnuncioMAQ2"), texto_dia)
    page.fill(SEL("textMaxFecAnuncioMAQ"), texto_dia)
    page.click(SEL("button1"))

    filas: list[dict] = []
    for _ in range(MAX_PAGINAS_POR_DIA):
        try:
            page.wait_for_selector("#myTablaBusquedaCustom tbody tr", timeout=60_000)
        except Exception:
            break  # sin resultados ese día (p. ej. domingo)
        primera = page.locator("#myTablaBusquedaCustom tbody tr").first.inner_text()
        filas.extend(page.evaluate(_JS_FILAS))
        siguiente = page.locator('input[id*=":form1:bt_"][value^="Siguiente"]')
        if siguiente.count() == 0 or not siguiente.first.is_enabled():
            break
        siguiente.first.click()
        # Espera a que cambie el contenido de la tabla (la navegación JSF
        # recarga la página entera, pero sin evento fiable que esperar).
        page.wait_for_function(
            """(prev) => { const tr = document.querySelector('#myTablaBusquedaCustom tbody tr');
                           return tr && tr.innerText !== prev; }""",
            arg=primera,
            timeout=60_000,
        )

    for f in filas:
        f["fecha_publicacion"] = dia.isoformat()
    return filas


def extraer() -> list[dict]:
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

    for r in resultados:
        r["fecha_limite"] = _fecha_es(r.pop("presentacion", ""))
        r["presupuesto"] = _importe_es(r.pop("importe", ""))
        r["moneda"] = "EUR"
    return [r for r in resultados if r.get("enlace") and r.get("titulo")]


def acumular(nuevos: list[dict]) -> list[dict]:
    """Une lo de hoy con lo acumulado de días anteriores (clave: deeplink) y
    poda lo que ya no puede ser una oportunidad abierta."""
    previos: dict[str, dict] = {}
    if ACUMULADO.exists():
        try:
            previos = {r["enlace"]: r for r in json.loads(ACUMULADO.read_text(encoding="utf-8"))}
        except (json.JSONDecodeError, OSError, KeyError):
            previos = {}

    for r in nuevos:
        anterior = previos.get(r["enlace"])
        # Conserva la fecha de publicación más antigua vista (una misma
        # licitación puede reaparecer otro día si se publica un anuncio nuevo
        # sobre ella, p. ej. una rectificación).
        if anterior and anterior.get("fecha_publicacion", "9999") < r["fecha_publicacion"]:
            r["fecha_publicacion"] = anterior["fecha_publicacion"]
        previos[r["enlace"]] = r

    hoy = _hoy_madrid().isoformat()
    corte_sin_plazo = (_hoy_madrid() - timedelta(days=DIAS_CONSERVAR_SIN_PLAZO)).isoformat()
    vigentes = [
        r for r in previos.values()
        if (r.get("fecha_limite") and r["fecha_limite"] >= hoy)
        or (not r.get("fecha_limite") and r.get("fecha_publicacion", "") >= corte_sin_plazo)
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


if __name__ == "__main__":
    main()
