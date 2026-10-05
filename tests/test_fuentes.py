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


def _como_en_plazo(texto: str) -> str:
    return texto.replace(">ADJ</cbc-place-ext:ContractFolderStatusCode>", ">PUB</cbc-place-ext:ContractFolderStatusCode>")


def test_placsp_criterios_sin_codigo_de_tipo():
    # La muestra es un expediente antiguo: "Oferta Económica", peso 1000,
    # sin códigos. Se reconoce como precio por la descripción.
    texto = _como_en_plazo((FIXTURES / "placsp_adjudicacion.atom").read_text(encoding="utf-8"))
    item = placsp._parsear_entry(ET.fromstring(texto.encode("utf-8")).find("atom:entry", placsp.NS))
    assert item["criterios_adjudicacion"] == [
        {"lote": None, "criterios": [{"descripcion": "Oferta Económica", "peso": 1000.0, "tipo": "precio"}]}]


def test_placsp_criterios_por_lote():
    # Forma real de un expediente con lotes (ZIP de octubre de 2026): los
    # criterios van dentro de cada ProcurementProjectLot.
    def criterio(descripcion, peso, tipo, subtipo):
        return (f"<cac:AwardingCriteria><cbc:Description>{descripcion}</cbc:Description>"
                f"<cbc:WeightNumeric>{peso}</cbc:WeightNumeric>"
                f"<cbc:AwardingCriteriaTypeCode>{tipo}</cbc:AwardingCriteriaTypeCode>"
                f"<cbc:AwardingCriteriaSubTypeCode>{subtipo}</cbc:AwardingCriteriaSubTypeCode></cac:AwardingCriteria>")
    lotes = "".join(
        f"<cac:ProcurementProjectLot><cbc:ID>{n}</cbc:ID><cac:TenderingTerms><cac:AwardingTerms>{criterios}"
        f"</cac:AwardingTerms></cac:TenderingTerms></cac:ProcurementProjectLot>"
        for n, criterios in ((1, criterio("Precio", 40, "OBJ", "1") + criterio("Propuesta creativa", 60, "SUBJ", "99")),
                             (2, criterio("Precio", 70, "OBJ", "01") + criterio("Horas adicionales", 30, "OBJ", "2"))))
    texto = _como_en_plazo((FIXTURES / "placsp_adjudicacion.atom").read_text(encoding="utf-8"))
    # Fuera los criterios generales de la muestra, dentro los lotes.
    inicio, fin = texto.index("<cac:AwardingTerms>"), texto.index("</cac:AwardingTerms>") + len("</cac:AwardingTerms>")
    texto = texto[:inicio] + texto[fin:]
    texto = texto.replace("</cac:TenderingTerms>", "</cac:TenderingTerms>" + lotes, 1)
    item = placsp._parsear_entry(ET.fromstring(texto.encode("utf-8")).find("atom:entry", placsp.NS))
    grupos = item["criterios_adjudicacion"]
    assert [g["lote"] for g in grupos] == ["1", "2"]
    assert [c["tipo"] for c in grupos[0]["criterios"]] == ["precio", "juicio"]
    assert [c["tipo"] for c in grupos[1]["criterios"]] == ["precio", "formula"]


def test_placsp_precio_con_codigo_de_otro_criterio():
    # Muchos organismos marcan el precio como "otro criterio con fórmula"
    # (OBJ, subtipo 2). Se reconoce cuando la descripción es solo el nombre
    # del precio; si lo mezcla con otros criterios o dice lo contrario, no.
    def criterio(descripcion, subtipo="2"):
        return ET.fromstring(
            '<cac:AwardingCriteria xmlns:cac="{cac}" xmlns:cbc="{cbc}"><cbc:Description>{d}</cbc:Description>'
            "<cbc:AwardingCriteriaTypeCode>OBJ</cbc:AwardingCriteriaTypeCode>"
            "<cbc:AwardingCriteriaSubTypeCode>{s}</cbc:AwardingCriteriaSubTypeCode></cac:AwardingCriteria>".format(
                cac=placsp.NS["cac"], cbc=placsp.NS["cbc"], d=descripcion, s=subtipo))
    for descripcion in ("Precio", "OFERTA ECONÓMICA", "B.1. Oferta Económica", "Precio más bajo",
                        "Proposición económica", "Criterio 1: Precio"):
        assert placsp._tipo_criterio(criterio(descripcion)) == "precio", descripcion
    for descripcion in ("Criterios Automáticos Distintos del Precio",
                        "Oferta económica y demás criterios cuantificables mediante fórmulas automáticas.",
                        "MEJOR RELACION CALIDAD - PRECIO", "Mantenimiento de los precios ofertados",
                        "Horas adicionales"):
        assert placsp._tipo_criterio(criterio(descripcion)) == "formula", descripcion


def test_placsp_criterios_solo_en_plazo(entrada_placsp):
    assert placsp._parsear_entry(entrada_placsp)["criterios_adjudicacion"] == []


def test_placsp_mismo_numero_de_expediente_en_dos_organismos(monkeypatch, tmp_path):
    # Dos organismos con el mismo número de expediente son dos expedientes;
    # dos versiones de la misma entrada, uno (se queda la más reciente).
    import zipfile

    muestra = (FIXTURES / "placsp_adjudicacion.atom").read_text(encoding="utf-8")
    cabecera, resto = muestra.split("<entry>", 1)
    entrada, pie = resto.rsplit("</entry>", 1)
    id_muestra = "https://contrataciondelestado.es/sindicacion/licitacionesPerfilContratante/7617825"
    fecha_muestra = "<updated>2021-09-30T14:44:19.077+02:00</updated>"
    assert id_muestra in entrada and fecha_muestra in entrada

    def copia(identificador, dia):
        return "<entry>" + entrada.replace(id_muestra, identificador).replace(
            fecha_muestra, f"<updated>2021-09-{dia}T10:00:00.000+02:00</updated>") + "</entry>"

    feed = cabecera + copia("id-organismo-A", "28") + copia("id-organismo-A", "29") + copia("id-organismo-B", "27") + pie

    def descarga_falsa(url, destino):
        with zipfile.ZipFile(destino, "w") as z:
            z.writestr("licitaciones.atom", feed)

    monkeypatch.setattr(placsp, "DIR_ZIPS", tmp_path)
    monkeypatch.setattr(placsp, "_descargar_zip", descarga_falsa)
    monkeypatch.setattr(placsp, "_meses_a_leer", lambda: ["202109"])

    items = placsp.extraer()

    assert [i["expediente"] for i in items] == ["1048/2021", "1048/2021"]
    assert sorted(i["fecha_actualizacion"][:10] for i in items) == ["2021-09-27", "2021-09-29"]


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
    # Criterios con su ponderación: el precio se reconoce por el nombre.
    assert ficha["criterios"] == [
        {"descripcion": "Precio", "peso": 70.0, "tipo": "precio"},
        {"descripcion": "Criterios cualitativos", "peso": 30.0, "tipo": "otro"},
    ]
    # Pliegos de la pestaña Ficheros, según el tipo que les pone el organismo.
    assert [p["tipo"] for p in ficha["pliegos"]] == esperado["pliegos"]
    assert all(p["url"].startswith(euskadi.URL_DESCARGA_FICHERO.split("{")[0]) for p in ficha["pliegos"])


@pytest.mark.parametrize("descripcion,tipo", [
    ("Precio", "precio"),
    ("Oferta económica", "precio"),
    ("21b. Precio (cálculo externo)", "precio"),
    ("Proposición económica", "precio"),
    ("Eskaintza ekonomikoa", "precio"),
    ("Criterios distintos del precio", "otro"),
    ("Memoria técnica", "otro"),
    ("Criterios Objetivos", "otro"),
])
def test_euskadi_criterio_de_precio(descripcion, tipo):
    pagina = ('<div class="col-xs-12 col-sm-4 col-md-4">Criterios de adjudicaci&oacute;n</div>'
              '<div class="col-xs-6 col-md-8"><p>Pluralidad de criterios</p></div>'
              f'<div class="col-xs-12 col-sm-4 col-md-4">Criterio</div><div class="col-xs-6 col-md-8"><p>{descripcion}</p></div>'
              '<div class="col-xs-12 col-sm-4 col-md-4">Ponderaci&oacute;n</div><div class="col-xs-6 col-md-8">51</div>'
              '<div class="col-xs-12 col-sm-4 col-md-4">Se utilizar&aacute; subasta electr&oacute;nica</div>')
    assert euskadi._criterios(pagina) == [{"descripcion": descripcion, "peso": 51.0, "tipo": tipo}]


def test_euskadi_fichas_solo_de_licitaciones_en_plazo_y_de_agencia(monkeypatch):
    leidas = []
    monkeypatch.setattr(euskadi, "leer_ficha", lambda url: leidas.append(url) or {
        "documentos": [], "licitadores": [{"nombre": "X"}], "pliegos": [{"tipo": "tecnico"}], "criterios": [], "lotes": []})
    monkeypatch.setattr(euskadi.time, "sleep", lambda s: None)
    items = [
        {"object": "Servicio de gestión de redes sociales", "deadlineDate": "2026-10-20T00:00:00", "mainEntityOfPage": "u1"},
        {"object": "Servicio de gestión de redes sociales", "deadlineDate": "2026-09-01T00:00:00", "mainEntityOfPage": "u2"},
        {"object": "Suministro de gasóleo", "deadlineDate": "2026-10-20T00:00:00", "mainEntityOfPage": "u3"},
        # Contrato menor: el radar no lo enseña, no se lee su ficha.
        {"object": "Servicio de gestión de redes sociales", "deadlineDate": "2026-10-20T00:00:00", "mainEntityOfPage": "u4",
         "minorContract": True},
        # Otro anuncio del mismo expediente: misma ficha, se lee una vez.
        {"object": "Servicio de gestión de redes sociales (corrección)", "deadlineDate": "2026-10-20T00:00:00", "mainEntityOfPage": "u1"},
    ]
    euskadi.anadir_fichas_licitaciones(items, hoy="2026-10-04")
    assert leidas == ["u1"]
    # De la ficha de una licitación solo se guardan pliegos, criterios y lotes.
    assert items[0]["ficha"] == {"pliegos": [{"tipo": "tecnico"}], "criterios": [], "lotes": []}
    assert items[4]["ficha"] == items[0]["ficha"] and "ficha" not in items[3]


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


def test_calls_documentos_de_la_convocatoria():
    import eu_grants
    condiciones = (
        '<h4>1. Admissibility</h4><p>see the <a href="https://ejemplo.invalid/call.pdf">call document</a></p>'
        '<h4>Call document and annexes:</h4>'
        '<p><a href="https://ejemplo.invalid/call.pdf" target="_blank">Call document</a></p>'
        '<p><a href="https://ejemplo.invalid/form.pdf">Application form &amp; templates</a></p>'
        '<p><a href="https://ejemplo.invalid/call.pdf">.</a></p>'
        '<h4>Additional documents:</h4><p><a href="https://ejemplo.invalid/reglamento.pdf">EU Financial Regulation</a></p>')
    assert eu_grants._documentos_convocatoria(condiciones) == [
        {"nombre": "Call document", "url": "https://ejemplo.invalid/call.pdf"},
        {"nombre": "Application form & templates", "url": "https://ejemplo.invalid/form.pdf"},
    ]
    assert eu_grants._documentos_convocatoria("<p>sin ese apartado</p>") == []
    # Horizonte Europa: sin ese apartado, el anexo de los criterios y los
    # modelos de solicitud y de evaluación.
    horizonte = (
        '<h4>2. Eligible Countries</h4><p>described in <a href="https://ejemplo.invalid/anexo-b.pdf">Annex B</a></p>'
        '<h4>5a. Evaluation and award: Award criteria, scoring and thresholds</h4>'
        '<p>are described in <a href="https://ejemplo.invalid/anexo-d.pdf">Annex D</a> of the Work Programme</p>'
        '<h4>5b. Evaluation and award: Submission</h4><p><a href="https://ejemplo.invalid/anexo-f.pdf">Annex F</a></p>'
        '<p><strong>Application form templates</strong></p>'
        '<p><a href="https://ejemplo.invalid/af.pdf">Standard application form (HE RIA, IA)</a></p>'
        '<p><a href="https://ejemplo.invalid/ef.pdf">Standard evaluation form (HE RIA, IA)</a></p>'
        '<p><a href="https://ejemplo.invalid/guia.pdf">HE Programme Guide</a></p>')
    assert eu_grants._documentos_convocatoria(horizonte) == [
        {"nombre": "Award criteria, scoring and thresholds (Annex D)", "url": "https://ejemplo.invalid/anexo-d.pdf"},
        {"nombre": "Standard application form (HE RIA, IA)", "url": "https://ejemplo.invalid/af.pdf"},
        {"nombre": "Standard evaluation form (HE RIA, IA)", "url": "https://ejemplo.invalid/ef.pdf"},
    ]


def test_calls_presupuesto_del_tema():
    import eu_grants
    resumen = json.dumps({"budgetTopicActionMap": {"1": [
        {"action": "TEMA-A - Project Grants", "expectedGrants": 2, "maxContribution": 500000, "budgetYearMap": {"2026": "600000", "2027": "400000"}},
        {"action": "TEMA-B - Project Grants", "expectedGrants": 9, "maxContribution": 9, "budgetYearMap": {"2026": "9"}}]}})
    assert eu_grants._presupuesto(resumen, "TEMA-A") == {
        "presupuesto": 1000000.0, "proyectos_previstos": 2, "subvencion_maxima": 500000.0}
    assert eu_grants._presupuesto("no es json", "TEMA-A") == {}
    assert eu_grants._presupuesto(None, "TEMA-A") == {}


def test_euskadi_lotes_de_la_ficha():
    def fila(etiqueta, valor):
        return (f'<div class="row"><div class="col-xs-12 col-sm-4 col-md-4">{etiqueta}</div>'
                f'<div class="col-xs-6 col-md-8"><p>{valor}</p></div></div>')
    pestana = (fila("Identificador", "Lote 1") + fila("Objeto del contrato", "Mantenimiento web")
               + fila("Valor estimado", "90.000") + fila("Presupuesto del contrato sin IVA", "45.000")
               + fila("Criterio", "Precio") + fila("Ponderaci&oacute;n", "35")
               + fila("Criterios de calidad (en su caso) Criterio", "Memoria t&eacute;cnica") + fila("Ponderaci&oacute;n", "65")
               + fila("Identificador", "Lote 2") + fila("Objeto del contrato", "Redes sociales")
               + fila("Presupuesto del contrato sin IVA", "12.345,67"))
    assert euskadi._lotes(pestana) == [
        {"id": "1", "nombre": "Mantenimiento web", "importe": 45000.0, "criterios": [
            {"descripcion": "Precio", "peso": 35.0, "tipo": "precio"},
            {"descripcion": "Memoria técnica", "peso": 65.0, "tipo": "otro"}]},
        {"id": "2", "nombre": "Redes sociales", "importe": 12345.67, "criterios": []},
    ]
    assert euskadi._lotes('<div class="col-xs-6 col-md-8">No existe informaci&oacute;n de lotes</div>') == []


def test_placsp_lotes():
    lotes = "".join(
        f"<cac:ProcurementProjectLot><cbc:ID>{n}</cbc:ID><cac:ProcurementProject><cbc:Name>{nombre}</cbc:Name>"
        f"<cac:BudgetAmount><cbc:TaxExclusiveAmount>{importe}</cbc:TaxExclusiveAmount></cac:BudgetAmount>"
        f"</cac:ProcurementProject></cac:ProcurementProjectLot>"
        for n, nombre, importe in ((1, "Gabinete de prensa", 20825), (2, "Comunicación digital", 46300)))
    texto = _como_en_plazo((FIXTURES / "placsp_adjudicacion.atom").read_text(encoding="utf-8"))
    texto = texto.replace("</cac:TenderingTerms>", "</cac:TenderingTerms>" + lotes, 1)
    item = placsp._parsear_entry(ET.fromstring(texto.encode("utf-8")).find("atom:entry", placsp.NS))
    assert item["lotes"] == [{"id": "1", "nombre": "Gabinete de prensa", "importe": "20825"},
                             {"id": "2", "nombre": "Comunicación digital", "importe": "46300"}]
