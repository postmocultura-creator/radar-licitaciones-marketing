# -*- coding: utf-8 -*-
"""Lectura de las fuentes con muestras reales guardadas: una entrada
adjudicada del ZIP de PLACSP (septiembre de 2026) y la ficha pública de un
expediente de Euskadi."""
import json
from xml.etree import ElementTree as ET

import pytest
import requests

import euskadi
import placsp
from conftest import FIXTURES


@pytest.fixture(scope="module")
def entrada_placsp():
    raiz = ET.parse(FIXTURES / "placsp_adjudicacion.atom").getroot()
    return raiz.find("atom:entry", placsp.NS)


def test_placsp_parsea_la_adjudicacion(entrada_placsp):
    item = placsp._parsear_entry(entrada_placsp)
    assert item["estado"] == "ADJ"
    assert item["empresa_adjudicataria"].startswith("DISEÑO Y TECNICAS GRAFICAS DE EXTREMADURA")
    assert item["empresa_nif"] == "A06036883"
    assert item["fecha_adjudicacion"]
    assert item["pliegos"] == []  # solo se guardan los pliegos de lo que está en plazo


def test_placsp_enmascara_a_las_personas_fisicas():
    # Misma entrada real, con la adjudicataria cambiada por un autónomo con
    # el DNI entero (así llegan los contratos menores de PLACSP).
    texto = (FIXTURES / "placsp_adjudicacion.atom").read_text(encoding="utf-8")
    texto = texto.replace("A06036883", "12345678Z").replace(
        "DISEÑO Y TECNICAS GRAFICAS DE EXTREMADURA TECNIGRAF, SAU", "Ana García López 12345678Z")
    entrada = ET.fromstring(texto.encode("utf-8")).find("atom:entry", placsp.NS)
    item = placsp._parsear_entry(entrada)
    assert item["empresa_nif"] == "***4567**"
    assert item["empresa_adjudicataria"] == "Ana García López ***4567**"


def test_placsp_documentos_de_adjudicacion(entrada_placsp):
    documentos = placsp._parsear_entry(entrada_placsp)["documentos_adjudicacion"]
    # La muestra trae un fichero "acta" sin código de tipo: se reconoce por el
    # nombre (antes salía como "otro").
    assert [d["tipo"] for d in documentos] == ["acta"]
    assert all(d["url"].startswith("http") for d in documentos)
    assert len(documentos) <= placsp.MAX_DOCUMENTOS_ADJUDICACION


class _Respuesta:
    def __init__(self, contenido: bytes):
        self.content = contenido
        self.status_code = 200

    def raise_for_status(self):
        pass


def test_euskadi_lee_la_ficha(monkeypatch):
    html = (FIXTURES / "euskadi_ficha.html").read_bytes()
    monkeypatch.setattr(requests, "request", lambda *a, **k: _Respuesta(html))
    esperado = json.loads((FIXTURES / "euskadi_ficha_esperado.json").read_text(encoding="utf-8"))

    ficha = euskadi.leer_ficha("https://ejemplo.invalid/ficha")

    assert [l["nombre"] for l in ficha["licitadores"]] == esperado["licitadores"]
    assert all(l["nif"] and l["nif"][0] in "AB" for l in ficha["licitadores"])
    assert len(ficha["documentos"]) == esperado["documentos"]
    assert all(d["url"].startswith(euskadi.URL_DESCARGA_FICHERO.split("{")[0]) for d in ficha["documentos"])
    # Solo se guardan nombre, NIF, pyme y provincia: nunca contacto.
    assert all(set(l) == {"nombre", "nif", "pyme", "provincia"} for l in ficha["licitadores"])


@pytest.mark.parametrize("texto,de_la_mesa,tipo", [
    ("Informe de valoración de criterios", False, "informe_valoracion"),
    ("Acta de la mesa apertura sobre B", False, "acta"),
    ("Resolución de adjudicación", False, "resolucion"),
    ("Autorizacion gasto_025.pdf", False, None),   # preparatorio colgado en Resolución
    ("Pliego de prescripciones técnicas", True, None),
    ("Apertura sobre C", True, "acta"),            # acuerdo de la mesa sin la palabra "acta"
])
def test_euskadi_tipo_documento(texto, de_la_mesa, tipo):
    assert euskadi._tipo_documento(texto, de_la_mesa) == tipo
