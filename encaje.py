# -*- coding: utf-8 -*-
"""
Nota de encaje de cada licitación con la agencia (0-10), con el motivo de
cada punto y los riesgos. Por reglas, con los datos que ya tiene la ficha:
categoría de servicio, lugar, cómo se puntúa, contratos anteriores
parecidos, importe y plazo. La lectura de pliegos con IA queda para el
asistente de propuestas.

El perfil de la agencia (servicios principales y provincias prioritarias)
NO va en el repositorio mientras sea público: se lee de la variable de
entorno PERFIL_AGENCIA (en GitHub, un secreto del repositorio) o del
fichero perfil_agencia.json, que git ignora. perfil_agencia.ejemplo.json
enseña el formato con valores inventados. Sin perfil, no hay nota.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

PERFIL_LOCAL = Path(__file__).resolve().parent / "perfil_agencia.json"

NOTA_BASE = 3
PUNTOS_SERVICIO_PRINCIPAL = 3
PUNTOS_SERVICIO_SECUNDARIO = 1.5
PUNTOS_PROVINCIA_PRIORITARIA = 2
PUNTOS_ESPANA = 1
PUNTOS_EXTRANJERA = 2         # se restan
IMPORTE_ALTO = 1_000_000      # a partir de aquí la solvencia exigida suele dejar fuera a una agencia mediana
DIAS_PLAZO_CORTO = 3
EDICIONES_MISMA_EMPRESA = 2   # la misma adjudicataria en las N últimas ediciones parecidas
# Poca competencia: provincias donde los concursos abiertos de agencia
# reciben de media un 20 % menos de ofertas que en España (medido el
# 2026-10-05 sobre 10.685 concursos desde 2023: España 4,2 de media;
# Gipuzkoa 2,8, Cantabria 3,2, La Rioja 3,3...). Con menos de
# MIN_CONCURSOS_PROVINCIA concursos la media dice poco.
PUNTOS_POCA_COMPETENCIA = 2
FACTOR_POCA_COMPETENCIA = 0.8
MIN_CONCURSOS_PROVINCIA = 30
ANIOS_COMPETENCIA = 3
PROCEDIMIENTOS_ABIERTOS = ("Abierto", "Abierto simplificado")


def leer_perfil() -> dict | None:
    texto = os.environ.get("PERFIL_AGENCIA")
    if not texto and PERFIL_LOCAL.exists():
        texto = PERFIL_LOCAL.read_text(encoding="utf-8")
    if not texto:
        return None
    try:
        perfil = json.loads(texto)
    except ValueError:
        print("[encaje] AVISO: PERFIL_AGENCIA no es un JSON válido: no se calcula la nota")
        return None
    return {
        "principales": set(perfil.get("servicios_principales") or []),
        "secundarios": set(perfil.get("servicios_secundarios") or []),
        "provincias": set(perfil.get("provincias_prioritarias") or []),
    }


def _comunidad_prioritaria(comunidad: str | None, provincias: set[str]) -> bool:
    """Si todas las provincias de la comunidad son prioritarias."""
    if not comunidad:
        return False
    import territorio  # noqa: E402

    suyas = set(territorio.PROVINCIAS_POR_COMUNIDAD.get(comunidad, []))
    return bool(suyas) and suyas <= provincias


def competencia_por_provincia(historico: dict | None, hoy: date | None = None) -> dict:
    """{"media": ofertas por concurso en España, "provincias": {provincia:
    (media, concursos)}} con los concursos abiertos (no menores) de los
    últimos ANIOS_COMPETENCIA años del histórico de adjudicaciones que
    publican cuántas ofertas recibieron. Solo provincias con al menos
    MIN_CONCURSOS_PROVINCIA concursos."""
    if not historico:
        return {}
    hoy = hoy or date.today()
    desde = str(hoy.year - ANIOS_COMPETENCIA)
    try:
        d = historico["dic"]
        abiertos = {i for i, p in enumerate(d["procedimiento"]) if p in PROCEDIMIENTOS_ABIERTOS}
        ofertas: dict[int, int] = {}
        for l in historico["lotes"]:  # [exp, empresa, fecha, importe, ofertas, pyme]
            if l[4]:
                ofertas[l[0]] = max(ofertas.get(l[0], 0), l[4])
        por_provincia: dict[str, list[int]] = {}
        for i, e in enumerate(historico["exp"]):
            if e[6] or e[5] not in abiertos or i not in ofertas or e[10][:4] < desde or len(e) <= 12:
                continue
            provincia = d["lugar"][e[12]][0]
            if provincia:
                por_provincia.setdefault(provincia, []).append(ofertas[i])
    except (KeyError, IndexError, TypeError):
        return {}
    todas = [x for v in por_provincia.values() for x in v]
    if not todas:
        return {}
    return {"media": sum(todas) / len(todas),
            "provincias": {p: (sum(v) / len(v), len(v)) for p, v in por_provincia.items() if len(v) >= MIN_CONCURSOS_PROVINCIA}}


def _miles(valor: float) -> str:
    return f"{round(valor):,}".replace(",", ".")


def _decimal(valor: float) -> str:
    return f"{valor:.1f}".replace(".", ",")


def _pct(valor: float) -> str:
    return f"{valor:g}".replace(".", ",") + " %"


def _frase_precio(cr: dict) -> str:
    """Cuánto pesa el precio, dicho con lo que la fuente permite afirmar.

    Solo el Estado separa el juicio de valor de las fórmulas; en Euskadi y
    TED se sabe el precio y "el resto", que puede ir en parte por fórmula.
    Con presupuesto cerrado el precio no puntúa (0 %)."""
    precio, juicio = cr["precio"], cr.get("juicio")
    if juicio:
        if precio == 0 and juicio >= 100:
            return "El precio no puntúa: todo es propuesta técnica"
        if precio == 0:
            return f"El precio no puntúa: la propuesta técnica vale el {_pct(juicio)} y el resto va por fórmulas"
        if juicio >= precio:
            return f"Pesa la propuesta: el juicio de valor cuenta el {_pct(juicio)} y el precio el {_pct(precio)}"
        return f"El precio cuenta el {_pct(precio)} y la propuesta técnica el {_pct(juicio)}"
    if precio == 0:
        return "El precio no puntúa"
    return f"El precio cuenta el {_pct(precio)}"


def nota(r: dict, perfil: dict, hoy: date | None = None, competencia: dict | None = None) -> dict:
    """{"nota": 0-10, "motivos": [...], "riesgos": [...]} de una licitación.
    competencia: lo que devuelve competencia_por_provincia."""
    hoy = hoy or date.today()
    puntos = NOTA_BASE
    motivos: list[str] = []
    riesgos: list[str] = []

    categorias = r.get("categorias") or []
    principales = [c for c in categorias if c in perfil["principales"]]
    secundarias = [c for c in categorias if c in perfil["secundarios"]]
    if principales:
        puntos += PUNTOS_SERVICIO_PRINCIPAL
        motivos.append("Servicio principal de la agencia: " + ", ".join(principales))
    elif secundarias:
        puntos += PUNTOS_SERVICIO_SECUNDARIO
        motivos.append("Servicio que la agencia también hace: " + ", ".join(secundarias))
    else:
        riesgos.append("No es uno de los servicios de la agencia")

    espanola = r.get("pais_territorio") in ("España", "País Vasco")
    if r.get("provincia") in perfil["provincias"]:
        puntos += PUNTOS_PROVINCIA_PRIORITARIA
        motivos.append(f"Provincia prioritaria: {r['provincia']}")
    elif not r.get("provincia") and _comunidad_prioritaria(r.get("comunidad"), perfil["provincias"]):
        # Solo se sabe la comunidad (organismo de ámbito autonómico), pero
        # todas sus provincias son prioritarias.
        puntos += PUNTOS_PROVINCIA_PRIORITARIA
        motivos.append(f"Comunidad prioritaria: {r['comunidad']}")
    elif espanola:
        puntos += PUNTOS_ESPANA
        motivos.append("En España" + (f" ({r['provincia']})" if r.get("provincia") else ""))
    else:
        # Sin esto, una extranjera de un servicio principal sacaba un 6,
        # casi lo mismo que una española fuera de las provincias prioritarias.
        puntos -= PUNTOS_EXTRANJERA
        riesgos.append(f"Fuera de España ({r.get('pais_territorio')}): idioma y presencia local")

    # Poca competencia en la provincia: se suma a lo anterior.
    dato = ((competencia or {}).get("provincias") or {}).get(r.get("provincia"))
    if dato and dato[0] <= FACTOR_POCA_COMPETENCIA * competencia["media"]:
        puntos += PUNTOS_POCA_COMPETENCIA
        motivos.append(f"Poca competencia en {r['provincia']}: {_decimal(dato[0])} ofertas de media por concurso "
                       f"(España: {_decimal(competencia['media'])})")

    cr = r.get("criterios")
    if cr and cr.get("precio") is not None:
        precio = cr["precio"]
        propuesta = (cr.get("juicio") or 0) > 0 or (cr.get("resto") or 0) > 0
        if precio <= 50 and propuesta:
            puntos += 2
            motivos.append(_frase_precio(cr))
        elif precio <= 70:
            puntos += 1
            motivos.append(_frase_precio(cr))
        elif precio >= 100:
            puntos -= 1
            riesgos.append("Solo cuenta el precio: gana la oferta más barata")

    # La misma empresa en las últimas ediciones parecidas del organismo.
    ant = [a for a in (r.get("antecedentes") or []) if a.get("empresas")]
    if len(ant) >= EDICIONES_MISMA_EMPRESA:
        ganadoras = {a["empresas"][0]["id"] for a in ant[:EDICIONES_MISMA_EMPRESA]}
        if len(ganadoras) == 1:
            puntos -= 1
            riesgos.append(f"La ha ganado {ant[0]['empresas'][0]['nombre']} en las {EDICIONES_MISMA_EMPRESA} últimas ediciones")

    if r.get("revisar_manual"):
        puntos -= 1
        riesgos.append("Mezcla servicios de agencia con otros (limpieza, obra...)")

    presupuesto = r.get("presupuesto_valor")
    if presupuesto and presupuesto >= IMPORTE_ALTO and espanola:
        riesgos.append(f"Importe alto ({_miles(presupuesto)} €): revisar la solvencia que piden")

    try:
        dias = (date.fromisoformat((r.get("fecha_limite") or "")[:10]) - hoy).days
    except ValueError:
        dias = None
    if dias is not None and 0 <= dias < DIAS_PLAZO_CORTO:
        puntos -= 1
        riesgos.append("Cierra hoy" if dias == 0 else f"Cierra en {dias} día{'s' if dias > 1 else ''}: poco tiempo para preparar la oferta")

    return {"nota": max(0, min(10, round(puntos))), "motivos": motivos, "riesgos": riesgos}


def anadir_notas(registros: list[dict], hoy: date | None = None, historico: dict | None = None) -> int:
    """Añade "encaje" a cada licitación. Devuelve cuántas se han puntuado.
    historico: el histórico completo de adjudicaciones, para la competencia
    por provincia (sin él, la nota no la tiene en cuenta)."""
    perfil = leer_perfil()
    if perfil is None:
        print("[encaje] Sin perfil de la agencia (PERFIL_AGENCIA o perfil_agencia.json): sin nota de encaje")
        return 0
    competencia = competencia_por_provincia(historico, hoy)
    if competencia:
        pocas = sorted(p for p, (media, _) in competencia["provincias"].items()
                       if media <= FACTOR_POCA_COMPETENCIA * competencia["media"])
        print(f"[encaje] provincias con poca competencia: {len(pocas)} ({', '.join(pocas)})")
    n = 0
    for r in registros:
        if r.get("tipo_registro") == "licitacion":
            r["encaje"] = nota(r, perfil, hoy, competencia)
            n += 1
    return n
