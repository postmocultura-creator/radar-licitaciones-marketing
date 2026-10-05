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
from datetime import date, timedelta
from pathlib import Path

import config
import nif

RAW_DIR = Path(__file__).resolve().parent / "data" / "raw"
SALIDA = Path(__file__).resolve().parent / "data" / "clasificado.json"
CACHE_FUENTES = Path(__file__).resolve().parent / "data" / "ultimo_bueno_por_fuente.json"
# Embudo de esta pasada y descartes revisables (lo lee normalizar.py para la
# página "Cómo se filtra"). No se guarda entre ejecuciones.
FILTRO = Path(__file__).resolve().parent / "data" / "filtro.json"

_CACHE_PATRONES: dict[str, re.Pattern] = {}


# "procedimiento/proceso negociado con/sin publicidad" y "publicidad
# obligatoria" son jerga jurídica del TIPO DE PROCEDIMIENTO (si el anuncio
# de licitación se publica o no), no una señal de que el contrato sea de
# servicios de publicidad. Detectado con datos reales: generaba falsos
# positivos en seguros de vehículos, obra civil (vía ciclista)... cualquier
# cosa tramitada con publicidad obligatoria del anuncio. Se limpia antes de
# comparar contra las keywords.
#
# No siempre va precedido de "procedimiento": "contrato negociado sin
# publicidad con..." se colaba como publicidad (5 casos en una muestra de
# 35.000 títulos). Y al añadir "publicitat"/"publicidade" a la taxonomía
# hace falta la misma limpieza en catalán y gallego ("negociat sense
# publicitat", "negociado sen publicidade").
_RUIDO_PROCEDIMENTAL = re.compile(
    r"\b(negociado|abierto|restringido|simplificado"
    r"|negociat|obert|restringit|simplificat|aberto|restrinxido)"
    r" (con|sin|amb|sense|sen) (publicidad|publicitat|publicidade)\b"
    r"|\bpublicidad obligatoria\b"
)


def _normalizar_texto(texto: str) -> str:
    if not texto:
        return ""
    # Los acentos se quitan (la marca que deja NFKD tras la letra); el resto
    # de caracteres no ASCII pasa a ser un espacio. Antes se borraban sin
    # más, y un apóstrofo tipográfico pegaba dos palabras: "servei
    # d’impressió" quedaba "dimpressio" y la exclusión de imprenta no
    # saltaba (caso real: un sistema dinámico de la Diputació de Girona). El
    # punt volat catalán sí se borra: "instal·lació" es una sola palabra.
    letras = []
    for c in unicodedata.normalize("NFKD", texto):
        if unicodedata.combining(c) or c == "·":
            continue
        letras.append(c if ord(c) < 128 else " ")
    minusculas = "".join(letras).lower()
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


def _coincide(texto_norm: str, keyword: str) -> bool:
    """_contiene_keyword con una excepción: "seo" suelto solo cuenta con
    contexto digital y fuera de los otros "seo" (ver config.SEO_CONTEXTO)."""
    if not _contiene_keyword(texto_norm, keyword):
        return False
    if keyword != "seo":
        return True
    if any(_contiene_keyword(texto_norm, no) for no in config.SEO_NO):
        return False
    return any(_contiene_keyword(texto_norm, palabra) for palabra in config.SEO_CONTEXTO)


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


# TED antepone al título el país y el tipo de servicio, sacado del CPV:
# "España – Servicios de diseño gráfico – <título>". Ese tipo cuenta para
# las categorías (así entran las licitaciones con el título en su idioma),
# pero no para las exclusiones: "Servicios de impresión y servicios conexos
# – Diseño gráfico y producción de elementos de comunicación" se descartaba
# por imprenta sin que el título la mencionara, y el grupo genérico de abajo
# tumbaba hasta "Servicios especializados de agencia de publicidad"
# (medido el 2026-10-04: 8 licitaciones y 9 adjudicaciones en una noche).
_RE_TIPO_TED = re.compile(r"^([^–]{2,40})\s–\s([^–]{2,120})\s–\s(.*)$", re.S)
# "Servicios a empresas: legislación, mercadotecnia, asesoría, selección de
# personal, imprenta y seguridad" (CPV 79000000) es un cajón de sastre: su
# "mercadotecnia" no dice nada. En ese grupo, el título tiene que decirlo
# (sin esto entraban guías de viaje, talleres o gestión de ciudad).
TIPOS_TED_GENERICOS = ("servicios a empresas",)


def textos_ted(titulo: str) -> tuple[str, str]:
    """(texto donde buscar las categorías, texto donde buscar exclusiones)
    de un título de TED. Sin el prefijo de TED, el título en los dos."""
    m = _RE_TIPO_TED.match(titulo or "")
    if not m:
        return titulo, titulo
    real = m.group(3)
    generico = _normalizar_texto(m.group(2)).strip().startswith(TIPOS_TED_GENERICOS)
    return (real if generico else titulo), real


def clasificar_texto(titulo: str, ted: bool = False) -> dict:
    """ted=True: título de TED con su prefijo (ver textos_ted)."""
    texto_categorias, texto_exclusiones = textos_ted(titulo) if ted else (titulo, titulo)
    texto_norm = _normalizar_texto(texto_categorias)
    categorias = [
        categoria
        for categoria, keywords in config.CATEGORIAS.items()
        if any(_coincide(texto_norm, kw) for kw in keywords)
    ]

    if not categorias:
        return {"incluir": False, "categorias": [], "revisar_manual": False}

    texto_norm = _normalizar_texto(texto_exclusiones)
    tiene_servicio_no_ofrecido = any(_contiene_keyword(texto_norm, kw) for kw in config.SERVICIOS_NO_OFRECIDOS)
    if tiene_servicio_no_ofrecido:
        return {"incluir": False, "categorias": [], "revisar_manual": False}

    tiene_exclusion = any(_contiene_keyword(texto_norm, kw) for kw in config.EXCLUSIONES)

    return {"incluir": True, "categorias": categorias, "revisar_manual": tiene_exclusion}


# ---------------------------------------------------------------------------
# Transparencia del filtro: por qué entra cada licitación y qué se queda
# fuera. Lo enseña la página "Cómo se filtra" del dashboard (filtro.html).
# ---------------------------------------------------------------------------

def _normalizar_con_mapa(texto: str) -> tuple[str, list[int]]:
    """Lo mismo que _normalizar_texto (sin quitar el ruido procedimental) y,
    para cada carácter del resultado, su posición en el texto original: así
    una palabra clave encontrada se puede enseñar tal como está escrita."""
    letras: list[str] = []
    mapa: list[int] = []
    for i, original in enumerate(texto or ""):
        for c in unicodedata.normalize("NFKD", original):
            if unicodedata.combining(c) or c == "·":
                continue
            letras.append((c if ord(c) < 128 else " ").lower())
            mapa.append(i)
    return "".join(letras), mapa


def _fragmento(texto: str, keyword: str) -> str | None:
    normal, mapa = _normalizar_con_mapa(texto)
    m = re.search(r"\b" + re.escape(keyword) + r"\b", normal)
    return texto[mapa[m.start()]:mapa[m.end() - 1] + 1] if m else None


MAX_TERMINOS = 4


def terminos_que_encajan(texto: str, categorias: dict[str, list[str]] | None = None) -> list[str]:
    """Las palabras clave que hacen entrar el texto, una por categoría y tal
    como se escriben en él ("Diseño gráfico", no "diseno grafico")."""
    texto_norm = _normalizar_texto(texto)
    terminos: list[str] = []
    for keywords in (categorias or config.CATEGORIAS).values():
        # La más larga primero: "redes sociales" dice más que "redes".
        for kw in sorted(keywords, key=len, reverse=True):
            if _coincide(texto_norm, kw):
                fragmento = _fragmento(texto, kw) or kw
                if fragmento.lower() not in (t.lower() for t in terminos):
                    terminos.append(fragmento)
                break
        if len(terminos) == MAX_TERMINOS:
            break
    return terminos


def _cpv_de_marketing(cpv_list: list) -> bool:
    for cpv in cpv_list or []:
        try:
            n = int(str(cpv).replace("-", "")[:8])
        except ValueError:
            continue
        if any(desde <= n <= hasta for desde, hasta, _ in config.CPV_RANGOS):
            return True
    return False


# Descartes del filtro de texto de la fuente que se está clasificando (lo
# prepara main antes de llamar a cada función): cuántos por cada motivo y,
# si guardar_lista, los que merece la pena poder revisar a mano.
_descartes: dict | None = None


def _apuntar_descarte(item: dict, titulo: str, cpv_list: list, motivo: str | None = None, ted: bool = False) -> None:
    """Motivos: "servicio_no_ofrecido" (el título es de agencia pero también
    dice imprenta, rotulación...: config.SERVICIOS_NO_OFRECIDOS) o
    "sin_categoria" (ninguna palabra clave). De los segundos solo se guardan
    los que tienen un CPV de marketing (config.CPV_RANGOS): son los que
    pueden ser un hueco de la taxonomía; el resto son miles de contratos de
    obras, limpieza o suministros."""
    if _descartes is None:
        return
    termino = None
    if motivo is None:
        texto_categorias, texto_exclusiones = textos_ted(titulo) if ted else (titulo, titulo)
        no_ofrecido = next((kw for kw in config.SERVICIOS_NO_OFRECIDOS
                            if _contiene_keyword(_normalizar_texto(texto_exclusiones), kw)), None)
        texto_norm = _normalizar_texto(texto_categorias)
        hay_categoria = no_ofrecido is not None and any(
            _coincide(texto_norm, kw) for kws in config.CATEGORIAS.values() for kw in kws)
        if hay_categoria:
            motivo, termino = "servicio_no_ofrecido", _fragmento(texto_exclusiones, no_ofrecido) or no_ofrecido
        else:
            motivo = "sin_categoria"
    _descartes[motivo] = _descartes.get(motivo, 0) + 1
    if _descartes.get("lista") is None:
        return
    if motivo == "servicio_no_ofrecido" or _cpv_de_marketing(cpv_list):
        _descartes["lista"].append({"original": item, "titulo": titulo, "cpv": cpv_list,
                                    "motivo": motivo, "termino": termino})


def clasificar_ted(items: list[dict]) -> list[dict]:
    salida = []
    for item in items:
        titulo = _titulo_ted(item)
        cpv_list = item.get("classification-cpv") or []
        resultado = clasificar_texto(titulo, ted=True)
        if not resultado["incluir"]:
            _apuntar_descarte(item, titulo, cpv_list, ted=True)
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
        resultado = clasificar_texto(titulo)
        if not resultado["incluir"]:
            _apuntar_descarte(item, titulo, cpv_list)
            continue
        salida.append({"fuente": "Estado", "original": item, "titulo": titulo, "cpv": cpv_list, **resultado})
    return salida


def clasificar_placsp_web(items: list[dict]) -> list[dict]:
    """Aviso temprano desde el buscador web de PLACSP (scrapers/placsp_web.py).
    El buscador ya filtra por estado "Publicada"; mismo criterio de texto que
    el feed. "Estado-web" es solo para que normalizar.py use su conversor:
    el registro final sale con fuente "Estado"."""
    salida = []
    for item in items:
        titulo = item.get("titulo") or ""
        resultado = clasificar_texto(titulo)
        if not resultado["incluir"]:
            _apuntar_descarte(item, titulo, [])
            continue
        salida.append({"fuente": "Estado-web", "original": item, "titulo": titulo, "cpv": [], **resultado})
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
        resultado = clasificar_texto(titulo)
        if not resultado["incluir"]:
            _apuntar_descarte(item, titulo, cpv_list)
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
        resultado = clasificar_texto(titulo, ted=True)
        if not resultado["incluir"]:
            _apuntar_descarte(item, titulo, cpv_list, ted=True)
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
        resultado = clasificar_texto(titulo)
        if not resultado["incluir"]:
            _apuntar_descarte(item, titulo, cpv_list)
            continue
        salida.append({"fuente": "Estado", "original": item, "titulo": titulo, "cpv": cpv_list, **resultado})
    return salida


# ---------------------------------------------------------------------------
# Plataformas autonómicas agregadas en PLACSP (sindicacion_1044). Mismo
# esquema y mismos criterios que el feed general; solo cambia la etiqueta
# ("Estado-agregadas") para que normalizar.py les dé menos prioridad al
# deduplicar que a la fuente propia de cada comunidad.
#
# Lo de la plataforma de Euskadi se deja fuera: el radar ya la lee por su
# API (scrapers/euskadi.py), que trae más datos, y aquí llegaría duplicado
# con el organismo escrito de otra forma ("Ayuntamiento de Getxo-Junta de
# Gobierno").
# ---------------------------------------------------------------------------
PLATAFORMA_EUSKADI = "contratacion.euskadi.eus"


def _sin_plataforma_euskadi(items: list[dict]) -> list[dict]:
    return [it for it in items if PLATAFORMA_EUSKADI not in (it.get("enlace") or "")]


def clasificar_placsp_agregadas(items: list[dict]) -> list[dict]:
    return [dict(r, fuente="Estado-agregadas") for r in clasificar_placsp(_sin_plataforma_euskadi(items))]


def clasificar_placsp_agregadas_adjudicaciones(items: list[dict]) -> list[dict]:
    return [dict(r, fuente="Estado-agregadas") for r in clasificar_placsp_adjudicaciones(_sin_plataforma_euskadi(items))]


def clasificar_euskadi_adjudicaciones(items: list[dict]) -> list[dict]:
    salida = []
    for item in items:
        titulo = item.get("object") or ""
        cpv = item.get("CPV")
        cpv_list = [cpv] if cpv else []
        resultado = clasificar_texto(titulo)
        if not resultado["incluir"]:
            _apuntar_descarte(item, titulo, cpv_list)
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
        resultado = clasificar_texto(titulo)
        if not resultado["incluir"]:
            _apuntar_descarte(item, titulo, cpv_list)
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
        resultado = clasificar_texto(titulo)
        if not resultado["incluir"]:
            _apuntar_descarte(item, titulo, cpv_list)
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
            _apuntar_descarte(item, titulo, [], motivo="sin_categoria")
            continue
        salida.append({"fuente": "UE-subvenciones", "original": item, "titulo": titulo, "cpv": [], **resultado})
    return salida


def _cargar_resultados(ruta: Path | None) -> list[dict]:
    if ruta is None:
        return []
    payload = json.loads(ruta.read_text(encoding="utf-8"))
    return payload.get("resultados", [])


# Fuentes cuyo crudo NO es una foto completa de lo vigente: el ZIP mensual de
# PLACSP trae solo los expedientes ACTUALIZADOS ese mes. Al cambiar de mes
# (primer cruce: 2026-10-01), el ZIP nuevo llega con uno o dos días de datos
# y, si sustituyera sin más al resultado anterior, desaparecerían del radar
# las licitaciones publicadas el mes pasado que siguen abiertas. Para estas
# fuentes el resultado se acumula entre ejecuciones.
FUENTES_ACUMULATIVAS = {"placsp", "placsp_agregadas", "placsp_menores"}
DIAS_MAX_ACUMULADO = 400  # tope para que la caché no crezca sin fin


def _sin_dni(clasificado: dict) -> None:
    """La caché guarda registros de hasta 400 días, de antes de que los
    scrapers enmascararan los DNI (octubre de 2026): se limpian al cargarla
    para que no vuelvan a versionarse. Mismos campos que enmascaran los
    scrapers (ver nif.py)."""
    original = clasificado.get("original") or {}
    for campo in ("empresa_nif", "CIF"):
        if original.get(campo):
            original[campo] = nif.limpiar(original[campo])
    for campo in ("empresa_adjudicataria", "socialReason"):
        if original.get(campo):
            original[campo] = nif.ocultar_en_texto(original[campo])
    for licitador in (original.get("ficha") or {}).get("licitadores") or []:
        licitador["nif"] = nif.limpiar(licitador.get("nif"))
        licitador["nombre"] = nif.ocultar_en_texto(licitador.get("nombre"))
    if clasificado.get("titulo"):
        clasificado["titulo"] = nif.ocultar_en_texto(clasificado["titulo"])


def _clave_placsp(original: dict) -> str | None:
    return original.get("enlace") or original.get("expediente")


# Las adjudicaciones solo se enseñan si son de los últimos
# DIAS_ANTIGUEDAD_MAXIMA días (normalizar._adjudicacion_reciente): guardar
# más solo engordaba la caché (de 441 adjudicaciones guardadas, 174 estaban
# en ventana el 2026-10-04). Margen por si se amplía la ventana.
DIAS_MAX_ADJUDICACIONES = config.DIAS_ANTIGUEDAD_MAXIMA + 15


def _acumular(previos: list[dict], items_nuevos: list[dict], clasificados: list[dict],
              tipo_registro: str = "licitacion") -> list[dict]:
    """Lo clasificado ahora + lo anterior que NO viene en el crudo nuevo.

    Un expediente que sí viene en el crudo nuevo -en el estado que sea- deja
    de contar con su versión anterior: si pasó de "publicado" a "en
    evaluación" o "anulado", clasificar ya no lo devuelve y aquí tampoco se
    conserva. normalizar.py sigue descartando lo caducado en cada pasada."""
    vistos = {_clave_placsp(it) for it in items_nuevos}
    if tipo_registro == "adjudicacion":
        campo, dias = "fecha_adjudicacion", DIAS_MAX_ADJUDICACIONES
    else:
        campo, dias = "fecha_actualizacion", DIAS_MAX_ACUMULADO
    corte = (date.today() - timedelta(days=dias)).isoformat()
    conservados = [
        c for c in previos
        if _clave_placsp(c["original"]) not in vistos
        and (c["original"].get(campo) or c["original"].get("fecha_actualizacion") or "9999")[:10] >= corte
    ]
    return clasificados + conservados


def main() -> None:
    resultado_final: list[dict] = []

    cache_previo: dict[str, list[dict]] = {}
    if CACHE_FUENTES.exists():
        try:
            cache_previo = json.loads(CACHE_FUENTES.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cache_previo = {}
    for registros in cache_previo.values():
        for c in registros:
            _sin_dni(c)
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
        ("placsp_agregadas", "licitacion", clasificar_placsp_agregadas),
        ("placsp_web", "licitacion", clasificar_placsp_web),
        ("euskadi", "licitacion", clasificar_euskadi),
        ("ted_adjudicaciones", "adjudicacion", clasificar_ted_adjudicaciones),
        ("placsp", "adjudicacion", clasificar_placsp_adjudicaciones),
        ("placsp_agregadas", "adjudicacion", clasificar_placsp_agregadas_adjudicaciones),
        ("euskadi_adjudicaciones", "adjudicacion", clasificar_euskadi_adjudicaciones),
        ("placsp_menores", "contrato_menor_venciendo", clasificar_placsp_contratos_menores),
        ("euskadi_menores", "contrato_menor_venciendo", clasificar_euskadi_contratos_menores),
        ("eu_grants", "convocatoria_ue", clasificar_eu_grants),
    ]

    global _descartes
    embudo: list[dict] = []
    lista_descartes: list[dict] = []
    for prefijo, tipo_registro, funcion in fuentes:
        clave_cache = f"{prefijo}|{tipo_registro}"
        ruta = _ultimo_raw(prefijo)
        if ruta is None:
            previos = cache_previo.get(clave_cache)
            embudo.append({"prefijo": prefijo, "tipo": tipo_registro, "sin_datos_nuevos": True,
                           "relevantes": len(previos or [])})
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
        # Las listas de descartes, solo de licitaciones: es donde un hueco de
        # la taxonomía hace perder una oportunidad.
        _descartes = {"lista": [] if tipo_registro == "licitacion" else None}
        clasificados = funcion(items)
        descartes, _descartes = _descartes, None
        for d in descartes.get("lista") or []:
            d["fuente_prefijo"] = prefijo
            lista_descartes.append(d)
        nuevos = len(clasificados)
        for c in clasificados:
            c["tipo_registro"] = tipo_registro
        if prefijo in FUENTES_ACUMULATIVAS:
            clasificados = _acumular(cache_previo.get(clave_cache) or [], items, clasificados, tipo_registro)
            print(f"[clasificar] {prefijo} ({tipo_registro}): {nuevos} del crudo nuevo + {len(clasificados) - nuevos} conservados de ejecuciones anteriores")
        print(f"[clasificar] {prefijo} ({tipo_registro}): {len(items)} extraídas -> {len(clasificados)} relevantes (de {ruta.name})")
        sin_categoria = descartes.get("sin_categoria", 0)
        no_ofrecido = descartes.get("servicio_no_ofrecido", 0)
        embudo.append({
            "prefijo": prefijo, "tipo": tipo_registro, "extraidas": len(items),
            # Estado no abierto, contrato menor, plataforma de Euskadi
            # repetida, sin adjudicataria...: lo que cada función mira antes
            # del texto.
            "otros_filtros": len(items) - nuevos - sin_categoria - no_ofrecido,
            "sin_categoria": sin_categoria, "servicio_no_ofrecido": no_ofrecido,
            "relevantes_nuevas": nuevos, "conservadas": len(clasificados) - nuevos,
            "relevantes": len(clasificados),
        })
        resultado_final.extend(clasificados)
        cache_nuevo[clave_cache] = clasificados

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(resultado_final, ensure_ascii=False, indent=2), encoding="utf-8")
    CACHE_FUENTES.write_text(json.dumps(cache_nuevo, ensure_ascii=False, indent=2), encoding="utf-8")
    for d in lista_descartes:
        _sin_dni(d)
    FILTRO.write_text(json.dumps({"fecha": date.today().isoformat(), "embudo": embudo, "descartes": lista_descartes},
                                 ensure_ascii=False), encoding="utf-8")
    n_revisar = sum(1 for r in resultado_final if r["revisar_manual"])
    print(f"[clasificar] Total: {len(resultado_final)} licitaciones relevantes ({n_revisar} para revisar manualmente) -> {SALIDA}")


if __name__ == "__main__":
    main()
