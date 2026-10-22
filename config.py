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
DIAS_AVISO_CONTRATO_MENOR = 60  # 90 hasta el 2026-10-23: 584 contratos, lista interminable

# Contratos adjudicados por licitación (no menores) que terminan en los
# próximos N días: el organismo está preparando el pliego nuevo. Un concurso
# tarda meses en prepararse, por eso más que en los menores; a un año vista
# todavía no hay nada que hacer (decisión de Mikel, 2026-10-23).
DIAS_AVISO_LICITACION = 182

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
# "seo" suelto (sin "posicionamiento", "auditoria seo"...) solo cuenta si el
# título dice algo más del mundo digital (SEO_CONTEXTO) y no es uno de los
# otros "seo" (SEO_NO). Medido el 2026-10-05 sobre 64.000 títulos y el
# histórico: 153 entraban solo por "seo" y la mitad eran ruido, sobre todo
# contratos técnicos de navegación aérea que empiezan por "Seo de..." (una
# sigla), la Seo de Urgell, SEO/BirdLife y los congresos de la Sociedad
# Española de Oftalmología. Ver clasificar._coincide.
SEO_CONTEXTO = [
    "web", "webs", "pagina", "paginas", "portal", "posicionamiento", "posicionament", "posicionamento",
    "buscador", "buscadores", "cercadors", "google", "digital", "digitales", "online", "internet",
    "sem", "rrss", "redes", "contenido", "contenidos", "optimizacion", "optimizar", "optimizado",
    "optimizados", "optimitzacio", "optimizazioa", "blog", "wordpress", "youtube", "trafico", "marketing",
    "analitica", "keywords", "publireportaje", "publirreportaje", "banner", "articulos", "redaccion",
    "campana", "promocion", "difusion", "estrategia", "auditoria", "informes", "asesoramiento",
    "formacion", "curso", "taller", "jornada", "ia", "chatgpt", "reputacion", "patrocinio", "canales",
    "informativas", "mensual", "eus", "com",
]
SEO_NO = [
    "calle seo", "calle de la seo", "plaza de la seo", "pza la seo", "plaza la seo",
    "seo de urgel", "seo de urgell", "seo d urgell", "seo birdlife", "seo bird life",
    "congreso seo", "congreso de la seo", "socio de la seo", "socios de la seo",
    # Navegación aérea: dicen "digital" o "canales" sin ser de agencia.
    "tacc", "sacta", "acc cats", "comunicaciones voz", "grabacion digital de comunicaciones",
]

# "sem" suelto, igual que "seo": solo cuenta si el título habla de algo
# digital o publicitario. Medido el 2026-10-17 sobre el radar y el histórico:
# 520 títulos con "sem" y solo 43 de marketing; el resto eran códigos de
# expediente ("SEM-340" en un mantenimiento de redes de agua), el Sistema
# d'Emergències Mèdiques catalán, microscopios SEM, semestres y semanas
# abreviados ("2º sem.") y congresos de la Sociedad Española de
# Microbiología. Ver clasificar._coincide.
SEM_CONTEXTO = [
    "seo", "posicionamiento", "posicionament", "google", "ads", "adwords", "campana", "campanas",
    "campanya", "campanyes", "kanpaina", "kanpainak", "online", "digital", "digitales", "internet",
    "web", "webgune", "webgunea", "webgunearen", "buscador", "buscadores", "cercadors",
    "redes sociales", "publicidad", "publicitaria", "publicitarias", "publicitat", "marketing",
    "display", "ppc", "anuncios", "banner", "banners", "paid media", "programatica",
    "analitica", "conversion", "conversiones",
]

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
        "gestion de comunidad digital", "community manager",
        # Formas de encargar la gestión que no decían "gestion de redes
        # sociales" tal cual: con ellas un contrato de medios conserva
        # Redes sociales (ver SOLO_CANAL_EN_MEDIOS).
        "gestion de las redes sociales", "coordinacion de redes sociales",
        "gestion y coordinacion de redes", "gestion y dinamizacion de redes",
        "contenidos en redes sociales", "contenidos para redes sociales",
        "contenidos en webs y redes sociales", "perfiles en redes sociales",
        "redes sociales municipales", "redes sociales institucionales",
    ],
    "Producción de vídeo / contenido audiovisual": [
        "produccion audiovisual", "produccion de video",
        "video corporativo", "contenido audiovisual", "spot publicitario",
        "realizacion audiovisual", "produccion de videos promocionales",
        # "pelicula" y "videocinta" se quitaron el 2026-10-22: 1.443 títulos
        # del histórico, casi todos proyecciones y derechos de exhibición.
        "grabacion y edicion de video", "cine y video",
        "contenidos de video", "contenido de video",
        "postproduccion", "posproduccion",
        "produccion de contenidos audiovisuales", "video promocional",
        "video institucional", "produccion de spots", "motion graphics",
        "animacion audiovisual", "video para redes sociales",
        "contenido para youtube", "edicion de video",
        # Ronda de octubre de 2026, medida contra 35.000 títulos reales:
        # "audiovisual"/"audiovisuales" sueltos siguen fuera (150 títulos,
        # casi todos alquiler y mantenimiento de equipos de sala), pero
        # estas frases solo aparecen cuando se encarga la pieza.
        "realizacion de un audiovisual", "realizacion de audiovisuales",
        "produccion de un audiovisual", "pieza audiovisual",
        "piezas audiovisuales", "realizacion de video",
        "realizacion de videos", "realizacion de un video",
        "grabacion de videos", "podcast", "podcasts",
        # Fotografía de actos fuera desde el 2026-10-22 (decisión de Mikel).
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
        "paginas web", "sitios web", "portales web", "web municipal",
        "web corporativa", "web institucional",
        "landing", "landing page", "landing pages",
        "web turistica", "portal turistico",
        # Con artículo: "Nuevo diseño de la web de la CNMC" se escapaba
        # (página "Cómo se filtra", 2026-10-04). Medido sobre 64.000 títulos
        # de PLACSP y TED: 8 nuevos, todos de web. "web de" a secas no: mete
        # aplicaciones y servicios web de gestión (24 nuevos, casi todos TI).
        "diseno de la web", "desarrollo de la web", "rediseno de la web",
        "mantenimiento de la web", "nueva web",
        "realizacion de la pagina web", "elaboracion de la pagina web",
    ],
    "Diseño y desarrollo de apps": [
        "aplicacion movil", "app movil", "desarrollo de app",
        "aplicacion para smartphone", "desarrollo de aplicaciones moviles",
        "app nativa", "aplicacion android", "aplicacion ios",
        # "desarrollo de aplicaciones" a secas se quitó el 2026-10-22: 314
        # títulos de informática genérica (licencias, low code, Kubernetes).
        "app hibrida",
        "aplicacion multiplataforma", "desarrollo de app movil",
        "diseno de app", "prototipado de app",
    ],
    "Reputación online / gestión de crisis": [
        # "gestion de crisis" a secas metía seguros y simulacros (2026-10-22).
        "reputacion online", "reputacion digital",
        "comunicacion de crisis", "crisis de comunicacion",
        "crisis de reputacion", "crisis reputacional",
        "monitorizacion de medios", "escucha activa", "gestion de la reputacion",
        "clipping de prensa", "seguimiento de medios",
        "monitorizacion de redes sociales", "analisis de sentimiento",
        "gestion de comentarios", "social listening", "escucha social",
        "gestion de crisis de comunicacion",
        "seguimiento de noticias", "seguimiento de prensa", "press clipping",
    ],
    # "Atención al cliente / soporte" se quitó el 2026-10-22 (decisión de
    # Mikel): call centers, auxiliares y chatbots de atención ciudadana, casi
    # nada de agencia (1.323 títulos del histórico).
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
        # "campana" a secas da 147 títulos de ruido (campaña de Navidad,
        # asfáltica, de saneamiento ganadero...), así que solo entran las
        # campañas con apellido. "promocion turistica" a secas tampoco:
        # acierta 3 de 17, el resto son nombres de organismo ("Sociedad de
        # Promoción Turística") y stands de feria.
        "campana de informacion", "campanas de informacion",
        "campana informativa", "campanas informativas",
        "campana de difusion", "campana de concienciacion",
        "campanas de concienciacion", "campanas de sensibilizacion",
        "campana de promocion", "campana turistica",
        "informacion y sensibilizacion", "difusion y sensibilizacion",
        "servicio de promocion turistica", "servicios de promocion turistica",
        "campana de promocion turistica", "plan de promocion turistica",
        # Vistas en los descartes de "Cómo se filtra" (2026-10-04) y medidas
        # sobre 64.000 títulos: "campaña institucional" mete 5 nuevas (4 de
        # agencia) y "gestión/captación de patrocinios" 2 (las 2). NO
        # "campaña de Navidad" (20 nuevas, casi todas alumbrado, pistas de
        # hielo o carpas) ni "patrocinio" suelto (166: patrocinios de eventos
        # y clubes, no servicios de agencia).
        "campana institucional", "campanas institucionales",
        "gestion de patrocinios", "captacion de patrocinios",
        "presencia digital", "estrategia digital", "canales digitales",
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
        # Octubre de 2026: con solo esas tres frases, los contratos de
        # inserción y compra de medios no entraban aquí y, como enumeran los
        # canales ("prensa, radio, televisión y redes sociales"), acababan
        # en Redes sociales (ver SOLO_CANAL_EN_MEDIOS).
        "espacios publicitarios", "espacio publicitario",
        "insercion publicitaria", "inserciones publicitarias",
        "insercion de publicidad", "insercion de anuncios",
        "insercion de campanas", "insercion de la campana",
        "central de medios", "agencia de medios", "compra de medios",
        "planificacion y compra", "difusion en medios",
        "difusion en los medios", "publicidad en medios",
        "campana en medios",
        # "soportes publicitarios" no: también es diseñar las piezas
        # ("elaboración de soportes publicitarios: página web, tríptico...").
    ],
    "Diseño gráfico / branding": [
        "diseno grafico", "identidad visual", "branding", "imagen corporativa",
        "diseno de marca", "manual de identidad corporativa",
        "maquetacion", "identidad de marca", "arquitectura de marca",
        "diseno de logotipo", "diseno de logo", "naming",
        "guia de estilo", "diseno editorial", "diseno de packaging",
        "diseno de catalogos", "rebranding", "diseno de material grafico",
        # Ronda del benchmark: 5 de 7 aciertos cada una (el resto,
        # señalización y monopostes).
        "imagen de marca", "marca turistica",
    ],
    "Producción de eventos digitales": [
        "evento digital", "retransmision en streaming", "webinar",
        "evento online", "streaming de eventos",
        "gestion de eventos online", "plataforma de eventos virtuales",
        "produccion de webinars", "eventos hibridos",
        "retransmision de eventos", "streaming",
        "retransmision audiovisual", "retransmision en directo",
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
        # Ronda del benchmark (2026-10-04), medida contra 203.000 títulos
        # de PLACSP: "difusion de contenidos" era lo que le faltaba a
        # "gestión, creación y difusión de contenidos en los canales
        # digitales" (Avilés). "contenidos digitales" acierta algo más de
        # la mitad (el resto: licencias de software y bibliotecas
        # digitales), como "comunicacion". Los singulares "contenido
        # digital"/"contenido multimedia" se probaron y son suscripciones.
        "contenidos digitales", "difusion de contenidos",
        "contenidos multimedia",
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
        "personalizacion con ia",
        # "chatbot" suelto se quitó el 2026-10-22: 160 de 164 eran
        # chatbots de atención ciudadana.
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
# Capa 2 en catalán, gallego y euskera
# ---------------------------------------------------------------------------
# El buscador web de PLACSP trae también las plataformas autonómicas, sin
# CPV, así que una licitación titulada en otra lengua solo entra si el
# título contiene un término de esta lista. Comparando con las alertas que
# un servicio comercial envió en cinco días (320 convocatorias), el radar
# tenía el 91 % de lo que su taxonomía reconocía, pero se le escapaban
# títulos como "Serveis comunicació, màrqueting, fotografia i gravació
# vídeos" o "Servei de disseny gràfic, maquetació...". Faltaban palabras,
# no fuentes.
#
# Criterio: traducción directa de términos que ya están en castellano, con
# las mismas líneas rojas ("campanya", "difusió", "premsa" o "kanpaina"
# sueltas se probaron y son ruido). Se escriben como quedan tras quitar
# acentos: "comunicació" -> "comunicacio", "deseño" -> "deseno",
# "comerç" -> "comerc". En euskera la palabra cambia con el caso, así que
# cada forma va por separado ("publizitate", "publizitatea"...).
#
# Las claves son las de CATEGORIAS: no se crean categorías nuevas (el
# histórico guarda las categorías como bits según el orden del diccionario).
# Canales que un contrato de medios nombra sin encargar nada sobre ellos
# ("inserción en prensa, radio, televisión y redes sociales", "banner en la
# página web de la revista"): no lo hacen de esa categoría. Solo cuenta si el
# título usa otra palabra clave de la categoría (gestionar las redes, diseñar
# la web...). Ver clasificar.clasificar_texto.
SOLO_CANAL_EN_MEDIOS = {
    "Redes sociales / community management": [
        "redes sociales", "social media", "xarxes socials", "redes sociais",
        "sare sozial", "sare sozialak", "sare sozialen", "sare sozialetan",
    ],
    "Diseño y desarrollo web": [
        "pagina web", "paginas web", "sitio web", "sitios web", "portal web",
        "portales web", "lloc web", "llocs web", "paxina web", "paxinas web",
        "webgune", "webgunea", "webgunearen",
    ],
}

# Auditoría de la taxonomía del 2026-10-22: cada categoría se muestreó sobre
# los 150.000 títulos del histórico y cada arreglo se midió antes de ponerlo.
#
# CONTEXTO_OBLIGATORIO: la palabra solo cuenta si el título dice además algo
# de esta lista (como "seo" y "sem"; ver clasificar._coincide).
CONTEXTO_OBLIGATORIO = {
    # 484 títulos: monitores, cables, displays de máquinas.
    "display": [
        "publicidad", "publicitaria", "publicitario", "publicitarias", "publicitarios", "publicitat", "publicidade",
        "campana", "campanas", "campanya", "banner", "banners", "programatica", "google", "ads", "sem", "seo",
        "rrss", "redes sociales", "anuncios", "anuncio", "marketing", "impresiones", "formatos", "medios digitales",
        "publicacion de display", "red de display",
    ],
    # Peste porcina, obras "PPC", maquinaria. Sin "ppc" en su propio contexto.
    "ppc": [c for c in SEM_CONTEXTO if c != "ppc"],
}

# NEGATIVOS: la palabra no cuenta si el título contiene alguna de estas.
_TELECOM = [
    "voz", "datos", "telefonia", "telefonica", "fibra", "nodos", "satelital", "satelite", "sistema de comunicacion",
    "sistemas de comunicacion", "equipos de comunicacion", "equipo de comunicacion", "vias de comunicacion",
    "via de comunicacion", "centrales de comunicacion", "redes de comunicacion", "red de comunicacion",
    "tecnologias de la informacion", "tecnologies de la informacio", "radiocomunicacion", "comunicaciones",
    "cableado", "control y comunicacion", "automatizacion", "scada", "telecomunicacion", "telecomunicaciones",
    "intercomunicacion", "megafonia", "walkie", "emisoras", "dispositivos", "terminales",
]
_CURSOS_DE_COMUNICACION = [
    "habilidades de comunicacion", "habilidades comunicativas", "comunicacion no verbal", "comunicacion oral",
    "comunicacion efectiva", "comunicacion en lengua", "comunicacion asertiva", "oratoria",
    "comunicacion en ingles", "competencias clave", "comunicacion y lenguaje", "trastornos de la comunicacion",
    "comunicacion aumentativa", "sistemas alternativos", "lengua de signos",
]
_COMPRAS_CON_COMUNICACION = [
    "suministro de mobiliario", "mobiliario", "portatil", "agencia de viajes", "comunicacion publica",
    "comunicacio publica", "derechos de explotacion", "prensa diaria", "suscripcion",
]
_LOGISTICA = [
    "alojamiento", "cena", "almuerzo", "comida", "restauracion", "manutencion", "transporte", "traslado",
    "traslados", "visita guiada", "agencia de viajes", "hotel", "billete", "billetes", "espectaculo",
    "exposicion", "charla", "transfers", "desayuno",
]
_MARCA_EN_OBJETOS = [
    "suministro", "adquisicion", "vestuario", "uniformidad", "uniformes", "carpetas", "letras", "placas",
    "vinilos", "vinilo", "vinilado", "banderolas", "tarjetas de visita", "usb", "estuches", "fundas",
    "corporeo", "atril", "totem", "boligrafos", "merchandising", "patrocinio", "patrocini",
]
NEGATIVOS = {
    # "comunicación" suelta: telecomunicaciones, TIC, cursos de habilidades.
    **{k: _TELECOM + _CURSOS_DE_COMUNICACION + _COMPRAS_CON_COMUNICACION
       for k in ("comunicacion", "comunicacio", "komunikazio", "komunikazioa")},
    # Mailing postal: reparto, manipulado, recibos.
    "mailing": [
        "postal", "postales", "reparto", "manipulado", "manipulacion", "recibos", "carta", "cartas", "correspondencia",
        "impresos", "tarjeta de discapacidad", "tarjetas de discapacidad", "tarjetas discapacidad", "buzoneo", "sobres",
        "ensobrado", "calendario", "correos", "envio postal", "preparacion y distribucion", "taller de escritura",
    ],
    # Redes de bibliotecas, de datos, de agua...
    "gestion de redes": [
        "biblioteca", "bibliotecas", "absysnet", "inalambricas", "de datos", "comunicaciones", "telecomunicaciones",
        "ip", "informaticas", "electricas", "agua", "abastecimiento", "saneamiento", "riego", "calor", "seguridad",
        "sistema de gestion de redes", "software",
    ],
    "landing": ["landing zone", "soft landing", "lamparas", "luz", "taxi", "kids landing"],
    # Plataformas de gestión de TI, no webs de agencia.
    "plataforma web": [
        "para la gestion", "de gestion", "gestion documental", "licencia", "suministro", "subministrament", "tramitacion",
        "intranet", "base de datos", "base de dades", "expedientes", "pagos", "pagaments", "software", "saas", "cloud",
        "nube", "datos", "parquimetros", "portafirmas", "oracle", "visores", "camaras",
    ],
    # Marca en objetos (vinilos, uniformes...) y patrocinios.
    "imagen corporativa": _MARCA_EN_OBJETOS, "imagen de marca": _MARCA_EN_OBJETOS,
    "marca turistica": _MARCA_EN_OBJETOS, "naming": ["naming rights", "naming & ip"],
    # Equipos y licencias de streaming o de videoconferencia, cursos.
    "streaming": ["licencia", "licencias", "suministro", "adquisicion", "emisora", "radio", "unified streaming",
                  "formacion virtual"],
    "webinar": ["licencia", "licencias", "zoom", "videoconferencia", "video conferencia", "inscripcion", "patrocinio",
                "curso", "impartir", "imparticion", "formacion", "formacio", "docencia", "software"],
    # Logística de viajes de prensa e influencers (cenas, hotel, traslados).
    **{k: _LOGISTICA for k in ("influencer", "influencers", "creadores de contenido", "creador de contenido")},
}

# Altas: formas de pedir el servicio que solo caían en la categoría general.
ALTAS_AUDITORIA = {
    "Planificación de medios": [
        "cunas publicitarias", "cuna publicitaria", "cunas de radio", "cuna de radio", "emision de cunas",
        "emision de spots", "publicidad en prensa", "publicidad en radio", "publicidad en la radio",
        "publicidad en television", "publicidad en la television", "publicidad exterior",
        "faldon publicitario", "faldones publicitarios", "falques publicitaries", "falques de radio",
        "publicidad radiofonica", "publicidad en emisoras",
        "publicidad institucional en medio", "publicidad institucional en medios", "publicidad institucional medios",
        "publicidad institucional medio", "en medio radiofonico", "en medios radiofonicos", "en medio impreso",
        "en medios impresos", "en medio digital",
        # Campañas de la Junta de Castilla y León ("...que se publicará entre
        # el 1 y el 15 de..."): 23.232 títulos, cada uno una compra de medios.
        "que se publicara entre", "que se publicara el", "que se realizara entre",
    ],
    "Reputación online / gestión de crisis": [
        "clipping", "recull de premsa", "resumen de prensa", "monitorizacion de noticias",
        "monitorizacion de contenidos en medios", "seguimiento de los impactos",
    ],
    "Redes sociales / community management": [
        "gestion de rrss", "gestion de las rrss", "dinamizacion de rrss", "xestion de rrss", "gestion rrss",
        "gestion de cuentas de instagram", "gestion de las cuentas de instagram",
    ],
    "Diseño gráfico / branding": [
        "identidad corporativa", "identidad grafica", "diseno de cartel", "diseno del cartel", "diseno de carteles",
        "creacion de logotipo", "creacion del logotipo", "creacion de un logotipo", "diseno del logotipo",
    ],
    "SEM / paid media": [
        "publicidad en instagram", "publicidad en facebook", "publicidad en meta", "campana de facebook",
        "campanas digitales", "campana digital", "medios pagados", "post promocionados", "publicaciones promocionadas",
        "anuncios en redes sociales", "promocion de pago",
    ],
}

TERMINOS_OTRAS_LENGUAS = {
    "SEO / posicionamiento en buscadores": [
        "posicionament web", "posicionament en cercadors",
        "posicionamento web", "posicionamento en buscadores",
    ],
    "Redes sociales / community management": [
        "xarxes socials", "redes sociais",
        "gestio de xarxes socials", "gestio de les xarxes socials",
        "dinamitzacio de xarxes socials", "continguts per a xarxes socials",
        "xestion de redes sociais",
        "sare sozial", "sare sozialak", "sare sozialen", "sare sozialetan",
    ],
    "Producción de vídeo / contenido audiovisual": [
        "produccio audiovisual", "produccio de videos", "postproduccio",
        "realitzacio audiovisual", "continguts audiovisuals",
        "gravacio de videos",
        "realizacion dun audiovisual", "contidos audiovisuais",
        "ikus-entzunezko ekoizpena",
    ],
    "Diseño y desarrollo web": [
        "disseny web", "desenvolupament web", "lloc web", "llocs web",
        "manteniment web",
        "deseno web", "desenvolvemento web", "paxina web", "paxinas web",
        "webgune", "webgunea", "webgunearen",
        "web orri", "web orria", "web orriaren",
    ],
    "Diseño y desarrollo de apps": [
        "aplicacio mobil", "aplicacion mobil",
    ],
    "Reputación online / gestión de crisis": [
        "reputacio online", "seguiment de mitjans",
    ],
    "Publicidad y comunicación (general)": [
        # Equivalentes de "publicidad", "comunicacion" y "marketing".
        # "publicitaria" y "comunicacion" ya valen para el gallego.
        "publicitat", "publicitari", "publicitaris", "publicitaries",
        "comunicacio", "marqueting", "canals digitals",
        "gabinet de premsa", "notes de premsa", "relacions publiques",
        "estudi de mercat", "estudis de mercat",
        "campanya de sensibilitzacio", "campanya de difusio",
        "campanya informativa",
        "publicidade", "relacions publicas", "estudo de mercado",
        "difusion e sensibilizacion",
        "publizitate", "publizitatea", "publizitateko",
        "komunikazio", "komunikazioa", "komunikazioko",
        "marketin", "marketina", "iragarki kanpaina",
    ],
    "Planificación de medios": [
        "pla de mitjans", "planificacio de mitjans", "compra de mitjans",
        "espais publicitaris", "insercio publicitaria", "insercio de publicitat",
        "insercio d'anuncis", "insercio d anuncis", "central de mitjans",
        "espazos publicitarios",
    ],
    "Diseño gráfico / branding": [
        "disseny grafic", "identitat visual", "imatge corporativa",
        "identitat corporativa", "maquetacio",
        "deseno grafico", "identidade visual", "imaxe corporativa",
        "identidade corporativa",
        "diseinu grafiko", "diseinu grafikoa",
        "imatge de marca",
    ],
    "Creación de contenidos": [
        "creacio de continguts", "creacion de contidos",
        "continguts digitals",
    ],
    "E-commerce": [
        "comerc electronic", "botiga online", "botiga en linia",
        "tenda en lina",
    ],
}

for _categoria, _terminos in TERMINOS_OTRAS_LENGUAS.items():
    CATEGORIAS[_categoria].extend(_terminos)
for _categoria, _terminos in ALTAS_AUDITORIA.items():
    CATEGORIAS[_categoria].extend(_terminos)

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
    # Los mismos servicios en catalán, gallego y euskera: sin ellos, al
    # entrar "comunicacio" o "maquetacio" se colarían encargos de imprenta
    # ("impressió i distribució dels elements de comunicació...").
    "impressio", "impremta", "retolacio", "senyaletica", "enquadernacio",
    "papereria", "sinaletica", "encadernacion", "papelaria",
    "inprimaketa", "inprenta",
    # Octubre de 2026: contratos que no son de agencia y que, por su tamaño,
    # encabezaban el análisis de mercado (296 M€ de atención y restauración
    # en trenes, concesiones de soportes publicitarios del metro, recogida de
    # residuos, licencias de software, la gestión de una televisión...).
    # Medido sobre el histórico: cada término solo aparece en el servicio en
    # sí, no en campañas sobre él (por eso no "recogida de residuos", que
    # también está en campañas de sensibilización).
    "restauracion a bordo", "explotacion publicitaria",
    "explotacion de la actividad publicitaria", "cesion temporal de uso de espacios",
    "paciente enfermera", "pacient infermera",
    "soporte de software", "software de sistema",
    "servicio publico de comunicacion audiovisual",
    "neteja viaria", "recollida i trasllat de residus",
    # 2026-10-22, decisión de Mikel tras la auditoría: patrocinar clubes,
    # eventos o deportistas (4.937 títulos) y el merchandising o material
    # publicitario físico (1.200), como la imprenta.
    "patrocinio publicitario", "patrocinios publicitarios", "patrocini publicitari",
    "patrocinio deportivo", "contrato de patrocinio", "contrato privado de patrocinio",
    "merchandising", "articulos publicitarios", "articulos promocionales",
    "productos publicitarios", "regalos promocionales", "objetos promocionales",
    "suministro de material publicitario", "publicidad y propaganda",
]
