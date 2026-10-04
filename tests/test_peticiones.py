# -*- coding: utf-8 -*-
"""Peticiones con reintentos (scrapers/peticiones.py): un corte puntual no
debe dejar una fuente sin datos ese día."""
import pytest
import requests

import peticiones


class _Respuesta:
    def __init__(self, status):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


def _secuencia(monkeypatch, resultados):
    """requests.request devuelve (o lanza) cada elemento por orden."""
    llamadas = []

    def falso(metodo, url, **kwargs):
        llamadas.append((metodo, url))
        r = resultados[len(llamadas) - 1]
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(requests, "request", falso)
    monkeypatch.setattr(peticiones.time, "sleep", lambda s: None)
    return llamadas


def test_reintenta_tras_un_corte(monkeypatch):
    llamadas = _secuencia(monkeypatch, [requests.ConnectionError("corte"), _Respuesta(200)])
    assert peticiones.pedir("GET", "https://ejemplo.invalid").status_code == 200
    assert len(llamadas) == 2


def test_reintenta_errores_del_servidor(monkeypatch):
    llamadas = _secuencia(monkeypatch, [_Respuesta(503), _Respuesta(502), _Respuesta(200)])
    assert peticiones.pedir("GET", "https://ejemplo.invalid").status_code == 200
    assert len(llamadas) == 3


def test_no_reintenta_errores_de_la_peticion(monkeypatch):
    llamadas = _secuencia(monkeypatch, [_Respuesta(400)])
    with pytest.raises(requests.HTTPError):
        peticiones.pedir("GET", "https://ejemplo.invalid")
    assert len(llamadas) == 1


def test_se_rinde_tras_los_intentos(monkeypatch):
    llamadas = _secuencia(monkeypatch, [requests.Timeout("lento")] * 3)
    with pytest.raises(requests.Timeout):
        peticiones.pedir("GET", "https://ejemplo.invalid", intentos=3)
    assert len(llamadas) == 3
