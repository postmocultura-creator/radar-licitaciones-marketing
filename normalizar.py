# -*- coding: utf-8 -*-
"""
Unifica los tres formatos heterogéneos (TED, PLACSP, Euskadi) ya clasificados
en data/clasificado.json en un único esquema, y escribe data/tenders.json,
el dataset que consume el dashboard.

Esquema final por licitación:
    id, titulo, organismo, fuente, pais_territorio, fecha_publicacion,
    fecha_primera_aparicion (str YYYY-MM-DD: fecha en la que este "id" se vio
    por primera vez en el radar, persistida entre ejecuciones en
    data/primera_aparicion.json. Puede no coincidir con fecha_publicacion —
    PLACSP no tiene API en tiempo real, solo un ZIP mensual con ~5 días de
    retraso estructural respecto al reloj real (ver README), así que un
    registro del Estado puede llevar varios días "publicado" antes de que
    esta fecha lo registre. Es el campo que usa el dashboard para
    "Publicadas recientemente" en vez de fecha_publicacion),
    region_nuts (solo licitaciones de TED: código NUTS del organismo, p. ej.
    "ES213"; el dashboard lo usa para repartir las españolas entre Estado y
    Euskadi en "Publicadas recientemente"),
    fecha_limite, presupuesto_valor (float|null), presupuesto_display (str),
    cpv (list[str]), categorias (list[str]), revisar_manual (bool),
    enlace, enlace_directo (bool: False cuando "enlace" es solo un buscador
    genérico, no la página del anuncio concreto — hoy solo pasa en Euskadi,
    que no expone URL de detalle por expediente), codigo_expediente
    (str|None, para poder copiarlo y pegarlo en el buscador cuando
    enlace_directo es False), resumen, tipo_contrato (str: la descripción
    oficial en español del primer código CPV de la licitación -p. ej.
    "Servicios de publicidad y de marketing"-, tal y como la publica la
    propia fuente; "no publicado" en Euskadi, que no expone CPV. Es solo
    informativo: NO se usa para decidir qué entra en el radar -eso lo
    decide únicamente el texto del título, capa 2 de clasificar.py-,
    porque se comprobó que el CPV real de una licitación de marketing a
    veces cae en un grupo genérico ajeno, p. ej. 50000000 "Servicios de
    reparación y mantenimiento", y filtrar por él dejaría fuera casos
    reales),
    provincia y comunidad (str|None: lugar del contrato en España, ver
    _lugar; None cuando la fuente no da código de lugar, como en lo que
    solo llega por el buscador web de PLACSP, o cuando el ámbito es todo el
    territorio),
    historial_organismo e historial_empresa (dict, solo si el organismo o
    la empresa están en el histórico de adjudicaciones: cuántas
    adjudicaciones de servicios de agencia suman, a cuántas empresas u
    organismos, por qué importe y desde qué año; ver _historiales)

Ningún campo se inventa: cuando la fuente no publica un dato (presupuesto,
fecha límite...), el valor es exactamente el texto "no publicado", nunca un
0 o una fecha estimada.

Deduplicación: algunas licitaciones sobre el umbral de la UE se publican a
la vez en TED y en PLACSP. Se deduplican solo cuando título normalizado Y
organismo normalizado coinciden entre dos fuentes (título exacto, sin el
prefijo "País – CPV – " que añade TED; organismo igual o igual salvo un
sufijo de departamento; heurística conservadora: prefiere duplicar de más a
fusionar mal). Se conserva la
entrada de TED (más estructurada) y se descarta la de PLACSP equivalente.
Se aplica igual a "adjudicacion" (bug real detectado en auditoría: el mismo
contrato sobre el umbral UE también puede aparecer adjudicado tanto en el
aviso "result" de TED como en el bloque TenderResult del feed general de
PLACSP — la razón de deduplicar licitaciones aplica exactamente igual aquí,
y antes de este arreglo nunca se comprobaba). La clave incluye el
tipo_registro como prefijo para que una licitación y una adjudicación con el
mismo título+organismo (algo normal: el título no cambia entre el anuncio y
el resultado) no se pisen entre sí al vivir en pestañas distintas del
dashboard.

Los "contrato_menor_venciendo" y "convocatoria_ue" NO se deduplican por
título+organismo a propósito: un mismo organismo puede adjudicar varios
contratos menores genuinamente distintos con un título casi idéntico (p. ej.
"Servicio de diseño gráfico" a proveedores distintos en fechas distintas) —
aplicar aquí la misma heurística fusionaría contratos reales en uno solo,
que es justo el error que la heurística intenta evitar en el otro sentido.
Las calls for proposals solo tienen una fuente (SEDIA), así que no hay
riesgo de duplicado cruzado que evitar.

Ejecutar:
    python normalizar.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import unicodedata
from datetime import date, timedelta
from pathlib import Path

from deep_translator import MyMemoryTranslator

import config
import nif
import territorio

CLASIFICADO = Path(__file__).resolve().parent / "data" / "clasificado.json"
SALIDA = Path(__file__).resolve().parent / "data" / "tenders.json"
SALIDA_DASHBOARD = Path(__file__).resolve().parent / "dashboard" / "tenders-data.js"
PRIMERA_APARICION = Path(__file__).resolve().parent / "data" / "primera_aparicion.json"
CPV_NOMBRES = Path(__file__).resolve().parent / "cpv_nombres.json"

NO_PUBLICADO = "no publicado"

# Vocabulario CPV 2008 oficial en español, descargado del codelist CODICE de
# PLACSP (contrataciondelestado.es/codice/cl/2.04/CPV2008-2.04.gc — 9454
# códigos con su descripción oficial). Se usa solo para mostrar "tipo de
# contrato" en la tarjeta -información de contexto, tal y como lo publica
# la fuente-, nunca para decidir inclusión: ver nota en el docstring de
# arriba sobre por qué el CPV real no es fiable como filtro.
_CPV_NOMBRES: dict[str, str] = json.loads(CPV_NOMBRES.read_text(encoding="utf-8")) if CPV_NOMBRES.exists() else {}


def _tipo_contrato(cpv_list) -> str:
    for codigo in cpv_list or []:
        digitos = "".join(ch for ch in str(codigo) if ch.isdigit())[:8]
        nombre = _CPV_NOMBRES.get(digitos)
        if nombre:
            return nombre
    return NO_PUBLICADO

# TED da el país del comprador como código ISO 3166-1 alfa-3. Se traduce a
# nombre en español tanto para que el filtro de país sea legible como para
# que las tarjetas no muestren "DEU"/"FRA" en vez de "Alemania"/"Francia".
PAISES_ISO3 = {
    "AUT": "Austria", "BEL": "Bélgica", "BGR": "Bulgaria", "HRV": "Croacia",
    "CYP": "Chipre", "CZE": "Chequia", "DNK": "Dinamarca", "EST": "Estonia",
    "FIN": "Finlandia", "FRA": "Francia", "DEU": "Alemania", "GRC": "Grecia",
    "HUN": "Hungría", "ISL": "Islandia", "IRL": "Irlanda", "ITA": "Italia",
    "LVA": "Letonia", "LTU": "Lituania", "LUX": "Luxemburgo", "MLT": "Malta",
    "NLD": "Países Bajos", "NOR": "Noruega", "POL": "Polonia",
    "PRT": "Portugal", "ROU": "Rumanía", "SVN": "Eslovenia",
    "SVK": "Eslovaquia", "ESP": "España", "SWE": "Suecia", "CHE": "Suiza",
    "GBR": "Reino Unido", "LIE": "Liechtenstein", "SAU": "Arabia Saudí",
    "CAN": "Canadá", "USA": "Estados Unidos", "AND": "Andorra",
    "MCO": "Mónaco", "SRB": "Serbia", "MKD": "Macedonia del Norte",
    "MNE": "Montenegro", "ALB": "Albania", "TUR": "Turquía", "UKR": "Ucrania",
    # Sin estos salían como código en el desplegable ("BIH", 2026-10-01).
    "BIH": "Bosnia y Herzegovina", "MDA": "Moldavia", "GEO": "Georgia",
    "ARM": "Armenia", "ISR": "Israel", "MAR": "Marruecos", "TUN": "Túnez",
}


def _normalizar_clave(texto: str) -> str:
    if not texto:
        return ""
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    sin_acentos = sin_acentos.lower()
    return re.sub(r"[^a-z0-9]+", " ", sin_acentos).strip()


def _titulo_ted_sin_prefijo(titulo: str) -> str:
    """TED antepone "País – descripción CPV – " al título real ("España –
    Servicios de publicidad – Servicio de difusión..."). Solo para la clave
    de deduplicación: con el prefijo, ningún título de TED coincidía nunca
    con su copia en PLACSP/Euskadi y la misma licitación salía dos veces
    (16 casos reales en los datos del 2026-09-30)."""
    partes = (titulo or "").split(" – ", 2)
    return partes[2] if len(partes) == 3 else titulo


def _organismos_compatibles(a: str, b: str) -> bool:
    """Mismo organismo aunque una fuente añada el departamento detrás
    ("Gobierno Vasco - Bienestar, Juventud..." en TED frente a "Gobierno
    Vasco" en Euskadi). Solo se usa cuando el título ya coincide exacto."""
    if a == b:
        return True
    return bool(a and b) and (a.startswith(b + " ") or b.startswith(a + " "))


def _limpiar_fecha(valor: str | None) -> str:
    """TED/PLACSP devuelven fechas tipo '2026-08-03+02:00'. Nos quedamos con
    la parte YYYY-MM-DD.

    Bug real detectado en auditoría: algunos campos de fecha de TED (p. ej.
    deadline-date-lot, deadline-receipt-tender-date-lot) vienen como
    '2026-09-30Z' -sin 'T' ni '+', solo la 'Z' de UTC pegada directamente a
    la fecha- y no los cazaba ninguno de los dos split() de abajo. Con la
    'Z' colgando, el dashboard no podía parsear la fecha (el guion de
    "22Z" no es un día válido) y mostraba "sin fecha límite" en vez de
    calcular los días reales. Verificado contra datos reales: 68 casos en
    un solo crudo de TED."""
    if not valor:
        return NO_PUBLICADO
    # Huso negativo ("2026-10-23-04:00", caso real de TED del 2026-10-01): ni
    # el "+" ni la "T" ni la "Z" de abajo lo cazaban, y en el dashboard esa
    # licitación salía "sin fecha límite" y al final de la lista. Si el valor
    # empieza por una fecha, se toma la fecha y se ignora cualquier sufijo.
    con_fecha = re.match(r"\s*(\d{4}-\d{2}-\d{2})", valor)
    if con_fecha:
        return con_fecha.group(1)
    limpio = valor.split("+")[0].split("T")[0].strip()
    if limpio.endswith("Z"):
        limpio = limpio[:-1]
    return limpio or NO_PUBLICADO


def _id_unico(*partes: str) -> str:
    base = "|".join(p or "" for p in partes)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def _parsear_presupuesto(valor, moneda: str = "EUR") -> tuple[float | None, str]:
    """Convierte un valor de presupuesto crudo (puede venir como string,
    int o float, o faltar). Un valor de exactamente 0 se trata igual que
    ausente: se comprobó con datos reales de TED que algunos marcos
    (framework agreements sin lotes valorados) devuelven literalmente la
    cadena "0" en estimated-value-proc en vez de omitir el campo — un
    contrato real nunca tiene presupuesto cero, así que mostrarlo como
    "0 EUR" es engañoso; se muestra como no publicado."""
    if valor is None or valor == "":
        return None, NO_PUBLICADO
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None, NO_PUBLICADO
    if numero == 0:
        return None, NO_PUBLICADO
    return numero, f"{numero:,.0f} {moneda}"


def _parsear_fecha_iso(valor: str) -> date | None:
    if not valor or valor == NO_PUBLICADO:
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        return None


def _adjudicacion_reciente(registro: dict) -> bool:
    """Para adjudicaciones no hay 'plazo': el contrato ya está cerrado. Se
    usa la misma ventana de antigüedad que el resto del radar, pero sobre
    la fecha de adjudicación en vez de la de publicación."""
    cutoff = date.today() - timedelta(days=config.DIAS_ANTIGUEDAD_MAXIMA)
    fecha = _parsear_fecha_iso(registro["fecha_publicacion"])
    return fecha is not None and fecha >= cutoff


def _contrato_menor_por_vencer(registro: dict) -> bool:
    """Vence dentro de la ventana de aviso Y no ha vencido ya (un contrato
    que ya venció no sirve para una visita comercial "antes de que
    renueve")."""
    fin = _parsear_fecha_iso(registro["fecha_fin_estimada"])
    if fin is None:
        return False
    hoy = date.today()
    limite = hoy + timedelta(days=config.DIAS_AVISO_CONTRATO_MENOR)
    return hoy <= fin <= limite


def _dentro_de_ventana_temporal(registro: dict) -> bool:
    """Filtro final: 'publicada en los últimos N días O aún en plazo', tal
    y como pide el encargo. Se recalcula aquí, con las fechas ya limpias y
    unificadas, porque se detectó con datos reales -y en dos fuentes
    distintas, Euskadi y PLACSP- que el campo de fecha que exponen como
    "publicación"/"actualización" no es fiable como señal de vigencia: se
    toca (vuelve a quedar "reciente") cuando el expediente cambia de
    estado internamente, aunque el contrato lleve años cerrado y resuelto
    (se han visto expedientes con "Estado: RES" de 2021-2023 con fecha de
    actualización de hoy mismo). Por eso un plazo límite conocido y ya
    vencido descarta la licitación SIEMPRE, gane lo que gane la fecha de
    publicación; la fecha de publicación solo se usa como señal de
    vigencia cuando no hay plazo límite publicado con el que contrastar."""
    hoy = date.today()
    cutoff = hoy - timedelta(days=config.DIAS_ANTIGUEDAD_MAXIMA)
    publicacion = _parsear_fecha_iso(registro["fecha_publicacion"])
    limite = _parsear_fecha_iso(registro["fecha_limite"])

    if limite is not None:
        return limite >= hoy

    return publicacion is not None and publicacion >= cutoff


def _texto_ted(valor, idiomas: tuple[str, ...] = ("spa", "eng")) -> str:
    """Texto de un campo multilingüe de TED ({"spa": ["..."], "eng": [...]}):
    el del primer idioma preferido que venga o, si no, el primero que haya."""
    if not isinstance(valor, dict):
        return NO_PUBLICADO
    textos = next((valor[i] for i in idiomas if valor.get(i)), None) or next(iter(valor.values()), None)
    if isinstance(textos, list):
        textos = textos[0] if textos else None
    return textos if isinstance(textos, str) and textos else NO_PUBLICADO


def _from_ted(registro: dict) -> dict:
    item = registro["original"]

    organismo = _texto_ted(item.get("buyer-name"))

    paises = item.get("buyer-country") or []
    codigo_pais = paises[0] if paises else None
    pais = PAISES_ISO3.get(codigo_pais, codigo_pais) if codigo_pais else "UE (sin país especificado)"

    fecha_publicacion = _limpiar_fecha(item.get("publication-date"))

    # "deadline-receipt-tender-date-lot" (eForms/BT-131) es el que de
    # verdad viene relleno en la mayoría de anuncios reales; "deadline-date-lot"
    # se pide igualmente por si acaso, como alias de formatos TED2 legados.
    deadlines = item.get("deadline-receipt-tender-date-lot") or item.get("deadline-date-lot") or []
    fecha_limite = _limpiar_fecha(deadlines[0]) if deadlines else NO_PUBLICADO

    moneda = item.get("estimated-value-cur-proc") or "EUR"
    presupuesto_valor, presupuesto_display = _parsear_presupuesto(item.get("estimated-value-proc"), moneda)

    numero_pub = item.get("publication-number", "")
    enlace = f"https://ted.europa.eu/es/notice/-/detail/{numero_pub}" if numero_pub else NO_PUBLICADO

    titulo = registro["titulo"]
    resumen = titulo  # TED search API no devuelve descripción larga con los campos consultados

    regiones = item.get("buyer-country-sub") or []
    region_nuts = regiones[0] if regiones else None

    return {
        "id": _id_unico("UE", numero_pub, titulo),
        "titulo": titulo,
        "organismo": organismo,
        "fuente": "UE",
        "pais_territorio": pais,
        "region_nuts": region_nuts,
        "fecha_publicacion": fecha_publicacion,
        "fecha_limite": fecha_limite,
        "presupuesto_valor": presupuesto_valor,
        "presupuesto_display": presupuesto_display,
        "cpv": registro["cpv"],
        "categorias": registro["categorias"],
        "revisar_manual": registro["revisar_manual"],
        "enlace": enlace,
        "enlace_directo": True,
        "codigo_expediente": None,
        "resumen": resumen,
        "tipo_contrato": _tipo_contrato(registro["cpv"]),
        "tipo_registro": "licitacion",
        "_clave_dedup": "licitacion|" + _normalizar_clave(_titulo_ted_sin_prefijo(titulo)) + "|" + _normalizar_clave(organismo),
    }


def _from_placsp(registro: dict) -> dict:
    item = registro["original"]

    organismo = item.get("organismo") or NO_PUBLICADO
    fecha_publicacion = _limpiar_fecha(item.get("fecha_actualizacion"))
    fecha_limite = _limpiar_fecha(item.get("fecha_limite"))

    presupuesto_valor, presupuesto_display = _parsear_presupuesto(item.get("presupuesto"), item.get("moneda") or "EUR")

    titulo = registro["titulo"]
    resumen = item.get("resumen_feed") or titulo

    return {
        "id": _id_unico("Estado", item.get("expediente", ""), titulo),
        "titulo": titulo,
        "organismo": organismo,
        "fuente": "Estado",
        "pais_territorio": "España",
        "fecha_publicacion": fecha_publicacion,
        "fecha_limite": fecha_limite,
        "presupuesto_valor": presupuesto_valor,
        "presupuesto_display": presupuesto_display,
        "cpv": registro["cpv"],
        "categorias": registro["categorias"],
        "revisar_manual": registro["revisar_manual"],
        "enlace": item.get("enlace") or NO_PUBLICADO,
        "enlace_directo": True,
        "codigo_expediente": item.get("expediente"),
        "resumen": resumen,
        "tipo_contrato": _tipo_contrato(registro["cpv"]),
        "tipo_registro": "licitacion",
        "_clave_dedup": "licitacion|" + _normalizar_clave(titulo) + "|" + _normalizar_clave(organismo),
    }


def _from_placsp_web(registro: dict) -> dict:
    """Aviso temprano del buscador web de PLACSP (scrapers/placsp_web.py).
    Mismo id que el feed (expediente + título, verificado: cuando el enlace
    coincide, título y organismo coinciden exactos), así que cuando la
    licitación llega por el feed se fusionan y se conserva la del feed."""
    item = registro["original"]
    titulo = registro["titulo"]
    organismo = item.get("organismo") or NO_PUBLICADO
    presupuesto_valor, presupuesto_display = _parsear_presupuesto(item.get("presupuesto"), item.get("moneda") or "EUR")

    return {
        "id": _id_unico("Estado", item.get("expediente", ""), titulo),
        "titulo": titulo,
        "organismo": organismo,
        "fuente": "Estado",
        "pais_territorio": "España",
        "fecha_publicacion": _limpiar_fecha(item.get("fecha_publicacion")),
        "fecha_limite": _limpiar_fecha(item.get("fecha_limite")),
        "presupuesto_valor": presupuesto_valor,
        "presupuesto_display": presupuesto_display,
        "cpv": [],
        "categorias": registro["categorias"],
        "revisar_manual": registro["revisar_manual"],
        "enlace": item.get("enlace") or NO_PUBLICADO,
        "enlace_directo": True,
        "codigo_expediente": item.get("expediente"),
        "resumen": titulo,
        # El listado web no da el código CPV, solo la categoría de servicio
        # ("Servicios de publicidad"), que es lo más parecido que hay.
        "tipo_contrato": item.get("subtipo") or NO_PUBLICADO,
        "tipo_registro": "licitacion",
        # Prioridad más baja al deduplicar: si la misma licitación está en el
        # feed, en TED o en la API de Euskadi (el buscador incluye también la
        # plataforma vasca agregada), gana esa versión, más completa y con
        # la fuente correcta.
        "_prioridad_dedup": 3,
        "_origen_web": True,
        "_clave_dedup": "licitacion|" + _normalizar_clave(titulo) + "|" + _normalizar_clave(organismo),
    }


# Topónimos que identifican sin ambigüedad a un organismo de la CAPV.
TOPONIMOS_VASCOS = (
    "euskadi", "pais vasco", "vasco", "vasca", "eusko", "bizkaia", "vizcaya", "gipuzkoa",
    "guipuzcoa", "araba", "alava", "bilbao", "bilbo", "donostia", "san sebastian",
    "vitoria", "gasteiz", "barakaldo", "getxo", "irun", "portugalete", "santurtzi",
    "basauri", "errenteria", "leioa", "eibar", "durango", "zarautz", "galdakao",
)
HISTORICO_DASHBOARD = Path(__file__).resolve().parent / "dashboard" / "historico-data.js"


_HISTORICO: dict | None | bool = False  # False = todavía no se ha intentado leer


def _historico() -> dict | None:
    """El histórico de adjudicaciones tal como lo publica el dashboard
    (dashboard/historico-data.js, ver historico_adjudicaciones._publicar), o
    None si no existe, está a medias o es de un formato anterior. Se lee una
    sola vez: son 8 MB."""
    global _HISTORICO
    if _HISTORICO is False:
        _HISTORICO = None
        if HISTORICO_DASHBOARD.exists():
            try:
                texto = HISTORICO_DASHBOARD.read_text(encoding="utf-8")
                datos = json.loads(texto[texto.index("{"):].rstrip().rstrip(";"))
                if datos["dic"]["organismo"] is not None and datos["exp"] is not None and datos["lotes"] is not None:
                    _HISTORICO = datos
            except (ValueError, KeyError, TypeError, OSError):
                pass
    return _HISTORICO


def _organismos_vascos(registros: list[dict]) -> set[str]:
    """Organismos ya conocidos como vascos: los de la API de Euskadi en los
    datos actuales y los de ámbito Euskadi del histórico de adjudicaciones."""
    vascos = {_normalizar_clave(r["organismo"]) for r in registros if r["fuente"] == "Euskadi"}
    datos = _historico()
    if datos:
        try:
            nombres = datos["dic"]["organismo"]
            # exp: [organismo, euskadi, ...] (ver historico_adjudicaciones._publicar)
            vascos |= {_normalizar_clave(nombres[e[0]]) for e in datos["exp"] if e[1] == 1}
        except (KeyError, IndexError, TypeError):
            pass
    vascos.discard("")
    return vascos


PRINCIPALES_POR_ORGANISMO = 3


def _historiales(registros: list[dict]) -> None:
    """Añade a cada registro español lo que el histórico sabe de su
    organismo y, en adjudicaciones y contratos menores, de su empresa:

      historial_organismo: {id, adjudicaciones, empresas, importe, desde,
          principales: [{id, nombre, adjudicaciones, importe}, ...]}
      historial_empresa: {id, adjudicaciones, organismos, importe, desde,
          en_este_organismo}

    Así la tarjeta puede decir quién ha ganado antes en ese organismo sin
    cargar los 8 MB del histórico. El organismo se busca por nombre
    normalizado; la empresa, por NIF y, si no hay, por nombre. Son los datos
    del histórico tal cual: mismas adjudicaciones de servicios de agencia y
    mismos importes que muestra la sección Competencia (con sus mismos
    contratos enormes que no son de agencia, ver README)."""
    datos = _historico()
    if not datos:
        return
    try:
        organismos = datos["dic"]["organismo"]
        empresas = datos["dic"]["empresa"]  # [nif, nombre]
        exp = datos["exp"]                  # [organismo, euskadi, tipo, procedimiento, menor, mascara]
        lotes = datos["lotes"]              # [exp, empresa, fecha, importe, ofertas, pyme]
        por_organismo: dict[int, dict] = {}
        por_empresa: dict[int, dict] = {}
        for i_exp, i_emp, fecha, importe, *_ in lotes:
            i_org = exp[i_exp][0]
            anio = (fecha or "")[:4]
            o = por_organismo.setdefault(i_org, {"n": 0, "importe": 0.0, "desde": anio, "empresas": {}})
            o["n"] += 1
            o["importe"] += importe or 0
            if anio and (not o["desde"] or anio < o["desde"]):
                o["desde"] = anio
            par = o["empresas"].setdefault(i_emp, [0, 0.0])
            par[0] += 1
            par[1] += importe or 0
            e = por_empresa.setdefault(i_emp, {"n": 0, "importe": 0.0, "desde": anio, "organismos": set()})
            e["n"] += 1
            e["importe"] += importe or 0
            e["organismos"].add(i_org)
            if anio and (not e["desde"] or anio < e["desde"]):
                e["desde"] = anio
    except (KeyError, IndexError, TypeError, ValueError):
        return  # formato inesperado: las tarjetas salen sin resumen

    id_organismo = {}
    for i, nombre in enumerate(organismos):
        id_organismo.setdefault(_normalizar_clave(nombre), i)
    id_por_nif = {}
    id_por_nombre = {}
    por_nif_enmascarado: dict[str, list[tuple[int, set[str]]]] = {}
    for i, empresa in enumerate(empresas):
        if len(empresa) > 2:
            continue  # ficha fusionada en otra (ver historico_adjudicaciones._compactar)
        nif, nombre = empresa
        if nif and nif_enmascarado(nif):
            por_nif_enmascarado.setdefault(nif, []).append((i, set(_normalizar_clave(nombre).split())))
        elif nif:
            id_por_nif.setdefault(_nif_limpio(nif), i)
        id_por_nombre.setdefault(_normalizar_clave(nombre), i)
    id_organismo.pop("", None)
    id_por_nombre.pop("", None)

    def buscar_empresa(nif: str, nombre: str) -> int | None:
        i_emp = id_por_nif.get(nif)
        if i_emp is None and nif_enmascarado(nif):
            # Un NIF enmascarado solo enseña tres o cuatro cifras y lo pueden
            # compartir personas distintas: además tiene que coincidir el
            # nombre en al menos dos palabras (tolera el orden cambiado y una
            # errata: "Marta Sánchez Ruis" / "MARTA SANCHEZ RUIZ").
            palabras = set(_normalizar_clave(nombre).split())
            i_emp = next((i for i, n in por_nif_enmascarado.get(nif, []) if len(n & palabras) >= 2), None)
        if i_emp is None and nombre != NO_PUBLICADO:
            i_emp = id_por_nombre.get(_normalizar_clave(nombre))
        return i_emp

    for r in registros:
        if r["tipo_registro"] == "convocatoria_ue":
            continue
        # Empresas que se presentaron (Euskadi): enlace a su ficha si están
        # en el histórico.
        for licitador in r.get("licitadores") or []:
            i_lic = buscar_empresa(licitador.get("nif") or "", licitador["nombre"])
            if i_lic is not None and i_lic in por_empresa:
                licitador["id"] = i_lic
        # "no publicado" también existe como nombre en el histórico: no es
        # un organismo ni una empresa, no se cruza.
        i_org = None if r["organismo"] == NO_PUBLICADO else id_organismo.get(_normalizar_clave(r["organismo"]))
        o = por_organismo.get(i_org) if i_org is not None else None
        if o:
            principales = sorted(o["empresas"].items(), key=lambda par: (-par[1][1], -par[1][0]))[:PRINCIPALES_POR_ORGANISMO]
            r["historial_organismo"] = {
                "id": i_org,
                "adjudicaciones": o["n"],
                "empresas": len(o["empresas"]),
                "importe": round(o["importe"]),
                "desde": o["desde"] or None,
                "principales": [
                    {"id": i_emp, "nombre": empresas[i_emp][1], "adjudicaciones": n, "importe": round(importe)}
                    for i_emp, (n, importe) in principales
                ],
            }
        if r["tipo_registro"] not in ("adjudicacion", "contrato_menor_venciendo"):
            continue
        nombre_empresa = r.get("empresa_adjudicataria") or NO_PUBLICADO
        i_emp = buscar_empresa(r.get("empresa_nif") or "", nombre_empresa)
        e = por_empresa.get(i_emp) if i_emp is not None else None
        if e:
            r["historial_empresa"] = {
                "id": i_emp,
                "adjudicaciones": e["n"],
                "organismos": len(e["organismos"]),
                "importe": round(e["importe"]),
                "desde": e["desde"] or None,
                "en_este_organismo": o["empresas"][i_emp][0] if o and i_emp in o["empresas"] else 0,
            }


HISTORICO_COMPLETO = Path(__file__).resolve().parent / "data" / "historico_adjudicaciones.json"
MAX_ANTECEDENTES = 3
# Dos títulos son "el mismo contrato" si comparten al menos el 30 % de sus
# palabras con contenido y dos como mínimo. Medido el 2026-10-04 sobre las
# licitaciones abiertas: con 0,3 salen sobre todo ediciones anteriores del
# mismo servicio; por debajo de 0,25 empiezan a colarse contratos del mismo
# organismo que no se parecen (mantenimiento web frente a montaje de stands).
UMBRAL_PARECIDO = 0.3
_PALABRAS_VACIAS_TITULO = frozenset(
    "para del las los con por una unos unas sus servicio servicios contrato contratacion contratos "
    "suministro realizacion prestacion asistencia tecnica tecnicos anos lote lotes mediante procedimiento "
    "abierto simplificado durante diferentes diversas diversos".split())
# TED antepone país y tipo de servicio: "España – Servicios de promoción – <título>".
_RE_PREFIJO_TED = re.compile(r"^[^–]{2,40}\s–\s[^–]{2,90}\s–\s")


def _palabras_titulo(titulo: str) -> frozenset[str]:
    titulo = _RE_PREFIJO_TED.sub("", titulo or "")
    return frozenset(w for w in _normalizar_clave(titulo).split()
                     if len(w) >= 4 and not w.isdigit() and w not in _PALABRAS_VACIAS_TITULO)


def _antecedentes(registros: list[dict]) -> None:
    """Añade a cada licitación española en plazo los contratos anteriores
    parecidos del mismo organismo que hay en el histórico de adjudicaciones
    (casi siempre, ediciones anteriores del mismo servicio): título, año,
    quién lo ganó, por cuánto y con cuántas ofertas.

      antecedentes: [{titulo, anio, enlace, importe, ofertas, rebaja,
                      empresas: [{id, nombre}]}, ...]  (los más recientes)
      antecedentes_total: cuántos parecidos hay en total

    Usa el histórico completo (data/historico_adjudicaciones.json), que
    tiene los títulos; el del dashboard no. Mismos índices de expediente y
    empresa que historico-data.js, así que el id de la empresa abre su ficha
    en historico.html. El organismo se busca por nombre normalizado, como en
    _historiales. Las licitaciones extranjeras de TED y las calls no tienen
    histórico."""
    if not HISTORICO_COMPLETO.exists():
        return
    try:
        c = json.loads(HISTORICO_COMPLETO.read_text(encoding="utf-8"))
        organismos = c["dic"]["organismo"]
        empresas = c["dic"]["empresa"]
        exp = c["exp"]  # [id, titulo, organismo, euskadi, tipo, proc, menor, mascara, enlace, ted, actualizado, presupuesto, lugar]
        prefijo = c.get("prefijo_enlace") or ""
        lotes_por_exp: dict[int, list] = {}
        for l in c["lotes"]:  # [exp, empresa, fecha, importe, ofertas, pyme]
            lotes_por_exp.setdefault(l[0], []).append(l)
    except (ValueError, KeyError, TypeError, OSError):
        return

    clave_org = [_normalizar_clave(o) for o in organismos]
    por_organismo: dict[str, list[int]] = {}
    for i, e in enumerate(exp):
        if i in lotes_por_exp:
            por_organismo.setdefault(clave_org[e[2]], []).append(i)
    por_organismo.pop("", None)

    def empresa(i_emp: int) -> dict:
        datos = empresas[i_emp]
        if len(datos) > 2:  # ficha fusionada: [None, nombre, índice de la buena]
            i_emp = datos[2]
            datos = empresas[i_emp]
        return {"id": i_emp, "nombre": datos[1]}

    palabras_exp: dict[int, frozenset[str]] = {}
    for r in registros:
        if r["tipo_registro"] != "licitacion" or r["organismo"] == NO_PUBLICADO:
            continue
        candidatos = por_organismo.get(_normalizar_clave(r["organismo"]))
        # El nombre del organismo dentro del título no dice nada del servicio
        # y hacía parecer iguales "mantenimiento de la web de la Agencia
        # Española de X" y "montaje de escaparates de la Agencia Española de X".
        del_organismo = _palabras_titulo(r["organismo"])
        palabras = _palabras_titulo(r["titulo"]) - del_organismo
        if not candidatos or len(palabras) < 2:
            continue
        propio = r.get("enlace") or ""
        parecidos = []
        for i in candidatos:
            if propio and propio.endswith(exp[i][8] or "\0"):
                continue  # el propio expediente, adjudicado ya en algún lote
            if i not in palabras_exp:
                palabras_exp[i] = _palabras_titulo(exp[i][1])
            otras = palabras_exp[i] - del_organismo
            comunes = len(palabras & otras)
            if comunes >= 2 and comunes / len(palabras | otras) >= UMBRAL_PARECIDO:
                parecidos.append(i)
        if not parecidos:
            continue
        fechas = {i: max(l[2] or "" for l in lotes_por_exp[i]) for i in parecidos}
        parecidos.sort(key=lambda i: fechas[i], reverse=True)
        lista = []
        repetidos = set()  # el histórico tiene algún contrato dos veces (mismo título, empresa e importe)
        for i in parecidos:
            e = exp[i]
            lotes = lotes_por_exp[i]
            # Por debajo de 100 € no es el importe del contrato sino un precio
            # unitario o una errata de la fuente ("4 €" en una compra de medios).
            importes = [l[3] for l in lotes if l[3]]
            importe = sum(importes) if importes and sum(importes) >= 100 else None
            ofertas = max((l[4] for l in lotes if l[4]), default=None)
            rebaja = None
            if len(lotes) == 1 and importe and e[11] and 0.005 <= 1 - importe / e[11] < 0.9:
                rebaja = round((1 - importe / e[11]) * 100, 1)
            nombres_vistos = set()
            lista_empresas = []
            for l in lotes:
                emp = empresa(l[1])
                if emp["id"] not in nombres_vistos:
                    nombres_vistos.add(emp["id"])
                    lista_empresas.append(emp)
            titulo = " ".join(e[1].split())
            firma = (_normalizar_clave(titulo), tuple(x["id"] for x in lista_empresas), importe)
            if firma in repetidos:
                continue
            repetidos.add(firma)
            enlace = e[8] if e[8].startswith("http") or not e[8] else prefijo + e[8]
            lista.append({
                "titulo": titulo, "anio": fechas[i][:4] or None, "enlace": enlace or None,
                "importe": importe, "ofertas": ofertas, "rebaja": rebaja, "empresas": lista_empresas[:3],
            })
        r["antecedentes"] = lista[:MAX_ANTECEDENTES]
        r["antecedentes_total"] = len(lista)


# ---------------------------------------------------------------------------
# Transparencia del filtro (página "Cómo se filtra", dashboard/filtro.html)
# ---------------------------------------------------------------------------
FILTRO = Path(__file__).resolve().parent / "data" / "filtro.json"
SALIDA_FILTRO = Path(__file__).resolve().parent / "dashboard" / "filtro-data.js"

def _por_que(registro: dict) -> dict | None:
    """Las palabras clave que hicieron entrar el registro, como se escriben
    en él. En TED, si ninguna está en el título propiamente dicho, también
    el tipo de servicio que TED antepone (el que decidió)."""
    from clasificar import _RE_TIPO_TED, terminos_que_encajan, textos_ted

    if registro.get("tipo_registro") == "convocatoria_ue":
        item = registro["original"]
        texto = " ".join([registro["titulo"], item.get("descripcion") or "",
                          item.get("destino_descripcion") or "", item.get("destino_detalle") or ""])
        terminos = terminos_que_encajan(texto, config.CATEGORIAS_CALLS_UE)
        return {"terminos": terminos} if terminos else None
    titulo = registro.get("titulo") or ""
    # TED: con el mismo criterio que clasificar (textos_ted), así que en el
    # grupo genérico "Servicios a empresas" solo cuenta el título.
    texto, real = textos_ted(titulo) if registro["fuente"] == "UE" else (titulo, titulo)
    terminos = terminos_que_encajan(texto)
    if not terminos:
        return None
    salida = {"terminos": terminos}
    m = _RE_TIPO_TED.match(titulo) if texto != real else None
    if m and not terminos_que_encajan(real):
        salida["tipo_ted"] = m.group(2).strip()
    return salida


ETIQUETAS_PREFIJO = {
    "ted": "TED (UE)", "placsp": "PLACSP, perfiles propios", "placsp_agregadas": "PLACSP, plataformas autonómicas",
    "placsp_web": "PLACSP, buscador web", "euskadi": "Euskadi", "ted_adjudicaciones": "TED (UE)",
    "euskadi_adjudicaciones": "Euskadi", "placsp_menores": "PLACSP, contratos menores",
    "euskadi_menores": "Euskadi, contratos menores", "eu_grants": "EU Funding & Tenders",
}
FUENTE_POR_PREFIJO = {"ted": "UE", "placsp": "Estado", "placsp_agregadas": "Estado-agregadas",
                      "placsp_web": "Estado-web", "euskadi": "Euskadi"}
MAX_DESCARTES = 300


def _publicar_filtro(etapas: dict) -> None:
    """dashboard/filtro-data.js: el embudo de esta ejecución (lo que
    clasificar.py dejó en data/filtro.json más las etapas de normalizar) y
    los descartes revisables de licitaciones en plazo, ya convertidos al
    formato de las tarjetas. De TED, solo los de organismos españoles: los
    extranjeros con CPV de marketing y sin palabra clave son cientos y casi
    siempre tienen el título en su idioma."""
    datos = {"fecha": date.today().isoformat(), "embudo": [], "etapas": etapas, "descartes": []}
    if FILTRO.exists():
        try:
            filtro = json.loads(FILTRO.read_text(encoding="utf-8"))
            datos["embudo"] = [dict(e, etiqueta=ETIQUETAS_PREFIJO.get(e["prefijo"], e["prefijo"])) for e in filtro["embudo"]]
            vistos = set()
            for d in filtro["descartes"]:
                fuente = FUENTE_POR_PREFIJO.get(d.get("fuente_prefijo"))
                if fuente is None:
                    continue
                registro = {"fuente": fuente, "original": d["original"], "titulo": d["titulo"], "cpv": d["cpv"],
                            "categorias": [], "revisar_manual": False, "tipo_registro": "licitacion"}
                try:
                    r = CONVERSORES[(fuente, "licitacion")](registro)
                except (KeyError, TypeError, ValueError, AttributeError):
                    continue
                if not _dentro_de_ventana_temporal(r):
                    continue
                if fuente == "UE" and r["pais_territorio"] != "España":
                    continue
                # Mismo id, o mismo título y organismo (TED publica a veces
                # el mismo anuncio varias veces, una por modificación).
                claves = {r["id"], _normalizar_clave(r["titulo"]) + "|" + _normalizar_clave(r["organismo"])}
                if claves & vistos:
                    continue
                vistos |= claves
                datos["descartes"].append({
                    "id": r["id"], "titulo": r["titulo"], "organismo": r["organismo"],
                    "fuente": "Estado" if fuente.startswith("Estado") else fuente,
                    "enlace": r["enlace"], "fecha_limite": r["fecha_limite"],
                    "presupuesto": r.get("presupuesto_valor"), "cpv": list(dict.fromkeys(r.get("cpv") or []))[:3],
                    "motivo": d["motivo"], "termino": d.get("termino"),
                })
        except (ValueError, KeyError, TypeError, OSError) as e:
            print(f"[normalizar] AVISO: no se pudo leer {FILTRO.name}: {e}", file=sys.stderr)
    datos["descartes"].sort(key=lambda d: (d["motivo"] != "servicio_no_ofrecido", d["fecha_limite"]))
    datos["descartes"] = datos["descartes"][:MAX_DESCARTES]
    for d in datos["descartes"]:
        _sin_dni(d)
    SALIDA_FILTRO.write_text(
        "// Generado por normalizar.py (_publicar_filtro). No editar a mano.\n"
        "window.FILTRO_DATA = " + json.dumps(datos, ensure_ascii=False) + ";\n", encoding="utf-8")


def _es_organismo_vasco(organismo: str, vascos: set[str]) -> bool:
    """Por topónimo, o porque el nombre es exactamente el de un organismo
    vasco conocido. Antes bastaba con que el nombre EMPEZARA igual
    (_organismos_compatibles), y entre los conocidos hay nombres genéricos
    como "Dirección General": la "Dirección General de Comunicación y
    Proyección Institucional" del Gobierno de Navarra salía como Euskadi
    (visto el 2026-10-02 al traer sus sistemas dinámicos)."""
    clave = _normalizar_clave(organismo)
    if any(re.search(r"\b" + t + r"\b", clave) for t in TOPONIMOS_VASCOS):
        return True
    return clave in vascos


EUSKADI_BUSQUEDA_ANUNCIOS = "https://www.contratacion.euskadi.eus/webkpe00-kpeperfi/es/ac70cPublicidadWar/busquedaAnuncios?locale=es"


def _from_euskadi(registro: dict) -> dict:
    item = registro["original"]

    autoridad = item.get("contractingAuthority") or {}
    organismo = autoridad.get("name") or NO_PUBLICADO

    fecha_publicacion = _limpiar_fecha(item.get("firstPublicationDate") or item.get("lastPublicationDate"))
    fecha_limite = _limpiar_fecha(item.get("deadlineDate"))

    presupuesto_valor, presupuesto_display = _parsear_presupuesto(item.get("budgetWithoutVAT"))

    tipo_proc = (item.get("contractProcedureType") or {}).get("name", "")
    estado_proc = (item.get("contractProcedureStatus") or {}).get("name", "")
    codigo = item.get("code", "")
    titulo = registro["titulo"]
    resumen = f"Expediente {codigo} · {tipo_proc} · Estado: {estado_proc}".strip(" ·")

    # La API de Euskadi no da una URL de detalle por expediente (se
    # comprobó en vivo: la "Búsqueda de anuncios" del propio portal es un
    # formulario que solo acepta POST, no hay URL con parámetros que
    # abra directamente un anuncio). La única excepción real observada en
    # los datos es el portal propio de Bizkaia (elicitacion.ebizkaia.eus),
    # que sí añade "numexpediente=" a la URL para su expediente concreto.
    # En cualquier otro caso se enlaza al buscador público (no al portal
    # de licitación electrónica, que es para presentar oferta con
    # certificado, no para consultar) y se deja el código de expediente
    # bien visible para que se pueda copiar y pegar en "Código del
    # expediente" del buscador.
    url_bidding = item.get("webpagElectronicBidding") or ""
    if "numexpediente=" in url_bidding:
        enlace = url_bidding
        enlace_directo = True
    else:
        enlace = EUSKADI_BUSQUEDA_ANUNCIOS
        enlace_directo = False

    return {
        "id": _id_unico("Euskadi", str(item.get("id", "")), titulo),
        "titulo": titulo,
        "organismo": organismo,
        "fuente": "Euskadi",
        "pais_territorio": "País Vasco",
        "fecha_publicacion": fecha_publicacion,
        "fecha_limite": fecha_limite,
        "presupuesto_valor": presupuesto_valor,
        "presupuesto_display": presupuesto_display,
        "cpv": registro["cpv"],
        "categorias": registro["categorias"],
        "revisar_manual": registro["revisar_manual"],
        "enlace": enlace,
        "enlace_directo": enlace_directo,
        "codigo_expediente": codigo or None,
        "resumen": resumen,
        # Euskadi no expone CPV (ver docstring de scrapers/euskadi.py), así
        # que no hay tipo de contrato oficial que mostrar — no se inventa.
        "tipo_contrato": NO_PUBLICADO,
        "tipo_registro": "licitacion",
        "_clave_dedup": "licitacion|" + _normalizar_clave(titulo) + "|" + _normalizar_clave(organismo),
    }


# ---------------------------------------------------------------------------
# Adjudicaciones (Fase 1). Esquema añadido respecto a una licitación:
# empresa_adjudicataria, fecha_adjudicacion, importe_adjudicado. No hay
# fecha_limite (el contrato ya está cerrado) ni urgencia de plazo; se
# reutiliza el campo fecha_publicacion para guardar la fecha de
# adjudicación, así el orden por defecto y el filtro de ventana temporal no
# necesitan un camino aparte.
# ---------------------------------------------------------------------------

# NIF: limpieza, enmascarado de personas y nacionalidad viven en nif.py
# (compartido con los scrapers y el histórico). Se mantienen estos nombres
# porque los usa el resto del módulo y el histórico.
_nif_limpio = nif.limpiar
nif_enmascarado = nif.enmascarado
es_empresa_espanola = nif.es_espanola


def _from_ted_adjudicacion(registro: dict) -> dict:
    item = registro["original"]

    organismo = _texto_ted(item.get("buyer-name"))

    empresa = _texto_ted(item.get("winner-name"), idiomas=())

    paises = item.get("buyer-country") or []
    codigo_pais = paises[0] if paises else None
    pais = PAISES_ISO3.get(codigo_pais, codigo_pais) if codigo_pais else "UE (sin país especificado)"

    fecha_adjudicacion = _limpiar_fecha(item.get("publication-date"))

    duraciones = item.get("contract-duration-end-date-lot") or []
    fecha_fin_estimada = _limpiar_fecha(duraciones[0]) if duraciones else NO_PUBLICADO

    valores_importe = item.get("result-value-lot") or []
    moneda_importe = (item.get("result-value-cur-lot") or ["EUR"])[0]
    importe_valor, importe_display = _parsear_presupuesto(valores_importe[0] if valores_importe else None, moneda_importe)

    numero_pub = item.get("publication-number", "")
    enlace = f"https://ted.europa.eu/es/notice/-/detail/{numero_pub}" if numero_pub else NO_PUBLICADO
    titulo = registro["titulo"]

    return {
        "id": _id_unico("UE-adj", numero_pub, titulo),
        "titulo": titulo,
        "organismo": organismo,
        "fuente": "UE",
        "pais_territorio": pais,
        "fecha_publicacion": fecha_adjudicacion,
        "fecha_limite": NO_PUBLICADO,
        "presupuesto_valor": None,
        "presupuesto_display": NO_PUBLICADO,
        "cpv": registro["cpv"],
        "categorias": registro["categorias"],
        "revisar_manual": registro["revisar_manual"],
        "enlace": enlace,
        "enlace_directo": True,
        "codigo_expediente": None,
        "resumen": titulo,
        "tipo_contrato": _tipo_contrato(registro["cpv"]),
        "tipo_registro": "adjudicacion",
        "empresa_adjudicataria": empresa,
        "fecha_adjudicacion": fecha_adjudicacion,
        "fecha_fin_estimada": fecha_fin_estimada,
        "importe_adjudicado_valor": importe_valor,
        "importe_adjudicado_display": importe_display,
        "_empresa_espanola": es_empresa_espanola(None, item.get("winner-country"), codigo_pais == "ESP"),
        "_clave_dedup": "adjudicacion|" + _normalizar_clave(_titulo_ted_sin_prefijo(titulo)) + "|" + _normalizar_clave(organismo),
    }


def _from_placsp_adjudicacion(registro: dict) -> dict:
    item = registro["original"]

    organismo = item.get("organismo") or NO_PUBLICADO
    fecha_adjudicacion = _limpiar_fecha(item.get("fecha_adjudicacion"))
    empresa = item.get("empresa_adjudicataria") or NO_PUBLICADO
    importe_valor, importe_display = _parsear_presupuesto(item.get("importe_adjudicado"), "EUR")
    # Presupuesto base sin IVA: con él se calcula la rebaja (ver _competencia).
    presupuesto_valor, presupuesto_display = _parsear_presupuesto(item.get("presupuesto_sin_iva"), "EUR")

    titulo = registro["titulo"]

    return {
        "id": _id_unico("Estado-adj", item.get("expediente", ""), titulo),
        "titulo": titulo,
        "organismo": organismo,
        "fuente": "Estado",
        "pais_territorio": "España",
        "fecha_publicacion": fecha_adjudicacion,
        "fecha_limite": NO_PUBLICADO,
        "presupuesto_valor": presupuesto_valor,
        "presupuesto_display": presupuesto_display,
        "cpv": registro["cpv"],
        "categorias": registro["categorias"],
        "revisar_manual": registro["revisar_manual"],
        "enlace": item.get("enlace") or NO_PUBLICADO,
        "enlace_directo": True,
        "codigo_expediente": item.get("expediente"),
        "resumen": titulo,
        "tipo_contrato": _tipo_contrato(registro["cpv"]),
        "tipo_registro": "adjudicacion",
        "empresa_adjudicataria": empresa,
        "empresa_nif": _nif_limpio(item.get("empresa_nif")),
        "fecha_adjudicacion": fecha_adjudicacion,
        "fecha_fin_estimada": NO_PUBLICADO,
        "importe_adjudicado_valor": importe_valor,
        "importe_adjudicado_display": importe_display,
        "_empresa_espanola": es_empresa_espanola(item.get("empresa_nif"), comprador_espanol=True),
        "_clave_dedup": "adjudicacion|" + _normalizar_clave(titulo) + "|" + _normalizar_clave(organismo),
    }


# Plataformas autonómicas agregadas en PLACSP (sindicacion_1044): mismos
# campos que el feed general, así que se convierten igual. Al deduplicar
# pierden frente a TED, al feed general y a la API de Euskadi, y ganan al
# buscador web (que no trae CPV ni lugar). Llevan la marca de origen web para
# que un organismo vasco que se colara salga como "Euskadi".
PRIORIDAD_AGREGADAS = 2.5


def _from_placsp_agregada(registro: dict) -> dict:
    salida = _from_placsp(registro)
    salida["_prioridad_dedup"] = PRIORIDAD_AGREGADAS
    salida["_origen_web"] = True
    return salida


def _from_placsp_agregada_adjudicacion(registro: dict) -> dict:
    salida = _from_placsp_adjudicacion(registro)
    salida["_prioridad_dedup"] = PRIORIDAD_AGREGADAS
    return salida


def _from_euskadi_adjudicacion(registro: dict) -> dict:
    item = registro["original"]

    organismo = item.get("organismo_resuelto") or NO_PUBLICADO
    fecha_adjudicacion = _limpiar_fecha(item.get("awardDate"))
    fecha_fin_estimada = _limpiar_fecha(item.get("contractEndDate"))
    empresa = item.get("socialReason") or NO_PUBLICADO
    importe_valor, importe_display = _parsear_presupuesto(item.get("awardAmount"))

    titulo = registro["titulo"]

    return {
        "id": _id_unico("Euskadi-adj", str(item.get("id", "")), titulo),
        "titulo": titulo,
        "organismo": organismo,
        "fuente": "Euskadi",
        "pais_territorio": "País Vasco",
        "fecha_publicacion": fecha_adjudicacion,
        "fecha_limite": NO_PUBLICADO,
        "presupuesto_valor": None,
        "presupuesto_display": NO_PUBLICADO,
        "cpv": registro["cpv"],
        "categorias": registro["categorias"],
        "revisar_manual": registro["revisar_manual"],
        "enlace": item.get("mainEntityOfPage") or NO_PUBLICADO,
        "enlace_directo": bool(item.get("mainEntityOfPage")),
        "codigo_expediente": str(item.get("id") or "") or None,
        "resumen": titulo,
        "tipo_contrato": _tipo_contrato(registro["cpv"]),
        "tipo_registro": "adjudicacion",
        "empresa_adjudicataria": empresa,
        "empresa_nif": _nif_limpio(item.get("CIF")),
        "fecha_adjudicacion": fecha_adjudicacion,
        "fecha_fin_estimada": fecha_fin_estimada,
        "importe_adjudicado_valor": importe_valor,
        "importe_adjudicado_display": importe_display,
        "_empresa_espanola": es_empresa_espanola(item.get("CIF"), comprador_espanol=True),
        "_clave_dedup": "adjudicacion|" + _normalizar_clave(titulo) + "|" + _normalizar_clave(organismo),
    }


# ---------------------------------------------------------------------------
# Contratos menores por vencer (Fase 2). Igual que una adjudicación
# (empresa_adjudicataria, fecha_adjudicacion) más fecha_fin_estimada -la
# razón de ser de esta categoría-. El filtro de ventana ("vence en los
# próximos config.DIAS_AVISO_CONTRATO_MENOR días") se aplica en main(), no
# aquí, igual que _dentro_de_ventana_temporal para las licitaciones.
# ---------------------------------------------------------------------------

# Aproximación documentada: PLACSP da una duración PLANEADA (DAY/MON/ANN),
# no una fecha fin. MON y ANN se aproximan a 30/365 días — suficiente para
# decidir "está a punto de vencer", no para precisión de calendario exacta.
_DIAS_POR_UNIDAD = {"DAY": 1, "MON": 30, "ANN": 365}


def _fecha_fin_estimada_placsp(fecha_adjudicacion_iso: str, duracion_valor, duracion_unidad) -> str:
    fecha = _parsear_fecha_iso(fecha_adjudicacion_iso)
    if fecha is None or not duracion_valor or duracion_unidad not in _DIAS_POR_UNIDAD:
        return NO_PUBLICADO
    try:
        dias = int(float(duracion_valor)) * _DIAS_POR_UNIDAD[duracion_unidad]
    except (TypeError, ValueError):
        return NO_PUBLICADO
    return (fecha + timedelta(days=dias)).isoformat()


def _from_placsp_contrato_menor(registro: dict) -> dict:
    item = registro["original"]

    organismo = item.get("organismo") or NO_PUBLICADO
    fecha_adjudicacion = _limpiar_fecha(item.get("fecha_adjudicacion"))
    fecha_fin_estimada = _fecha_fin_estimada_placsp(fecha_adjudicacion, item.get("duracion_valor"), item.get("duracion_unidad"))
    empresa = item.get("empresa_adjudicataria") or NO_PUBLICADO
    importe_valor, importe_display = _parsear_presupuesto(item.get("importe_adjudicado"), "EUR")

    titulo = registro["titulo"]

    return {
        "id": _id_unico("Estado-menor", item.get("expediente", ""), titulo),
        "titulo": titulo,
        "organismo": organismo,
        "fuente": "Estado",
        "pais_territorio": "España",
        "fecha_publicacion": fecha_adjudicacion,
        "fecha_limite": NO_PUBLICADO,
        "presupuesto_valor": None,
        "presupuesto_display": NO_PUBLICADO,
        "cpv": registro["cpv"],
        "categorias": registro["categorias"],
        "revisar_manual": registro["revisar_manual"],
        "enlace": item.get("enlace") or NO_PUBLICADO,
        "enlace_directo": True,
        "codigo_expediente": item.get("expediente"),
        "resumen": titulo,
        "tipo_contrato": _tipo_contrato(registro["cpv"]),
        "tipo_registro": "contrato_menor_venciendo",
        "empresa_adjudicataria": empresa,
        "empresa_nif": _nif_limpio(item.get("empresa_nif")),
        "fecha_adjudicacion": fecha_adjudicacion,
        "fecha_fin_estimada": fecha_fin_estimada,
        "importe_adjudicado_valor": importe_valor,
        "importe_adjudicado_display": importe_display,
        "_clave_dedup": "",
    }


def _from_euskadi_contrato_menor(registro: dict) -> dict:
    item = registro["original"]

    organismo = item.get("organismo_resuelto") or NO_PUBLICADO
    fecha_adjudicacion = _limpiar_fecha(item.get("awardDate"))
    fecha_fin_estimada = _limpiar_fecha(item.get("contractEndDate"))
    empresa = item.get("socialReason") or NO_PUBLICADO
    importe_valor, importe_display = _parsear_presupuesto(item.get("awardAmount"))

    titulo = registro["titulo"]

    return {
        "id": _id_unico("Euskadi-menor", str(item.get("id", "")), titulo),
        "titulo": titulo,
        "organismo": organismo,
        "fuente": "Euskadi",
        "pais_territorio": "País Vasco",
        "fecha_publicacion": fecha_adjudicacion,
        "fecha_limite": NO_PUBLICADO,
        "presupuesto_valor": None,
        "presupuesto_display": NO_PUBLICADO,
        "cpv": registro["cpv"],
        "categorias": registro["categorias"],
        "revisar_manual": registro["revisar_manual"],
        "enlace": item.get("mainEntityOfPage") or NO_PUBLICADO,
        "enlace_directo": bool(item.get("mainEntityOfPage")),
        "codigo_expediente": str(item.get("id") or "") or None,
        "resumen": titulo,
        "tipo_contrato": _tipo_contrato(registro["cpv"]),
        "tipo_registro": "contrato_menor_venciendo",
        "empresa_adjudicataria": empresa,
        "empresa_nif": _nif_limpio(item.get("CIF")),
        "fecha_adjudicacion": fecha_adjudicacion,
        "fecha_fin_estimada": fecha_fin_estimada,
        "importe_adjudicado_valor": importe_valor,
        "importe_adjudicado_display": importe_display,
        "_clave_dedup": "",
    }


# ---------------------------------------------------------------------------
# Calls for proposals UE (Fase 3). Semántica de fecha como una licitación
# (fecha_limite = fecha límite de solicitud de la convocatoria, con
# urgencia/countdown igual que las licitaciones abiertas) -por eso
# reutiliza _dentro_de_ventana_temporal tal cual, sin función de ventana
# propia-. No hay presupuesto por convocatoria fiable de forma sencilla
# (budgetOverview es una estructura anidada por año/acción/lote, no un
# número único) así que se deja "no publicado" en vez de inventar una
# cifra aproximada.
# ---------------------------------------------------------------------------

# El EU Funding & Tenders Portal, a diferencia de TED, NO publica el texto
# de sus convocatorias en español -se comprobó pidiéndolo explícitamente
# con language=es a la API SEDIA: el título y la descripción vuelven en
# inglés igualmente, el campo "language" es metadato de indexación, no una
# traducción real-. Se traduce con MyMemory (gratuito, sin API key) solo
# para las convocatorias que YA pasaron el filtro de taxonomía (aquí, no
# en el scraper): son decenas, no las ~560 totales, así que no hace falta
# ni conviene traducir todo lo que se descarta.
#
# MyMemory resultó nada fiable en la práctica: TooManyRequests ya a los
# pocos segundos de uso seguido, de forma persistente (no un pico
# puntual -se reintentó minutos después y seguía igual-, probablemente por
# ser una IP/red compartida). TRADUCCIONES_MANUALES es un caché de
# traducciones ya hechas a mano (título + resumen) para no depender de
# ese servicio en cada ejecución; se consulta primero, y solo si el texto
# no está ahí se intenta la API como último recurso. Si tampoco funciona,
# se avisa por stderr en vez de mostrar inglés sin decir nada.
_RUTA_TRADUCCIONES_MANUALES = Path(__file__).resolve().parent / "data" / "traducciones_manuales.json"
_TRADUCCIONES_MANUALES: dict[str, str] = (
    json.loads(_RUTA_TRADUCCIONES_MANUALES.read_text(encoding="utf-8"))
    if _RUTA_TRADUCCIONES_MANUALES.exists() else {}
)
_SIN_TRADUCIR: list[str] = []

# Las traducciones automáticas que sí salieron se guardan entre noches (en
# GitHub Actions, con actions/cache; data/cache/ no se versiona): sin esto se
# pedían otra vez todas cada noche. Y si MyMemory falla varias veces seguidas
# se deja de llamar hasta la noche siguiente: con sus reintentos y esperas,
# un MyMemory caído alargaba Normalizar unos 15 minutos.
_RUTA_CACHE_TRADUCCION = Path(__file__).resolve().parent / "data" / "cache" / "traducciones_auto.json"
FALLOS_SEGUIDOS_MAX = 3


def _leer_cache_traduccion() -> dict[str, str]:
    try:
        cache = json.loads(_RUTA_CACHE_TRADUCCION.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return cache if isinstance(cache, dict) else {}


_CACHE_TRADUCCION: dict[str, str] = _leer_cache_traduccion()
_USADAS: set[str] = set()  # para no arrastrar en la caché convocatorias ya cerradas
_fallos_seguidos = 0


def _traducir_en_es(texto: str) -> str:
    """Nunca debe tumbar el pipeline: si no hay traducción manual ni guardada
    y MyMemory falla o satura el límite de peticiones, se deja el texto en
    inglés -avisando por stderr, no en silencio-."""
    global _fallos_seguidos
    if not texto:
        return texto
    if texto in _TRADUCCIONES_MANUALES:
        return _TRADUCCIONES_MANUALES[texto]
    if texto in _CACHE_TRADUCCION:
        _USADAS.add(texto)
        return _CACHE_TRADUCCION[texto]
    traducido = None
    if _fallos_seguidos < FALLOS_SEGUIDOS_MAX:
        for intento in range(3):
            try:
                traducido = MyMemoryTranslator(source="en-GB", target="es-ES").translate(texto[:490])
                break
            except Exception:  # deep_translator lanza tipos variados (red, cuota, respuesta vacía)
                if intento < 2:
                    time.sleep(3 * (intento + 1))
        time.sleep(0.5)  # ritmo prudente: es un servicio gratuito compartido, no una API propia
    if not traducido:
        _fallos_seguidos += 1
        _SIN_TRADUCIR.append(texto[:80])
        return texto
    _fallos_seguidos = 0
    _CACHE_TRADUCCION[texto] = traducido
    _USADAS.add(texto)
    return traducido


def _guardar_cache_traduccion() -> None:
    _RUTA_CACHE_TRADUCCION.parent.mkdir(parents=True, exist_ok=True)
    vigentes = {t: v for t, v in _CACHE_TRADUCCION.items() if t in _USADAS}
    _RUTA_CACHE_TRADUCCION.write_text(json.dumps(vigentes, ensure_ascii=False), encoding="utf-8")


def _from_eu_grant(registro: dict) -> dict:
    item = registro["original"]

    titulo = _traducir_en_es(registro["titulo"]) or "(sin título)"
    fecha_publicacion = _limpiar_fecha(item.get("startDate"))
    fecha_limite = _limpiar_fecha(item.get("deadlineDate"))
    enlace = item.get("url_detalle") or item.get("url") or NO_PUBLICADO
    identifier = item.get("identifier")
    # Presupuesto del tema, de "budgetOverview" (eu_grants._presupuesto).
    presupuesto_valor, presupuesto_display = _parsear_presupuesto(item.get("presupuesto"), "EUR")

    return {
        "id": _id_unico("UEsub", identifier or item.get("reference", ""), titulo),
        "titulo": titulo,
        "organismo": "Comisión Europea",
        "fuente": "UE-subvenciones",
        "pais_territorio": "UE",
        "fecha_publicacion": fecha_publicacion,
        "fecha_limite": fecha_limite,
        "presupuesto_valor": presupuesto_valor,
        "presupuesto_display": presupuesto_display,
        "proyectos_previstos": item.get("proyectos_previstos"),
        "subvencion_maxima": item.get("subvencion_maxima"),
        # Documento de la convocatoria y anexos (eu_grants._documentos_convocatoria).
        "pliegos": [{"tipo": "convocatoria", "nombre": d.get("nombre"), "url": d["url"]}
                    for d in item.get("documentos") or [] if str(d.get("url") or "").startswith("http")][:MAX_PLIEGOS],
        "cpv": [],
        "categorias": registro["categorias"],
        "revisar_manual": registro["revisar_manual"],
        "enlace": enlace,
        "enlace_directo": True,
        "codigo_expediente": identifier,
        "resumen": _traducir_en_es((item.get("descripcion") or "")[:450]) or titulo,
        "tipo_contrato": NO_PUBLICADO,
        "tipo_registro": "convocatoria_ue",
        "programa": item.get("typesOfAction") or item.get("frameworkProgramme") or NO_PUBLICADO,
        "_clave_dedup": "",
    }


def _lugar(registro: dict) -> tuple[str | None, str | None]:
    """(provincia, comunidad) de un registro clasificado, con el código de
    lugar que publique su fuente (territorio.py hace la traducción):

      - PLACSP: lugar de ejecución del contrato (NUTS) y, si no lo hay,
        código postal del organismo. Las plataformas agregadas solo dan el
        primero; el buscador web, ninguno.
      - Euskadi: región del organismo (codNUTS de la autoridad contratante).
      - TED: región del organismo, solo si es español.

    No se deduce nada del nombre del organismo ni del título."""
    item = registro["original"]
    fuente = registro["fuente"]
    if fuente in ("Estado", "Estado-agregadas", "Estado-web"):
        return territorio.lugar(item.get("lugar_nuts"), None, item.get("organismo_cp"))
    if fuente == "Euskadi":
        autoridad = item.get("contractingAuthority") or {}
        provincia, comunidad = territorio.lugar(None, autoridad.get("codNUTS") or item.get("organismo_nuts"))
        return provincia, comunidad or "País Vasco"
    if fuente == "UE":
        if "ESP" not in (item.get("buyer-country") or []):
            return None, None
        regiones = item.get("buyer-country-sub") or []
        return territorio.lugar(None, regiones[0] if regiones else None)
    return None, None


def _hora(valor) -> str | None:
    """'14:00:00', '14:00:00+02:00' o '14:00:00Z' -> '14:00'."""
    m = re.match(r"\s*(\d{2}):(\d{2})", valor or "")
    return f"{m.group(1)}:{m.group(2)}" if m else None


MAX_PLIEGOS = 6


def _hora_y_pliegos(registro: dict) -> tuple[str | None, list[dict]]:
    """Hora a la que cierra el plazo y enlaces a los pliegos de una
    licitación, tal como los publica su fuente:

      - PLACSP (perfiles propios y plataformas agregadas): hora peninsular y
        los pliegos administrativo y técnico, con su dirección de descarga.
      - TED: hora local del organismo y la dirección donde están los
        documentos (suele ser la ficha en la plataforma nacional).
      - Euskadi: los pliegos administrativo y técnico y la carátula, de la
        ficha pública del expediente (euskadi.anadir_fichas_licitaciones).
        Sin hora: la API da la fecha límite con una hora que casi siempre
        es 00:00 y sin huso fiable, así que no se enseña.
      - Buscador web de PLACSP: nada.

    Cada pliego: {tipo: administrativo | tecnico | caratula | documentacion,
    nombre, url}."""
    item = registro["original"]
    fuente = registro["fuente"]
    if fuente in ("Estado", "Estado-agregadas"):
        pliegos = [p for p in (item.get("pliegos") or []) if (p.get("url") or "").startswith("http")]
        return _hora(item.get("hora_limite")), pliegos[:MAX_PLIEGOS]
    if fuente == "UE":
        horas = item.get("deadline-receipt-tender-time-lot") or []
        urls = []
        for url in item.get("document-url-lot") or []:
            if isinstance(url, str) and url.startswith("http") and url not in urls:
                urls.append(url)
        pliegos = [{"tipo": "documentacion", "nombre": None, "url": url} for url in urls[:MAX_PLIEGOS]]
        return _hora(horas[0] if horas else None), pliegos
    if fuente == "Euskadi":
        pliegos = [p for p in (item.get("ficha") or {}).get("pliegos") or [] if (p.get("url") or "").startswith("http")]
        return None, pliegos[:MAX_PLIEGOS]
    return None, []


MAX_CRITERIOS = 12
# Por encima, casi siempre presupuesto e importe están en unidades distintas
# (anual frente a total, precio unitario...): 379 de 20.800 expedientes
# del histórico el 2026-10-04.
REBAJA_MAX = 0.8


def _competencia(registro: dict, licitadores: list[dict]) -> dict:
    """Ofertas recibidas y rebaja de la adjudicataria sobre el presupuesto.

    - PLACSP: las ofertas del resultado y los dos importes sin IVA. Solo con
      un único resultado: con lotes o acuerdos marco el presupuesto es del
      expediente entero. Rebaja 0 no se enseña: es lo normal en negociados
      (90 % en el histórico) y en contratos a precios unitarios, donde el
      importe adjudicado es el máximo y la rebaja real no se ve.
    - Euskadi: las ofertas son las empresas que se presentaron (ficha).

    Medido en el histórico (2026-10-04): cuando hay rebaja, la mediana es del
    16 %, y crece con la competencia (7 % con una oferta, 30 % con seis o más)."""
    salida = {}
    item = registro["original"]
    if registro["fuente"] in ("Estado", "Estado-agregadas"):
        if item.get("resultados") != 1:
            return salida
        if item.get("ofertas"):
            salida["ofertas"] = item["ofertas"]
        presupuesto = _parsear_presupuesto(item.get("presupuesto_sin_iva"), "EUR")[0]
        importe = _parsear_presupuesto(item.get("importe_adjudicado_sin_iva"), "EUR")[0]
        if presupuesto and importe:
            rebaja = 1 - importe / presupuesto
            if 0.0005 <= rebaja <= REBAJA_MAX:
                salida["rebaja"] = round(rebaja * 100, 1)
    elif licitadores:
        salida["ofertas"] = len(licitadores)
    return salida


def _criterios(registro: dict) -> dict | None:
    """Cómo se puntúa una licitación de PLACSP: qué parte es precio, qué
    parte otros criterios con fórmula y qué parte juicio de valor (la
    propuesta que valora la mesa). Para una agencia es lo que dice si puede
    competir con su propuesta o si gana el que más baja.

    {precio, formulas, juicio: % enteros que suman 100,
     detalle: [{descripcion, peso (%), tipo}], por_lotes: bool}

    Con lotes se enseña el expediente si trae criterios generales y, si no,
    el primer lote; por_lotes avisa de que hay más grupos (pueden puntuar
    distinto). None si la fuente no los publica o no traen peso.

    Euskadi (ver _criterios_euskadi) no dice si un criterio va con fórmula o
    con juicio de valor: da {precio, resto, detalle, por_lotes: False}."""
    if registro["fuente"] == "Euskadi":
        return _criterios_euskadi(registro)
    if registro["fuente"] == "UE":
        return _criterios_ted(registro)
    if registro["fuente"] not in ("Estado", "Estado-agregadas"):
        return None
    grupos = registro["original"].get("criterios_adjudicacion") or []
    if not grupos:
        return None
    grupo = next((g for g in grupos if g["lote"] is None), grupos[0])
    reparto = _reparto_placsp(grupo["criterios"])
    if reparto:
        reparto["por_lotes"] = len(grupos) > 1
    return reparto


def _reparto_placsp(criterios: list[dict]) -> dict | None:
    """{precio, formulas, juicio, detalle} de una lista de criterios de PLACSP
    (los del expediente o los de un lote)."""
    con_peso = [c for c in criterios if c.get("peso") is not None and c["peso"] >= 0]
    total = sum(c["peso"] for c in con_peso)
    if total <= 0:
        return None
    reparto = {"precio": 0.0, "formula": 0.0, "juicio": 0.0}
    for c in con_peso:
        reparto[c["tipo"]] += c["peso"] * 100 / total
    precio, juicio = round(reparto["precio"]), round(reparto["juicio"])
    detalle = sorted(con_peso, key=lambda c: -c["peso"])[:MAX_CRITERIOS]
    return {
        "precio": precio,
        "formulas": max(0, 100 - precio - juicio),  # dos redondeos hacia arriba darían -1
        "juicio": juicio,
        "detalle": [{"descripcion": c["descripcion"] or "(sin descripción)",
                     "peso": round(c["peso"] * 100 / total, 1), "tipo": c["tipo"]} for c in detalle],
    }


MAX_LOTES = 40


def _lotes(registro: dict) -> list[dict]:
    """Lotes de una licitación, con lo que publique su fuente:
    [{id, nombre, importe (sin IVA) | None, precio: % | None}].

      - PLACSP, perfiles propios: nombre, importe y lo que pesa el precio en
        cada lote. Plataformas agregadas: solo el nombre.
      - Euskadi: pestaña "Lotes" de la ficha, con nombre, importe y precio.
      - TED: título de cada lote y, si viene uno por lote, su valor estimado.
        Los criterios no: TED los da todos seguidos, sin decir de qué lote son.
      - Calls for proposals: no tienen lotes (cada tema es una convocatoria).

    Un único lote no se enseña: es la licitación entera."""
    item = registro["original"]
    fuente = registro["fuente"]
    lotes: list[dict] = []
    if fuente in ("Estado", "Estado-agregadas"):
        por_lote = {g["lote"]: _reparto_placsp(g["criterios"]) for g in item.get("criterios_adjudicacion") or [] if g["lote"]}
        for l in item.get("lotes") or []:
            reparto = por_lote.get(l.get("id"))
            lotes.append({"id": l.get("id"), "nombre": l.get("nombre"),
                          "importe": _parsear_presupuesto(l.get("importe"), "EUR")[0],
                          "precio": reparto["precio"] if reparto else None})
    elif fuente == "Euskadi":
        for l in (item.get("ficha") or {}).get("lotes") or []:
            reparto = _reparto_precio_resto(l.get("criterios") or [])
            lotes.append({"id": l.get("id"), "nombre": l.get("nombre"), "importe": l.get("importe") or None,
                          "precio": reparto["precio"] if reparto else None})
    elif fuente == "UE":
        ids = item.get("identifier-lot") or []
        titulos = _textos_ted(item.get("title-lot"), len(ids)) or [None] * len(ids)
        valores = item.get("estimated-value-lot") or []
        valores = valores if len(valores) == len(ids) else [None] * len(ids)
        for ident, titulo, valor in zip(ids, titulos, valores):
            numero = re.sub(r"^LOT-0*", "", str(ident)) or str(ident)
            lotes.append({"id": numero, "nombre": " ".join(titulo.split()) if titulo else None,
                          "importe": _parsear_presupuesto(valor, "EUR")[0], "precio": None})
    return lotes[:MAX_LOTES] if len(lotes) > 1 else []


def _reparto_precio_resto(lista: list[dict]) -> dict | None:
    """{precio, resto, detalle} de una lista de criterios de Euskadi. Solo
    cuando las ponderaciones suman 100 y hay algún criterio de precio (ver
    _criterios_euskadi)."""
    con_peso = [c for c in lista if c.get("peso") is not None and c["peso"] >= 0]
    if not con_peso or len(con_peso) != len(lista):
        return None
    total = sum(c["peso"] for c in con_peso)
    if abs(total - 100) > 0.5 or not any(c["tipo"] == "precio" for c in con_peso):
        return None
    precio = round(sum(c["peso"] for c in con_peso if c["tipo"] == "precio"))
    detalle = sorted(con_peso, key=lambda c: -c["peso"])[:MAX_CRITERIOS]
    return {
        "precio": precio,
        "resto": 100 - precio,
        "detalle": [{"descripcion": c["descripcion"] or "(sin descripción)",
                     "peso": round(c["peso"], 1), "tipo": c["tipo"]} for c in detalle],
    }


def _criterios_euskadi(registro: dict) -> dict | None:
    """Criterios de la ficha pública de Euskadi (euskadi._criterios), que
    solo permite separar el precio del resto:

    {precio, resto: % enteros que suman 100,
     detalle: [{descripcion, peso (%), tipo: precio | otro}], por_lotes: False}

    Solo cuando las ponderaciones suman 100: si suman 200 o 300 es que la
    ficha mezcla los criterios de varios lotes, y si suman menos, que está
    incompleta; en los dos casos el reparto saldría falso. Y solo cuando se
    reconoce algún criterio de precio: sin él no se sabe cuánto pesa (hay
    fichas que solo dicen "Criterios objetivos 47 / Criterios subjetivos 53")."""
    ficha = registro["original"].get("ficha") or {}
    reparto = _reparto_precio_resto(ficha.get("criterios") or [])
    if reparto:
        reparto["por_lotes"] = False
        return reparto
    # Sin criterios generales pero con lotes: se enseñan los del primero y se
    # avisa (como en PLACSP); el precio de cada lote va en la lista de lotes.
    for lote in ficha.get("lotes") or []:
        reparto = _reparto_precio_resto(lote.get("criterios") or [])
        if reparto:
            reparto["por_lotes"] = True
            return reparto
    return None


# El precio por su nombre, en los idiomas que más salen en TED. En los avisos
# españoles hace falta: PLACSP los manda a TED con todos los criterios
# marcados como "quality", también el precio.
_RE_NOMBRE_PRECIO = re.compile(
    r"\bprecio|\bprice\b|\bpreu\b|\bprix\b|\bpreis|\bprezzo|\bpreco\b|\bprijs"
    r"|(?:oferta|proposicion|propuesta)\s+economica", re.I)
_NOMBRE_GENERICO_TED = {"price": "Precio", "cost": "Coste", "quality": "Calidad"}


def _textos_ted(valor, cuantos: int) -> list[str] | None:
    """Lista de textos de un campo multilingüe de TED ({idioma: [..]}), en
    español, inglés o el idioma que venga; None si no hay uno por criterio
    (entonces no se sabe a cuál corresponde cada texto)."""
    if isinstance(valor, dict):
        valor = valor.get("spa") or valor.get("eng") or next(iter(valor.values()), None)
    if isinstance(valor, list) and len(valor) == cuantos and all(isinstance(v, str) for v in valor):
        return valor
    return None


def _criterios_ted(registro: dict) -> dict | None:
    """Criterios de un aviso de TED. Como en Euskadi, solo se puede separar
    el precio (tipos price y cost, o un criterio que se llame "precio") del
    resto: {precio, resto, detalle, por_lotes}.

    TED da todos los lotes seguidos en la misma lista. Si es el mismo
    reparto repetido se enseña una vez (por_lotes); si cada lote puntúa
    distinto no hay forma de separarlos y no se enseña. Tampoco si los pesos
    no suman 100 (o 1, cuando vienen en tanto por uno), ni si ningún
    criterio es el precio: entonces no se sabe cuánto pesa."""
    item = registro["original"]
    tipos = item.get("award-criterion-type-lot") or []
    numeros = item.get("award-criterion-number-lot") or []
    if not tipos or len(tipos) != len(numeros):
        return None
    try:
        pesos = [float(str(n).replace(",", ".")) for n in numeros]
    except ValueError:
        return None
    nombres = (_textos_ted(item.get("award-criterion-name-lot"), len(tipos))
               or _textos_ted(item.get("award-criterion-description-lot"), len(tipos))
               or [None] * len(tipos))
    filas = list(zip(tipos, pesos, nombres))
    por_lotes = False
    reparto = [(t, p) for t, p, _ in filas]
    for periodo in range(1, len(filas) // 2 + 1):
        if len(filas) % periodo == 0 and reparto == reparto[:periodo] * (len(filas) // periodo):
            filas, por_lotes = filas[:periodo], True
            break
    total = sum(p for _, p, _ in filas)
    if abs(total - 100) <= 0.5:
        escala = 1
    elif abs(total - 1) <= 0.005:
        escala = 100
    else:
        return None
    detalle = []
    for tipo, peso, nombre in filas:
        if peso < 0:
            return None
        es_precio = tipo in ("price", "cost") or bool(nombre and _RE_NOMBRE_PRECIO.search(_normalizar_clave(nombre)))
        detalle.append({"descripcion": " ".join(nombre.split()) if nombre else _NOMBRE_GENERICO_TED.get(tipo, "Criterio"),
                        "peso": round(peso * escala, 1), "tipo": "precio" if es_precio else "otro"})
    if not any(d["tipo"] == "precio" for d in detalle):
        return None
    precio = round(sum(d["peso"] for d in detalle if d["tipo"] == "precio"))
    return {"precio": precio, "resto": 100 - precio,
            "detalle": sorted(detalle, key=lambda d: -d["peso"])[:MAX_CRITERIOS], "por_lotes": por_lotes}


def _heredar_hora_y_pliegos(superviviente: dict, duplicado: dict) -> None:
    """Al fusionar la misma licitación vista en dos fuentes, la que se
    queda conserva la hora de cierre y los pliegos de la otra si le faltan:
    TED (que gana al deduplicar) solo da la dirección general de los
    documentos, y PLACSP da los pliegos uno a uno."""
    if not superviviente.get("hora_limite") and duplicado.get("hora_limite"):
        superviviente["hora_limite"] = duplicado["hora_limite"]
    # Las ofertas y la rebaja solo vienen de PLACSP y de Euskadi.
    for campo in ("ofertas", "rebaja"):
        if not superviviente.get(campo) and duplicado.get(campo):
            superviviente[campo] = duplicado[campo]
    # Criterios: mandan los de PLACSP, que separan fórmula y juicio de
    # valor; los de TED y Euskadi solo separan el precio del resto.
    propios, ajenos = superviviente.get("criterios"), duplicado.get("criterios")
    if ajenos and (not propios or ("resto" in propios and "resto" not in ajenos)):
        superviviente["criterios"] = ajenos
    # Lotes: los de la fuente que diga lo que pesa el precio en cada uno
    # (PLACSP o Euskadi) antes que los de TED.
    mios, suyos = superviviente.get("lotes"), duplicado.get("lotes")
    if suyos and (not mios or (any(l.get("precio") is not None for l in suyos)
                               and not any(l.get("precio") is not None for l in mios))):
        superviviente["lotes"] = suyos
    # Adjudicaciones: TED gana al deduplicar, pero las actas e informes de
    # valoración uno a uno solo vienen de PLACSP y de Euskadi; de TED, como
    # mucho, el enlace a la documentación del expediente. Se juntan: primero
    # los documentos sueltos y, si no estaba ya, ese enlace.
    mios, suyos = superviviente.get("documentos_adjudicacion") or [], duplicado.get("documentos_adjudicacion") or []
    sueltos = lambda docs: [d for d in docs if d.get("tipo") != "expediente"]  # noqa: E731
    if suyos and (not mios or (sueltos(suyos) and not sueltos(mios))):
        urls = {d.get("url") for d in suyos}
        superviviente["documentos_adjudicacion"] = suyos + [d for d in mios if d.get("url") not in urls]
    # Empresas que se presentaron (Euskadi): TED no las da.
    if not superviviente.get("licitadores") and duplicado.get("licitadores"):
        superviviente["licitadores"] = duplicado["licitadores"]
    propios = superviviente.get("pliegos") or []
    ajenos = [p for p in duplicado.get("pliegos") or [] if p["tipo"] != "documentacion"]
    if ajenos and not any(p["tipo"] != "documentacion" for p in propios):
        superviviente["pliegos"] = (ajenos + propios)[:MAX_PLIEGOS]
    elif not propios and duplicado.get("pliegos"):
        superviviente["pliegos"] = duplicado["pliegos"]


def _sin_dni(registro: dict) -> None:
    """Última red antes de publicar: ningún DNI o NIE completo en los textos
    que enseña el radar, venga de la fuente que venga (los scrapers ya los
    enmascaran en los campos de NIF; aquí se cubren nombres y títulos con el
    DNI pegado, ver nif.ocultar_en_texto)."""
    for campo in ("titulo", "resumen", "empresa_adjudicataria"):
        if registro.get(campo):
            registro[campo] = nif.ocultar_en_texto(registro[campo])
    for licitador in registro.get("licitadores") or []:
        licitador["nombre"] = nif.ocultar_en_texto(licitador["nombre"])


CONVERSORES = {
    ("UE", "licitacion"): _from_ted,
    ("Estado", "licitacion"): _from_placsp,
    ("Estado-agregadas", "licitacion"): _from_placsp_agregada,
    ("Estado-web", "licitacion"): _from_placsp_web,
    ("Euskadi", "licitacion"): _from_euskadi,
    ("UE", "adjudicacion"): _from_ted_adjudicacion,
    ("Estado", "adjudicacion"): _from_placsp_adjudicacion,
    ("Estado-agregadas", "adjudicacion"): _from_placsp_agregada_adjudicacion,
    ("Euskadi", "adjudicacion"): _from_euskadi_adjudicacion,
    ("Estado", "contrato_menor_venciendo"): _from_placsp_contrato_menor,
    ("Euskadi", "contrato_menor_venciendo"): _from_euskadi_contrato_menor,
    ("UE-subvenciones", "convocatoria_ue"): _from_eu_grant,
}


# Longitud mínima (ya normalizado) para fusionar dos licitaciones porque un
# título empieza igual que el otro: por debajo, "Servicio de comunicación"
# sería el comienzo de demasiados contratos distintos del mismo organismo.
MIN_TITULO_PREFIJO = 40


def main() -> None:
    if not CLASIFICADO.exists():
        print("[normalizar] No existe data/clasificado.json. Ejecuta antes clasificar.py.", file=sys.stderr)
        sys.exit(1)

    registros = json.loads(CLASIFICADO.read_text(encoding="utf-8"))

    normalizados = []
    for registro in registros:
        tipo_registro = registro.get("tipo_registro", "licitacion")
        conversor = CONVERSORES.get((registro["fuente"], tipo_registro))
        if conversor is None:
            continue
        salida = conversor(registro)
        por_que = _por_que(registro)
        if por_que:
            salida["por_que"] = por_que
        salida["provincia"], salida["comunidad"] = _lugar(registro)
        if tipo_registro == "licitacion":
            salida["hora_limite"], salida["pliegos"] = _hora_y_pliegos(registro)
            criterios = _criterios(registro)
            if criterios:
                salida["criterios"] = criterios
            lotes = _lotes(registro)
            if lotes:
                salida["lotes"] = lotes
        elif tipo_registro == "adjudicacion":
            # Actas de la mesa, informes de valoración y resolución: PLACSP
            # los publica en el feed (perfiles propios, ver
            # placsp._documentos_adjudicacion) y Euskadi en la ficha del
            # expediente, que también dice qué empresas se presentaron (ver
            # euskadi.leer_ficha).
            original = registro["original"]
            licitadores = []
            if registro["fuente"] == "Euskadi":
                licitadores = (original.get("ficha") or {}).get("licitadores") or []
            salida.update(_competencia(registro, licitadores))
            if registro["fuente"] == "Estado":
                documentos = original.get("documentos_adjudicacion") or []
            elif registro["fuente"] == "Euskadi":
                documentos = (original.get("ficha") or {}).get("documentos") or []
                licitadores = (original.get("ficha") or {}).get("licitadores") or []
                if licitadores:
                    salida["licitadores"] = [
                        {"nombre": l["nombre"], "nif": _nif_limpio(l.get("nif")), "pyme": l.get("pyme"),
                         "provincia": l.get("provincia")} for l in licitadores if l.get("nombre")]
            elif registro["fuente"] == "UE":
                # TED no da los documentos sueltos: la documentación del
                # expediente en la plataforma del organismo, sacada del
                # anuncio de licitación (ted._documentos_del_procedimiento).
                url = original.get("documentos-procedimiento")
                documentos = [{"tipo": "expediente", "nombre": "Documentación del expediente", "url": url}] if url else []
            else:
                # Plataformas autonómicas: su feed no trae actas ni informes
                # (medido el 2026-10-05: 0 de 494 adjudicaciones de agencia).
                documentos = []
            documentos = [d for d in documentos if (d.get("url") or "").startswith("http")]
            if documentos:
                salida["documentos_adjudicacion"] = documentos
        _sin_dni(salida)
        normalizados.append(salida)

    _FILTROS_VENTANA = {
        "licitacion": _dentro_de_ventana_temporal,
        "adjudicacion": _adjudicacion_reciente,
        "contrato_menor_venciendo": _contrato_menor_por_vencer,
        "convocatoria_ue": _dentro_de_ventana_temporal,
    }
    # Adjudicaciones: solo las ganadas por empresas españolas (ver
    # es_empresa_espanola).
    def por_tipo(registros: list[dict]) -> dict[str, int]:
        cuenta: dict[str, int] = {}
        for r in registros:
            cuenta[r["tipo_registro"]] = cuenta.get(r["tipo_registro"], 0) + 1
        return cuenta

    # Recuento de cada etapa, para la página "Cómo se filtra".
    etapas = {"clasificadas": por_tipo(normalizados)}
    antes_nacionalidad = len(normalizados)
    normalizados = [r for r in normalizados if r.pop("_empresa_espanola", True)]
    print(f"[normalizar] {antes_nacionalidad - len(normalizados)} adjudicaciones descartadas por ser de empresas no españolas")
    etapas["empresas_espanolas"] = por_tipo(normalizados)

    antes_ventana = len(normalizados)
    normalizados = [r for r in normalizados if _FILTROS_VENTANA[r["tipo_registro"]](r)]
    etapas["en_ventana"] = por_tipo(normalizados)
    fuera_de_ventana = antes_ventana - len(normalizados)

    # Deduplicación conservadora: mismo título+organismo normalizados,
    # prioridad TED > Estado > Euskadi (en ese orden, si coinciden entre sí).
    prioridad = {"UE": 0, "Estado": 1, "Euskadi": 2}
    normalizados.sort(key=lambda r: r.pop("_prioridad_dedup", None) or prioridad.get(r["fuente"], 9))

    # Título exacto + organismo compatible (ver _organismos_compatibles). El
    # registro que se queda guarda los ids de sus duplicados para heredar
    # abajo la fecha_primera_aparicion más antigua del grupo.
    vistos = {}  # "tipo|titulo" -> [(registro superviviente, organismo)]
    # Segunda regla, solo para licitaciones con fecha límite: mismo plazo,
    # organismo compatible y un título que es el comienzo del otro. TED
    # publica el título corto y la plataforma autonómica le añade detalle
    # ("...del Ayuntamiento de Viladecans" frente a "...del Ayuntamiento de
    # Viladecans, mediante el fomento de la contratación de..."): con título
    # exacto no se fusionaban (2 de 42 al añadir sindicacion_1044).
    por_plazo = {}  # fecha límite -> [(registro superviviente, título, organismo)]
    finales = []
    duplicados = 0
    ids_vistos = set()
    por_id = {}  # id -> registro que se queda con él
    for r in normalizados:
        clave = r.pop("_clave_dedup")
        # Mismo id = mismo registro (p. ej. PLACSP por feed y por buscador
        # web aunque el organismo se escriba distinto): nunca dos veces.
        if r["id"] in ids_vistos:
            duplicados += 1
            _heredar_hora_y_pliegos(por_id[r["id"]], r)
            continue
        ids_vistos.add(r["id"])
        por_id[r["id"]] = r
        if clave:
            tipo, titulo_clave, organismo_clave = clave.split("|")
            grupo = vistos.setdefault(tipo + "|" + titulo_clave, [])
            superviviente = next((s for s, o in grupo if _organismos_compatibles(o, organismo_clave)), None)
            plazo = r["fecha_limite"][:10] if tipo == "licitacion" and r["fecha_limite"] != NO_PUBLICADO else None
            if superviviente is None and plazo and len(titulo_clave) >= MIN_TITULO_PREFIJO:
                for s, titulo_s, organismo_s in por_plazo.get(plazo, []):
                    corto, largo = sorted((titulo_s, titulo_clave), key=len)
                    if largo.startswith(corto) and _organismos_compatibles(organismo_s, organismo_clave):
                        superviviente = s
                        break
            if superviviente is not None:
                duplicados += 1
                superviviente.setdefault("_ids_equivalentes", []).append(r["id"])
                _heredar_hora_y_pliegos(superviviente, r)
                # Un tercer registro con el mismo id que este duplicado tiene
                # que heredar sobre el que se queda.
                por_id[r["id"]] = superviviente
                continue
            grupo.append((r, organismo_clave))
            if plazo and len(titulo_clave) >= MIN_TITULO_PREFIJO:
                por_plazo.setdefault(plazo, []).append((r, titulo_clave, organismo_clave))
        finales.append(r)

    # fecha_primera_aparicion: cuándo vio ESTE radar el registro por primera
    # vez, clave = "id" (estable entre ejecuciones porque se deriva de datos
    # de la propia fuente, ver _id_unico). Se persiste en un fichero aparte
    # que el workflow commitea junto al resto de datos -si no se guardara,
    # cada ejecución "olvidaría" lo visto el día anterior y todo parecería
    # nuevo siempre-. Se reconstruye desde cero en cada ejecución a partir
    # de "finales", así que un id que deja de aparecer (licitación cerrada,
    # etc.) se poda solo del fichero, sin crecer indefinidamente.
    hoy_iso = date.today().isoformat()
    mapa_previo = {}
    if PRIMERA_APARICION.exists():
        try:
            mapa_previo = json.loads(PRIMERA_APARICION.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            mapa_previo = {}

    # Si el registro absorbió duplicados de otra fuente, hereda la fecha más
    # antigua del grupo: la misma licitación vista hace 5 días en TED no debe
    # volver a salir como "nueva" el día que llega por PLACSP (o al revés).
    mapa_nuevo = {}
    for r in finales:
        ids = [r["id"]] + r.pop("_ids_equivalentes", [])
        fechas = [mapa_previo[i] for i in ids if i in mapa_previo]
        primera = min(fechas) if fechas else hoy_iso
        r["fecha_primera_aparicion"] = primera
        for i in ids:
            mapa_nuevo[i] = primera

    PRIMERA_APARICION.parent.mkdir(parents=True, exist_ok=True)
    PRIMERA_APARICION.write_text(json.dumps(mapa_nuevo, ensure_ascii=False, indent=2), encoding="utf-8")

    # El buscador web de PLACSP incluye la plataforma de Euskadi agregada
    # pero no dice de qué comunidad es el organismo: lo que solo llega por
    # ahí salía como "Estado" (caso real del 2026-10-01: redes sociales del
    # Ayuntamiento de Bilbao). Se pasa a "Euskadi" si el organismo es vasco.
    vascos = _organismos_vascos(finales)
    for r in finales:
        if r.pop("_origen_web", False) and _es_organismo_vasco(r["organismo"], vascos):
            r["fuente"] = "Euskadi"
            r["comunidad"] = r["comunidad"] or "País Vasco"

    _historiales(finales)
    _antecedentes(finales)

    # Orden final: fecha límite ascendente para lo que tiene plazo; dentro
    # del bloque sin plazo (todos los contratos menores, y alguna
    # licitación abierta sin fecha publicada), el más reciente primero.
    # Se hace en dos pasadas aprovechando que sort() en Python es estable:
    # la pasada de "más reciente primero" fija el orden base, y la pasada
    # de fecha límite solo reordena entre sí a los que SÍ tienen plazo,
    # dejando intacto el orden relativo de los que no lo tienen.
    finales.sort(key=lambda r: r["fecha_publicacion"], reverse=True)
    finales.sort(key=lambda r: (r["fecha_limite"] == NO_PUBLICADO, r["fecha_limite"]))

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(finales, ensure_ascii=False, indent=2), encoding="utf-8")

    # El dashboard se abre con doble clic vía file://, y bajo ese esquema
    # fetch() de un .json es bloqueado por CORS en Chrome/Edge. Por eso los
    # mismos datos se vuelcan también como script JS con los datos inline,
    # que index.html carga con <script src="tenders-data.js"> y sí funciona
    # sin servidor en cualquier navegador.
    SALIDA_DASHBOARD.parent.mkdir(parents=True, exist_ok=True)
    contenido_js = "window.TENDERS_DATA = " + json.dumps(finales, ensure_ascii=False, indent=2) + ";\n"
    SALIDA_DASHBOARD.write_text(contenido_js, encoding="utf-8")

    etapas["publicadas"] = por_tipo(finales)
    _publicar_filtro(etapas)

    _guardar_cache_traduccion()

    n_revisar = sum(1 for r in finales if r["revisar_manual"])
    conteo_tipos = {}
    for r in finales:
        conteo_tipos[r["tipo_registro"]] = conteo_tipos.get(r["tipo_registro"], 0) + 1
    print(f"[normalizar] {fuera_de_ventana} descartadas por estar fuera de ventana (ni publicadas en los últimos {config.DIAS_ANTIGUEDAD_MAXIMA} días ni con plazo confirmado abierto)")
    print(f"[normalizar] {len(finales)} registros unificados ({duplicados} duplicados eliminados, {n_revisar} para revisar manualmente) — {conteo_tipos}")
    print(f"[normalizar] -> {SALIDA}")
    print(f"[normalizar] -> {SALIDA_DASHBOARD} (el dashboard lee este archivo, no el .json)")
    if _SIN_TRADUCIR:
        print(
            f"[normalizar] AVISO: {len(_SIN_TRADUCIR)} textos de 'calls for proposals' se quedaron en "
            f"inglés (sin traducción manual en data/traducciones_manuales.json y MyMemory no respondió): "
            + "; ".join(_SIN_TRADUCIR[:5]) + ("..." if len(_SIN_TRADUCIR) > 5 else ""),
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
