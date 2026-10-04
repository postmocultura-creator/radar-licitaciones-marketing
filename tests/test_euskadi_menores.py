# -*- coding: utf-8 -*-
"""Contratos menores de Euskadi por vencer: lectura por meses en rotación y
acumulado entre noches. Antes se leían 150 de ~1.500 páginas y solo salían
los adjudicados en los últimos 3-4 meses (comprobado el 2026-10-04)."""
import json
from datetime import date

import pytest

import euskadi


def test_ventana_de_meses():
    meses = euskadi._ventana_menores(date(2026, 10, 4))
    assert len(meses) == euskadi.MESES_MENORES
    assert meses[0] == "202610" and meses[1] == "202609"
    assert meses[-1] == "202508"


def test_meses_a_leer_prioriza_los_nunca_leidos():
    hoy = date(2026, 10, 4)
    ventana = euskadi._ventana_menores(hoy)
    a_leer = euskadi._meses_a_leer_menores(hoy, leidos={})
    assert a_leer[:2] == ["202610", "202609"]                  # siempre: llegan con retraso
    assert len(a_leer) == 2 + euskadi.MESES_NUEVOS_POR_NOCHE
    assert set(a_leer[2:]) <= set(ventana[2:])


def test_meses_a_leer_con_todo_leido_rota_uno():
    hoy = date(2026, 10, 4)
    ventana = euskadi._ventana_menores(hoy)
    leidos = {m: "2026-10-01" for m in ventana}
    a_leer = euskadi._meses_a_leer_menores(hoy, leidos)
    assert len(a_leer) == 3
    # En len(ventana)-2 noches seguidas se repasan todos los meses antiguos.
    rotados = {euskadi._meses_a_leer_menores(date.fromordinal(hoy.toordinal() + i), leidos)[2]
               for i in range(len(ventana) - 2)}
    assert rotados == set(ventana[2:])


def _contrato(id_, objeto, adjudicado, fin, menor=True):
    return {"id": id_, "object": objeto, "awardDate": adjudicado + "T00:00:00Z", "contractEndDate": fin,
            "minorContract": menor, "socialReason": "AGENCIA, S.L.", "CIF": "B12345678",
            "_links": {"contractingAuthority": {"href": "https://api.euskadi.eus/procurements/contracting-authorities/1"}}}


@pytest.fixture
def api_falsa(monkeypatch):
    paginas = {}
    pedidas = []

    class Resp:
        def __init__(self, datos):
            self._datos = datos

        def json(self):
            return self._datos

    def pedir(metodo, url, **kwargs):
        if "contracting-authorities" in url:
            return Resp({"name": "Ayuntamiento de Prueba", "codNUTS": "ES213"})
        params = kwargs["params"]
        assert params["minor-contract"] == "true"               # filtra el servidor, no nosotros
        mes = params["award-date.lt"][:7].replace("-", "")
        pedidas.append(mes)
        return Resp({"items": paginas.get(mes, []), "totalPages": 1})

    monkeypatch.setattr(euskadi.peticiones, "pedir", pedir)
    monkeypatch.setattr(euskadi.time, "sleep", lambda s: None)
    return paginas, pedidas


def test_acumula_solo_lo_relevante_y_poda_lo_vencido(api_falsa, tmp_path, monkeypatch):
    paginas, pedidas = api_falsa
    monkeypatch.setattr(euskadi, "ACUMULADO_MENORES", tmp_path / "menores.json")
    hoy = date(2026, 10, 4)
    paginas["202610"] = [_contrato(1, "Gestión de redes sociales", "2026-10-02", "2027-10-01"),
                         _contrato(2, "Limpieza de oficinas", "2026-10-02", "2027-10-01")]   # no es de agencia
    paginas["202609"] = [_contrato(3, "Campaña de publicidad", "2026-09-10", "2026-09-30")]  # ya vencido

    items = euskadi.actualizar_menores(hoy)

    assert [i["id"] for i in items] == [1]
    assert items[0]["organismo_resuelto"] == "Ayuntamiento de Prueba"
    guardado = json.loads((tmp_path / "menores.json").read_text(encoding="utf-8"))
    assert set(guardado["meses_leidos"]) == set(pedidas)


def test_releer_un_mes_sustituye_lo_que_habia(api_falsa, tmp_path, monkeypatch):
    paginas, _ = api_falsa
    monkeypatch.setattr(euskadi, "ACUMULADO_MENORES", tmp_path / "menores.json")
    hoy = date(2026, 10, 4)
    paginas["202610"] = [_contrato(1, "Gestión de redes sociales", "2026-10-02", "2027-10-01")]
    euskadi.actualizar_menores(hoy)
    # Al día siguiente el contrato 1 ya no está (anulado) y aparece el 4.
    paginas["202610"] = [_contrato(4, "Diseño gráfico de la revista", "2026-10-03", "2027-01-01")]
    items = euskadi.actualizar_menores(date(2026, 10, 5))
    assert [i["id"] for i in items] == [4]
