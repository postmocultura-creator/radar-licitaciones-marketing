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

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

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
        resp = requests.get(BASE_URL, params=params, timeout=30, headers={"Accept": "application/json"})
        resp.raise_for_status()
        datos = resp.json()

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


BASE_URL_AUTORIDADES = "https://api.euskadi.eus/procurements/contracting-authorities"
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
    # TODAS de golpe (aislado funcionan 603/603); probablemente una
    # conexión reutilizada en mal estado, no un fallo real del servidor.
    # 3 intentos con backoff lo hace resiliente sin depender de la causa
    # exacta.
    nombre = None
    nuts = None
    for intento in range(3):
        try:
            resp = requests.get(href, timeout=15, headers={"Accept": "application/json"})
            resp.raise_for_status()
            autoridad = resp.json()
            nombre = autoridad.get("name")
            # Región del organismo ("ES213" = Bizkaia): la misma respuesta
            # la trae, y es el único dato de lugar de un contrato vasco.
            nuts = autoridad.get("codNUTS")
            break
        except requests.RequestException:
            if intento < 2:
                time.sleep(2 * (intento + 1))
    _CACHE_ORGANISMO[href] = nombre
    _CACHE_NUTS[href] = nuts
    time.sleep(1 / PETICIONES_POR_SEGUNDO)
    return nombre


def extraer_contratos(dias_atras: int, solo_menores: bool = False) -> list[dict]:
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
        resp = requests.get(BASE_URL_CONTRATOS, params=params, timeout=30, headers={"Accept": "application/json"})
        resp.raise_for_status()
        datos = resp.json()

        items = datos.get("items", [])
        if solo_menores:
            items = [it for it in items if it.get("minorContract")]
        resultados.extend(items)

        total_paginas = datos.get("totalPages", 1)
        if pagina >= total_paginas or not datos.get("items"):
            break
        pagina += 1
        time.sleep(1 / PETICIONES_POR_SEGUNDO)

    for item in resultados:
        href = (item.get("_links") or {}).get("contractingAuthority", {}).get("href")
        item["organismo_resuelto"] = _resolver_organismo(href)
        item["organismo_nuts"] = _CACHE_NUTS.get(href)

    return resultados


def guardar_crudo(items: list[dict], prefijo: str = "euskadi") -> Path:
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
    ruta_adj = guardar_crudo(adjudicaciones, "euskadi_adjudicaciones")
    print(f"[euskadi] {len(adjudicaciones)} adjudicaciones guardadas en {ruta_adj}")

    # Ventana distinta a la de arriba a propósito: "adjudicado hace poco"
    # (30 días) no tiene nada que ver con "vence pronto" -un contrato de
    # hace 10 meses con 1 año de duración vence pronto igual-, así que
    # contratos menores necesita mirar mucho más atrás. Ver
    # config.DIAS_HISTORIAL_CONTRATO_MENOR.
    try:
        menores = extraer_contratos(dias_atras=config.DIAS_HISTORIAL_CONTRATO_MENOR, solo_menores=True)
    except requests.RequestException as exc:
        print(f"[euskadi] ERROR al consultar contratos menores en la API de Euskadi: {exc}", file=sys.stderr)
        _guardar_error("euskadi_menores", exc)
        return
    ruta_menores = guardar_crudo(menores, "euskadi_menores")
    print(f"[euskadi] {len(menores)} contratos menores guardados en {ruta_menores}")


if __name__ == "__main__":
    main()
