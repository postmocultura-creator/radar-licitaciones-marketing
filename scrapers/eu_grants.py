# -*- coding: utf-8 -*-
"""
Cliente de la API de búsqueda "SEDIA" del EU Funding & Tenders Portal, para
"calls for proposals" (subvenciones, no compras públicas).

Método de acceso: API REST pública y documentada oficialmente por la propia
Comisión (https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/support/apis),
endpoint https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA.
"apiKey=SEDIA" es el identificador público documentado en esa página, no un
secreto por usuario.

IMPORTANTE (verificado en vivo interceptando la petición real del portal, no
de la documentación de prosa, que no bastó): el body NO se manda como JSON
plano -eso lo comprobé primero y el servidor lo ignora silenciosamente y
devuelve millones de resultados sin filtrar-. Se manda como multipart/form-data
con 4 campos (`query`, `languages`, `displayFields`, `sort`), cada uno un
blob JSON. Sin esto no hay manera de que el filtro de type/status funcione.

Caso de uso (a petición explícita de la agencia, no es "ser beneficiaria de
la subvención"): detectar convocatorias cuyo proyecto financiado
previsiblemente va a necesitar contratar comunicación/difusión/marketing
como parte de sus actividades, para ofrecerse como proveedora a quien gane
la subvención. Por eso se filtra por texto (capa 2 en inglés,
config.CATEGORIAS_CALLS_UE) sobre título + texto de "Expected
Outcome"/objetivo, no por si la propia agencia pudiera solicitarla.

El listado (displayFields) NO incluye la descripción larga de cada
convocatoria -se comprobó pidiéndola explícitamente y no vuelve-: solo con
el título el matching por texto tiene muy poco recall (se probó: 4/100
títulos reales encajaban con la taxonomía). Hace falta una petición
adicional por convocatoria al mismo endpoint, pidiendo el identificador
exacto entre comillas (`text="<identifier>"`), que sí devuelve
`descriptionByte` (pese al nombre, es el HTML completo de "Expected
Outcome", no un tamaño en bytes) y `destinationDetails`/`destinationDescription`.
Son ~500-600 peticiones adicionales; a 1 por segundo, por respeto a la
fuente, eran 15 de los 37 minutos de la actualización diaria (medido el
2026-10-02). El texto de una convocatoria casi nunca cambia, así que los
detalles se guardan entre ejecuciones (CACHE_DETALLE) y cada noche solo se
piden los de las convocatorias nuevas y un séptimo de las ya conocidas, en
rotación.

Ejecutar directamente para lanzar la extracción y guardar el crudo (desde
la carpeta licitaciones_marketing/):
    python scrapers/eu_grants.py
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import zlib
from datetime import date, datetime, timezone
from pathlib import Path

import requests

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

FUENTE = "UE-subvenciones"
SEARCH_URL = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
API_KEY = "SEDIA"

# type: 1/2/8 son variantes de "calls for proposals" (subvenciones); type=0
# son "calls for tenders" (compras públicas de las propias instituciones,
# ya cubiertas por TED, no interesa duplicar). status: Forthcoming=31094501,
# Open=31094502 (verificado contra la página oficial de documentación de
# la API, sección 4).
QUERY_BASE = {
    "bool": {
        "must": [
            {"terms": {"type": ["1", "2", "8"]}},
            {"terms": {"status": ["31094501", "31094502"]}},
            {"terms": {"DATASOURCE": ["SEDIA"]}},
            {"terms": {"language": ["en"]}},
        ]
    }
}
LANGUAGES = ["en"]
DISPLAY_FIELDS = [
    "caName", "callccm2Id", "deadlineDate", "deadlineModel",
    "frameworkProgramme", "identifier", "projectAcronym", "reference",
    "startDate", "status", "title", "type", "typesOfAction",
]
SORT = {"order": "DESC", "field": "relevance"}
PAGE_SIZE = 100  # confirmado en vivo: el servidor limita a 100 aunque se pida más
PETICIONES_POR_SEGUNDO = 1

# Detalles ya pedidos, por identificador de convocatoria. No se versiona
# (data/cache/ está en .gitignore): en GitHub Actions lo conserva entre
# ejecuciones el paso actions/cache del workflow; si falta, se piden todos
# otra vez y ya está. Cada convocatoria se vuelve a pedir un día de cada
# DIAS_REFRESCO_DETALLE, repartidas por su identificador para que no toquen
# todas la misma noche, por si la Comisión corrige el texto.
CACHE_DETALLE = Path(__file__).resolve().parent.parent / "data" / "cache" / "eu_grants_detalle.json"
DIAS_REFRESCO_DETALLE = 7


def _leer_cache_detalle() -> dict[str, dict]:
    try:
        cache = json.loads(CACHE_DETALLE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return cache if isinstance(cache, dict) else {}


def _toca_refrescar(identifier: str, hoy: date) -> bool:
    return (hoy.toordinal() + zlib.crc32(identifier.encode("utf-8"))) % DIAS_REFRESCO_DETALLE == 0


def _peticion(text_param: str, query: dict | None, display_fields: list[str] | None,
              page_size: int | None = None, page_number: int | None = None) -> dict:
    params = {"apiKey": API_KEY, "text": text_param}
    if page_size is not None:
        params["pageSize"] = page_size
    if page_number is not None:
        params["pageNumber"] = page_number

    files = {"languages": (None, json.dumps(LANGUAGES), "application/json")}
    if query is not None:
        files["query"] = (None, json.dumps(query), "application/json")
    if display_fields is not None:
        files["displayFields"] = (None, json.dumps(display_fields), "application/json")
        files["sort"] = (None, json.dumps(SORT), "application/json")

    # Reintentos: un timeout puntual de la API de SEDIA (pasó de verdad en
    # producción, "Read timed out" a los 30s) tumbaba toda la extracción -y
    # con ella, toda la pestaña "Calls for proposals UE" ese día, porque sin
    # crudo nuevo clasificar.py se limita a omitir la fuente esa pasada-.
    # Mismo patrón que los reintentos de traducción en normalizar.py.
    ultimo_error: requests.RequestException | None = None
    for intento in range(3):
        try:
            resp = requests.post(SEARCH_URL, params=params, files=files, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            ultimo_error = exc
            if intento < 2:
                time.sleep(5 * (intento + 1))
    raise ultimo_error


def extraer_listado() -> list[dict]:
    """Página 1 a 1 (PAGE_SIZE=100, tope real del servidor) el listado base
    de calls for proposals abiertas/próximas."""
    resultados = []
    pagina = 1
    while True:
        datos = _peticion("***", QUERY_BASE, DISPLAY_FIELDS, page_size=PAGE_SIZE, page_number=pagina)
        items = datos.get("results", [])
        if not items:
            break
        resultados.extend(items)
        total = datos.get("totalResults", 0)
        if len(resultados) >= total:
            break
        pagina += 1
        time.sleep(1 / PETICIONES_POR_SEGUNDO)
    return resultados


def _texto_plano(texto_html: str) -> str:
    """El texto de 'Expected Outcome' viene en HTML; se quita el marcado y
    se decodifican entidades (&amp; -> &) para poder buscar palabras clave
    sin que <p>/<li> corten una frase ni queden entidades literales en el
    resumen mostrado en el dashboard."""
    sin_tags = re.sub(r"<[^>]+>", " ", texto_html or "")
    return re.sub(r"\s+", " ", html.unescape(sin_tags)).strip()


def extraer_detalle(identifier: str) -> dict:
    """Segunda petición por convocatoria: da el texto largo que el listado
    no incluye (ver docstring del módulo)."""
    texto = f'"{identifier}"'
    datos = _peticion(texto, None, None)
    resultados = datos.get("results", [])
    if not resultados:
        return {}
    md = resultados[0].get("metadata", {})

    def _primero(campo):
        valor = md.get(campo)
        return valor[0] if isinstance(valor, list) and valor else None

    return {
        "descripcion": _texto_plano(_primero("descriptionByte") or ""),
        "destino_descripcion": _primero("destinationDescription") or "",
        "destino_detalle": _texto_plano(_primero("destinationDetails") or ""),
        "url_detalle": _primero("url"),
    }


def extraer() -> list[dict]:
    listado = extraer_listado()
    cache = _leer_cache_detalle()
    cache_nuevo: dict[str, dict] = {}
    hoy = date.today()
    pedidos = 0
    resultados = []
    for item in listado:
        md = item.get("metadata", {})

        def _primero(campo):
            valor = md.get(campo)
            return valor[0] if isinstance(valor, list) and valor else None

        identifier = _primero("identifier")
        registro = {
            "reference": item.get("reference"),
            "identifier": identifier,
            "titulo": _primero("title"),
            "deadlineDate": _primero("deadlineDate"),
            "startDate": _primero("startDate"),
            "frameworkProgramme": _primero("frameworkProgramme"),
            "status": _primero("status"),
            "type": _primero("type"),
            "typesOfAction": _primero("typesOfAction"),
            "callccm2Id": _primero("callccm2Id"),
            "url": item.get("url"),
        }

        if identifier:
            # Varias entradas del listado comparten identificador (una por
            # tema de la convocatoria): el detalle se pide una sola vez.
            detalle = cache_nuevo.get(identifier)
            if detalle is None:
                detalle = cache.get(identifier)
                if not detalle or _toca_refrescar(identifier, hoy):
                    try:
                        pedido = extraer_detalle(identifier)
                    except requests.RequestException:
                        pedido = {}
                    pedidos += 1
                    time.sleep(1 / PETICIONES_POR_SEGUNDO)
                    # Si la petición falla o vuelve vacía, vale lo que hubiera.
                    detalle = pedido or detalle or {}
                if detalle:
                    cache_nuevo[identifier] = detalle
            registro.update(detalle)

        resultados.append(registro)

    # Solo se guardan las convocatorias que siguen en el listado: las que se
    # cierran salen de la caché solas.
    CACHE_DETALLE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_DETALLE.write_text(json.dumps(cache_nuevo, ensure_ascii=False), encoding="utf-8")
    print(f"[eu_grants] detalles de {len(cache_nuevo)} convocatorias: {pedidos} pedidos a la API, el resto de la caché")
    return resultados


def guardar_crudo(items: list[dict]) -> Path:
    ahora = datetime.now(timezone.utc)
    raw_dir = Path(__file__).resolve().parent.parent / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    nombre = f"eu_grants_{ahora.strftime('%Y%m%dT%H%M%SZ')}.json"
    ruta = raw_dir / nombre

    payload = {
        "fuente": FUENTE,
        "timestamp": ahora.isoformat(),
        "num_resultados": len(items),
        "resultados": items,
    }
    ruta.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


def main() -> None:
    try:
        items = extraer()
    except requests.RequestException as exc:
        print(f"[eu_grants] ERROR al consultar la API SEDIA: {exc}", file=sys.stderr)
        ahora = datetime.now(timezone.utc)
        raw_dir = Path(__file__).resolve().parent.parent / "data" / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        ruta = raw_dir / f"eu_grants_{ahora.strftime('%Y%m%dT%H%M%SZ')}_error.json"
        ruta.write_text(
            json.dumps({"fuente": FUENTE, "timestamp": ahora.isoformat(), "error": str(exc)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        sys.exit(1)

    ruta = guardar_crudo(items)
    print(f"[eu_grants] {len(items)} calls for proposals guardadas en {ruta}")


if __name__ == "__main__":
    main()
