# -*- coding: utf-8 -*-
"""NIF, fechas, horas, importes y lugar: las conversiones que comparten el
radar diario y el histórico."""
import pytest

import territorio
from normalizar import (
    NO_PUBLICADO,
    _hora,
    _limpiar_fecha,
    _nif_limpio,
    _organismos_compatibles,
    _parsear_presupuesto,
    _titulo_ted_sin_prefijo,
    es_empresa_espanola,
    nif_enmascarado,
)


@pytest.mark.parametrize("crudo,limpio", [
    ("B-12345678", "B12345678"),
    ("b12.345.678", "B12345678"),
    ("ESB28016970", "B28016970"),   # prefijo de IVA: misma empresa que B28016970
    ("***9688**", "***9688**"),      # PLACSP enmascara a las personas físicas
    # DNI y NIE completos de personas físicas: se enmascaran igual que PLACSP
    # (criterio de la AEPD), nunca se guardan enteros.
    ("12345678Z", "***4567**"),
    ("12.345.678-Z", "***4567**"),
    ("ES12345678Z", "***4567**"),
    ("X1234567L", "****4567*"),
    ("", None),
    (None, None),
])
def test_nif_limpio(crudo, limpio):
    assert _nif_limpio(crudo) == limpio


def test_dni_dentro_de_un_texto_se_enmascara():
    import nif

    # Caso real: el organismo pega el DNI al nombre del autónomo.
    assert nif.ocultar_en_texto("Laura Blanco Gutierrez 71635468J") == "Laura Blanco Gutierrez ***3546**"
    assert nif.ocultar_en_texto("Ana Ruiz (X1234567L)") == "Ana Ruiz (****4567*)"
    assert nif.ocultar_en_texto("AGENCIA B12345678 S.L.") == "AGENCIA B12345678 S.L."   # sociedad: se queda
    assert nif.ocultar_en_texto(None) is None
    # Códigos de expediente de PLACSP que acaban como un DNI: no se tocan.
    assert nif.ocultar_en_texto("Id licitación: 2026/SP03038000/00000545E; Estado: RES") == \
        "Id licitación: 2026/SP03038000/00000545E; Estado: RES"
    assert nif.ocultar_en_texto("Expediente 2026-00003540E") == "Expediente 2026-00003540E"


def test_nif_enmascarado():
    assert nif_enmascarado("***9688**")
    assert nif_enmascarado("XXXXX155F")   # así enmascara Euskadi
    assert not nif_enmascarado("B12345678")
    assert not nif_enmascarado(None)


@pytest.mark.parametrize("nif,paises,esperado", [
    ("B12345678", None, True),
    ("12345678Z", None, True),       # DNI
    ("X1234567L", None, True),       # NIE de residente
    ("IE6388047V", None, False),     # IVA irlandés
    ("N0012345J", None, False),      # entidad extranjera
    (None, ["ESP"], True),           # TED: manda el país del adjudicatario
    (None, ["FRA"], False),
])
def test_es_empresa_espanola(nif, paises, esperado):
    assert es_empresa_espanola(nif, paises) is esperado


def test_nif_de_relleno_depende_del_comprador():
    assert es_empresa_espanola("X00000000", comprador_espanol=True) is True
    assert es_empresa_espanola("X00000000", comprador_espanol=False) is False


@pytest.mark.parametrize("crudo,limpia", [
    ("2026-08-03+02:00", "2026-08-03"),
    ("2026-09-30Z", "2026-09-30"),          # TED, sin "T"
    ("2026-10-23-04:00", "2026-10-23"),     # huso negativo
    ("2026-10-23T14:00:00", "2026-10-23"),
    ("", NO_PUBLICADO),
    (None, NO_PUBLICADO),
])
def test_limpiar_fecha(crudo, limpia):
    assert _limpiar_fecha(crudo) == limpia


@pytest.mark.parametrize("crudo,hora", [
    ("14:00:00", "14:00"), ("14:00:00+02:00", "14:00"), ("23:59:00Z", "23:59"), (None, None), ("", None),
])
def test_hora(crudo, hora):
    assert _hora(crudo) == hora


def test_presupuesto_cero_es_no_publicado():
    assert _parsear_presupuesto("0") == (None, NO_PUBLICADO)
    assert _parsear_presupuesto(None) == (None, NO_PUBLICADO)
    assert _parsear_presupuesto("15000.5") == (15000.5, "15,000 EUR")


def test_titulo_ted_sin_prefijo():
    assert _titulo_ted_sin_prefijo("España – Servicios de publicidad – Difusión de la campaña") == "Difusión de la campaña"
    assert _titulo_ted_sin_prefijo("Título sin prefijo") == "Título sin prefijo"


def test_organismos_compatibles():
    assert _organismos_compatibles("gobierno vasco", "gobierno vasco bienestar juventud")
    assert not _organismos_compatibles("gobierno vasco", "gobierno de navarra")


def test_traductor_caido_no_alarga_la_noche(monkeypatch):
    import normalizar

    llamadas = []

    class TraductorCaido:
        def __init__(self, **kwargs):
            pass

        def translate(self, texto):
            llamadas.append(texto)
            raise ConnectionError("MyMemory no responde")

    monkeypatch.setattr(normalizar, "MyMemoryTranslator", TraductorCaido)
    monkeypatch.setattr(normalizar.time, "sleep", lambda s: None)
    monkeypatch.setattr(normalizar, "_CACHE_TRADUCCION", {})
    monkeypatch.setattr(normalizar, "_fallos_seguidos", 0)

    textos = [f"Call number {i}" for i in range(10)]
    assert [normalizar._traducir_en_es(t) for t in textos] == textos  # se queda en inglés
    # 3 intentos por texto hasta FALLOS_SEGUIDOS_MAX textos fallidos; después ya no llama.
    assert len(llamadas) == 3 * normalizar.FALLOS_SEGUIDOS_MAX


@pytest.mark.parametrize("args,esperado", [
    (("ES213",), ("Bizkaia", "País Vasco")),
    (("ES",), (None, None)),                          # todo el territorio
    (("ES21", None, "20001"), ("Gipuzkoa", "País Vasco")),
    ((None, None, "48001"), ("Bizkaia", "País Vasco")),
    (("ES21", None, "28001"), (None, "País Vasco")),  # CP de otra comunidad: no afina
    (("FR101",), (None, None)),
])
def test_territorio_lugar(args, esperado):
    assert territorio.lugar(*args) == esperado
