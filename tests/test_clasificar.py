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
])
def test_titulos_de_agencia_entran(titulo):
    resultado = clasificar_texto(titulo, [])
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
    assert clasificar_texto(titulo, [])["incluir"] is False


def test_mezcla_con_exclusion_entra_para_revisar():
    resultado = clasificar_texto("Contrato de servicio de comunicación y limpieza de edificios municipales", [])
    assert resultado["incluir"] is True
    assert resultado["revisar_manual"] is True


def test_normalizar_texto_quita_tildes_y_ruido_procedimental():
    assert _normalizar_texto("Comunicación ABIERTO SIN PUBLICIDAD").split() == ["comunicacion"]
    # El punt volat catalán une la palabra; el apóstrofo tipográfico la separa.
    assert "installacio" in _normalizar_texto("Instal·lació")
    assert _normalizar_texto("d’impressió").split() == ["d", "impressio"]
