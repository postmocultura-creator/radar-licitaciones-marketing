# -*- coding: utf-8 -*-
"""Nota de encaje de cada licitación con la agencia, con un perfil inventado."""
import json
from datetime import date

import encaje

PERFIL = {"principales": {"Redes sociales / community management"},
          "secundarios": {"Producción de vídeo / contenido audiovisual"},
          "provincias": {"Zaragoza"}}
HOY = date(2026, 10, 5)


def licitacion(**extra):
    base = {"tipo_registro": "licitacion", "categorias": ["Redes sociales / community management"],
            "pais_territorio": "España", "provincia": "Zaragoza", "fecha_limite": "2026-10-20",
            "presupuesto_valor": 60000.0}
    base.update(extra)
    return base


def test_la_que_mejor_encaja():
    n = encaje.nota(licitacion(criterios={"precio": 40, "formulas": 10, "juicio": 50}), PERFIL, HOY)
    # 3 de base + 3 servicio principal + 2 provincia + 2 pesa la propuesta.
    assert n["nota"] == 10 and n["riesgos"] == []
    assert n["motivos"] == ["Servicio principal de la agencia: Redes sociales / community management",
                            "Provincia prioritaria: Zaragoza",
                            "Pesa la propuesta: el juicio de valor cuenta el 50 % y el precio el 40 %"]


def test_frase_del_precio_segun_lo_que_dice_la_fuente():
    frase = encaje._frase_precio
    # Presupuesto cerrado: el precio no puntúa y casi todo va por fórmulas.
    assert frase({"precio": 0, "formulas": 72, "juicio": 28}) == (
        "El precio no puntúa: la propuesta técnica vale el 28 % y el resto va por fórmulas")
    assert frase({"precio": 0, "formulas": 0, "juicio": 100}) == "El precio no puntúa: todo es propuesta técnica"
    assert frase({"precio": 60, "formulas": 10, "juicio": 30}) == "El precio cuenta el 60 % y la propuesta técnica el 30 %"
    # Euskadi y TED: solo se sabe el precio y "el resto".
    assert frase({"precio": 45, "resto": 55}) == "El precio cuenta el 45 %"
    assert frase({"precio": 0, "resto": 100}) == "El precio no puntúa"
    assert frase({"precio": 12.5, "resto": 87.5}) == "El precio cuenta el 12,5 %"


def test_riesgos_que_restan():
    n = encaje.nota(licitacion(
        categorias=["Producción de vídeo / contenido audiovisual"], provincia="Sevilla", fecha_limite="2026-10-06",
        criterios={"precio": 100, "resto": 0}, revisar_manual=True, presupuesto_valor=2_000_000.0,
        antecedentes=[{"empresas": [{"id": 7, "nombre": "Agencia Uno SL"}]}, {"empresas": [{"id": 7, "nombre": "Agencia Uno SL"}]}]),
        PERFIL, HOY)
    # 3 + 1,5 secundario + 1 España - 1 solo precio - 1 misma empresa - 1 mezcla - 1 cierra mañana = 1,5 -> 2
    assert n["nota"] == 2
    assert n["riesgos"] == [
        "Solo cuenta el precio: gana la oferta más barata",
        "La ha ganado Agencia Uno SL en las 2 últimas ediciones",
        "Mezcla servicios de agencia con otros (limpieza, obra...)",
        "Importe alto (2.000.000 €): revisar la solvencia que piden",
        "Cierra en 1 día: poco tiempo para preparar la oferta"]


def test_extranjera_y_fuera_de_servicio():
    n = encaje.nota(licitacion(categorias=["Atención al cliente / soporte"], pais_territorio="Francia", provincia=None),
                    PERFIL, HOY)
    assert n["nota"] == 1  # 3 de base - 2 por estar fuera de España
    assert n["riesgos"] == ["No es uno de los servicios de la agencia", "Fuera de España (Francia): idioma y presencia local"]


def test_comunidad_con_todas_sus_provincias_prioritarias():
    perfil = dict(PERFIL, provincias={"Álava", "Gipuzkoa", "Bizkaia"})
    vasca = encaje.nota(licitacion(provincia=None, comunidad="País Vasco"), perfil, HOY)
    assert "Comunidad prioritaria: País Vasco" in vasca["motivos"]
    # Si falta una de sus provincias, no cuenta.
    perfil["provincias"] = {"Álava", "Bizkaia"}
    assert "Comunidad prioritaria: País Vasco" not in encaje.nota(licitacion(provincia=None, comunidad="País Vasco"), perfil, HOY)["motivos"]


def test_poca_competencia_en_la_provincia():
    def exp(i, provincia, proc=0):
        # [id, titulo, organismo, euskadi, tipo, proc, menor, mascara, enlace, ted, actualizado, presupuesto, lugar]
        return [str(i), "t", 0, 0, 0, proc, 0, 0, "", 0, "2025-01-01", None, provincia]
    historico = {"dic": {"procedimiento": ["Abierto", "Negociado sin publicidad"], "lugar": [["Soria", "Castilla y León"], ["Madrid", "Madrid"]]},
                 "exp": [], "lotes": []}
    # 40 concursos abiertos en Soria con 2 ofertas y 40 en Madrid con 6;
    # los negociados (1 oferta) no cuentan.
    for i in range(40):
        historico["exp"].append(exp(len(historico["exp"]), 0)); historico["lotes"].append([len(historico["exp"]) - 1, 0, "2025-01-01", 1, 2, 1])
        historico["exp"].append(exp(len(historico["exp"]), 1)); historico["lotes"].append([len(historico["exp"]) - 1, 0, "2025-01-01", 1, 6, 1])
        historico["exp"].append(exp(len(historico["exp"]), 0, proc=1)); historico["lotes"].append([len(historico["exp"]) - 1, 0, "2025-01-01", 1, 1, 1])
    competencia = encaje.competencia_por_provincia(historico, HOY)
    assert competencia["media"] == 4 and competencia["provincias"] == {"Soria": (2, 40), "Madrid": (6, 40)}
    soria = encaje.nota(licitacion(provincia="Soria"), PERFIL, HOY, competencia)
    assert "Poca competencia en Soria: 2,0 ofertas de media por concurso (España: 4,0)" in soria["motivos"]
    madrid = encaje.nota(licitacion(provincia="Madrid"), PERFIL, HOY, competencia)
    assert soria["nota"] == madrid["nota"] + 2


def test_sin_perfil_no_hay_nota(monkeypatch, tmp_path):
    monkeypatch.delenv("PERFIL_AGENCIA", raising=False)
    monkeypatch.setattr(encaje, "PERFIL_LOCAL", tmp_path / "no_existe.json")
    registros = [licitacion()]
    assert encaje.anadir_notas(registros) == 0 and "encaje" not in registros[0]


def test_perfil_desde_el_secreto(monkeypatch, tmp_path):
    monkeypatch.setattr(encaje, "PERFIL_LOCAL", tmp_path / "no_existe.json")
    monkeypatch.setenv("PERFIL_AGENCIA", json.dumps({"servicios_principales": ["Redes sociales / community management"],
                                                     "provincias_prioritarias": ["Zaragoza"]}))
    registros = [licitacion(), {"tipo_registro": "adjudicacion"}]
    assert encaje.anadir_notas(registros, HOY) == 1
    assert registros[0]["encaje"]["nota"] == 8 and "encaje" not in registros[1]
