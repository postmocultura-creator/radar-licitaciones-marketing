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
    # Vistas en los descartes de "Cómo se filtra" (2026-10-04).
    "Servicio realizacion de la Campana Institucional de Navidad 2026",
    "Contratación del servicio de apoyo a la captación y gestión de patrocinios",
    "Nuevo diseño de la web de la CNMC",
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
    # "Campaña de Navidad" y "patrocinio" sueltos son ruido (medido).
    "Suministro de luminarias ornamentales y decorativas para la campaña de Navidad del municipio",
    "Patrocinio del evento Festival Internacional de trompetas",
])
def test_titulos_ajenos_no_entran(titulo):
    assert clasificar_texto(titulo)["incluir"] is False


@pytest.mark.parametrize("titulo, entra", [
    # El tipo de servicio de TED dice "impresión", el título no: entra.
    ("España – Servicios de impresión y servicios conexos – Diseño gráfico y producción de elementos de comunicación", True),
    # Grupo genérico "Servicios a empresas": su "imprenta" ya no tumba un
    # título de agencia...
    ("España – Servicios a empresas: legislación, mercadotecnia, asesoría, selección de personal, imprenta y seguridad – "
     "Servicios especializados de agencia de publicidad y de agencia de medios", True),
    # ...pero su "mercadotecnia" tampoco basta: el título tiene que decirlo.
    ("Alemania – Servicios a empresas: legislación, mercadotecnia, asesoría, selección de personal, imprenta y seguridad – "
     "7 Reiseführer und 35 Workshops", False),
    # El tipo de servicio sí cuenta para entrar (títulos en otro idioma).
    ("Letonia – Servicios de relaciones públicas – Komunikācijas aktivitāšu nodrošināšana", True),
    # Y la imprenta en el título sigue descartando.
    ("España – Servicios de diseño gráfico – Diseño e impresión de folletos", False),
])
def test_titulos_de_ted(titulo, entra):
    assert clasificar_texto(titulo, ted=True)["incluir"] is entra


@pytest.mark.parametrize("titulo, entra", [
    # "seo" suelto solo con contexto digital (config.SEO_CONTEXTO)...
    ("Posicionamiento SEO de la web de SODERCAN", True),
    ("Mantenimiento SEO web", True),
    ("Seo y reputación II", True),
    ("Campaña RRSS y SEO máster", True),
    # ...y nunca los otros "seo": catedrales, calles, ornitología,
    # oftalmología, siglas de navegación aérea.
    ("Seo sistema visual tacc valencia", False),
    ("Seo de un radar modo s en Taborno (Tenerife)", False),
    ("Urbanización Pza LA Seo, sector Occidental", False),
    ("Inscripción 100 congreso SEO socio de la SEO", False),
    ("Desayuno actividad con Seo-Birdlife en el PCT", False),
    ("Reforma del vertedero en la SEO DE URGEL, LERIDA", False),
])
def test_seo_suelto(titulo, entra):
    assert clasificar_texto(titulo)["incluir"] is entra


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


def test_terminos_que_encajan_tal_como_se_escriben():
    from clasificar import terminos_que_encajan

    # Por categoría, la palabra clave más larga que encaje.
    assert terminos_que_encajan("Gestión de REDES SOCIALES y Diseño Gráfico") == ["Gestión de REDES SOCIALES", "Diseño Gráfico"]
    assert terminos_que_encajan("Instal·lació de publicitat exterior") == ["publicitat"]
    assert terminos_que_encajan("Obras de urbanización") == []


def test_descartes_con_su_motivo():
    import clasificar

    items = [
        {"estado": "PUB", "titulo": "Diseño e impresión de piezas publicitarias", "cpv": ["79800000"]},
        {"estado": "PUB", "titulo": "Campaña de Navidad del comercio local", "cpv": ["79341400"]},
        {"estado": "PUB", "titulo": "Obras de la calle Mayor", "cpv": ["45000000"]},
        {"estado": "ADJ", "titulo": "Gestión de redes sociales", "cpv": []},
        {"estado": "PUB", "titulo": "Gestión de redes sociales", "cpv": []},
    ]
    clasificar._descartes = {"lista": []}
    try:
        relevantes = clasificar.clasificar_placsp(items)
        descartes = clasificar._descartes
    finally:
        clasificar._descartes = None
    assert [r["titulo"] for r in relevantes] == ["Gestión de redes sociales"]
    assert (descartes["servicio_no_ofrecido"], descartes["sin_categoria"]) == (1, 2)
    # Se guardan el de imprenta (con la palabra) y el de CPV de publicidad;
    # la obra no, y el adjudicado ni siquiera llega al filtro de texto.
    assert [(d["titulo"], d["motivo"], d["termino"]) for d in descartes["lista"]] == [
        ("Diseño e impresión de piezas publicitarias", "servicio_no_ofrecido", "impresión"),
        ("Campaña de Navidad del comercio local", "sin_categoria", None),
    ]
