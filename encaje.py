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


def _miles(valor: float) -> str:
    return f"{round(valor):,}".replace(",", ".")


def nota(r: dict, perfil: dict, hoy: date | None = None) -> dict:
    """{"nota": 0-10, "motivos": [...], "riesgos": [...]} de una licitación."""
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

    cr = r.get("criterios")
    if cr and cr.get("precio") is not None:
        precio = cr["precio"]
        propuesta = (cr.get("juicio") or 0) > 0 or (cr.get("resto") or 0) > 0
        if precio <= 50 and propuesta:
            puntos += 2
            motivos.append(f"Pesa la propuesta: el precio cuenta el {precio} %")
        elif precio <= 70:
            puntos += 1
            motivos.append(f"El precio cuenta el {precio} %")
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


def anadir_notas(registros: list[dict], hoy: date | None = None) -> int:
    """Añade "encaje" a cada licitación. Devuelve cuántas se han puntuado."""
    perfil = leer_perfil()
    if perfil is None:
        print("[encaje] Sin perfil de la agencia (PERFIL_AGENCIA o perfil_agencia.json): sin nota de encaje")
        return 0
    n = 0
    for r in registros:
        if r.get("tipo_registro") == "licitacion":
            r["encaje"] = nota(r, perfil, hoy)
            n += 1
    return n
