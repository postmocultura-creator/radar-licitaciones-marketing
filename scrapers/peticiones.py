# -*- coding: utf-8 -*-
"""Peticiones HTTP con reintentos, compartidas por los scrapers.

Un corte puntual de red o un error 5xx de la fuente dejaba esa fuente sin
datos todo el día (pasó el 2026-10-02 con los contratos menores de
Euskadi). Se reintenta lo que suele arreglarse solo esperando (conexión,
tiempo agotado, 429 y 5xx) y no lo que no (400, 404...: la petición está
mal o el recurso no existe).

Las descargas grandes en streaming (los ZIP de PLACSP) no pasan por aquí:
repetir 300 MB a ciegas puede costar más que el límite de tiempo del paso.
"""
from __future__ import annotations

import time

import requests

CABECERAS = {"User-Agent": "licitaciones-marketing-radar/1.0"}


def _reintentable(resp: requests.Response) -> bool:
    return resp.status_code == 429 or resp.status_code >= 500


def pedir(metodo: str, url: str, intentos: int = 3, espera: float = 5, **kwargs) -> requests.Response:
    """requests.request con reintentos y espera creciente (espera, 2·espera...).
    Devuelve la respuesta ya comprobada con raise_for_status()."""
    kwargs.setdefault("timeout", 30)
    kwargs["headers"] = {**CABECERAS, **(kwargs.get("headers") or {})}
    for intento in range(intentos):
        ultimo = intento == intentos - 1
        try:
            resp = requests.request(metodo, url, **kwargs)
        except (requests.ConnectionError, requests.Timeout):
            if ultimo:
                raise
        else:
            if not _reintentable(resp) or ultimo:
                resp.raise_for_status()
                return resp
        time.sleep(espera * (intento + 1))
    raise AssertionError("inalcanzable")  # el último intento devuelve o lanza
