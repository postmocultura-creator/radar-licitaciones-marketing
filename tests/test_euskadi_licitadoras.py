# -*- coding: utf-8 -*-
"""Licitadoras acumuladas de Euskadi e índice de éxito por empresa. NIF y
expedientes inventados."""
import json

import euskadi

URL = "https://www.contratacion.euskadi.eus/webkpe00-kpeperfi/es/contenidos/anuncio_contratacion/{}/es_doc/index.html"


def test_clave_expediente_igual_en_api_y_en_historico():
    assert euskadi.clave_expediente(URL.format("expjaso100001")) == "expjaso100001"
    assert euskadi.clave_expediente(URL.format("expjaso100001")[:-1]) == "expjaso100001"  # ".htm"
    assert euskadi.clave_expediente(None) is None


def test_acumula_solo_lo_que_trae_ficha():
    adjudicaciones = [
        {"mainEntityOfPage": URL.format("expjaso100001"), "awardDate": "2026-09-15T00:00:00Z", "CIF": "B10000001",
         "ficha": {"licitadores": [{"nombre": "Una SL", "nif": "B10000001", "pyme": True},
                                   {"nombre": "Otra SA", "nif": "A10000002", "pyme": False}], "documentos": []}},
        {"mainEntityOfPage": URL.format("expjaso100002"), "CIF": "B10000001"},  # sin ficha: no se guarda
    ]
    acumulado = {}
    assert euskadi.acumular_licitadoras(adjudicaciones, acumulado) == 1
    assert acumulado == {"expjaso100001": {
        "fecha": "2026-09-15", "ganadoras": ["B10000001"],
        "licitadoras": [{"nif": "B10000001", "pyme": True}, {"nif": "A10000002", "pyme": False}]}}


def test_indice_exito_sin_personas_fisicas():
    acumulado = {
        "expjaso1": {"fecha": "2025-03-01", "ganadoras": ["B10000001"],
                     "licitadoras": [{"nif": "B10000001"}, {"nif": "A10000002"}, {"nif": "***4567**"}]},
        "expjaso2": {"fecha": "2024-06-01", "ganadoras": ["A10000002"],
                     "licitadoras": [{"nif": "B10000001"}, {"nif": "A10000002"}]},
        "expjaso3": {"fecha": "2026-01-10", "ganadoras": ["U10000003"],  # gana una UTE: no cuenta
                     "licitadoras": [{"nif": "B10000001"}, {"nif": "B10000001"}]},
    }
    assert euskadi.indice_exito(acumulado) == {
        "B10000001": [3, 1, "2024-06-01"],
        "A10000002": [2, 1, "2024-06-01"],
    }


def _historico(tmp_path):
    exp = [
        # [id, título, organismo, euskadi, tipo, proc, menor, máscara, enlace, ted, actualizado, presupuesto, lugar]
        ["a", "T1", 0, 1, 0, 0, 0, 1, URL.format("expjaso200001")[:-1], 0, "2024-02-01", 1000, 0],
        ["b", "T2", 0, 1, 0, 0, 0, 1, URL.format("expjaso200002")[:-1], 0, "2026-02-01", 1000, 0],
        ["c", "T3", 0, 1, 0, 0, 1, 1, URL.format("expjaso200003")[:-1], 0, "2026-03-01", 1000, 0],  # menor
        ["d", "T4", 0, 0, 0, 0, 0, 1, "https://contrataciondelestado.es/x", 0, "2026-04-01", 1000, 0],  # no vasco
    ]
    empresas = [["B10000001", "Una SL"], [None, "UNA, S.L.", 0]]  # la segunda, fusionada en la primera
    ruta = tmp_path / "historico.json"
    ruta.write_text(json.dumps({"exp": exp, "lotes": [[0, 1], [1, 0]], "dic": {"empresa": empresas}}), encoding="utf-8")
    return ruta


def test_pendientes_del_historico(tmp_path, monkeypatch):
    monkeypatch.setattr(euskadi, "HISTORICO", _historico(tmp_path))
    pendientes = euskadi._pendientes_del_historico({"expjaso200002": {}})
    assert [(p[0], p[3]) for p in pendientes] == [("expjaso200001", ["B10000001"])]


def test_rellenar_desde_historico(tmp_path, monkeypatch):
    monkeypatch.setattr(euskadi, "HISTORICO", _historico(tmp_path))
    monkeypatch.setattr(euskadi, "LICITADORAS_ACUMULADO", tmp_path / "acumulado.json")
    monkeypatch.setattr(euskadi.time, "sleep", lambda s: None)
    monkeypatch.setattr(euskadi, "leer_ficha", lambda url: {"licitadores": [{"nif": "B10000001", "pyme": True}], "documentos": []})
    acumulado = {}
    assert euskadi.rellenar_desde_historico(acumulado) == 2
    assert acumulado["expjaso200002"]["ganadoras"] == ["B10000001"]
    assert euskadi.rellenar_desde_historico(acumulado) == 0   # ya no queda nada pendiente
