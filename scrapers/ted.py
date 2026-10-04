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

import sys
from pathlib import Path

import requests

import comun
import peticiones

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
    # Hora de cierre (BT-131, con el huso del organismo: "14:00:00+02:00") y
    # dirección donde están los pliegos (BT-15). Verificado en vivo el
    # 2026-10-02: 38 de 39 avisos españoles traen la hora y los 39 la
    # dirección, que suele ser la ficha de la licitación en PLACSP o en la
    # plataforma autonómica.
    "deadline-receipt-tender-time-lot",
    "document-url-lot",
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


def consulta_cpv() -> str:
    """OR de los rangos CPV de config.py en sintaxis experta de TED. TED no
    admite rangos numéricos sobre classification-cpv: cada rango se expresa
    como comodín sobre los grupos de 5 cifras que cubre (lo/hi son códigos
    de 8 cifras; dividir por 1000 deja las 5 primeras exactas, sin ceros de
    más que harían que el prefijo no exista)."""
    return " OR ".join(f"classification-cpv={grupo:05d}*"
                       for lo, hi, _ in config.CPV_RANGOS for grupo in range(lo // 1000, hi // 1000 + 1))


# Títulos, organismos y adjudicatarias llegan en todos los idiomas de la UE
# (5,9 MB de la caché para 540 avisos, medido el 2026-10-04). El radar solo
# usa el español o, si no hay, el inglés o el primero que venga.
CAMPOS_MULTILINGUES = ("notice-title", "buyer-name", "winner-name")


def _solo_idiomas_utiles(aviso: dict) -> dict:
    for campo in CAMPOS_MULTILINGUES:
        valores = aviso.get(campo)
        if isinstance(valores, dict) and len(valores) > 1:
            utiles = {k: valores[k] for k in ("spa", "eng") if k in valores}
            aviso[campo] = utiles or dict([next(iter(valores.items()))])
    return aviso


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
    aportar nada que el radar no fuera a mostrar igualmente después. Los
    avisos "result" sí se traen, para otra cosa: ver
    _construir_query_adjudicaciones.)"""
    fecha_desde = config.fecha_corte().strftime("%Y%m%d")
    return f"({consulta_cpv()}) AND publication-date>={fecha_desde} AND form-type=competition"


def _consultar(query: str, campos: list[str], limite_paginas: int, scope: str = "ACTIVE") -> list[dict]:
    resultados: list[dict] = []
    token = None
    pagina = 0

    while pagina < limite_paginas:
        cuerpo = {
            "query": query,
            "fields": campos,
            "limit": 250,
            # "ALL" para el histórico de adjudicaciones: un aviso de años
            # anteriores ya no está "activo".
            "scope": scope,
            "paginationMode": "ITERATION",
        }
        if token:
            cuerpo["iterationNextToken"] = token

        datos = peticiones.pedir("POST", TED_SEARCH_URL, json=cuerpo).json()

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
    return [_solo_idiomas_utiles(n) for n in _consultar(_construir_query(), CAMPOS, limite_paginas)]


CAMPOS_ADJUDICACIONES = [
    "publication-number",
    "notice-title",
    "buyer-name",
    "buyer-country",
    "buyer-country-sub",
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
    return f"({consulta_cpv()}) AND publication-date>={fecha_desde} AND form-type=result"


def extraer_adjudicaciones(limite_paginas: int = 20) -> list[dict]:
    avisos = _consultar(_construir_query_adjudicaciones(), CAMPOS_ADJUDICACIONES, limite_paginas)
    return [_solo_idiomas_utiles(n) for n in avisos]


def guardar_crudo(notices: list[dict], prefijo: str = "ted") -> Path:
    return comun.guardar_crudo(FUENTE, prefijo, notices)


def _guardar_error(prefijo: str, exc: Exception) -> None:
    comun.guardar_error(FUENTE, prefijo, exc)


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
