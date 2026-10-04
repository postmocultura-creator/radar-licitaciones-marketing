# -*- coding: utf-8 -*-
"""NIF, fechas, horas, importes y lugar: las conversiones que comparten el
radar diario y el histórico."""
import pytest

import normalizar
import territorio
from normalizar import (
    NO_PUBLICADO,
    _competencia,
    _criterios,
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
    assert nif.ocultar_en_texto("Ana Martín Ruiz 12345678Z") == "Ana Martín Ruiz ***4567**"
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


def test_campos_multilingues_de_ted():
    import ted
    from normalizar import _texto_ted

    aviso = {"buyer-name": {"deu": ["Stadt"], "spa": ["Ayuntamiento de Bilbao"], "eus": ["Bilboko Udala"]},
             "winner-name": {"fra": ["Agence"], "ita": ["Agenzia"]},
             "notice-title": {"eng": ["Campaign"]}}
    ted._solo_idiomas_utiles(aviso)
    assert aviso["buyer-name"] == {"spa": ["Ayuntamiento de Bilbao"]}
    assert aviso["winner-name"] == {"fra": ["Agence"]}         # sin español ni inglés: el primero
    assert _texto_ted(aviso["buyer-name"]) == "Ayuntamiento de Bilbao"
    assert _texto_ted(aviso["winner-name"], idiomas=()) == "Agence"
    assert _texto_ted(None) == NO_PUBLICADO


def test_titulo_ted_sin_prefijo():
    assert _titulo_ted_sin_prefijo("España – Servicios de publicidad – Difusión de la campaña") == "Difusión de la campaña"
    assert _titulo_ted_sin_prefijo("Título sin prefijo") == "Título sin prefijo"


def _con_criterios(grupos, fuente="Estado"):
    return {"fuente": fuente, "original": {"criterios_adjudicacion": grupos}}


def test_criterios_en_porcentaje():
    # Pesos sobre 10 (pasa): se reparten igual que sobre 100.
    resultado = _criterios(_con_criterios([{"lote": None, "criterios": [
        {"descripcion": "Precio", "peso": 4, "tipo": "precio"},
        {"descripcion": "Propuesta creativa", "peso": 5, "tipo": "juicio"},
        {"descripcion": "Plazo de entrega", "peso": 1, "tipo": "formula"},
    ]}]))
    assert (resultado["precio"], resultado["formulas"], resultado["juicio"]) == (40, 10, 50)
    assert [c["descripcion"] for c in resultado["detalle"]] == ["Propuesta creativa", "Precio", "Plazo de entrega"]
    assert resultado["detalle"][0]["peso"] == 50
    assert resultado["por_lotes"] is False


def test_criterios_con_lotes_y_sin_peso():
    lotes = [{"lote": "1", "criterios": [{"descripcion": "Precio", "peso": 100, "tipo": "precio"}]},
             {"lote": "2", "criterios": [{"descripcion": "Precio", "peso": 30, "tipo": "precio"},
                                         {"descripcion": "Memoria", "peso": 70, "tipo": "juicio"}]}]
    resultado = _criterios(_con_criterios(lotes))
    assert resultado["precio"] == 100 and resultado["por_lotes"] is True   # el primer lote
    sin_peso = [{"lote": None, "criterios": [{"descripcion": "Precio", "peso": None, "tipo": "precio"}]}]
    assert _criterios(_con_criterios(sin_peso)) is None
    assert _criterios(_con_criterios(lotes, fuente="Euskadi")) is None


def _adjudicacion_placsp(**campos):
    original = {"resultados": 1, "ofertas": 4, "presupuesto_sin_iva": "10000", "importe_adjudicado_sin_iva": "8200"}
    original.update(campos)
    return {"fuente": "Estado", "original": original}


def test_competencia_rebaja_y_ofertas():
    assert _competencia(_adjudicacion_placsp(), []) == {"ofertas": 4, "rebaja": 18.0}


def test_competencia_sin_rebaja_visible():
    # Adjudicado por el presupuesto (negociados, precios unitarios): no se
    # enseña una rebaja de 0; tampoco una imposible.
    assert _competencia(_adjudicacion_placsp(importe_adjudicado_sin_iva="10000"), []) == {"ofertas": 4}
    assert _competencia(_adjudicacion_placsp(importe_adjudicado_sin_iva="1000"), []) == {"ofertas": 4}
    assert _competencia(_adjudicacion_placsp(importe_adjudicado_sin_iva="12000"), []) == {"ofertas": 4}


def test_competencia_con_varios_resultados_no_calcula():
    assert _competencia(_adjudicacion_placsp(resultados=3), []) == {}


def test_competencia_euskadi_cuenta_licitadoras():
    licitadoras = [{"nombre": "Empresa Uno SL"}, {"nombre": "Empresa Dos SA"}]
    assert _competencia({"fuente": "Euskadi", "original": {}}, licitadoras) == {"ofertas": 2}


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


def _euskadi_con_criterios(*criterios):
    return {"fuente": "Euskadi", "original": {"ficha": {"criterios": [
        {"descripcion": d, "peso": p, "tipo": t} for d, p, t in criterios]}}}


def test_criterios_euskadi_precio_y_resto():
    c = normalizar._criterios(_euskadi_con_criterios(
        ("Precio", 51.0, "precio"), ("Avance del plan de comunicación", 30.0, "otro"), ("Equipo", 19.0, "otro")))
    assert (c["precio"], c["resto"]) == (51, 49)
    assert [d["tipo"] for d in c["detalle"]] == ["precio", "otro", "otro"]
    assert "juicio" not in c and c["por_lotes"] is False


def test_criterios_euskadi_solo_si_el_reparto_es_fiable():
    # Varios lotes mezclados (suman 200), ficha incompleta (suman 40) o sin
    # ningún criterio reconocible como precio: no se enseña.
    assert normalizar._criterios(_euskadi_con_criterios(
        ("Precio", 74.0, "precio"), ("Precio", 52.0, "precio"), ("Oferta técnica", 48.0, "otro"), ("Oferta técnica", 26.0, "otro"))) is None
    assert normalizar._criterios(_euskadi_con_criterios(("Mejora", 20.0, "otro"), ("Precio", 20.0, "precio"))) is None
    assert normalizar._criterios(_euskadi_con_criterios(("Criterios Objetivos", 47.0, "otro"), ("Criterios Subjetivos", 53.0, "otro"))) is None
    assert normalizar._criterios({"fuente": "Euskadi", "original": {}}) is None


def test_pliegos_de_euskadi_salen_de_la_ficha():
    registro = {"fuente": "Euskadi", "original": {"ficha": {"pliegos": [
        {"tipo": "administrativo", "nombre": "PCAP.pdf", "url": "https://ejemplo.invalid/1"},
        {"tipo": "tecnico", "nombre": "PPT.pdf", "url": "javascript:void(0)"}]}}}
    hora, pliegos = normalizar._hora_y_pliegos(registro)
    assert hora is None
    assert [p["tipo"] for p in pliegos] == ["administrativo"]


def _ted(tipos, numeros, nombres=None):
    original = {"award-criterion-type-lot": tipos, "award-criterion-number-lot": numeros}
    if nombres:
        original["award-criterion-name-lot"] = {"fra": nombres}
    return {"fuente": "UE", "original": original}


def test_criterios_ted_precio_y_resto():
    c = normalizar._criterios(_ted(["price", "quality", "quality"], ["40", "55", "5"], ["Prix", "Qualité technique", "RSE"]))
    assert (c["precio"], c["resto"], c["por_lotes"]) == (40, 60, False)
    assert c["detalle"][0] == {"descripcion": "Qualité technique", "peso": 55.0, "tipo": "otro"}


def test_criterios_ted_lotes_repetidos_y_tanto_por_uno():
    # El mismo reparto en tres lotes se enseña una vez; pesos en tanto por uno.
    c = normalizar._criterios(_ted(["price", "quality"] * 3, ["0.4", "0.6"] * 3))
    assert (c["precio"], c["resto"], c["por_lotes"]) == (40, 60, True)
    assert [d["descripcion"] for d in c["detalle"]] == ["Calidad", "Precio"]


def test_criterios_ted_avisos_espanoles_marcan_todo_como_calidad():
    # PLACSP manda a TED todos los criterios como "quality": el precio se
    # reconoce por el nombre.
    registro = {"fuente": "UE", "original": {
        "award-criterion-type-lot": ["quality", "quality"], "award-criterion-number-lot": ["49", "51"],
        "award-criterion-description-lot": {"spa": ["Precio", "Memoria técnica"]}}}
    assert normalizar._criterios(registro)["precio"] == 49


def test_criterios_ted_solo_si_el_reparto_es_fiable():
    assert normalizar._criterios(_ted(["price", "quality", "price", "quality"], ["40", "60", "70", "30"])) is None  # lotes distintos
    assert normalizar._criterios(_ted(["quality", "quality"], ["50", "50"])) is None  # no se sabe cuánto pesa el precio
    assert normalizar._criterios(_ted(["price", "quality"], ["40"])) is None  # listas descuadradas
    assert normalizar._criterios({"fuente": "UE", "original": {}}) is None


def test_al_fusionar_mandan_los_criterios_de_placsp():
    de_ted = {"precio": 40, "resto": 60, "detalle": [], "por_lotes": False}
    de_placsp = {"precio": 40, "formulas": 10, "juicio": 50, "detalle": [], "por_lotes": False}
    superviviente = {"criterios": dict(de_ted)}
    normalizar._heredar_hora_y_pliegos(superviviente, {"criterios": de_placsp})
    assert superviviente["criterios"] == de_placsp
    superviviente = {"criterios": dict(de_placsp)}
    normalizar._heredar_hora_y_pliegos(superviviente, {"criterios": de_ted})
    assert superviviente["criterios"] == de_placsp


def test_lotes_placsp_con_el_peso_del_precio_de_cada_uno():
    registro = {"fuente": "Estado", "original": {
        "lotes": [{"id": "1", "nombre": "Prensa", "importe": "20825"}, {"id": "2", "nombre": "Digital", "importe": None}],
        "criterios_adjudicacion": [
            {"lote": "1", "criterios": [{"descripcion": "Precio", "peso": 40.0, "tipo": "precio"},
                                        {"descripcion": "Propuesta", "peso": 60.0, "tipo": "juicio"}]}]}}
    assert normalizar._lotes(registro) == [
        {"id": "1", "nombre": "Prensa", "importe": 20825.0, "precio": 40},
        {"id": "2", "nombre": "Digital", "importe": None, "precio": None}]


def test_lotes_ted_y_euskadi():
    ted = {"fuente": "UE", "original": {
        "identifier-lot": ["LOT-0001", "LOT-0002"], "title-lot": {"spa": ["Plan EE.UU.", "Plan México"]},
        "estimated-value-lot": ["100000"]}}  # un solo valor para dos lotes: no se sabe de cuál es
    assert normalizar._lotes(ted) == [
        {"id": "1", "nombre": "Plan EE.UU.", "importe": None, "precio": None},
        {"id": "2", "nombre": "Plan México", "importe": None, "precio": None}]
    euskadi = {"fuente": "Euskadi", "original": {"ficha": {"lotes": [
        {"id": "1", "nombre": "Web", "importe": 45000.0, "criterios": [
            {"descripcion": "Precio", "peso": 35.0, "tipo": "precio"}, {"descripcion": "Memoria", "peso": 65.0, "tipo": "otro"}]},
        {"id": "2", "nombre": "Redes", "importe": 30000.0, "criterios": []}]}}}
    assert [(l["id"], l["importe"], l["precio"]) for l in normalizar._lotes(euskadi)] == [("1", 45000.0, 35), ("2", 30000.0, None)]
    # Sin criterios generales, la ficha enseña los del primer lote y lo avisa.
    criterios = normalizar._criterios(euskadi)
    assert (criterios["precio"], criterios["resto"], criterios["por_lotes"]) == (35, 65, True)


def test_un_solo_lote_no_se_ensena():
    assert normalizar._lotes({"fuente": "UE", "original": {"identifier-lot": ["LOT-0000"], "title-lot": {"spa": ["Todo"]}}}) == []
    assert normalizar._lotes({"fuente": "Estado-web", "original": {}}) == []
