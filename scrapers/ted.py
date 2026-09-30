# -*- coding: utf-8 -*-
"""
Cliente de la API pública de TED (Tenders Electronic Daily, Unión Europea).

Método de acceso: API REST v3 oficial (https://api.ted.europa.eu/v3/notices/search),
POST, sin autenticación (confirmado en la documentación oficial: "The Search API
does not require a key"). Es la fuente más fiable de las tres porque devuelve
JSON estructurado y admite filtrar por classification-cpv directamente en el
servidor.

Ejecutar directamente para lanzar la extracción y guardar el crudo (desde
la carpeta licitaciones_marketing/):
    python scrapers/ted.py
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import requests

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402

TED_SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"
FUENTE = "UE"

CAMPOS = [
    "publication-number",
    "notice-title",
    "buyer-name",
    "buyer-country",
    # Región NUTS del organismo (p. ej. "ES213" = Bizkaia). Sirve para
    # asignar a "Euskadi" o "Estado" las licitaciones españolas que solo
    # salen en TED (Metro Bilbao, Diputación Foral de Gipuzkoa...) en la
    # pestaña "Publicadas recientemente".
    "buyer-country-sub",
    "classification-cpv",
    "publication-date",
    "deadline-date-lot",
    "deadline-receipt-tender-date-lot",
    "estimated-value-proc",
    "estimated-value-cur-proc",
]
# Se piden los dos campos de fecha límite porque se comprobó con datos
# reales que "deadline-date-lot" viene vacío en muchísimos anuncios
# (~75% de los "competition" reales de una muestra) mientras que
# "deadline-receipt-tender-date-lot" -el campo eForms estándar, BT-131- sí
# está poblado en esos mismos anuncios. Probablemente sea una diferencia
# entre notificaciones en formato TED2 legado y eForms nativo. normalizar.py
# usa el que venga relleno, priorizando el de eForms.


def _construir_query() -> str:
    """Construye la query de sintaxis experta de TED: un OR de todos los
    rangos CPV amplios de config.py, acotado a notificaciones recientes Y
    a anuncios de licitación activos (form-type=competition).

    Sin el filtro de form-type, TED devuelve mezclados en el mismo
    resultado los anuncios de licitación abierta (form-type "competition")
    con anuncios de ADJUDICACIÓN ("result") y de MODIFICACIÓN de un
    contrato ya en marcha ("cont-modif") — verificado con un caso real: un
    contrato de servicio "durante los años 2024 y 2025" aparecía como
    "publicado" hoy porque TED había publicado una modificación reciente
    sobre un contrato firmado hace tiempo, sin plazo de presentación
    (porque ya no lo hay: no es una oportunidad para pujar). Esos avisos
    no son oportunidades de negocio nuevas y no deben aparecer aquí.

    (Se probó también traer avisos "result" para detectar contratos a
    punto de vencer y anticipar relicitaciones; se descartó a petición del
    usuario: en cuanto la relicitación se publica de verdad, ya aparece
    aquí por su cuenta — la señal de "vence pronto" solo añadía ruido sin
    aportar nada que el radar no fuera a mostrar igualmente después.)"""
    fecha_desde = config.fecha_corte().strftime("%Y%m%d")
    partes_cpv = []
    for lo, hi, _ in config.CPV_RANGOS:
        # TED no soporta rangos numéricos directos sobre classification-cpv;
        # se expresa como wildcard sobre el prefijo de división/grupo cuando
        # el rango cubre una división/grupo completo de 3 dígitos, y si no,
        # se listan los códigos de grupo (6 dígitos) que caen en el rango.
        for grupo in range(lo // 1000, hi // 1000 + 1):
            # lo/hi son códigos CPV de 8 dígitos: dividir por 1000 deja los
            # primeros 5 dígitos exactos (nunca hay que rellenar con un cero
            # de más, o el prefijo deja de existir en la nomenclatura CPV).
            partes_cpv.append(f'classification-cpv={grupo:05d}*')
    cpv_query = " OR ".join(partes_cpv)
    return f"({cpv_query}) AND publication-date>={fecha_desde} AND form-type=competition"


def _consultar(query: str, campos: list[str], limite_paginas: int) -> list[dict]:
    resultados: list[dict] = []
    token = None
    pagina = 0

    while pagina < limite_paginas:
        cuerpo = {
            "query": query,
            "fields": campos,
            "limit": 250,
            "scope": "ACTIVE",
            "paginationMode": "ITERATION",
        }
        if token:
            cuerpo["iterationNextToken"] = token

        resp = requests.post(TED_SEARCH_URL, json=cuerpo, timeout=30)
        resp.raise_for_status()
        datos = resp.json()

        notices = datos.get("notices", [])
        resultados.extend(notices)

        token = datos.get("iterationNextToken")
        pagina += 1
        if not token or not notices:
            break

    return resultados


def extraer(limite_paginas: int = 20) -> list[dict]:
    """Consulta la API de TED con paginación por iteración. Devuelve una
    lista de notices en formato semi-crudo (ya con nombres de campo TED)."""
    return _consultar(_construir_query(), CAMPOS, limite_paginas)


CAMPOS_ADJUDICACIONES = [
    "publication-number",
    "notice-title",
    "buyer-name",
    "buyer-country",
    "classification-cpv",
    "publication-date",
    "winner-name",
    "winner-country",
    "contract-duration-end-date-lot",
    "result-value-lot",
    "result-value-cur-lot",
]


def _construir_query_adjudicaciones() -> str:
    """Misma acotación por CPV y ventana temporal que las licitaciones
    abiertas, pero sobre avisos de RESULTADO (form-type=result) en vez de
    de licitación (form-type=competition). Confirmado con la API real que
    estos avisos traen winner-name y contract-duration-end-date-lot —
    exactamente lo que hace falta para "adjudicaciones" y para estimar
    cuándo vence un contrato ya adjudicado. Se había descartado antes usar
    avisos "result" para anticipar relicitaciones (ver docstring de
    _construir_query): ese caso de uso concreto se quitó porque era
    redundante. Este es distinto -mostrar quién gana, no adivinar cuándo
    relicita- así que no aplica la misma objeción."""
    fecha_desde = config.fecha_corte().strftime("%Y%m%d")
    partes_cpv = []
    for lo, hi, _ in config.CPV_RANGOS:
        for grupo in range(lo // 1000, hi // 1000 + 1):
            partes_cpv.append(f'classification-cpv={grupo:05d}*')
    cpv_query = " OR ".join(partes_cpv)
    return f"({cpv_query}) AND publication-date>={fecha_desde} AND form-type=result"


def extraer_adjudicaciones(limite_paginas: int = 20) -> list[dict]:
    return _consultar(_construir_query_adjudicaciones(), CAMPOS_ADJUDICACIONES, limite_paginas)


def guardar_crudo(notices: list[dict], prefijo: str = "ted") -> Path:
    ahora = datetime.now(timezone.utc)
    raw_dir = Path(__file__).resolve().parent.parent / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    nombre = f"{prefijo}_{ahora.strftime('%Y%m%dT%H%M%SZ')}.json"
    ruta = raw_dir / nombre

    payload = {
        "fuente": FUENTE,
        "timestamp": ahora.isoformat(),
        "num_resultados": len(notices),
        "resultados": notices,
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
        notices = extraer()
    except requests.RequestException as exc:
        print(f"[ted] ERROR al consultar la API de TED: {exc}", file=sys.stderr)
        # Guarda un crudo vacío con el error para trazabilidad, sin tumbar
        # la ejecución de las otras fuentes.
        _guardar_error("ted", exc)
        sys.exit(1)

    ruta = guardar_crudo(notices, "ted")
    print(f"[ted] {len(notices)} notificaciones guardadas en {ruta}")

    try:
        adjudicaciones = extraer_adjudicaciones()
    except requests.RequestException as exc:
        print(f"[ted] ERROR al consultar adjudicaciones en la API de TED: {exc}", file=sys.stderr)
        _guardar_error("ted_adjudicaciones", exc)
        return

    ruta_adj = guardar_crudo(adjudicaciones, "ted_adjudicaciones")
    print(f"[ted] {len(adjudicaciones)} adjudicaciones guardadas en {ruta_adj}")


if __name__ == "__main__":
    main()
