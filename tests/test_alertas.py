# -*- coding: utf-8 -*-
"""Alerta diaria por correo: qué cuenta como nuevo, qué se recuerda y qué se
envía. Sin red: el envío SMTP se sustituye por una función que lo apunta."""
import json
from datetime import date

import pytest

import alertas


def registro(id_, tipo="licitacion", primera="2026-10-05", **extra):
    base = {"id": id_, "tipo_registro": tipo, "titulo": f"Título {id_}", "organismo": "Ayuntamiento de Ejemplo",
            "pais_territorio": "España", "fecha_primera_aparicion": primera, "fecha_limite": "2026-10-20",
            "presupuesto_valor": 50000.0, "presupuesto_display": "50,000 EUR", "enlace": "https://ejemplo.es/a"}
    base.update(extra)
    return base


@pytest.fixture
def rutas(tmp_path, monkeypatch):
    monkeypatch.setattr(alertas, "DATOS", tmp_path / "tenders.json")
    monkeypatch.setattr(alertas, "ENVIADAS", tmp_path / "alertas_enviadas.json")
    monkeypatch.setattr(alertas, "PRUEBA", tmp_path / "prueba.html")
    for clave in ("ALERTAS_SMTP_SERVIDOR", "ALERTAS_SMTP_USUARIO", "ALERTAS_SMTP_CLAVE", "ALERTAS_DE", "ALERTAS_PARA"):
        monkeypatch.setenv(clave, "x@ejemplo.es")
    enviados = []
    monkeypatch.setattr(alertas, "enviar", lambda conf, asunto, texto, html: enviados.append(asunto))
    monkeypatch.setattr(alertas.sys, "argv", ["alertas.py", "--hoy", "2026-10-05"])
    return tmp_path, enviados


def test_primera_vez_solo_lo_visto_hoy_y_despues_lo_no_enviado():
    regs = [registro("a"), registro("b", primera="2026-09-30")]
    assert [r["id"] for r in alertas.novedades(regs, None, "2026-10-05")] == ["a"]
    # Con estado, lo que no se ha enviado nunca, sea del día que sea.
    assert [r["id"] for r in alertas.novedades(regs, {"a"}, "2026-10-05")] == ["b"]


def test_envia_y_recuerda_lo_enviado(rutas):
    carpeta, enviados = rutas
    (carpeta / "tenders.json").write_text(json.dumps([registro("a"), registro("b", primera="2026-09-30")]), encoding="utf-8")
    alertas.main()
    assert enviados == ["1 licitación nueva, 5 oct: 1 en el resto de España"]
    # La primera vez se marca todo lo vigente: "b" no se enviará nunca.
    assert json.loads((carpeta / "alertas_enviadas.json").read_text(encoding="utf-8"))["ids"] == ["a", "b"]
    # Al día siguiente: "c" es nueva; "b" desaparece del radar y se olvida.
    (carpeta / "tenders.json").write_text(json.dumps([registro("a"), registro("c", primera="2026-10-06")]), encoding="utf-8")
    alertas.main()
    assert len(enviados) == 2
    assert json.loads((carpeta / "alertas_enviadas.json").read_text(encoding="utf-8"))["ids"] == ["a", "c"]
    # Sin novedades no se manda nada.
    alertas.main()
    assert len(enviados) == 2


def test_si_el_envio_falla_no_marca_nada(rutas, monkeypatch):
    carpeta, _ = rutas
    (carpeta / "tenders.json").write_text(json.dumps([registro("a")]), encoding="utf-8")

    def falla(*args):
        raise alertas.smtplib.SMTPAuthenticationError(535, b"clave mal")

    monkeypatch.setattr(alertas, "enviar", falla)
    alertas.main()
    assert not (carpeta / "alertas_enviadas.json").exists()


def test_prueba_con_lo_publicado_sin_marcar_nada(rutas, monkeypatch):
    carpeta, enviados = rutas
    # Sin data/tenders.json: lee lo publicado en el dashboard.
    publicado = carpeta / "tenders-data.js"
    publicado.write_text("window.TENDERS_DATA = " + json.dumps([registro("a", primera="2026-10-03")]) + ";\n", encoding="utf-8")
    monkeypatch.setattr(alertas, "DATOS_PUBLICADOS", publicado)
    monkeypatch.setattr(alertas.sys, "argv", ["alertas.py", "--sin-guardar", "--hoy", "2026-10-05"])
    alertas.main()
    # Hoy no hay nada nuevo: la prueba manda lo del último día con novedades.
    assert enviados == ["[Prueba] 1 licitación nueva, 5 oct: 1 en el resto de España"]
    assert not (carpeta / "alertas_enviadas.json").exists()


def test_sin_configuracion_no_envia_ni_marca(rutas, monkeypatch):
    carpeta, enviados = rutas
    monkeypatch.delenv("ALERTAS_PARA")
    (carpeta / "tenders.json").write_text(json.dumps([registro("a")]), encoding="utf-8")
    alertas.main()
    assert enviados == [] and not (carpeta / "alertas_enviadas.json").exists()


def test_solo_licitaciones_euskadi_espana_europa(rutas):
    carpeta, enviados = rutas
    (carpeta / "tenders.json").write_text(json.dumps([
        registro("a"), registro("adj", tipo="adjudicacion"), registro("call", tipo="convocatoria_ue")]), encoding="utf-8")
    alertas.main()
    assert enviados == ["1 licitación nueva, 5 oct: 1 en el resto de España"]
    # Solo se recuerdan licitaciones: lo demás no va en el correo.
    assert json.loads((carpeta / "alertas_enviadas.json").read_text(encoding="utf-8"))["ids"] == ["a"]


def test_correo_por_bloques_con_datos_de_la_ficha():
    nuevas = [
        registro("de", pais_territorio="Alemania", presupuesto_valor=90000.0, presupuesto_display="90,000 SEK"),
        registro("es", titulo="Redes sociales <municipales>", provincia="Sevilla", comunidad="Andalucía",
                 fecha_limite="2026-10-08", hora_limite="14:00",
                 criterios={"precio": 30, "formulas": 10, "juicio": 60},
                 lotes=[{"id": "1"}, {"id": "2"}],
                 antecedentes=[{"anio": "2024", "importe": 40000, "empresas": [{"id": 1, "nombre": "Agencia Uno SL"}]}]),
        registro("eus", fuente="Euskadi", pais_territorio="País Vasco", provincia="Bizkaia", comunidad="País Vasco"),
        # Un organismo vasco que llega por TED también va en Euskadi.
        registro("ted-eus", fuente="UE", comunidad="País Vasco"),
    ]
    hoy = date(2026, 10, 5)
    assert alertas.asunto(nuevas, hoy) == "4 licitaciones nuevas, 5 oct: 2 en Euskadi, 1 en el resto de España, 1 en Europa"
    cuerpo = alertas.cuerpo_html(nuevas, hoy)
    assert cuerpo.index("Euskadi · 2") < cuerpo.index("Resto de España · 1") < cuerpo.index("Europa · 1")
    assert "Redes sociales &lt;municipales&gt;" in cuerpo          # escapado
    assert "50.000 € (sin IVA)" in cuerpo and "90.000 SEK" in cuerpo
    assert "Sevilla, Andalucía" in cuerpo and "Bizkaia, País Vasco" in cuerpo
    assert "8 oct 2026, 14:00 · quedan 3 días" in cuerpo
    assert "Precio 30 % · puntúa la propuesta" in cuerpo and "2 lotes" in cuerpo
    assert "Agencia Uno SL (2024, 40.000 €)" in cuerpo
    assert alertas.DASHBOARD + "#/licitaciones/abiertas?id=es" in cuerpo
