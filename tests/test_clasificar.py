# -*- coding: utf-8 -*-
"""Taxonomía: qué entra en el radar y qué no. Títulos reales o calcados de
casos reales documentados en clasificar.py y en el README."""
import pytest

from clasificar import _normalizar_texto, clasificar_texto


@pytest.mark.parametrize("titulo", [
    "Servicio de gestión de redes sociales del Ayuntamiento de Bilbao",
    "Contratación de una Agencia de Publicidad para el Plan de Comunicación sobre las actuaciones derivadas del PAI",
    "Publicidad de la marca Turismo de Navarra 2023 - 2026",
    "Instal·lació de publicitat exterior",
    # Se escapaban frente a un radar comercial (benchmark del 2026-10-04).
    "Los servicios para la gestión, creación y difusión de contenidos en los canales digitales del Ayuntamiento de Avilés.",
    "Web turística + imagen de marca",
])
def test_titulos_de_agencia_entran(titulo):
    resultado = clasificar_texto(titulo)
    assert resultado["incluir"] is True
    assert resultado["categorias"]


@pytest.mark.parametrize("titulo", [
    # "seo" dentro de "museo": coincidencia por palabra completa.
    "Servicio de limpieza del museo de Bellas Artes",
    # "negociado sin publicidad" es el tipo de procedimiento, no publicidad.
    "Seguro de vehículos mediante procedimiento negociado sin publicidad",
    # Imprenta: servicio que la agencia no ofrece (exclusión dura), también
    # con apóstrofo tipográfico catalán.
    "Servei d’impressió i comunicació de la Diputació",
    "Obras de urbanización de la calle Mayor",
])
def test_titulos_ajenos_no_entran(titulo):
    assert clasificar_texto(titulo)["incluir"] is False


def test_mezcla_con_exclusion_entra_para_revisar():
    resultado = clasificar_texto("Contrato de servicio de comunicación y limpieza de edificios municipales")
    assert resultado["incluir"] is True
    assert resultado["revisar_manual"] is True


def test_acumular_conserva_lo_que_no_viene_y_poda_lo_viejo():
    from datetime import date, timedelta

    from clasificar import DIAS_MAX_ADJUDICACIONES, _acumular

    hace = lambda dias: (date.today() - timedelta(days=dias)).isoformat()  # noqa: E731
    previos = [
        {"original": {"enlace": "a", "fecha_actualizacion": hace(5), "fecha_adjudicacion": hace(5)}},
        {"original": {"enlace": "b", "fecha_actualizacion": hace(5), "fecha_adjudicacion": hace(DIAS_MAX_ADJUDICACIONES + 1)}},
        {"original": {"enlace": "c", "fecha_actualizacion": hace(1), "fecha_adjudicacion": hace(1)}},
    ]
    nuevos_items = [{"enlace": "c"}]   # "c" viene en el crudo nuevo: manda su versión nueva
    licitaciones = _acumular(previos, nuevos_items, [], "licitacion")
    assert [c["original"]["enlace"] for c in licitaciones] == ["a", "b"]
    adjudicaciones = _acumular(previos, nuevos_items, [], "adjudicacion")
    assert [c["original"]["enlace"] for c in adjudicaciones] == ["a"]   # "b" ya no se enseña


def test_normalizar_texto_quita_tildes_y_ruido_procedimental():
    assert _normalizar_texto("Comunicación ABIERTO SIN PUBLICIDAD").split() == ["comunicacion"]
    # El punt volat catalán une la palabra; el apóstrofo tipográfico la separa.
    assert "installacio" in _normalizar_texto("Instal·lació")
    assert _normalizar_texto("d’impressió").split() == ["d", "impressio"]
