# -*- coding: utf-8 -*-
"""Histórico de adjudicaciones: agrupación de empresas, formato compacto y
consultas a las fuentes."""
import historico_adjudicaciones as h
import placsp


def _registro(id_, empresa, nif, fecha="2025-03-01", importe=1000.0, enlace="https://ejemplo.invalid/x"):
    return {
        "id": id_, "expediente": None, "titulo": "Servicio de comunicación", "organismo": "Ayuntamiento de Prueba",
        "organismo_nif": None, "ambito": "Estado", "provincia": "Bizkaia", "comunidad": "País Vasco",
        "tipo_contrato": "Servicios", "procedimiento": "Abierto", "menor": False, "presupuesto": None,
        "cpv": [], "categorias": ["Publicidad y comunicación (general)"], "enlace": enlace,
        "fuente": "PLACSP", "actualizado": fecha,
        "lotes": [{"empresa": empresa, "nif": nif, "fecha": fecha, "importe": importe,
                   "ofertas": 3, "pyme": True, "lote": None}],
    }


def test_clave_empresa_agrupa_por_nif_con_y_sin_prefijo():
    assert h._clave_empresa("ESB28016970", "Uniprex SA") == h._clave_empresa("B28016970", "UNIPREX, S.A.")


def test_clave_empresa_nif_de_relleno_agrupa_por_nombre():
    assert h._clave_empresa("A00000000", "Varias empresas") != h._clave_empresa("A00000000", "Otra UTE")


def test_clave_empresa_enmascarado_exige_el_mismo_nombre():
    misma = h._clave_empresa("***9688**", "GARCÍA LÓPEZ, ANA")
    assert misma == h._clave_empresa("***9688**", "Ana García López")
    assert misma != h._clave_empresa("***9688**", "Pedro Ruiz Gil")


def test_dni_completo_no_se_guarda_y_agrupa_por_nombre():
    registros = [_registro("a", "GARCÍA LÓPEZ, ANA", "12345678Z"),
                 _registro("b", "Ana García López", "12345678Z"),
                 _registro("c", "Pedro Ruiz Gil", "99345678A")]   # otra persona, mismas cifras visibles
    compacto = h._compactar(registros)
    nifs = [e[0] for e in compacto["dic"]["empresa"]]
    assert nifs == ["***4567**", "***4567**"]
    assert len({l[1] for l in compacto["lotes"][:2]}) == 1          # Ana: una sola ficha
    assert compacto["lotes"][2][1] != compacto["lotes"][0][1]       # Pedro: otra


def test_dni_ya_publicado_se_enmascara_al_volver_a_compactar():
    previo = h._compactar([_registro("a", "Ana García López", "12345678Z")])
    previo["dic"]["empresa"][0][0] = "12345678Z"   # como estaba publicado antes del cambio
    vueltos = h._expandir(previo)
    compacto = h._compactar(vueltos, previo["dic"])
    assert compacto["dic"]["empresa"][0][0] == "***4567**"
    assert "12345678Z" not in str(compacto)


def test_compactar_y_expandir_conservan_los_datos():
    registros = [_registro("a", "Uniprex SA", "B28016970"), _registro("b", "UNIPREX, S.A.", "ESB28016970")]
    compacto = h._compactar(registros)
    assert len(compacto["dic"]["empresa"]) == 1          # misma empresa
    vueltos = h._expandir(compacto)
    assert [r["id"] for r in vueltos] == ["a", "b"]
    assert vueltos[0]["lotes"][0]["nif"] == "B28016970"
    assert vueltos[0]["provincia"] == "Bizkaia"


def test_rango_euskadi_incluye_el_primer_dia_del_mes():
    import euskadi

    # La API trata award-date.gt como exclusivo y .lt como inclusivo
    # (comprobado el 2026-10-04): pedir gt=día 1 perdía los del día 1.
    assert euskadi.rango_mes_api("202609") == ("2026-08-31", "2026-09-30")
    assert euskadi.rango_mes_api("202601") == ("2025-12-31", "2026-01-31")
    assert euskadi.rango_mes_api("202612") == ("2026-11-30", "2026-12-31")
    assert euskadi.rango_mes_api("2025") == ("2024-12-31", "2025-12-31")


def test_enlace_de_navarra_se_repara():
    roto = "https://hacienda.navarra.es/sicpportal/ctaDatosAdjudicacion.aspx?cod=8071&' || 'Ticket=2405151655379A9081FD"
    assert placsp.limpiar_enlace(roto) == (
        "https://hacienda.navarra.es/sicpportal/ctaDatosAdjudicacion.aspx?cod=8071&Ticket=2405151655379A9081FD")
    assert placsp.limpiar_enlace("https://contrataciondelestado.es/x?a=1") == "https://contrataciondelestado.es/x?a=1"
    assert placsp.limpiar_enlace(None) is None


def test_concatenacion_de_navarra_en_nombres():
    # Navarra cambia "&" por "&' || '" también en los nombres de empresa.
    assert placsp.limpiar_texto("AGENCIA RIDER CULTURE &' || ' SPORT, S.L.") == "AGENCIA RIDER CULTURE & SPORT, S.L."


def test_compactar_limpia_nombres_y_titulos():
    r = _registro("a", "Ana Martín Ruiz 12345678Z", "12345678Z")
    r["titulo"] = "Diseño gráfico &' || ' maquetación"
    compacto = h._compactar([r])
    assert compacto["dic"]["empresa"][0] == ["***4567**", "Ana Martín Ruiz ***4567**"]
    assert compacto["exp"][0][1] == "Diseño gráfico & maquetación"


def test_compactar_repara_enlaces_ya_publicados():
    roto = "https://hacienda.navarra.es/sicpportal/ctaDatosAdjudicacion.aspx?cod=1&' || 'Ticket=X"
    compacto = h._compactar([_registro("a", "Uniprex SA", "B28016970", enlace=roto)])
    assert "' || '" not in compacto["exp"][0][8]


def test_fin_del_contrato_por_fecha_o_por_duracion():
    from xml.etree import ElementTree as ET

    ns = ('xmlns:cac="urn:dgpe:names:draft:codice:schema:xsd:CommonAggregateComponents-2" '
          'xmlns:cbc="urn:dgpe:names:draft:codice:schema:xsd:CommonBasicComponents-2"')

    def proyecto(periodo, prorroga=False):
        return ET.fromstring(f'<cac:ProcurementProject {ns}><cac:PlannedPeriod>{periodo}</cac:PlannedPeriod>'
                             + ("<cac:ContractExtension><cbc:OptionsDescription>1 año</cbc:OptionsDescription></cac:ContractExtension>" if prorroga else "")
                             + "</cac:ProcurementProject>")

    lotes = [{"fecha": "2025-03-01"}, {"fecha": "2025-04-01"}]
    # Duración en meses desde la adjudicación más reciente (30 días por mes).
    assert h._fin_contrato(proyecto('<cbc:DurationMeasure unitCode="MON">12</cbc:DurationMeasure>', True), lotes) == ("2026-03-27", True)
    # Con fecha de inicio, desde el inicio.
    assert h._fin_contrato(proyecto('<cbc:StartDate>2025-06-01</cbc:StartDate><cbc:DurationMeasure unitCode="ANN">1</cbc:DurationMeasure>'), lotes) == ("2026-06-01", False)
    # La fecha de fin publicada manda.
    assert h._fin_contrato(proyecto('<cbc:EndDate>2026-12-31</cbc:EndDate><cbc:DurationMeasure unitCode="MON">3</cbc:DurationMeasure>'), lotes) == ("2026-12-31", False)
    assert h._fin_contrato(proyecto(""), lotes) == (None, False)


def test_fin_y_prorroga_sobreviven_al_formato_compacto():
    r = _registro("a", "Uniprex SA", "B28016970")
    r["fin"], r["prorroga"] = "2026-12-31", True
    vuelto = h._expandir(h._compactar([r]))[0]
    assert (vuelto["fin"], vuelto["prorroga"]) == ("2026-12-31", True)
    # Lo publicado antes, sin esas columnas, se lee sin fin.
    compacto = h._compactar([_registro("b", "Uniprex SA", "B28016970")])
    compacto["exp"] = [e[:13] for e in compacto["exp"]]
    assert h._expandir(compacto)[0]["fin"] is None
