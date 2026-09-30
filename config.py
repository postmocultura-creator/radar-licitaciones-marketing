# -*- coding: utf-8 -*-
"""
Configuración central del radar de licitaciones para agencia de marketing digital.

Este archivo es el único sitio que hay que tocar para:
  - ampliar los rangos CPV que se consideran "amplios"
  - añadir categorías nuevas o sinónimos/variantes de las existentes
  - ajustar exclusiones y términos de mezcla

No se toca clasificar.py ni normalizar.py para ampliar la taxonomía.
"""

from __future__ import annotations

from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Ventana temporal de captura
# ---------------------------------------------------------------------------
DIAS_ANTIGUEDAD_MAXIMA = 30  # licitaciones publicadas en los últimos N días


def fecha_corte() -> date:
    return date.today() - timedelta(days=DIAS_ANTIGUEDAD_MAXIMA)


# Ventana de aviso para "contratos menores por vencer": cuántos días hacia
# delante desde hoy se considera que un contrato menor "está a punto de
# terminar" y merece una visita comercial. Ver README, sección "Contratos
# menores".
DIAS_AVISO_CONTRATO_MENOR = 90

# Cuánto hay que mirar hacia ATRÁS al pedir contratos menores a Euskadi para
# no perderse ninguno que venza pronto. No es lo mismo que "adjudicado
# recientemente" (eso usa DIAS_ANTIGUEDAD_MAXIMA, 30 días, para
# "Adjudicaciones"): un contrato menor adjudicado hace 10 meses con
# duración de 1 año vence pronto igualmente, así que hay que buscar tan
# atrás como la duración máxima legal de un contrato menor (hasta 1 año,
# hasta 2 en ciertos casos) más el propio margen de aviso.
DIAS_HISTORIAL_CONTRATO_MENOR = 455  # ~15 meses (365 + DIAS_AVISO_CONTRATO_MENOR de margen)


# ---------------------------------------------------------------------------
# Capa 1 — CPV amplios (verificados en simap.ted.europa.eu/cpv, no de memoria)
# ---------------------------------------------------------------------------
# Se usan subrangos concretos dentro de cada división, no divisiones completas.
# La división 79 completa (79000000-79999999) incluye servicios jurídicos,
# contabilidad, limpieza, seguridad, imprenta... que no son de una agencia de
# marketing y generarían más ruido que señal. Lo mismo con la división 72
# completa (72000000-72999999), que incluye soporte técnico, hosting puro,
# mantenimiento de hardware, etc. Por eso se acotan a los grupos relevantes.
#
# Cada tupla: (cpv_desde, cpv_hasta, etiqueta descriptiva)
CPV_RANGOS = [
    (79300000, 79342999, "Estudios de mercado, publicidad y marketing"),
    (79416000, 79416200, "Relaciones públicas"),
    (79510000, 79512999, "Atención telefónica / centros de llamada"),
    (72400000, 72428999, "Internet, diseño y desarrollo web"),
    (92100000, 92200999, "Producción audiovisual, cine, radio y televisión"),
    (79822500, 79822500, "Servicios de diseño gráfico"),
]
# El rango de "Relaciones públicas" se acotó de (79416000-79417000) a
# (79416000-79416200): con datos reales de TED se comprobó que 79417000 es
# "Servicios de consultoría en seguridad" (ciberseguridad, protección de
# datos, guardias de seguridad) — un CPV completamente distinto que no
# tiene nada que ver con relaciones públicas. Verificar siempre el
# significado exacto de un código antes de asumirlo por el rango vecino.
# Se probó (72200000, 72266999, "Desarrollo de software y aplicaciones") como
# capa CPV para apps, y se descartó con datos reales de TED: ese grupo mete
# consultoría de sistemas, ERP, mantenimiento de software y proyectos de TI
# genéricos que no tienen nada que ver con una agencia (verificado con
# ejemplos reales devueltos por la API, no de memoria). No existe un
# subgrupo CPV limpio solo para "apps de una agencia": el desarrollo de
# apps se detecta aquí exclusivamente por la capa 2 (texto/keywords), no
# por CPV.


def cpv_en_rango_amplio(cpv: str) -> bool:
    """True si el código CPV (8 dígitos, con o sin dígito de control) cae
    dentro de alguno de los CPV_RANGOS."""
    if not cpv:
        return False
    digitos = "".join(ch for ch in str(cpv) if ch.isdigit())[:8]
    if len(digitos) < 8:
        return False
    valor = int(digitos)
    return any(lo <= valor <= hi for lo, hi, _ in CPV_RANGOS)


def etiqueta_cpv(cpv: str) -> str | None:
    if not cpv:
        return None
    digitos = "".join(ch for ch in str(cpv) if ch.isdigit())[:8]
    if len(digitos) < 8:
        return None
    valor = int(digitos)
    for lo, hi, etiqueta in CPV_RANGOS:
        if lo <= valor <= hi:
            return etiqueta
    return None


# ---------------------------------------------------------------------------
# Capa 2 — Categorías y palabras clave (EXTENSIBLE)
# ---------------------------------------------------------------------------
# Diccionario categoría -> lista de keywords (minúsculas, sin acentos NO es
# necesario: la normalización de texto en clasificar.py ya quita acentos).
# Para añadir una categoría nueva: añadir una entrada aquí. No hace falta
# tocar clasificar.py.
#
# Ronda de recall (a petición explícita del usuario): "prefiero que se
# cuele alguna que no interese a que no metamos otras que sí puedan ser
# interesantes". Se han añadido muchas más variantes/sinónimos por
# categoría frente a la ronda anterior (que priorizaba precisión). La
# única línea roja que se mantiene: palabras sueltas que en datos reales
# dieron 50-100% de ruido puro (formacion, consultoria, tecnologia,
# automatizacion, inteligencia artificial/ia a secas) siguen exigiendo
# frase completa — no es una cuestión de gusto, es que con esas sueltas la
# categoría deja de ser navegable (cientos de contratos de limpieza,
# obra civil o cursos de conducción por cada uno relevante). Con el resto
# de términos se ha preferido ampliar aunque cuele algún falso positivo
# ocasional (p. ej. "influencer"/"marketplace"/"chatbot" sueltos).
CATEGORIAS = {
    "SEO / posicionamiento en buscadores": [
        "seo", "posicionamiento en buscadores", "posicionamiento web",
        "posicionamiento organico", "search engine optimization",
        "optimizacion para motores de busqueda", "optimizacion seo",
        "auditoria seo", "consultoria seo", "estrategia seo",
        "linkbuilding", "link building", "posicionamiento en google",
        "seo tecnico", "seo on page", "seo off page", "seo local",
    ],
    "SEM / paid media": [
        "sem", "paid media", "publicidad programatica", "google ads",
        "campanas de publicidad digital", "display", "ppc",
        "compra programatica", "medios digitales de pago",
        "publicidad en buscadores", "google adwords", "adwords",
        "meta ads", "facebook ads", "instagram ads", "linkedin ads",
        "tiktok ads", "publicidad en redes sociales", "campanas ppc",
        "gestion de campanas sem", "compra de medios digitales",
        "publicidad en internet", "anuncios digitales", "publicidad online",
        "publicidad digital",
    ],
    "Email marketing y CRM": [
        "email marketing", "marketing automation", "mailing",
        "newsletter", "correo electronico masivo", "automatizacion de marketing",
        "envio de comunicaciones electronicas", "emailing",
        "campanas de email", "campanas de emailing", "email marketer",
        "marketing directo digital", "automatizacion de emails",
        "flujos de automatizacion de marketing",
        # "crm" a secas se descartó: en datos reales de PLACSP/Euskadi es un
        # término genérico de software de gestión (sistemas de relación con
        # CIUDADANOS, no con clientes) que no tiene nada que ver con una
        # agencia. Se exige contexto de cliente/marketing.
        "gestion de relaciones con clientes", "crm de clientes",
        "implantacion de crm comercial",
    ],
    "Redes sociales / community management": [
        "redes sociales", "community management", "gestion de redes sociales",
        "social media", "contenido para redes", "gestion de perfiles sociales",
        "gestor de comunidades digitales", "gestion de redes",
        "social media manager", "estrategia de redes sociales",
        "plan de social media", "gestion de instagram", "gestion de facebook",
        "gestion de tiktok", "gestion de linkedin", "gestion de twitter",
        "dinamizacion de redes sociales", "dinamizacion de redes",
        "gestion de comunidad digital",
    ],
    "Producción de vídeo / contenido audiovisual": [
        "produccion audiovisual", "produccion de video",
        "video corporativo", "contenido audiovisual", "spot publicitario",
        "realizacion audiovisual", "produccion de videos promocionales",
        "grabacion y edicion de video", "cine y video", "pelicula",
        "videocinta", "contenidos de video", "contenido de video",
        "postproduccion", "posproduccion",
        "produccion de contenidos audiovisuales", "video promocional",
        "video institucional", "produccion de spots", "motion graphics",
        "animacion audiovisual", "video para redes sociales",
        "contenido para youtube", "edicion de video",
    ],
    "Diseño y desarrollo web": [
        "diseno web", "desarrollo web", "diseno y desarrollo de pagina web",
        "pagina web", "sitio web", "portal web", "rediseno web",
        "desarrollo de sitio web", "mantenimiento web",
        "diseno de sitios web", "diseno de pagina web", "diseno de paginas web",
        "creacion de pagina web", "creacion de sitio web", "creacion de paginas web",
        "programacion web", "plataforma web",
        "desarrollo de landing page", "diseno de landing page",
        "desarrollo frontend", "diseno ux", "diseno ui", "diseno ux ui",
        "experiencia de usuario", "diseno responsive",
        "desarrollo de plataforma web", "actualizacion de pagina web",
        "migracion web", "diseno de interfaz web",
    ],
    "Diseño y desarrollo de apps": [
        "aplicacion movil", "app movil", "desarrollo de app",
        "aplicacion para smartphone", "desarrollo de aplicaciones moviles",
        "app nativa", "aplicacion android", "aplicacion ios",
        "desarrollo de aplicaciones", "app hibrida",
        "aplicacion multiplataforma", "desarrollo de app movil",
        "diseno de app", "prototipado de app",
    ],
    "Reputación online / gestión de crisis": [
        "reputacion online", "reputacion digital", "gestion de crisis",
        "monitorizacion de medios", "escucha activa", "gestion de la reputacion",
        "clipping de prensa", "seguimiento de medios",
        "monitorizacion de redes sociales", "analisis de sentimiento",
        "gestion de comentarios", "social listening", "escucha social",
        "gestion de crisis de comunicacion",
    ],
    "Atención al cliente / soporte": [
        "atencion al cliente", "centro de llamadas", "call center",
        "atencion telefonica", "soporte al usuario", "contact center",
        "atencion multicanal", "servicio de atencion ciudadana",
        "atencion por whatsapp", "atencion por redes sociales",
        "gestion de chat en vivo", "chatbot de atencion al cliente",
    ],
    "Publicidad y comunicación (general)": [
        "publicidad", "campana de comunicacion", "agencia de publicidad",
        "agencia de comunicacion", "promocion institucional",
        "difusion publicitaria", "plan de comunicacion", "gabinete de prensa",
        "estrategia de comunicacion",
        # añadidas tras comparar con datos reales de TED/Euskadi: "marketing"
        # a secas no estaba en ninguna categoría (fallo grave detectado con
        # licitaciones reales tituladas literalmente "Servicio. Marketing"),
        # y "publicidad" con \b no cazaba las formas adjetivas
        # (publicitaria/publicitario/-os/-as) ni "relaciones públicas".
        "marketing", "mercadotecnia",
        "publicitaria", "publicitario", "publicitarios", "publicitarias",
        "espacios publicitarios", "gestion publicitaria",
        "relaciones publicas",
        "estudios de mercado", "estudio de mercado",
        "investigacion de mercado", "investigacion de mercados",
        "servicios de promocion",
        "campana publicitaria", "campanas publicitarias",
        "difusion de campanas", "creatividad publicitaria",
        "concepto creativo", "campana de comunicacion digital",
        "comunicacion 360", "comunicacion integral", "notas de prensa",
        "gestion de prensa", "agencia creativa", "campana de sensibilizacion",
        "campana de divulgacion", "gabinete de comunicacion",
        "plan integral de comunicacion",
        # "comunicacion" a secas: se verificó con datos reales de Euskadi
        # (muestra de 23 títulos discartados) que ronda el 55-60% de
        # precisión -"Servicio de gabinete de comunicacion", "Servicio de
        # comunicación del Ayuntamiento de X", "agencia que coordine la
        # comunicación..."- frente a falsos positivos como "comunicación
        # oral en euskera" (programa de idioma) o "software de gestión,
        # comunicación..." (telecomunicaciones). Muy por encima del 0-10%
        # de "formacion"/"consultoria"/"ia" sueltos, así que se acepta bajo
        # el criterio de recall explícito del usuario. NO añadir "marca" ni
        # "agencia" sueltas: en la misma muestra "marca" salió sobre todo
        # en "marca [fabricante]" de equipamiento (50% falsos) y "agencia"
        # salió dominada por "agencia de viajes" (8 de 14, nada que ver).
        "comunicacion",
    ],
    "Planificación de medios": [
        "planificacion de medios", "plan de medios", "compra de espacios",
    ],
    "Diseño gráfico / branding": [
        "diseno grafico", "identidad visual", "branding", "imagen corporativa",
        "diseno de marca", "manual de identidad corporativa",
        "maquetacion", "identidad de marca", "arquitectura de marca",
        "diseno de logotipo", "diseno de logo", "naming",
        "guia de estilo", "diseno editorial", "diseno de packaging",
        "diseno de catalogos", "rebranding", "diseno de material grafico",
    ],
    "Producción de eventos digitales": [
        "evento digital", "retransmision en streaming", "webinar",
        "evento online", "streaming de eventos",
        "gestion de eventos online", "plataforma de eventos virtuales",
        "produccion de webinars", "eventos hibridos",
        "retransmision de eventos",
    ],
    "Analítica / medición de marketing": [
        "analitica web", "analitica digital", "medicion de campanas",
        "auditoria de marketing digital", "kpis digitales",
        "cuadro de mando de marketing", "analitica de datos digitales",
        "google analytics", "business intelligence de marketing",
        "reporting de marketing", "dashboard de marketing",
        "medicion de resultados digitales", "atribucion de marketing",
        "analisis de datos de marketing",
    ],
    "Estrategia de marketing": [
        "estrategia de marketing", "plan de marketing",
        "planificacion estrategica de marketing",
        "consultoria estrategica de marketing",
        "definicion de estrategia de marketing",
        "diagnostico de marketing", "plan estrategico de comunicacion",
        "brief estrategico de marketing", "consultoria de marketing estrategico",
        "estrategia de marca",
    ],
    "Creación de contenidos": [
        "creacion de contenidos", "creacion de contenido",
        "creacion de contenidos digitales",
        "redaccion de contenidos", "redaccion de contenido",
        "generacion de contenidos", "marketing de contenidos",
        "content marketing", "copywriting", "redaccion publicitaria",
        "produccion de contenidos", "estrategia de contenidos",
        "calendario de contenidos", "content strategy",
        "redactor de contenidos", "guion publicitario",
        "contenido digital para marketing",
    ],
    "E-commerce": [
        "comercio electronico", "ecommerce", "e-commerce",
        "tienda online", "tienda virtual", "plataforma de ecommerce",
        "plataforma ecommerce", "gestion de tienda online",
        "desarrollo de ecommerce", "diseno de ecommerce",
        "marketplace", "venta online", "tienda electronica",
        "catalogo online", "gestion de marketplace",
        "optimizacion de ficha de producto", "tienda digital",
    ],
    "Marketing de influencers / creators": [
        "marketing de influencers", "marketing de influencer",
        "campana de influencers", "campanas de influencers",
        "gestion de influencers", "marketing de creadores",
        "colaboracion con creadores de contenido",
        "influencer", "influencers", "creador de contenido",
        "creadores de contenido", "embajador de marca",
        "prescriptor digital", "colaboracion con influencers",
    ],
    "Automatización e IA de marketing": [
        "inteligencia artificial aplicada al marketing",
        "ia generativa para marketing", "ia aplicada al marketing",
        "automatizacion de procesos de marketing",
        "herramientas de inteligencia artificial para marketing",
        "chatbot de marketing", "asistente virtual de marketing",
        "marketing conversacional", "ia para marketing",
        "personalizacion con ia", "chatbot",
    ],
    "Marketing B2B": [
        "marketing b2b", "marketing btob", "account based marketing",
        "generacion de leads b2b", "captacion de leads b2b",
        "estrategia b2b de marketing", "generacion de leads",
        "captacion de leads", "b2b marketing", "marketing empresarial",
        "generacion de demanda", "demand generation",
    ],
    "Formación y consultoría de marketing": [
        "formacion en marketing digital", "formacion en marketing",
        "formacion en publicidad digital", "formacion en comunicacion digital",
        "consultoria de marketing", "consultoria en marketing digital",
        "asesoria en marketing digital", "capacitacion en marketing digital",
        "formacion en redes sociales", "formacion en seo",
        "talleres de marketing digital", "cursos de marketing digital",
        "consultoria en comunicacion digital", "auditoria de marketing",
    ],
    "Tecnología y MarTech": [
        "martech", "plataforma de marketing", "software de marketing",
        "herramientas de marketing digital",
        "plataforma de automatizacion de marketing",
        "tecnologia de marketing", "stack de marketing",
        "plataforma crm de marketing", "crm de marketing",
        "implantacion de martech", "consultoria martech",
        "seleccion de herramientas de marketing",
        "plataforma de gestion de campanas",
    ],
}

# ---------------------------------------------------------------------------
# Capa 2 en inglés — Fase 3, calls for proposals de la UE (EU Funding &
# Tenders Portal). No es CPV (las subvenciones no lo usan) ni español (el
# contenido del portal es mayoritariamente en inglés): se busca en el
# título + texto de "Expected Outcome"/objetivo de cada convocatoria un
# indicio de que el proyecto financiado va a necesitar comunicación/
# difusión/marketing como parte de sus actividades -el caso de uso no es
# que la agencia sea beneficiaria, es ofrecerse como proveedora a quien sí
# lo sea, ver README-. Reutiliza los NOMBRES de categoría del resto del
# proyecto (para que el desplegable de categorías del dashboard sea
# consistente entre pestañas) con keywords en inglés propias de esta
# fuente.
#
# Ronda 1 (retirada, con datos reales): "dissemination", "citizen
# engagement", "stakeholder engagement", "public engagement" y "outreach
# activities" sueltos generaron 162 coincidencias, 101 solo por
# "dissemination" -jerga administrativa obligatoria en CASI CUALQUIER
# proyecto europeo (todo Horizon Europe exige un plan de dissemination
# como entregable formal, sea del tema que sea), no una señal real de que
# haga falta una agencia-. Caso real detectado: "Fire prevention and
# mitigation for EVs in confined areas" (nada que ver con marketing) coló
# solo por esa palabra. Mismo problema de fondo que "formacion"/
# "consultoria" sueltas en la taxonomía en español (ver más abajo): se
# retiran como término suelto y solo quedan frases específicas de verdad
# (p. ej. "dissemination and exploitation" sí es un paquete de trabajo
# dedicado, no jerga de relleno).
CATEGORIAS_CALLS_UE = {
    "Publicidad y comunicación (general)": [
        "communication strategy", "communication plan", "communication campaign",
        "public communication campaign", "media campaign",
        "press campaign", "advertising campaign", "promotional campaign",
        "visibility plan", "public awareness campaign",
        "raising public awareness", "media relations", "press relations",
    ],
    "Creación de contenidos": [
        "dissemination activities", "dissemination plan",
        "dissemination and exploitation", "dissemination events",
        "content creation", "storytelling",
        "editorial content", "multimedia content", "digital content production",
    ],
    "Redes sociales / community management": [
        "social media", "social media strategy", "social media campaign",
        "community management",
    ],
    "Producción de vídeo / contenido audiovisual": [
        "audiovisual production", "video production", "documentary production",
        "promotional video", "animation production", "podcast production",
    ],
    "Diseño gráfico / branding": [
        "graphic design", "branding", "visual identity", "brand identity",
    ],
    "Diseño y desarrollo web": [
        "website development", "website design", "web platform development",
    ],
    "Reputación online / gestión de crisis": [
        "stakeholder engagement strategy", "public engagement campaign",
        "media monitoring",
    ],
    "Producción de eventos digitales": [
        "webinar", "online event", "virtual conference", "hybrid event",
    ],
}


# ---------------------------------------------------------------------------
# Exclusiones: si el título está dominado por estos términos, NO es una
# licitación de agencia de marketing aunque el CPV caiga en rango límite.
# ---------------------------------------------------------------------------
EXCLUSIONES = [
    "limpieza de edificios", "limpieza viaria", "seguridad privada",
    "vigilancia y seguridad", "obra civil", "suministro de mobiliario",
    "servicio de catering", "transporte de viajeros",
    "mantenimiento de instalaciones", "jardineria", "suministro electrico",
    "suministro de combustible", "seguro de responsabilidad civil",
]

# ---------------------------------------------------------------------------
# Servicios que NO se quieren ofrecer aunque el título también mencione una
# categoría de agencia: si aparecen, la licitación se DESCARTA por completo
# (no se incluye, ni siquiera como "revisar manual"). A petición explícita
# del usuario: toda la pila de "pendientes de revisar" resultó ser esto
# -imprenta/impresión mezclada con diseño o comunicación- y no le interesa
# ofrecer producción física/imprenta, así que no tiene sentido ni mostrarlo
# para revisión; se descarta directamente, aunque el resto del contrato sí
# sea de agencia.
# ---------------------------------------------------------------------------
SERVICIOS_NO_OFRECIDOS = [
    "imprenta", "artes graficas offset", "papeleria", "rotulacion",
    "senaletica", "cartelera exterior", "material de oficina",
    "encuadernacion", "impresion", "impresora", "impresoras",
    "servicios de impresion", "trabajos de imprenta",
]
