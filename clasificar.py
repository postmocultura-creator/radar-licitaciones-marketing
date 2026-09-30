# -*- coding: utf-8 -*-
"""
Clasificación en dos capas de las licitaciones extraídas por los scrapers.

Capa 1 (CPV): se usa solo para acotar QUÉ se trae de cada fuente (la query
de TED, y de forma orientativa en Euskadi/PLACSP) — no decide por sí sola
si una licitación entra en el dataset final. Se probó usarla como criterio
de inclusión ("CPV amplio pero sin texto que lo confirme -> revisar
manual") y se descartó con datos reales: el CPV público es demasiado
grosero (division/grupo, no la licitación concreta) y esa vía colaba
sobre todo contratos de ISP/banda ancha, consultoría de sistemas genérica
y evaluaciones de políticas públicas, no servicios de agencia. Ese bolsón
generaba cientos de falsos positivos sin ninguna señal real de tratarse
de una agencia.

Capa 2 (texto, la que decide): busca las keywords de config.CATEGORIAS en
el título/objeto. Es la ÚNICA fuente de verdad para incluir o no una
licitación — si el título no confirma con texto una categoría de agencia,
no entra, tenga el CPV que tenga.

Regla de decisión (ver config.py para tocar las listas):
  - Si ninguna categoría de texto encaja -> se descarta. No es ambiguo,
    es simplemente que el título no dice nada de marketing/publicidad.
  - Si el título contiene un término de SERVICIOS_NO_OFRECIDOS (imprenta,
    impresión, artes gráficas...) -> se descarta directamente, aunque el
    resto del contrato sí sea de agencia. A petición explícita del
    usuario: no le interesa ofrecer producción física/imprenta, así que
    ni siquiera se muestra para revisión manual.
  - Si SÍ encaja una categoría de texto pero el título también contiene un
    término de EXCLUSIONES (p. ej. el contrato mezcla comunicación con
    limpieza) -> se incluye, pero marcada "revisar_manual": es un caso
    real y concreto de mezcla de servicios, no una interpretación dudosa
    del CPV.
  - En cualquier otro caso con categoría de texto -> se incluye limpio.

Entrada: el último data/raw/<fuente>_*.json de cada fuente (se ignoran los
que terminan en _error.json).
Salida: data/clasificado.json, con un registro por licitación que añade
"fuente", "categorias" y "revisar_manual" sin perder los campos originales
de cada fuente (normalizar.py se encarga de unificar el esquema final).

Fallback por fuente caída: si una fuente no trae crudo nuevo esta pasada
(scraper caído, API externa con timeout tras agotar sus reintentos...), en
vez de vaciar esa categoría del dashboard entero ese día, se reutilizan los
últimos clasificados buenos conocidos de esa fuente+tipo_registro, cacheados
en data/ultimo_bueno_por_fuente.json (persistido entre ejecuciones, igual
que data/primera_aparicion.json). No hace falta limitar cuántos días se
puede reutilizar un fallback: los propios filtros de ventana temporal de
normalizar.py (fecha_limite vencida, más de N días desde la publicación)
acaban descartando esos registros por su cuenta según pasan los días, igual
que descartarían un registro fresco cuyo plazo ya venció.

Ejecutar:
    python clasificar.py
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

import config

RAW_DIR = Path(__file__).resolve().parent / "data" / "raw"
SALIDA = Path(__file__).resolve().parent / "data" / "clasificado.json"
CACHE_FUENTES = Path(__file__).resolve().parent / "data" / "ultimo_bueno_por_fuente.json"

_CACHE_PATRONES: dict[str, re.Pattern] = {}


# "procedimiento/proceso negociado con/sin publicidad" y "publicidad
# obligatoria" son jerga jurídica del TIPO DE PROCEDIMIENTO (si el anuncio
# de licitación se publica o no), no una señal de que el contrato sea de
# servicios de publicidad. Detectado con datos reales: generaba falsos
# positivos en seguros de vehículos, obra civil (vía ciclista)... cualquier
# cosa tramitada con publicidad obligatoria del anuncio. Se limpia antes de
# comparar contra las keywords.
_RUIDO_PROCEDIMENTAL = re.compile(
    r"\b(procedimiento|proceso) (negociado|abierto|restringido) (con|sin) publicidad\b"
    r"|\bpublicidad obligatoria\b"
)


def _normalizar_texto(texto: str) -> str:
    if not texto:
        return ""
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    minusculas = sin_acentos.lower()
    return _RUIDO_PROCEDIMENTAL.sub(" ", minusculas)


def _contiene_keyword(texto_norm: str, keyword: str) -> bool:
    """Coincidencia por palabra/frase completa, no subcadena: 'seo' no debe
    encajar dentro de 'museo', 'aseo', 'deseo'... (bug real detectado con
    datos en vivo: 'seo' como subcadena disparaba falsos positivos en
    licitaciones de museos). Usa límites de palabra (\\b) vía regex."""
    patron = _CACHE_PATRONES.get(keyword)
    if patron is None:
        patron = re.compile(r"\b" + re.escape(keyword) + r"\b")
        _CACHE_PATRONES[keyword] = patron
    return patron.search(texto_norm) is not None


def _ultimo_raw(fuente_prefijo: str) -> Path | None:
    # El patrón exige un dígito justo después del guion bajo (el timestamp)
    # para que "euskadi_*.json"/"ted_*.json" no capturen también
    # "euskadi_adjudicaciones_*.json"/"ted_adjudicaciones_*.json" -mismo
    # prefijo de fuente, dataset distinto- (bug real detectado antes de
    # lanzar nada: sin esto, el glob de "euskadi" a veces elegía como "más
    # reciente" el crudo de adjudicaciones en vez del de avisos).
    candidatos = sorted(
        p for p in RAW_DIR.glob(f"{fuente_prefijo}_[0-9]*.json") if not p.name.endswith("_error.json")
    )
    return candidatos[-1] if candidatos else None


def _titulo_ted(item: dict) -> str:
    titulos = item.get("notice-title") or {}
    if isinstance(titulos, dict):
        return titulos.get("spa") or titulos.get("eng") or next(iter(titulos.values()), "")
    return str(titulos)


def clasificar_texto(titulo: str, cpv_list: list[str]) -> dict:
    texto_norm = _normalizar_texto(titulo)
    categorias = [
        categoria
        for categoria, keywords in config.CATEGORIAS.items()
        if any(_contiene_keyword(texto_norm, kw) for kw in keywords)
    ]

    if not categorias:
        return {"incluir": False, "categorias": [], "revisar_manual": False}

    tiene_servicio_no_ofrecido = any(_contiene_keyword(texto_norm, kw) for kw in config.SERVICIOS_NO_OFRECIDOS)
    if tiene_servicio_no_ofrecido:
        return {"incluir": False, "categorias": [], "revisar_manual": False}

    tiene_exclusion = any(_contiene_keyword(texto_norm, kw) for kw in config.EXCLUSIONES)

    return {"incluir": True, "categorias": categorias, "revisar_manual": tiene_exclusion}


def clasificar_ted(items: list[dict]) -> list[dict]:
    salida = []
    for item in items:
        titulo = _titulo_ted(item)
        cpv_list = item.get("classification-cpv") or []
        resultado = clasificar_texto(titulo, cpv_list)
        if not resultado["incluir"]:
            continue
        salida.append({"fuente": "UE", "original": item, "titulo": titulo, "cpv": cpv_list, **resultado})
    return salida


# Estados de PLACSP que representan una convocatoria todavía abierta a
# presentar oferta. Verificado contra datos reales: sin este filtro se
# colaban expedientes "EV" (en evaluación, el plazo ya cerró), "RES"
# (resuelto) y "ADJ" (adjudicado, ya tiene ganador) como si fueran
# oportunidades nuevas — precisamente porque muchos de ellos no publican
# fecha límite y el filtro de ventana temporal caía entonces en la fecha
# de actualización del expediente, que se toca aunque ya esté cerrado
# (mismo problema de fondo que ya se documentó para las fechas). "PRE"
# (información previa) tampoco es una convocatoria abierta todavía.
PLACSP_ESTADOS_ABIERTOS = {"PUB"}


def clasificar_placsp(items: list[dict]) -> list[dict]:
    salida = []
    for item in items:
        if item.get("estado") not in PLACSP_ESTADOS_ABIERTOS:
            continue
        titulo = item.get("titulo") or ""
        cpv_list = item.get("cpv") or []
        resultado = clasificar_texto(titulo, cpv_list)
        if not resultado["incluir"]:
            continue
        salida.append({"fuente": "Estado", "original": item, "titulo": titulo, "cpv": cpv_list, **resultado})
    return salida


def clasificar_euskadi(items: list[dict]) -> list[dict]:
    salida = []
    for item in items:
        # Un "contrato menor" (minorContract=true) se adjudica DIRECTAMENTE
        # por la administración, sin proceso competitivo: no es una
        # oportunidad a la que una agencia pueda presentarse, es la
        # publicación por transparencia de un contrato que ya se ha
        # cerrado con un proveedor elegido de antemano. Se probó
        # recuperarlos como inteligencia de mercado (quién compra qué a
        # quién) y se quitó a petición del usuario: en el dashboard
        # aparecían SIEMPRE como "Adjudicado" -es la definición legal de
        # contrato menor, no hay estado "en plazo" posible- y no son una
        # oportunidad real, solo ruido.
        if item.get("minorContract"):
            continue
        titulo = item.get("object") or ""
        cpv_list: list[str] = []  # Euskadi no expone CPV, ver docstring del módulo
        resultado = clasificar_texto(titulo, cpv_list)
        if not resultado["incluir"]:
            continue
        salida.append({"fuente": "Euskadi", "original": item, "titulo": titulo, "cpv": cpv_list, **resultado})
    return salida


# ---------------------------------------------------------------------------
# Adjudicaciones (Fase 1): misma capa de texto que las licitaciones abiertas
# (config.CATEGORIAS vía clasificar_texto), pero sobre avisos de RESULTADO en
# vez de avisos de licitación. El criterio de inclusión es idéntico a
# propósito -no hace falta una taxonomía nueva, es el mismo tipo de
# contrato, solo que ya adjudicado-.
# ---------------------------------------------------------------------------

def clasificar_ted_adjudicaciones(items: list[dict]) -> list[dict]:
    salida = []
    for item in items:
        titulo = _titulo_ted(item)
        cpv_list = item.get("classification-cpv") or []
        resultado = clasificar_texto(titulo, cpv_list)
        if not resultado["incluir"]:
            continue
        salida.append({"fuente": "UE", "original": item, "titulo": titulo, "cpv": cpv_list, **resultado})
    return salida


# Estados PLACSP que representan un expediente ya resuelto con ganador
# conocido. "ADJ" (adjudicado) y "RES" (formalizado/resuelto) son los dos
# estados en los que, con datos reales, aparece el bloque TenderResult
# relleno; se exige además que empresa_adjudicataria no sea None por si
# algún expediente está en ese estado sin el bloque poblado todavía.
PLACSP_ESTADOS_ADJUDICADOS = {"ADJ", "RES"}


def clasificar_placsp_adjudicaciones(items: list[dict]) -> list[dict]:
    salida = []
    for item in items:
        if item.get("estado") not in PLACSP_ESTADOS_ADJUDICADOS:
            continue
        if not item.get("empresa_adjudicataria"):
            continue
        titulo = item.get("titulo") or ""
        cpv_list = item.get("cpv") or []
        resultado = clasificar_texto(titulo, cpv_list)
        if not resultado["incluir"]:
            continue
        salida.append({"fuente": "Estado", "original": item, "titulo": titulo, "cpv": cpv_list, **resultado})
    return salida


def clasificar_euskadi_adjudicaciones(items: list[dict]) -> list[dict]:
    salida = []
    for item in items:
        titulo = item.get("object") or ""
        cpv = item.get("CPV")
        cpv_list = [cpv] if cpv else []
        resultado = clasificar_texto(titulo, cpv_list)
        if not resultado["incluir"]:
            continue
        salida.append({"fuente": "Euskadi", "original": item, "titulo": titulo, "cpv": cpv_list, **resultado})
    return salida


# ---------------------------------------------------------------------------
# Contratos menores por vencer (Fase 2). Misma capa de texto que el resto;
# la ventana de "está a punto de terminar" (config.DIAS_AVISO_CONTRATO_MENOR)
# se aplica en normalizar.py una vez calculada fecha_fin_estimada, no aquí.
# ---------------------------------------------------------------------------

def clasificar_placsp_contratos_menores(items: list[dict]) -> list[dict]:
    salida = []
    for item in items:
        if not item.get("empresa_adjudicataria"):
            continue
        titulo = item.get("titulo") or ""
        cpv_list = item.get("cpv") or []
        resultado = clasificar_texto(titulo, cpv_list)
        if not resultado["incluir"]:
            continue
        salida.append({"fuente": "Estado", "original": item, "titulo": titulo, "cpv": cpv_list, **resultado})
    return salida


def clasificar_euskadi_contratos_menores(items: list[dict]) -> list[dict]:
    salida = []
    for item in items:
        if not item.get("minorContract"):
            continue
        if not item.get("contractEndDate"):
            continue
        titulo = item.get("object") or ""
        cpv = item.get("CPV")
        cpv_list = [cpv] if cpv else []
        resultado = clasificar_texto(titulo, cpv_list)
        if not resultado["incluir"]:
            continue
        salida.append({"fuente": "Euskadi", "original": item, "titulo": titulo, "cpv": cpv_list, **resultado})
    return salida


# ---------------------------------------------------------------------------
# Calls for proposals UE (Fase 3). Misma mecánica de coincidencia por
# palabra/frase completa que el resto (_contiene_keyword), pero sobre
# config.CATEGORIAS_CALLS_UE (inglés) y sobre título + texto de "Expected
# Outcome"/destino de la convocatoria -no hay CPV en subvenciones, y con
# solo el título el recall es demasiado bajo, ver scrapers/eu_grants.py-.
# ---------------------------------------------------------------------------

def clasificar_texto_calls_ue(texto: str) -> dict:
    texto_norm = _normalizar_texto(texto)
    categorias = [
        categoria
        for categoria, keywords in config.CATEGORIAS_CALLS_UE.items()
        if any(_contiene_keyword(texto_norm, kw) for kw in keywords)
    ]
    return {"incluir": bool(categorias), "categorias": categorias, "revisar_manual": False}


def clasificar_eu_grants(items: list[dict]) -> list[dict]:
    salida = []
    for item in items:
        titulo = item.get("titulo") or ""
        texto_completo = " ".join([
            titulo,
            item.get("descripcion") or "",
            item.get("destino_descripcion") or "",
            item.get("destino_detalle") or "",
        ])
        resultado = clasificar_texto_calls_ue(texto_completo)
        if not resultado["incluir"]:
            continue
        salida.append({"fuente": "UE-subvenciones", "original": item, "titulo": titulo, "cpv": [], **resultado})
    return salida


def _cargar_resultados(ruta: Path | None) -> list[dict]:
    if ruta is None:
        return []
    payload = json.loads(ruta.read_text(encoding="utf-8"))
    return payload.get("resultados", [])


def main() -> None:
    resultado_final: list[dict] = []

    cache_previo: dict[str, list[dict]] = {}
    if CACHE_FUENTES.exists():
        try:
            cache_previo = json.loads(CACHE_FUENTES.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cache_previo = {}
    # Arranca como copia del anterior: las claves que esta pasada no
    # actualiza (fuente caída) se quedan tal cual para la próxima ejecución,
    # no se pierden por no haberse usado hoy.
    cache_nuevo: dict[str, list[dict]] = dict(cache_previo)

    # (prefijo del crudo, tipo_registro, función de clasificación). El mismo
    # "fuente" (UE/Estado/Euskadi) puede aparecer en más de un tipo_registro
    # -licitación y adjudicación son crudos y funciones distintos- por eso
    # normalizar.py despacha por tipo_registro, no solo por fuente.
    fuentes = [
        ("ted", "licitacion", clasificar_ted),
        ("placsp", "licitacion", clasificar_placsp),
        ("euskadi", "licitacion", clasificar_euskadi),
        ("ted_adjudicaciones", "adjudicacion", clasificar_ted_adjudicaciones),
        ("placsp", "adjudicacion", clasificar_placsp_adjudicaciones),
        ("euskadi_adjudicaciones", "adjudicacion", clasificar_euskadi_adjudicaciones),
        ("placsp_menores", "contrato_menor_venciendo", clasificar_placsp_contratos_menores),
        ("euskadi_menores", "contrato_menor_venciendo", clasificar_euskadi_contratos_menores),
        ("eu_grants", "convocatoria_ue", clasificar_eu_grants),
    ]

    for prefijo, tipo_registro, funcion in fuentes:
        clave_cache = f"{prefijo}|{tipo_registro}"
        ruta = _ultimo_raw(prefijo)
        if ruta is None:
            previos = cache_previo.get(clave_cache)
            if previos:
                print(
                    f"[clasificar] AVISO: no hay crudo de '{prefijo}' en data/raw/. "
                    f"Se reutilizan {len(previos)} clasificados de la última vez que esta fuente sí respondió "
                    "(normalizar.py descartará los que ya hayan caducado).",
                    file=sys.stderr,
                )
                resultado_final.extend(previos)
            else:
                print(f"[clasificar] AVISO: no hay crudo de '{prefijo}' en data/raw/ y tampoco hay un resultado anterior en caché. Se omite esta fuente en esta pasada.", file=sys.stderr)
            continue
        items = _cargar_resultados(ruta)
        clasificados = funcion(items)
        for c in clasificados:
            c["tipo_registro"] = tipo_registro
        print(f"[clasificar] {prefijo} ({tipo_registro}): {len(items)} extraídas -> {len(clasificados)} relevantes (de {ruta.name})")
        resultado_final.extend(clasificados)
        cache_nuevo[clave_cache] = clasificados

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(resultado_final, ensure_ascii=False, indent=2), encoding="utf-8")
    CACHE_FUENTES.write_text(json.dumps(cache_nuevo, ensure_ascii=False, indent=2), encoding="utf-8")
    n_revisar = sum(1 for r in resultado_final if r["revisar_manual"])
    print(f"[clasificar] Total: {len(resultado_final)} licitaciones relevantes ({n_revisar} para revisar manualmente) -> {SALIDA}")


if __name__ == "__main__":
    main()
