# -*- coding: utf-8 -*-
"""Crudos y errores de los scrapers (scrapers/comun.py) tal como los busca
clasificar.py."""
import json

import clasificar
import comun


def test_clasificar_encuentra_el_crudo_y_salta_los_errores(tmp_path, monkeypatch):
    monkeypatch.setattr(comun, "RAW_DIR", tmp_path)
    monkeypatch.setattr(clasificar, "RAW_DIR", tmp_path)

    ruta = comun.guardar_crudo("Euskadi", "euskadi", [{"id": 1}])
    comun.guardar_error("Euskadi", "euskadi_adjudicaciones", RuntimeError("caída"))

    assert clasificar._ultimo_raw("euskadi") == ruta
    # Mismo prefijo de fuente, dataset distinto: no se confunden.
    assert clasificar._ultimo_raw("euskadi_adjudicaciones") is None
    assert clasificar._cargar_resultados(ruta) == [{"id": 1}]
    error = next(tmp_path.glob("*_error.json"))
    assert json.loads(error.read_text(encoding="utf-8"))["error"] == "caída"
