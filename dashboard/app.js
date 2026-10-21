(function () {
  "use strict";

  var Nav = window.RadarNav;
  var DATOS = (window.TENDERS_DATA || []).slice();

  // Vistas de listado de esta página, por ruta de hash. "recientes",
  // "licitacion" y "plazo_largo" son tres pestañas de la misma sección
  // (Licitaciones): la primera y la tercera son subconjuntos de la segunda
  // (españolas vistas por primera vez en los últimos tres días; abiertas a
  // las que les quedan más de DIAS_PLAZO_LARGO días).
  var VISTAS = {
    "licitaciones/recientes": { tipo: "recientes", nav: "licitaciones", titulo: "Licitaciones" },
    "licitaciones/abiertas": { tipo: "licitacion", nav: "licitaciones", titulo: "Licitaciones" },
    "licitaciones/plazo-largo": { tipo: "plazo_largo", nav: "licitaciones", titulo: "Licitaciones" },
    "calls": { tipo: "convocatoria_ue", nav: "calls", titulo: "Calls for proposals UE" },
    "menores": { tipo: "contrato_menor_venciendo", nav: "menores", titulo: "Contratos menores por vencer" },
    "adjudicaciones": { tipo: "adjudicacion", nav: "adjudicaciones", titulo: "Adjudicaciones recientes" },
    "guardadas": { tipo: "guardadas", nav: "guardadas", titulo: "Guardadas" },
  };
  var RUTA_POR_TIPO = {};
  Object.keys(VISTAS).forEach(function (ruta) { RUTA_POR_TIPO[VISTAS[ruta].tipo] = ruta; });

  var PESTANAS_LICITACIONES = [
    ["licitaciones/recientes", "Publicadas recientemente", "recientes"],
    ["licitaciones/abiertas", "Licitaciones abiertas", "licitacion"],
    ["licitaciones/plazo-largo", "Sistemas dinámicos y plazo largo", "plazo_largo"],
  ];

  // Lista completa de categorías de la taxonomía (debe reflejar las claves
  // de config.CATEGORIAS en el proyecto Python — el dashboard es JS estático
  // sin acceso a ese archivo, así que se mantiene a mano aquí; tocar los dos
  // sitios si se añade/renombra una categoría). A petición explícita del
  // usuario, el desplegable de categorías siempre las lista TODAS, aunque
  // la vista activa no tenga ahora mismo ninguna licitación en alguna de
  // ellas (sale "(0)" en vez de desaparecer la categoría del selector).
  var CATEGORIAS_CONOCIDAS = [
    "SEO / posicionamiento en buscadores",
    "SEM / paid media",
    "Email marketing y CRM",
    "Redes sociales / community management",
    "Producción de vídeo / contenido audiovisual",
    "Diseño y desarrollo web",
    "Diseño y desarrollo de apps",
    "Reputación online / gestión de crisis",
    "Atención al cliente / soporte",
    "Publicidad y comunicación (general)",
    "Planificación de medios",
    "Diseño gráfico / branding",
    "Producción de eventos digitales",
    "Analítica / medición de marketing",
    "Estrategia de marketing",
    "Creación de contenidos",
    "E-commerce",
    "Marketing de influencers / creators",
    "Automatización e IA de marketing",
    "Marketing B2B",
    "Formación y consultoría de marketing",
    "Tecnología y MarTech",
  ];

  // Opciones fijas de los filtros de fuente y país por vista: igual que
  // las categorías, se muestran siempre (con 0 si ese día no hay nada), a
  // petición del usuario. Fijas POR VISTA, no globales: "Euskadi (0)" en
  // las calls for proposals de la UE sería ruido, ahí nunca puede haber nada.
  var FUENTES_POR_TIPO = {
    recientes: ["Euskadi", "Estado"],
    licitacion: ["Euskadi", "Estado", "UE"],
    plazo_largo: ["Euskadi", "Estado", "UE"],
    adjudicacion: ["Euskadi", "Estado", "UE"],
    contrato_menor_venciendo: ["Euskadi", "Estado"],
    convocatoria_ue: ["UE-subvenciones"],
    guardadas: ["Euskadi", "Estado", "UE"],
  };
  // Países que publican en TED: UE-27 + EEE + Suiza y Reino Unido. Debe
  // coincidir con los nombres de PAISES_ISO3 en normalizar.py. Si aparece
  // un país que no está aquí (TED trae a veces Canadá, Arabia Saudí...), se
  // añade igualmente desde los datos.
  var PAISES_TED = [
    "Alemania", "Austria", "Bélgica", "Bulgaria", "Chequia", "Chipre", "Croacia", "Dinamarca",
    "Eslovaquia", "Eslovenia", "España", "Estonia", "Finlandia", "Francia", "Grecia", "Hungría",
    "Irlanda", "Islandia", "Italia", "Letonia", "Liechtenstein", "Lituania", "Luxemburgo", "Malta",
    "Noruega", "País Vasco", "Países Bajos", "Polonia", "Portugal", "Reino Unido", "Rumanía",
    "Suecia", "Suiza",
  ];
  // El filtro de país solo existe en "Licitaciones abiertas" y en su
  // subconjunto de plazo largo, las únicas vistas con licitaciones de otros
  // países. En las demás solo ofrecía "España / País Vasco" (o "UE"), que
  // duplica el filtro Estado/Euskadi -y mal: una licitación vasca que llega
  // por TED figura como "España"-.
  var PAISES_POR_TIPO = {
    licitacion: PAISES_TED,
    plazo_largo: PAISES_TED,
  };

  // Filtro de importe (mínimo/máximo) por vista: qué campo se filtra, cómo
  // se llama y con qué tramos. Las licitaciones tienen presupuesto; las
  // adjudicaciones y los contratos menores, importe adjudicado (los menores
  // rara vez pasan de 15.000 €, de ahí sus tramos más bajos); las calls for
  // proposals no publican importe por convocatoria: sin filtro.
  var TRAMOS_GENERALES = [15000, 40000, 100000, 500000];
  var IMPORTE_POR_TIPO = {
    recientes: { campo: "presupuesto_valor", nombre: "Presupuesto", tramos: TRAMOS_GENERALES },
    licitacion: { campo: "presupuesto_valor", nombre: "Presupuesto", tramos: TRAMOS_GENERALES },
    plazo_largo: { campo: "presupuesto_valor", nombre: "Presupuesto", tramos: TRAMOS_GENERALES },
    guardadas: { campo: "presupuesto_valor", nombre: "Presupuesto", tramos: TRAMOS_GENERALES },
    adjudicacion: { campo: "importe_adjudicado_valor", nombre: "Importe adjudicado", tramos: TRAMOS_GENERALES },
    contrato_menor_venciendo: { campo: "importe_adjudicado_valor", nombre: "Importe adjudicado", tramos: [3000, 5000, 10000, 15000] },
  };

  // Opciones de "Ordenar por" de cada vista: [clave, etiqueta]. La primera
  // es el orden por defecto. Solo criterios que existen en esa vista. Una
  // vista sin entrada no muestra el selector: "Adjudicaciones recientes" va
  // siempre de la más reciente a la más antigua.
  var ORDENES_POR_TIPO = {
    recientes: [
      ["fecha-desc", "Publicación (más reciente)"],
      ["plazo", "Fecha límite (más próxima)"],
      ["importe-desc", "Presupuesto (mayor primero)"],
      ["encaje-desc", "Encaje con la agencia (mejor primero)"],
    ],
    licitacion: [
      ["plazo", "Fecha límite (más próxima)"],
      ["fecha-desc", "Publicación (más reciente)"],
      ["importe-desc", "Presupuesto (mayor primero)"],
      ["encaje-desc", "Encaje con la agencia (mejor primero)"],
    ],
    plazo_largo: [
      ["plazo", "Fecha límite (más próxima)"],
      ["importe-desc", "Presupuesto (mayor primero)"],
      ["encaje-desc", "Encaje con la agencia (mejor primero)"],
    ],
    contrato_menor_venciendo: [
      ["vencimiento", "Vencimiento (más próximo)"],
      ["importe-desc", "Importe adjudicado (mayor primero)"],
      ["fecha-desc", "Adjudicación (más reciente)"],
    ],
    convocatoria_ue: [
      ["plazo", "Fecha límite de solicitud (más próxima)"],
      ["encaje-desc", "Encaje con la agencia (mejor primero)"],
      ["fecha-desc", "Apertura (más reciente)"],
    ],
    guardadas: [
      ["plazo", "Fecha límite (más próxima)"],
      ["encaje-desc", "Encaje con la agencia (mejor primero)"],
      ["importe-desc", "Presupuesto (mayor primero)"],
    ],
  };
  var ORDEN_SIN_SELECTOR = "fecha-desc";

  function ordenPorDefecto(tipo) {
    return ORDENES_POR_TIPO[tipo] ? ORDENES_POR_TIPO[tipo][0][0] : ORDEN_SIN_SELECTOR;
  }

  // La búsqueda de texto también mira la empresa adjudicataria donde la hay.
  var BUSQUEDA_POR_TIPO = {
    adjudicacion: "Buscar por título, organismo o empresa…",
    contrato_menor_venciendo: "Buscar por título, organismo o empresa…",
  };
  var BUSQUEDA_GENERAL = "Buscar por título u organismo…";

  // Ventana de "recientes": el dato solo tiene fecha (YYYY-MM-DD), no hora,
  // así que "últimos 3 días" se aproxima a nivel de día -publicado hoy,
  // ayer o anteayer- en vez de horas exactas, que no se pueden calcular con
  // lo que publican las fuentes.
  var DIAS_VENTANA_RECIENTES = 2;

  // "Plazo largo": más de este número de días hasta la fecha límite. Debe
  // coincidir con DIAS_PLAZO_LARGO de scrapers/placsp_web.py, que es quien
  // trae de PLACSP las convocatorias que cumplen esto.
  var DIAS_PLAZO_LARGO = 60;

  var ETIQUETAS_CONTEO = {
    recientes: "publicadas recientemente",
    licitacion: "licitaciones",
    plazo_largo: "de plazo largo",
    adjudicacion: "adjudicaciones",
    contrato_menor_venciendo: "contratos menores",
    convocatoria_ue: "calls for proposals",
    guardadas: "guardadas",
  };

  var estado = {
    tipoRegistro: "recientes",
    texto: "",
    fuente: "",
    categoria: "",
    pais: "",
    // "" | "c:<comunidad>" | "p:<provincia>" | "sin" (española sin lugar publicado)
    lugar: "",
    soloRevisarManual: false,
    soloPropuesta: false,
    verDescartadas: false,
    presupuestoMin: 0,
    presupuestoMax: null,
    orden: ordenPorDefecto("recientes"),
  };

  var NO_PUBLICADO = "no publicado";
  var MS_DIA = 24 * 60 * 60 * 1000;
  var MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

  var elVistaListado = document.getElementById("vista-listado");
  var elContenido = document.getElementById("contenido");
  var elTitulo = document.getElementById("titulo-pagina");
  var elPestanas = document.getElementById("pestanas-vista");
  var elTexto = document.getElementById("filtro-texto");
  var elFiltros = document.getElementById("filtros");
  var elFiltrosActivos = document.getElementById("filtros-activos");
  var elCampoFuente = document.getElementById("campo-fuente");
  var elSegmentedFuente = document.getElementById("segmented-fuente");
  var elCategoria = document.getElementById("filtro-categoria");
  var elCampoPais = document.getElementById("campo-pais");
  var elPais = document.getElementById("filtro-pais");
  var elCampoLugar = document.getElementById("campo-lugar");
  var elLugar = document.getElementById("filtro-lugar");
  var elCampoImporte = document.getElementById("campo-importe");
  var elPresupuestoMin = document.getElementById("filtro-presupuesto-min");
  var elPresupuestoMax = document.getElementById("filtro-presupuesto-max");
  var elEtiquetaImporteMin = document.getElementById("etiqueta-importe-min");
  var elEtiquetaImporteMax = document.getElementById("etiqueta-importe-max");
  var elOrden = document.getElementById("filtro-orden");
  var elCampoOrden = document.getElementById("campo-orden");
  var elReset = document.getElementById("boton-reset");
  var elContenedor = document.getElementById("contenedor-tarjetas");
  var elConteo = document.getElementById("conteo-resultados");
  var elFranja = document.getElementById("franja-cifras");
  var elBotonRevisar = document.getElementById("boton-revisar");
  var elBotonPropuesta = document.getElementById("boton-propuesta");
  var elSinResultados = document.getElementById("sin-resultados");
  var TEXTO_SIN_RESULTADOS = elSinResultados.textContent;
  var elFechaGeneracion = document.getElementById("fecha-generacion");

  function hoy() {
    var d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  }

  function parsearFecha(str) {
    if (!str || str === NO_PUBLICADO) return null;
    var partes = str.split("-");
    if (partes.length !== 3) return null;
    var d = new Date(Number(partes[0]), Number(partes[1]) - 1, Number(partes[2]));
    d.setHours(0, 0, 0, 0);
    return isNaN(d.getTime()) ? null : d;
  }

  // "2026-10-19" -> "19 oct 2026"; sin fecha, el texto que se pase.
  function fechaLarga(str, siFalta) {
    var d = parsearFecha(str);
    if (!d) return siFalta || "No publicada";
    return d.getDate() + " " + MESES[d.getMonth()] + " " + d.getFullYear();
  }

  function diasRestantes(fechaLimiteStr) {
    var fecha = parsearFecha(fechaLimiteStr);
    if (!fecha) return null;
    return Math.round((fecha.getTime() - hoy().getTime()) / MS_DIA);
  }

  // "19 oct 2026, 14:00" si la fuente publica la hora de cierre. En TED la
  // hora es la local del organismo: fuera de España se dice.
  function fechaLimiteTexto(t) {
    var texto = fechaLarga(t.fecha_limite);
    if (!t.hora_limite || !parsearFecha(t.fecha_limite)) return texto;
    return texto + ", " + t.hora_limite + (esOrganismoEspanol(t) ? "" : " (hora local)");
  }

  // `t` (opcional): el registro, para afinar el día de cierre con la hora.
  function infoUrgencia(fechaLimiteStr, t) {
    var dias = diasRestantes(fechaLimiteStr);
    if (dias === null) {
      return { clase: "urgencia-sin-fecha", texto: "Sin fecha límite" };
    }
    if (dias < 0) {
      return { clase: "urgencia-roja", texto: "Plazo cerrado" };
    }
    if (dias === 0 && t && t.hora_limite) {
      // Solo se da por cerrado si el organismo es español: la hora es la
      // peninsular y se compara con el reloj de quien mira el radar.
      var ahora = new Date();
      var partes = t.hora_limite.split(":");
      var pasada = esOrganismoEspanol(t) &&
        (ahora.getHours() > Number(partes[0]) || (ahora.getHours() === Number(partes[0]) && ahora.getMinutes() >= Number(partes[1])));
      return { clase: "urgencia-roja", texto: (pasada ? "Cerró hoy a las " : "Cierra hoy a las ") + t.hora_limite };
    }
    if (dias <= 7) {
      return { clase: "urgencia-roja", texto: dias === 0 ? "Cierra hoy" : "Quedan " + dias + " día" + (dias === 1 ? "" : "s") };
    }
    if (dias <= 21) {
      return { clase: "urgencia-ambar", texto: "Quedan " + dias + " días" };
    }
    // Sistemas dinámicos y homologaciones: "Quedan 1.365 días" no dice nada.
    if (dias > 365) {
      return { clase: "urgencia-verde", texto: "Abierta hasta " + parsearFecha(fechaLimiteStr).getFullYear() };
    }
    return { clase: "urgencia-verde", texto: "Quedan " + dias + " días" };
  }

  function infoVencimiento(fechaFinStr) {
    var dias = diasRestantes(fechaFinStr);
    if (dias === null) {
      return { clase: "urgencia-sin-fecha", texto: "Fecha fin no publicada" };
    }
    if (dias < 0) {
      return { clase: "urgencia-sin-fecha", texto: "Ya vencido" };
    }
    if (dias === 0) {
      return { clase: "urgencia-roja", texto: "Vence hoy" };
    }
    if (dias <= 30) {
      return { clase: "urgencia-roja", texto: "Vence en " + dias + " día" + (dias === 1 ? "" : "s") };
    }
    if (dias <= 60) {
      return { clase: "urgencia-ambar", texto: "Vence en " + dias + " días" };
    }
    return { clase: "urgencia-verde", texto: "Vence en " + dias + " días" };
  }

  // NIF que se puede enseñar: el de una sociedad. El de una persona física
  // llega enmascarado ("***4567**", "XXXXX155F") y no se enseña ni se pone en
  // direcciones (ver nif.py).
  function nifPublicable(nif) {
    return nif && nif.indexOf("*") === -1 && nif.indexOf("XXX") !== 0 ? nif : null;
  }

  // Texto de las fuentes dentro de HTML, también dentro de atributos
  // (title, href): por eso se escapan las comillas, no solo < > &.
  var ENTIDADES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  function escaparHtml(str) {
    return (str == null ? "" : String(str)).replace(/[&<>"']/g, function (c) { return ENTIDADES[c]; });
  }

  // Minúsculas y sin tildes, para que "comunicacion" encuentre "Comunicación".
  // Otras licitaciones en plazo del mismo organismo y otras calls del mismo
  // programa (las dos primeras partes del código: "HORIZON-CL6",
  // "CREA-MEDIA"; si la segunda es un año, solo la primera). Índice hecho
  // una vez, al abrir la primera ficha.
  var MAX_OTRAS_ABIERTAS = 5;
  var indiceAbiertas = null;

  function claveGrupo(t) {
    if (t.tipo_registro === "licitacion") {
      return t.organismo && t.organismo !== NO_PUBLICADO ? "o|" + sinTildes(t.organismo).replace(/\s+/g, " ").trim() : null;
    }
    if (t.tipo_registro === "convocatoria_ue" && t.codigo_expediente) {
      var partes = String(t.codigo_expediente).split("-");
      return "p|" + (/^\d+$/.test(partes[1] || "") ? partes[0] : partes.slice(0, 2).join("-"));
    }
    return null;
  }

  function otrasAbiertas(t) {
    var clave = claveGrupo(t);
    if (!clave) return [];
    if (!indiceAbiertas) {
      indiceAbiertas = {};
      DATOS.forEach(function (o) {
        var dias = diasRestantes(o.fecha_limite);
        if (dias !== null && dias < 0) return;
        var k = claveGrupo(o);
        if (k) (indiceAbiertas[k] = indiceAbiertas[k] || []).push(o);
      });
      Object.keys(indiceAbiertas).forEach(function (k) {
        indiceAbiertas[k].sort(function (a, b) { return porFechaProxima("fecha_limite", a, b); });
      });
    }
    return (indiceAbiertas[clave] || []).filter(function (o) { return o.id !== t.id; });
  }

  function sinTildes(str) {
    return String(str).toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  }

  // Con punto de millar siempre: toLocaleString("es-ES") no agrupa los
  // números de cuatro cifras ("3000 €" junto a "10.000 €").
  function miles(valor) {
    return String(valor).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  }

  function redondeoMil(valor) { return Math.round(valor / 1000) * 1000; }

  function euros(valor) {
    return miles(valor) + " €";
  }

  // 18.5 -> "18,5"; 18 -> "18".
  function numeroEs(valor) {
    return String(valor).replace(".", ",");
  }

  // Solvencia económica que el pliego puede pedir (encaje.solvencia_exigible)
  // y, si quien mira ha guardado su facturación en este navegador, si llega.
  // La facturación nunca sale del navegador: la ficha es pública.
  var CLAVE_FACTURACION = "radar-facturacion";
  function facturacionGuardada() {
    try { return Number(localStorage.getItem(CLAVE_FACTURACION)) || 0; } catch (e) { return 0; }
  }
  function veredictoSolvencia(s) {
    var f = facturacionGuardada();
    if (!f) return null;
    if (f < s.seguro) return { clase: "riesgo", texto: "Con tu facturación, no llegáis" + (s.lotes ? " ni en el lote más barato" : "") };
    if (f < s.hasta) return { clase: "aviso", texto: s.lotes ? "Llegáis a algún lote, no a todos" : "Depende de lo que dure: mirar el pliego" };
    return { clase: "ok", texto: "Llegáis aunque pidan el máximo" };
  }
  function textoSolvencia(s, html) {
    var rango = s.seguro < s.hasta
      ? "entre " + euros(s.seguro) + " y " + euros(s.hasta) + (s.lotes ? " (según el lote)" : " (según lo que dure)")
      : "hasta " + euros(s.hasta);
    var v = veredictoSolvencia(s);
    if (!html) return rango + " de facturación anual" + (v ? ". " + v.texto : "");
    return rango + ' de facturación anual <span class="barras__sec">(1,5 × el valor anual, LCSP art. 87)</span>' +
      (v ? '<br><span class="solvencia solvencia--' + v.clase + '">' + v.texto + "</span> " : "<br>") +
      '<button type="button" class="boton boton--texto" data-facturacion>' + (facturacionGuardada() ? "Cambiar tu facturación" : "Comparar con tu facturación") + "</button>";
  }

  // De dónde sale cada cifra de la previsión (normalizar._prevision).
  function basePrevision(x) {
    if (x.base === "parecidos") return "media de " + cuantos(x.n, "contrato parecido", "contratos parecidos") + " de este organismo";
    return "mediana de " + cuantos(x.n, "concurso abierto", "concursos abiertos") + " de «" + x.categoria + "» " +
      "en " + (x.base === "espana" ? "toda España" : x.lugar) + " (últimos 3 años)";
  }

  // Quién suele presentarse a los contratos parecidos vascos (normalizar._habituales).
  function textoHabituales(t, nombre) {
    var h = t.habituales;
    return "Quién se presentó " + (h.concursos === 1 ? "a la edición anterior con lista de licitadoras" : "a " + h.concursos + " de ellos (los que tienen lista de licitadoras)") + ": " +
      h.empresas.map(function (e) {
        return nombre(e) + " (" + (h.concursos === 1 ? (e.ganadas ? "ganó" : "no ganó") : e.veces + (e.ganadas ? ", ganó " + e.ganadas : ", no ganó")) + ")";
      }).join(", ") + ".";
  }

  // "2 años", "13 meses", "1,5 meses", "15 días".
  function duracionTexto(meses) {
    if (meses >= 12 && meses % 12 === 0) return cuantos(meses / 12, "año", "años");
    return meses < 1 ? cuantos(Math.round(meses * 30), "día", "días") : numeroEs(meses) + (meses === 1 ? " mes" : " meses");
  }

  // "1 empresa", "16 empresas".
  function cuantos(n, uno, varios) {
    return miles(n) + " " + (n === 1 ? uno : varios);
  }

  // Ofertas y rebaja medias de todos los contratos parecidos (los calcula
  // normalizar._resumen_antecedentes). `fuerte` resalta las cifras.
  function resumenAntecedentes(t, fuerte) {
    var r = t.antecedentes_resumen;
    var total = t.antecedentes_total;
    var conDato = function (n) { return n < total ? ", en " + miles(n) + " con dato" : ""; };
    var partes = [];
    if (r.ofertas) {
      partes.push(fuerte(numeroEs(r.ofertas.media) + (r.ofertas.media === 1 ? " oferta" : " ofertas")) +
        " (de " + r.ofertas.min + " a " + r.ofertas.max + conDato(r.ofertas.n) + ")");
    }
    if (r.rebaja) {
      partes.push(fuerte(numeroEs(r.rebaja.media) + " % de rebaja") +
        " (de " + numeroEs(r.rebaja.min) + " a " + numeroEs(r.rebaja.max) + " %" + conDato(r.rebaja.n) + ")");
    }
    return "Media de los " + miles(total) + " contratos parecidos: " + partes.join(" y ") + ".";
  }

  // Los importes llegan ya formateados desde normalizar.py, a la inglesa y
  // con el código de moneda ("865,200 EUR", "8,000,000 SEK": TED publica
  // cada licitación en su moneda). Se pasan a formato español sin tocar la
  // moneda; null si no está publicado.
  function importeTexto(display) {
    if (!display || display === NO_PUBLICADO) return null;
    var m = /^([\d,]+)(?:\.\d+)?\s+([A-Z]{3})$/.exec(display);
    if (!m) return display;
    return m[1].replace(/,/g, ".") + " " + (m[2] === "EUR" ? "€" : m[2]);
  }

  // Ámbito de una licitación española para "Publicadas recientemente":
  // "Estado", "Euskadi" o null si no es de un organismo español. Las de TED
  // entran también si el organismo es español -hay licitaciones que solo se
  // publican ahí (Metro Bilbao, Diputación Foral de Gipuzkoa...) y, al
  // deduplicar, la copia de TED es la que se queda-; se asignan a Euskadi
  // por la región NUTS del organismo (ES21x = País Vasco).
  function ambitoReciente(t) {
    if (t.fuente === "Estado" || t.fuente === "Euskadi") return t.fuente;
    if (t.fuente === "UE" && t.pais_territorio === "España") {
      return (t.region_nuts || "").indexOf("ES21") === 0 ? "Euskadi" : "Estado";
    }
    return null;
  }

  function esPublicacionReciente(t) {
    if (t.tipo_registro !== "licitacion" || ambitoReciente(t) === null) return false;
    // Sin fecha de publicación son las convocatorias de plazo largo leídas
    // del buscador de PLACSP (ver placsp_web.py): pueden llevar años
    // publicadas; que el radar las vea hoy por primera vez no las hace
    // recientes.
    if (t.fecha_publicacion === NO_PUBLICADO) return false;
    // Se usa fecha_primera_aparicion (cuándo lo vio el radar por primera
    // vez), no fecha_publicacion (la fecha oficial que da la fuente): los
    // lotes de exportación de PLACSP llegan con días de retraso y, para
    // cuando una licitación "aparecía" para nosotros, ya tenía más días que
    // la ventana de esta vista. fecha_primera_aparicion la calcula
    // normalizar.py y persiste entre ejecuciones.
    var dias = diasRestantes(t.fecha_primera_aparicion);
    // diasRestantes da (fecha - hoy); hoy, ayer o anteayer dan 0, -1 o -2.
    return dias !== null && dias <= 0 && dias >= -DIAS_VENTANA_RECIENTES;
  }

  function esPlazoLargo(t) {
    if (t.tipo_registro !== "licitacion") return false;
    var dias = diasRestantes(t.fecha_limite);
    return dias !== null && dias > DIAS_PLAZO_LARGO;
  }

  // ---------- Guardadas ----------
  // Se guardan en el navegador (localStorage): sin cuentas ni servidor, así
  // que cada navegador tiene su propia lista. De cada una se guarda lo justo
  // para enseñarla aunque deje de estar en los datos del radar antes de su
  // fecha límite (la fuente la retira o le cambia el identificador).
  // Solo se guardan las que tienen plazo de entrega: licitaciones y calls.
  var CLAVE_GUARDADAS = "radar-guardadas";
  var TIPOS_GUARDABLES = ["licitacion", "convocatoria_ue"];
  var guardadas = leerGuardadas();
  var porId = {};
  DATOS.forEach(function (t) { porId[t.id] = t; });

  function leerGuardadas() {
    try { return JSON.parse(localStorage.getItem(CLAVE_GUARDADAS)) || {}; } catch (e) { return {}; }
  }

  function escribirGuardadas() {
    try { localStorage.setItem(CLAVE_GUARDADAS, JSON.stringify(guardadas)); } catch (e) { /* sin almacenamiento: la lista dura lo que la página */ }
  }

  function esGuardable(t) {
    return TIPOS_GUARDABLES.indexOf(t.tipo_registro) !== -1;
  }

  function estaGuardada(id) {
    return Object.prototype.hasOwnProperty.call(guardadas, id);
  }

  function caducada(fecha) {
    var dias = diasRestantes(fecha);
    return dias !== null && dias < 0;
  }

  // Quita las que ya han pasado su fecha límite. Se llama al abrir el radar.
  function purgarGuardadas() {
    var cambio = false;
    Object.keys(guardadas).forEach(function (id) {
      if (caducada(guardadas[id].fecha_limite)) {
        delete guardadas[id];
        cambio = true;
      }
    });
    if (cambio) escribirGuardadas();
  }

  function alternarGuardada(id) {
    var t = porId[id];
    if (estaGuardada(id) || !t) {
      delete guardadas[id];
    } else {
      guardadas[id] = {
        titulo: t.titulo, organismo: t.organismo, fuente: t.fuente,
        fecha_limite: t.fecha_limite, enlace: t.enlace, tipo_registro: t.tipo_registro,
      };
    }
    escribirGuardadas();
  }

  // ---------- Descartadas (con motivo) ----------
  // {id: {motivo, fecha_limite, titulo, fecha}} en el navegador. Se quitan
  // del listado; «Ver descartadas» las enseña solas. Los motivos servirán
  // para afinar la nota de encaje (encaje.py).
  var CLAVE_DESCARTADAS = "radar-descartadas";
  var MOTIVOS_DESCARTE = [["precio", "Precio"], ["solvencia", "Solvencia"], ["plazo", "Plazo"], ["servicio", "No es nuestro servicio"],
    ["organismo", "Organismo"], ["otro", "Otro"]];
  var descartadas = (function () {
    try { return JSON.parse(localStorage.getItem(CLAVE_DESCARTADAS)) || {}; } catch (e) { return {}; }
  })();
  function escribirDescartadas() {
    try { localStorage.setItem(CLAVE_DESCARTADAS, JSON.stringify(descartadas)); } catch (e) { /* sin almacenamiento: dura lo que la página */ }
  }
  function estaDescartada(id) {
    return Object.prototype.hasOwnProperty.call(descartadas, id);
  }
  function nombreMotivo(clave) {
    var m = MOTIVOS_DESCARTE.filter(function (x) { return x[0] === clave; })[0];
    return m ? m[1] : clave;
  }
  function purgarDescartadas() {
    var cambio = false;
    Object.keys(descartadas).forEach(function (id) {
      if (caducada(descartadas[id].fecha_limite)) { delete descartadas[id]; cambio = true; }
    });
    if (cambio) escribirDescartadas();
  }

  function deTipo(tipo) {
    if (tipo === "guardadas") {
      return DATOS.filter(function (t) { return estaGuardada(t.id) && !caducada(t.fecha_limite); });
    }
    if (tipo === "recientes") return DATOS.filter(esPublicacionReciente);
    if (tipo === "plazo_largo") return DATOS.filter(esPlazoLargo);
    return DATOS.filter(function (t) { return t.tipo_registro === tipo; });
  }

  function subconjuntoActivo() {
    var lista = deTipo(estado.tipoRegistro);
    if (estado.tipoRegistro === "guardadas") return lista;
    return lista.filter(function (t) { return estado.verDescartadas ? estaDescartada(t.id) : !estaDescartada(t.id); });
  }

  function pintarBotonDescartadas() {
    var b = document.getElementById("boton-descartadas");
    var n = deTipo(estado.tipoRegistro).filter(function (t) { return estaDescartada(t.id); }).length;
    b.hidden = estado.tipoRegistro === "guardadas" || (!n && !estado.verDescartadas);
    b.textContent = estado.verDescartadas ? "Volver a las no descartadas" : "Ver descartadas (" + n + ")";
  }

  // ---------- Controles del listado ----------

  // Reconstruye los controles que cambian de una vista a otra: filtro de
  // importe (campo, nombre y tramos), "Ordenar por" y el texto del buscador.
  // Deja el estado en los valores por defecto de la vista.
  function construirControlesDeVista() {
    var tipo = estado.tipoRegistro;

    var importe = IMPORTE_POR_TIPO[tipo];
    elCampoImporte.hidden = !importe;
    estado.presupuestoMin = 0;
    estado.presupuestoMax = null;
    if (importe) {
      elEtiquetaImporteMin.textContent = importe.nombre + " mínimo";
      elEtiquetaImporteMax.textContent = importe.nombre + " máximo";
      var opciones = importe.tramos.map(function (v) { return '<option value="' + v + '">' + euros(v) + "</option>"; }).join("");
      elPresupuestoMin.innerHTML = '<option value="0">Sin mínimo</option>' + opciones;
      elPresupuestoMax.innerHTML = '<option value="">Sin máximo</option>' + opciones;
    }

    var ordenes = ORDENES_POR_TIPO[tipo];
    elCampoOrden.hidden = !ordenes;
    estado.orden = ordenPorDefecto(tipo);
    if (ordenes) {
      elOrden.innerHTML = ordenes.map(function (par) { return '<option value="' + par[0] + '">' + par[1] + "</option>"; }).join("");
      elOrden.value = estado.orden;
    }

    elTexto.placeholder = BUSQUEDA_POR_TIPO[tipo] || BUSQUEDA_GENERAL;
  }

  // Opciones fijas de la vista + cualquier valor presente en los datos que
  // no esté en la lista fija (para no esconder nunca un dato real).
  function conOpcionesFijas(fijas, conteos) {
    var lista = (fijas || []).slice();
    Object.keys(conteos).forEach(function (v) {
      if (v && lista.indexOf(v) === -1) lista.push(v);
    });
    return lista;
  }

  // Construye los controles de filtro de la vista: qué opciones hay y en qué
  // orden. Eso se decide con la vista entera y no cambia al filtrar, para
  // que las opciones no bailen ni desaparezcan mientras se combinan
  // filtros. Los números de cada opción los pone actualizarConteos(), que se
  // llama en cada aplicarFiltros().
  function construirControles() {
    var subconjunto = subconjuntoActivo();
    var fuentes = {};
    var categorias = {};
    var totalRevisar = 0;
    var totalPropuesta = 0;
    var paises = {};
    var comunidades = {};  // comunidad -> { provincias: { provincia: true } }
    var sinLugar = 0;

    subconjunto.forEach(function (t) {
      var f = fuenteDe(t);
      fuentes[f] = (fuentes[f] || 0) + 1;
      (t.categorias || []).forEach(function (c) {
        categorias[c] = (categorias[c] || 0) + 1;
      });
      paises[t.pais_territorio] = (paises[t.pais_territorio] || 0) + 1;
      if (t.comunidad) {
        var com = comunidades[t.comunidad] || (comunidades[t.comunidad] = { provincias: {} });
        if (t.provincia) com.provincias[t.provincia] = true;
      } else if (esOrganismoEspanol(t)) {
        sinLugar++;
      }
      if (t.revisar_manual) totalRevisar++;
      if (pesaLaPropuesta(t)) totalPropuesta++;
    });

    // Fuente: "Todas" + las fuentes fijas de la vista (FUENTES_POR_TIPO),
    // aunque alguna esté a 0 ese día: que un filtro desaparezca parecería un
    // fallo, no información.
    var opcionesFuente = [["", "Todas"]];
    var fuentesVista = conOpcionesFijas(FUENTES_POR_TIPO[estado.tipoRegistro], fuentes);
    // Orden fijo: Euskadi, Estado y Europa (TED se llama «UE» en los datos).
    fuentesVista.forEach(function (f) {
      opcionesFuente.push([f, f === "UE" ? "Europa" : f]);
    });
    // Con una sola fuente posible (calls for proposals: solo la UE) no hay
    // nada que filtrar.
    elCampoFuente.hidden = fuentesVista.length < 2;

    elSegmentedFuente.innerHTML = "";
    opcionesFuente.forEach(function (opcion) {
      var valor = opcion[0];
      var boton = document.createElement("button");
      boton.type = "button";
      boton.className = "opciones__opcion";
      boton.innerHTML = "<span>" + escaparHtml(opcion[1]) + '</span><span class="opciones__conteo"></span>';
      boton.setAttribute("data-valor", valor);
      boton.setAttribute("aria-pressed", valor === estado.fuente ? "true" : "false");
      boton.addEventListener("click", function () {
        estado.fuente = valor;
        marcarFuente();
        aplicarFiltros();
      });
      elSegmentedFuente.appendChild(boton);
    });

    // Desplegable de categoría: TODAS las de CATEGORIAS_CONOCIDAS, no solo
    // las presentes en la vista activa (ver comentario junto a esa
    // constante) — ordenadas por volumen en esta vista, y a igualdad
    // (incluido 0) alfabéticamente, para que el orden no salga arbitrario.
    var categoriasOrdenadas = CATEGORIAS_CONOCIDAS.slice().sort(function (a, b) {
      var diferencia = (categorias[b] || 0) - (categorias[a] || 0);
      return diferencia !== 0 ? diferencia : a.localeCompare(b, "es");
    });
    elCategoria.innerHTML = "";
    opcionConEtiqueta("", "Todas las categorías", elCategoria);
    categoriasOrdenadas.forEach(function (c) {
      opcionConEtiqueta(c, c, elCategoria);
    });
    elCategoria.value = estado.categoria;

    // Desplegable de país/territorio: solo en las vistas con entrada en
    // PAISES_POR_TIPO; ahí, los fijos aunque estén a 0, alfabético.
    var paisesFijos = PAISES_POR_TIPO[estado.tipoRegistro];
    elCampoPais.hidden = !paisesFijos;
    var paisesOrdenados = !paisesFijos ? [] : conOpcionesFijas(paisesFijos, paises)
      .sort(function (a, b) { return a.localeCompare(b, "es"); });
    elPais.innerHTML = "";
    opcionConEtiqueta("", "Todos los países", elPais);
    paisesOrdenados.forEach(function (p) {
      opcionConEtiqueta(p, p, elPais);
    });

    // Desplegable de provincia: las comunidades con registros en la vista y,
    // dentro de cada una, sus provincias. Una comunidad de una sola
    // provincia (Madrid, Navarra...) es una opción suelta. No hay lista fija:
    // solo tienen provincia los registros españoles cuya fuente publica el
    // código de lugar, y en las calls de la UE no la tiene ninguno.
    var nombresComunidad = Object.keys(comunidades).sort(function (a, b) { return a.localeCompare(b, "es"); });
    elCampoLugar.hidden = nombresComunidad.length === 0;
    elLugar.innerHTML = "";
    opcionConEtiqueta("", "Todas", elLugar);
    nombresComunidad.forEach(function (nombre) {
      var provincias = Object.keys(comunidades[nombre].provincias).sort(function (a, b) { return a.localeCompare(b, "es"); });
      if (provincias.length === 0 || (provincias.length === 1 && provincias[0] === nombre)) {
        opcionConEtiqueta("c:" + nombre, nombre, elLugar);
        return;
      }
      var grupoComunidad = document.createElement("optgroup");
      grupoComunidad.label = nombre;
      opcionConEtiqueta("c:" + nombre, nombre + ": todas", grupoComunidad);
      provincias.forEach(function (p) {
        opcionConEtiqueta("p:" + p, p, grupoComunidad);
      });
      elLugar.appendChild(grupoComunidad);
    });
    if (sinLugar && nombresComunidad.length) opcionConEtiqueta("sin", "Sin provincia publicada", elLugar);
    elLugar.value = estado.lugar;
    if (elLugar.value !== estado.lugar) {
      // La provincia elegida no existe en esta vista.
      estado.lugar = "";
      elLugar.value = "";
    }

    elBotonRevisar.hidden = totalRevisar === 0;
    elBotonRevisar.setAttribute("aria-pressed", estado.soloRevisarManual ? "true" : "false");

    // Si en esta vista no hay ninguna (adjudicaciones, calls...), el botón
    // no sale y el filtro se suelta.
    if (!totalPropuesta) estado.soloPropuesta = false;
    elBotonPropuesta.hidden = totalPropuesta === 0;
    elBotonPropuesta.setAttribute("aria-pressed", estado.soloPropuesta ? "true" : "false");
  }

  // Opción de desplegable cuyo texto es "etiqueta (n)": la etiqueta se guarda
  // aparte para que actualizarConteos() solo cambie el número.
  function opcionConEtiqueta(valor, etiqueta, padre) {
    var opt = document.createElement("option");
    opt.value = valor;
    opt.setAttribute("data-etiqueta", etiqueta);
    opt.textContent = etiqueta;
    padre.appendChild(opt);
  }

  // Pone en cada opción de filtro cuántos registros quedarían al elegirla,
  // con los demás filtros como están (ver recorrerFiltros). Cambia solo los
  // números: las opciones, su orden y el foco no se tocan.
  function actualizarConteos(conteos) {
    Array.prototype.forEach.call(elSegmentedFuente.children, function (b) {
      var valor = b.getAttribute("data-valor");
      b.querySelector(".opciones__conteo").textContent = valor ? (conteos.fuente.valores[valor] || 0) : conteos.fuente.total;
    });
    [[elCategoria, conteos.categoria], [elPais, conteos.pais], [elLugar, conteos.lugar]].forEach(function (par) {
      Array.prototype.forEach.call(par[0].querySelectorAll("option"), function (opt) {
        var n = opt.value ? (par[1].valores[opt.value] || 0) : par[1].total;
        opt.textContent = opt.getAttribute("data-etiqueta") + " (" + n + ")";
      });
    });
    elBotonRevisar.textContent = "Solo pendientes de revisar (" + conteos.revisar + ")";
    elBotonPropuesta.textContent = "El precio puntúa el 50 % o menos (" + conteos.propuesta + ")";
  }

  // Licitaciones donde la mesa valora la propuesta (hay juicio de valor) y
  // el precio pesa la mitad o menos: donde una agencia puede ganar sin ser
  // la más barata. Sin juicio de valor no entran aunque no haya criterio de
  // precio: suelen puntuar descuentos sobre tarifas o la comisión de agencia,
  // que son precio con otro nombre. Solo las que publican sus criterios con
  // peso (PLACSP, perfiles propios).
  // Euskadi y TED no dicen si un criterio va con fórmula o con juicio de
  // valor (solo separan el precio del resto): allí basta con que el precio
  // pese la mitad o menos y haya algún criterio que no sea el precio.
  function pesaLaPropuesta(t) {
    var cr = t.criterios;
    if (!cr || cr.precio > 50) return false;
    return cr.resto != null ? cr.resto > 0 : cr.juicio > 0;
  }

  function marcarFuente() {
    Array.prototype.forEach.call(elSegmentedFuente.children, function (b) {
      b.setAttribute("aria-pressed", b.getAttribute("data-valor") === estado.fuente ? "true" : "false");
    });
  }

  // Fuente con la que se filtra y se cuenta: en "Publicadas recientemente",
  // el ámbito (Estado, Euskadi o UE en España) en vez de la fuente tal cual.
  function fuenteDe(t) {
    return estado.tipoRegistro === "recientes" ? ambitoReciente(t) : t.fuente;
  }

  function pasaLugar(t) {
    if (estado.lugar === "sin") return !t.comunidad && esOrganismoEspanol(t);
    if (estado.lugar.charAt(0) === "c") return t.comunidad === estado.lugar.slice(2);
    return t.provincia === estado.lugar.slice(2);
  }

  // Valores del desplegable de provincia en los que cuenta un registro.
  function clavesLugar(t) {
    if (t.comunidad) return t.provincia ? ["c:" + t.comunidad, "p:" + t.provincia] : ["c:" + t.comunidad];
    return esOrganismoEspanol(t) ? ["sin"] : [];
  }

  function pasaTexto(t) {
    // Se incluye empresa_adjudicataria (undefined en licitaciones/calls for
    // proposals, de ahí el || "") para poder buscar por el nombre de la
    // empresa ganadora en Adjudicaciones y Contratos menores.
    var pajar = sinTildes(t.titulo + " " + t.organismo + " " + t.resumen + " " + (t.empresa_adjudicataria || "") + " " + (t.codigo_expediente || "") +
      " " + (t.provincia || "") + " " + (t.comunidad || ""));
    return pajar.indexOf(estado.texto) !== -1;
  }

  function pasaImporte(t) {
    var importe = IMPORTE_POR_TIPO[estado.tipoRegistro];
    var minActivo = estado.presupuestoMin > 0;
    var maxActivo = estado.presupuestoMax !== null && estado.presupuestoMax !== "";
    if (!importe || (!minActivo && !maxActivo)) return true;
    // Sin importe publicado no se puede saber si entra en el rango: fuera.
    var valor = t[importe.campo];
    if (valor === null || valor === undefined) return false;
    if (minActivo && valor < estado.presupuestoMin) return false;
    if (maxActivo && valor > Number(estado.presupuestoMax)) return false;
    return true;
  }

  // Filtros activos que no pasa un registro, por su nombre de faceta
  // ("fuente", "categoria", "pais", "lugar", "revisar", "propuesta") o
  // "texto" e "importe", que no tienen recuento propio.
  function fallosDeFiltro(t) {
    var fallos = [];
    if (estado.soloRevisarManual && !t.revisar_manual) fallos.push("revisar");
    if (estado.soloPropuesta && !pesaLaPropuesta(t)) fallos.push("propuesta");
    if (estado.fuente && fuenteDe(t) !== estado.fuente) fallos.push("fuente");
    if (estado.categoria && (t.categorias || []).indexOf(estado.categoria) === -1) fallos.push("categoria");
    if (estado.pais && t.pais_territorio !== estado.pais) fallos.push("pais");
    if (estado.lugar && !pasaLugar(t)) fallos.push("lugar");
    if (estado.texto && !pasaTexto(t)) fallos.push("texto");
    if (!pasaImporte(t)) fallos.push("importe");
    return fallos;
  }

  // Una pasada por la vista: los registros que pasan todos los filtros y,
  // para cada filtro, cuántos quedarían al elegir cada opción con los demás
  // filtros como están. Un registro que solo falla un filtro cuenta en las
  // opciones de ese filtro (es lo que habría al cambiarlo) y en ningún
  // otro; así un filtro no se cuenta a sí mismo: con Euskadi marcado se
  // sigue viendo cuántas habría en Estado y en Europa.
  function recorrerFiltros(subconjunto) {
    var nueva = function () { return { total: 0, valores: {} }; };
    var conteos = { fuente: nueva(), categoria: nueva(), pais: nueva(), lugar: nueva(), revisar: 0, propuesta: 0 };
    var sumar = function (faceta, valores) {
      faceta.total++;
      valores.forEach(function (v) { faceta.valores[v] = (faceta.valores[v] || 0) + 1; });
    };
    var filtrados = [];
    subconjunto.forEach(function (t) {
      var fallos = fallosDeFiltro(t);
      if (fallos.length > 1) return;
      if (fallos.length === 0) filtrados.push(t);
      var cuenta = function (faceta) { return fallos.length === 0 || fallos[0] === faceta; };
      if (cuenta("fuente")) sumar(conteos.fuente, [fuenteDe(t)]);
      if (cuenta("categoria")) sumar(conteos.categoria, t.categorias || []);
      if (cuenta("pais")) sumar(conteos.pais, [t.pais_territorio]);
      if (cuenta("lugar")) sumar(conteos.lugar, clavesLugar(t));
      if (cuenta("revisar") && t.revisar_manual) conteos.revisar++;
      if (cuenta("propuesta") && pesaLaPropuesta(t)) conteos.propuesta++;
    });
    return { filtrados: filtrados, conteos: conteos };
  }

  // Fecha más reciente primero. fecha_publicacion guarda la fecha propia de
  // cada tipo: publicación (licitaciones), adjudicación (adjudicaciones y
  // contratos menores) o apertura (calls for proposals).
  function porFechaDesc(a, b) {
    var fa = a.fecha_publicacion === NO_PUBLICADO ? "" : (a.fecha_publicacion || "");
    var fb = b.fecha_publicacion === NO_PUBLICADO ? "" : (b.fecha_publicacion || "");
    return fb.localeCompare(fa);
  }

  // Fecha más próxima primero; detrás, lo que ya ha pasado (plazo cerrado,
  // contrato vencido: lo más reciente antes) y, al final, lo que no tiene
  // fecha. Antes lo ya pasado salía lo primero de la lista.
  function porFechaProxima(campo, a, b) {
    var da = diasRestantes(a[campo]);
    var db = diasRestantes(b[campo]);
    if (da === null && db === null) return 0;
    if (da === null) return 1;
    if (db === null) return -1;
    if ((da < 0) !== (db < 0)) return da < 0 ? 1 : -1;
    return da < 0 ? db - da : da - db;
  }

  // Ordena según estado.orden, que siempre es una de las claves de
  // ORDENES_POR_TIPO de la vista activa (o ORDEN_SIN_SELECTOR). A igualdad
  // en el criterio elegido, lo más reciente primero.
  function comparar(a, b) {
    var resultado = 0;
    if (estado.orden === "plazo") {
      resultado = porFechaProxima("fecha_limite", a, b);
    } else if (estado.orden === "vencimiento") {
      resultado = porFechaProxima("fecha_fin_estimada", a, b);
    } else if (estado.orden === "importe-desc") {
      // Mayor importe primero; sin importe publicado, al final.
      var campo = IMPORTE_POR_TIPO[estado.tipoRegistro].campo;
      var ia = a[campo] === null || a[campo] === undefined ? -Infinity : a[campo];
      var ib = b[campo] === null || b[campo] === undefined ? -Infinity : b[campo];
      resultado = ib === ia ? 0 : (ib > ia ? 1 : -1);
    } else if (estado.orden === "encaje-desc") {
      // Mejor nota primero; a igual nota, la que cierra antes.
      var na = notaEncaje(a);
      var nb = notaEncaje(b);
      resultado = nb - na || porFechaProxima("fecha_limite", a, b);
    }
    return resultado || porFechaDesc(a, b);
  }

  // ---------- Tarjetas ----------

  // Cuándo entró en el radar, si fue dentro de la ventana de "recientes".
  function chipNovedad(t) {
    var dias = diasRestantes(t.fecha_primera_aparicion);
    if (dias === null || dias > 0 || dias < -DIAS_VENTANA_RECIENTES) return "";
    var texto = dias === 0 ? "Nuevo hoy" : (dias === -1 ? "Nuevo ayer" : "Hace " + (-dias) + " días");
    return '<span class="chip chip--nuevo">' + texto + "</span>";
  }

  // Nota de encaje (normalizar -> encaje.py): alta 7-10, media 4-6, baja 0-3.
  // Las calls no tienen nota de 0 a 10, solo nivel (normalizar._encaje_call):
  // para ordenar, cada nivel cuenta como una nota de su tramo.
  var NOTA_NIVEL_CALL = { alto: 8, medio: 5, bajo: 2 };

  // Cómo entraría la agencia en una call for proposals: la Comisión no la
  // contrata, subvenciona un proyecto (normalizar._encaje_call).
  var VIAS_CALL = {
    socio: {
      corto: "Socio de comunicación",
      largo: "Como socio de comunicación del consorcio",
      explicacion: "La Comisión no contrata a la agencia: subvenciona a un grupo de entidades (universidades, centros, empresas) que presenta el proyecto, y alguien del grupo lleva su comunicación y difusión. Ahí entraríamos, dentro de la propuesta.",
    },
    solicitante: {
      corto: "Solicitante posible",
      largo: "Como solicitante o socio",
      explicacion: "Esta línea de Europa Creativa la pueden pedir organizaciones del sector cultural y creativo: hay que mirar en el documento de la convocatoria si la agencia cumple el perfil.",
    },
    proveedor: {
      corto: "Proveedor del ganador",
      largo: "Como proveedor de quien la gane",
      explicacion: "La subvención va a entidades del sector (productoras, organizaciones profesionales...), que luego contratan servicios. Interesa apuntarse quién la gana para ofrecerse.",
    },
  };
  function notaEncaje(t) {
    if (t.encaje) return t.encaje.nota;
    return t.encaje_call ? NOTA_NIVEL_CALL[t.encaje_call.nivel] : -1;
  }

  function nivelEncaje(nota) {
    return nota >= 7 ? "alto" : nota >= 4 ? "medio" : "bajo";
  }

  function par(etiqueta, valor, numerico) {
    return '<div class="datos__par"><dt>' + etiqueta + "</dt><dd" + (numerico ? ' class="dato-numerico"' : "") + ">" + valor + "</dd></div>";
  }

  function grupo(icono, titulo, pares) {
    return '<div class="datos__grupo"><h4>' + Nav.icono(icono) + titulo + "</h4><dl>" + pares.join("") + "</dl></div>";
  }

  // El histórico de adjudicaciones solo cubre organismos españoles.
  function esOrganismoEspanol(t) {
    return t.fuente === "Estado" || t.fuente === "Euskadi" || t.pais_territorio === "España" || t.pais_territorio === "País Vasco";
  }

  // "Bizkaia · País Vasco", "Madrid" (provincia y comunidad se llaman igual),
  // "Andalucía" (la fuente solo da la comunidad) o, si no hay código de
  // lugar, el país o territorio de siempre.
  function textoLugar(t) {
    if (t.provincia) return t.provincia === t.comunidad ? t.provincia : t.provincia + " · " + t.comunidad;
    return t.comunidad || t.pais_territorio;
  }

  function plantillaTarjeta(t, abierta) {
    var tipo = t.tipo_registro;
    var esAdjudicacion = tipo === "adjudicacion";
    var esMenor = tipo === "contrato_menor_venciendo";
    var esCall = tipo === "convocatoria_ue";
    var conEmpresa = esAdjudicacion || esMenor;

    var urgencia = esMenor ? infoVencimiento(t.fecha_fin_estimada) : (esAdjudicacion ? null : infoUrgencia(t.fecha_limite, t));
    var empresa = t.empresa_adjudicataria === NO_PUBLICADO ? "Empresa no publicada" : t.empresa_adjudicataria;
    var presupuesto = importeTexto(t.presupuesto_display);
    var adjudicado = importeTexto(t.importe_adjudicado_display);
    var importeLateral = conEmpresa ? adjudicado : presupuesto;
    var finEstimado = fechaLarga(t.fecha_fin_estimada, "No publicado");

    // --- Fila resumen ---
    var chips =
      (t.codigo_expediente ? '<span class="chip chip--codigo" title="Expediente">' + escaparHtml(t.codigo_expediente) + "</span>" : "") +
      '<span class="chip">' + escaparHtml(t.fuente) + "</span>" +
      (esGuardable(t) ? '<span class="chip chip--guardada"' + (estaGuardada(t.id) ? "" : " hidden") + ">Guardada</span>" : "") +
      chipNovedad(t) +
      (t.encaje ? '<span class="chip chip--encaje chip--encaje-' + nivelEncaje(t.encaje.nota) + '" title="Encaje con la agencia (0-10)">Encaje ' + t.encaje.nota + "/10</span>" : "") +
      (t.encaje_call ? '<span class="chip chip--encaje chip--encaje-' + t.encaje_call.nivel + '" title="Encaje con la agencia">Encaje ' + t.encaje_call.nivel + "</span>" +
        '<span class="chip">' + VIAS_CALL[t.encaje_call.via].corto + "</span>" : "") +
      (t.revisar_manual ? '<span class="chip chip--aviso">Revisar</span>' : "") +
      (t.criterios
        ? '<span class="chip' + (pesaLaPropuesta(t) ? " chip--propuesta" : "") + '" title="Peso del precio en la puntuación">Precio ' + t.criterios.precio + " %</span>"
        : "") +
      (t.lotes && t.lotes.length ? '<span class="chip">' + t.lotes.length + " lotes</span>" : "") +
      (urgencia ? '<span class="insignia ' + urgencia.clase + '">' + escaparHtml(urgencia.texto) + "</span>" : "");

    var pie;
    if (esAdjudicacion) {
      pie = '<span class="tarjeta__pie-dato">Adjudicataria: <strong>' + escaparHtml(empresa) + "</strong></span>" +
        "<span>Adjudicada: <strong>" + fechaLarga(t.fecha_adjudicacion) + "</strong></span>" +
        (t.ofertas ? "<span>Ofertas: <strong>" + t.ofertas + "</strong></span>" : "") +
        (t.rebaja ? "<span>Rebaja: <strong>" + numeroEs(t.rebaja) + " %</strong></span>" : "");
    } else if (esMenor) {
      pie = '<span class="tarjeta__pie-dato">Lo tiene: <strong>' + escaparHtml(empresa) + "</strong></span>" +
        "<span>Vence (estimado): <strong>" + finEstimado + "</strong></span>";
    } else if (esCall) {
      pie = "<span>Fecha límite de solicitud: <strong>" + fechaLarga(t.fecha_limite) + "</strong></span>" +
        "<span>Apertura: <strong>" + fechaLarga(t.fecha_publicacion) + "</strong></span>";
    } else {
      // Las convocatorias de plazo largo leídas del buscador de PLACSP no
      // traen fecha de publicación: el dato se omite, no se da por "no
      // publicada".
      pie = "<span>Fin de presentación: <strong>" + fechaLimiteTexto(t) + "</strong></span>" +
        (t.fecha_publicacion === NO_PUBLICADO ? "" : "<span>Publicada: <strong>" + fechaLarga(t.fecha_publicacion) + "</strong></span>");
    }

    // --- Detalle ---
    var cpv = (t.cpv || []).filter(function (c, i, lista) { return lista.indexOf(c) === i; });
    var general = [
      par("Organismo", escaparHtml(t.organismo)),
      par("Territorio", escaparHtml(t.pais_territorio)),
    ];
    if (t.comunidad) general.push(par(t.provincia ? "Provincia" : "Comunidad", escaparHtml(textoLugar(t))));
    general = general.concat([
      par("Fuente", escaparHtml(t.fuente)),
    ]);
    if (!esCall) general.push(par("Tipo de contrato", escaparHtml(t.tipo_contrato === NO_PUBLICADO ? "No publicado" : t.tipo_contrato)));
    if (t.codigo_expediente) general.push(par("Expediente", escaparHtml(t.codigo_expediente)));
    var ec = t.encaje_call;
    if (ec && ec.programa) general.push(par("Programa", escaparHtml(ec.programa)));
    else if (t.programa && !/^\d+$/.test(t.programa)) general.push(par("Programa", escaparHtml(t.programa)));
    if (ec && ec.accion) general.push(par("Tipo de acción", escaparHtml(ec.accion)));
    if (cpv.length) general.push(par("CPV", escaparHtml(cpv.join(", ")), true));

    var fechas;
    if (esAdjudicacion) {
      fechas = [par("Fecha de adjudicación", fechaLarga(t.fecha_adjudicacion), true), par("Vigente hasta", finEstimado, true)];
    } else if (esMenor) {
      fechas = [par("Adjudicado el", fechaLarga(t.fecha_adjudicacion), true), par("Vence el (estimado)", finEstimado, true)];
    } else if (esCall) {
      fechas = [par("Apertura", fechaLarga(t.fecha_publicacion), true), par("Fecha límite de solicitud", fechaLarga(t.fecha_limite), true)];
    } else {
      fechas = [par("Publicada", fechaLarga(t.fecha_publicacion, "Sin fecha en la fuente"), true), par("Fecha límite", fechaLimiteTexto(t), true)];
    }
    fechas.push(par("En el radar desde", fechaLarga(t.fecha_primera_aparicion, "—"), true));

    var importes = [];
    if (conEmpresa) {
      importes.push(par(esMenor ? "Empresa que lo tiene hoy" : "Empresa adjudicataria", escaparHtml(empresa)));
      if (nifPublicable(t.empresa_nif)) importes.push(par("NIF", escaparHtml(t.empresa_nif), true));
      importes.push(par("Importe adjudicado", adjudicado || "No publicado", true));
      if (presupuesto) importes.push(par("Presupuesto de licitación", presupuesto, true));
      if (t.ofertas) importes.push(par("Ofertas recibidas", String(t.ofertas), true));
      // Solo cuando la hay: un 0 % suele ser un contrato a precios unitarios
      // o un negociado, no una oferta sin descuento (ver normalizar._competencia).
      if (t.rebaja) importes.push(par("Rebaja sobre el presupuesto", numeroEs(t.rebaja) + " %", true));
    } else {
      importes.push(par(esCall ? "Presupuesto de la convocatoria" : "Presupuesto", presupuesto || "No publicado", true));
      if (t.duracion_meses) importes.push(par("Duración (sin prórrogas)", duracionTexto(t.duracion_meses), true));
      if (t.solvencia) importes.push(par("Solvencia económica que pueden pedir", textoSolvencia(t.solvencia, true)));
      // Calls for proposals: cuántos proyectos se van a financiar y con cuánto.
      if (t.proyectos_previstos) importes.push(par("Proyectos que se prevé financiar", String(t.proyectos_previstos), true));
      if (t.subvencion_maxima) importes.push(par("Subvención máxima por proyecto", euros(Math.round(t.subvencion_maxima)), true));
      if (ec && ec.via === "socio" && t.subvencion_maxima) {
        importes.push(par("Partida de comunicación por proyecto (orientativa)",
          euros(redondeoMil(t.subvencion_maxima * 0.05)) + " – " + euros(redondeoMil(t.subvencion_maxima * 0.10)) +
          ' <span class="barras__sec">(5-10 % del proyecto, estimación del radar)</span>'));
      }
    }

    var categoriasHtml = (t.categorias || [])
      .map(function (c) { return '<span class="etiqueta-categoria">' + escaparHtml(c) + "</span>"; })
      .join("");
    var revisarHtml = t.revisar_manual
      ? '<span class="etiqueta-revisar">Revisar: mezcla con otros servicios no propios de agencia</span>'
      : "";
    // Por qué está en el radar: las palabras clave que encontró el filtro
    // (normalizar._por_que). En TED puede decidir el tipo de servicio que
    // TED antepone al título, sacado del CPV.
    var pq = t.por_que;
    var porQueHtml = "";
    if (pq && pq.terminos && pq.terminos.length) {
      var lista = pq.terminos.map(function (x) { return "«" + escaparHtml(x) + "»"; }).join(", ");
      porQueHtml = '<p class="tarjeta__nota">' + (pq.tipo_ted
        ? "Entra por el tipo de servicio que TED le asigna, «" + escaparHtml(pq.tipo_ted) + "»: el título no dice nada que el filtro reconozca."
        : "Entra porque " + (t.tipo_registro === "convocatoria_ue" ? "el texto de la convocatoria" : "el título") + " dice " + lista + ".") +
        ' <a class="enlace" href="filtro.html">Cómo se filtra</a></p>';
    }

    // Lo que el histórico de adjudicaciones sabe del organismo y de la
    // empresa (lo calcula normalizar.py; no está si no aparecen allí).
    var ho = t.historial_organismo;
    var he = t.historial_empresa;
    var historialHtml = "";
    if (he) {
      historialHtml += '<div class="tarjeta__bloque"><h4>' + (esMenor ? "La empresa que lo tiene, en el histórico" : "La adjudicataria en el histórico") + "</h4>" +
        '<p class="tarjeta__resumen-texto">' + cuantos(he.adjudicaciones, "adjudicación", "adjudicaciones") + " de servicios de agencia" +
        (he.desde ? " desde " + he.desde : "") + ", en " + cuantos(he.organismos, "organismo", "organismos") + ", por " + euros(he.importe) + "." +
        (he.en_este_organismo ? " En este organismo: " + he.en_este_organismo + "." : "") + "</p></div>";
    }
    if (ho) {
      historialHtml += '<div class="tarjeta__bloque"><h4>Este organismo en el histórico</h4>' +
        '<p class="tarjeta__resumen-texto">' + cuantos(ho.adjudicaciones, "adjudicación", "adjudicaciones") + " de servicios de agencia" +
        (ho.desde ? " desde " + ho.desde : "") + ", a " + cuantos(ho.empresas, "empresa", "empresas") + ", por " + euros(ho.importe) + "." +
        (ho.empresas > 1 ? " Las que más importe suman:" : "") + "</p>" +
        (ho.empresas > 1
          ? '<ol class="tarjeta__principales">' + ho.principales.map(function (e) {
              return '<li><a class="enlace" href="historico.html#/empresa/' + e.id + '">' + escaparHtml(e.nombre) + "</a>" +
                "<span>" + euros(e.importe) + " · " + cuantos(e.adjudicaciones, "adjudicación", "adjudicaciones") + "</span></li>";
            }).join("") + "</ol>"
          : "") +
        "</div>";
    }

    // Encaje con la agencia: nota, por qué y riesgos (encaje.py).
    var encajeHtml = "";
    var siguienteHtml = "";
    if (t.encaje) {
      var lista = function (items, clase) {
        return items.length ? '<ul class="tarjeta__encaje-lista tarjeta__encaje-lista--' + clase + '">' +
          items.map(function (x) { return "<li>" + escaparHtml(x) + "</li>"; }).join("") + "</ul>" : "";
      };
      encajeHtml = '<div class="tarjeta__bloque"><h4>Encaje con la agencia: ' + t.encaje.nota + "/10</h4>" +
        lista(t.encaje.motivos, "a-favor") + lista(t.encaje.riesgos, "riesgo") +
        '<p class="tarjeta__nota">Nota orientativa con los datos de la ficha (servicio, provincia, cómo se puntúa, competencia, plazo). No lee el pliego: la solvencia y los requisitos hay que mirarlos en él.</p></div>';
    }

    // Calls for proposals: cómo entraría la agencia, qué pide de
    // comunicación, cómo se puntúa y qué hacer (normalizar._encaje_call).
    if (ec) {
      var via = VIAS_CALL[ec.via];
      encajeHtml = '<div class="tarjeta__bloque"><h4>Encaje con la agencia: ' + ec.nivel + "</h4>" +
        '<p class="tarjeta__resumen-texto"><strong>' + via.largo + ".</strong> " + via.explicacion + "</p>" +
        '<p class="tarjeta__resumen-texto">' + escaparHtml(ec.motivo) + ".</p>" +
        (t.proyectos_previstos ? '<p class="tarjeta__resumen-texto">Competencia: se ' + (t.proyectos_previstos === 1 ? "financia un solo proyecto" : "financian " + t.proyectos_previstos + " proyectos") +
          ". El portal no publica cuántas propuestas se presentan.</p>" : "") +
        "</div>";
      if (ec.frases && ec.frases.length) {
        encajeHtml += '<div class="tarjeta__bloque"><h4>Qué dice de comunicación</h4><ul class="tarjeta__citas">' +
          ec.frases.map(function (f) { return "<li>«" + escaparHtml(f) + "»</li>"; }).join("") + "</ul>" +
          '<p class="tarjeta__nota">Frases de la convocatoria (traducidas) que hablan de difusión, campañas, eventos o participación: de ahí sale el servicio que venderíamos.</p></div>';
      }
      var pasos = [];
      if (ec.dos_fases) pasos.push("Se presenta en dos fases: primero una propuesta corta, con la fecha límite de arriba, y solo si pasa, la completa.");
      if (ec.via === "socio") {
        pasos.push("Los consorcios se forman con meses de antelación: si interesa, hay que buscar uno ya.");
        pasos.push('En la ficha del portal europeo, pestaña «Partner search», están las entidades que buscan socios para este tema.');
      } else if (ec.via === "proveedor") {
        pasos.push("Apuntarla y, cuando se publiquen los proyectos financiados, contactar con los ganadores.");
      } else {
        pasos.push("Leer en el documento de la convocatoria quién puede presentarse y con cuántos socios.");
      }
      siguienteHtml = '<div class="tarjeta__bloque"><h4>Siguiente paso</h4><ul class="tarjeta__encaje-lista tarjeta__encaje-lista--pasos">' +
        pasos.map(function (x) { return "<li>" + x + "</li>"; }).join("") + "</ul>" +
        (t.enlace && t.enlace !== NO_PUBLICADO ? '<a class="enlace" href="' + escaparHtml(t.enlace) + '" target="_blank" rel="noopener noreferrer">Abrir la ficha en el portal europeo' + Nav.icono("externo") + "</a>" : "") +
        "</div>";
    }

    // Previsión de competencia y rebaja (normalizar._prevision).
    var previsionHtml = "";
    var pv = t.prevision;
    if (pv) {
      var cifra = function (valor, unidad) {
        return '<div class="prevision__dato"><span class="prevision__cifra">' + valor + "</span><span>" + unidad + "</span></div>";
      };
      previsionHtml = '<div class="tarjeta__bloque"><h4>Previsión: competencia y rebaja</h4><div class="prevision">' +
        (pv.ofertas ? cifra(numeroEs(pv.ofertas.valor), pv.ofertas.valor === 1 ? "oferta" : "ofertas") : "") +
        (pv.rebaja ? cifra(numeroEs(pv.rebaja.valor) + " %", "de rebaja de la ganadora") : "") + "</div>" +
        '<p class="tarjeta__nota">' + escaparHtml([pv.ofertas ? "Ofertas: " + basePrevision(pv.ofertas) : "",
          pv.rebaja ? "Rebaja: " + basePrevision(pv.rebaja) : ""].filter(Boolean).join(". ") + ".") + "</p>" +
        '<details class="prevision__info"><summary>' + Nav.icono("info") + "Cómo se calcula</summary><p class=\"tarjeta__nota\">" +
        "Primero, los contratos parecidos de este mismo organismo (casi siempre, ediciones anteriores del servicio), si hay al menos 3 con dato: su media. " +
        "Si no, la mediana de los concursos abiertos de la misma categoría de servicio de los últimos 3 años, en la provincia; si allí hay menos de 5, en la comunidad, y si no, en toda España. " +
        "No cuentan los contratos menores ni los negociados, las subidas de precio ni las rebajas de más del 60 % (suelen ser errores o importes en unidades distintas). " +
        "La rebaja solo se calcula en contratos de un lote con presupuesto publicado. Es una orientación, no una garantía.</p></details></div>";
    }

    // Contratos anteriores parecidos del mismo organismo (casi siempre,
    // ediciones anteriores del mismo servicio): quién lo ganó y a qué
    // precio. Los busca normalizar._antecedentes en el histórico.
    var parecidasHtml = "";
    var ant = t.antecedentes;
    if (ant && ant.length) {
      parecidasHtml += '<div class="tarjeta__bloque"><h4>Contratos anteriores parecidos</h4>' +
        '<p class="tarjeta__resumen-texto">' + (t.antecedentes_total > ant.length
          ? "Este organismo ha adjudicado " + cuantos(t.antecedentes_total, "contrato parecido", "contratos parecidos") + ". Los " + ant.length + " más recientes:"
          : "Lo que este organismo adjudicó antes con un título parecido:") + "</p>" +
        '<ul class="tarjeta__antecedentes">' + ant.map(function (a) {
          var empresas = (a.empresas || []).map(function (e) {
            return '<a class="enlace" href="historico.html#/empresa/' + e.id + '">' + escaparHtml(e.nombre) + "</a>";
          }).join(", ");
          var datos = [a.anio,
            empresas ? "Ganó " + empresas : "",
            a.importe ? euros(Math.round(a.importe)) : "",
            a.ofertas ? cuantos(a.ofertas, "oferta", "ofertas") : "",
            a.rebaja != null ? "rebaja del " + numeroEs(a.rebaja) + " %" : ""].filter(Boolean).join(" · ");
          return "<li>" + (a.enlace
            ? '<a class="enlace" href="' + escaparHtml(a.enlace) + '" target="_blank" rel="noopener">' + escaparHtml(a.titulo) + "</a>"
            : escaparHtml(a.titulo)) +
            '<span class="tarjeta__antecedente-datos">' + datos + "</span></li>";
        }).join("") + "</ul>" +
        (t.antecedentes_resumen ? '<p class="tarjeta__resumen-texto">' + resumenAntecedentes(t, function (s) { return "<strong>" + s + "</strong>"; }) + "</p>" : "") +
        (t.habituales ? '<p class="tarjeta__resumen-texto">' + textoHabituales(t, function (e) {
          var nombre = escaparHtml(e.nombre);
          return e.id != null ? '<a class="enlace" href="historico.html#/empresa/' + e.id + '">' + nombre + "</a>" : nombre;
        }) + "</p>" : "") +
        '<p class="tarjeta__nota">Importes adjudicados sin IVA. La rebaja solo se calcula en contratos de un lote con presupuesto publicado. Parecido = comparten buena parte de las palabras del título; conviene abrirlos para confirmarlo.</p></div>';
    }
    // Otras en plazo del mismo organismo o, en las calls, del mismo programa.
    var otras = otrasAbiertas(t);
    if (otras.length) {
      parecidasHtml += '<div class="tarjeta__bloque"><h4>' +
        (t.tipo_registro === "convocatoria_ue" ? "Otras convocatorias abiertas de este programa" : "Otras licitaciones abiertas de este organismo") +
        " (" + otras.length + ")</h4><ul class=\"tarjeta__antecedentes\">" + otras.slice(0, MAX_OTRAS_ABIERTAS).map(function (o) {
          return '<li><a class="enlace" href="#/' + RUTA_POR_TIPO[o.tipo_registro] + "?id=" + encodeURIComponent(o.id) + '">' + escaparHtml(o.titulo) + "</a>" +
            '<span class="tarjeta__antecedente-datos">' + (parsearFecha(o.fecha_limite) ? "Plazo: " + fechaLarga(o.fecha_limite) : "") + "</span></li>";
        }).join("") + "</ul></div>";
    }

    // Cómo se puntúa (PLACSP): reparto entre precio, otros criterios con
    // fórmula y juicio de valor, y cada criterio con su peso.
    var NOMBRES_CRITERIO = { precio: "Precio", formula: "Fórmula", juicio: "Juicio de valor", otro: "Otro criterio" };
    var criteriosHtml = "";
    // Criterios comunes de Horizon Europe (RIA, IA y CSA). Sin tipo de acción
    // en el portal también se muestran, salvo en el EIC, que puntúa distinto.
    var conCriteriosHorizon = ec && ec.programa === "Horizon Europe" &&
      (["RIA", "IA", "CSA"].indexOf(ec.sigla) !== -1 || (!ec.sigla && !/-EIC-/.test(t.codigo_expediente || "")));
    if (conCriteriosHorizon) {
      criteriosHtml = '<div class="tarjeta__bloque"><h4>Cómo se puntúa</h4>' +
        '<ul class="tarjeta__criterios">' +
          "<li><span class=\"tarjeta__criterio-nombre\">Excelencia: objetivos, ambición y método</span><span class=\"dato-numerico\">0-5</span></li>" +
          "<li><span class=\"tarjeta__criterio-nombre\">Impacto: resultados esperados y <strong>plan de comunicación, difusión y explotación</strong></span><span class=\"dato-numerico\">0-5" + (ec.sigla === "IA" ? " (× 1,5)" : "") + "</span></li>" +
          "<li><span class=\"tarjeta__criterio-nombre\">Ejecución: plan de trabajo, recursos y consorcio</span><span class=\"dato-numerico\">0-5</span></li>" +
        "</ul>" +
        '<p class="tarjeta__nota">Criterios comunes de Horizon Europe: hace falta un 3 en cada uno y 10 de 15 en total.' +
        (ec.sigla === "IA" ? " En los proyectos de innovación, Impacto pesa 1,5 al ordenar las propuestas." : "") +
        (ec.dos_fases ? " En la primera fase solo se evalúan Excelencia e Impacto." : "") +
        " La comunicación cuenta dentro de Impacto: ahí es donde la agencia suma puntos al consorcio. El detalle, en el «Annex D» de los documentos.</p></div>";
    }
    var cr = t.criterios;
    if (cr) {
      // Euskadi: solo se sabe cuánto pesa el precio y cuánto el resto.
      var soloPrecioYResto = cr.resto != null;
      var conclusion = cr.precio >= 100
        ? "Solo cuenta el precio: gana la oferta más barata."
        : soloPrecioYResto
        ? "El precio pesa el " + cr.precio + " % y el resto de criterios el " + cr.resto + " %."
        : (cr.precio ? "El precio pesa el " + cr.precio + " %. " : "No hay un criterio de precio como tal. ") + (cr.juicio > 0
          ? "La mesa valora la propuesta técnica (juicio de valor) con el " + cr.juicio + " %" +
            (cr.formulas > 0 ? " y el " + cr.formulas + " % se puntúa con fórmulas (mejoras, plazos, equipo...)." : ".")
          : (cr.precio ? "El resto" : "Todo") + " se puntúa con fórmulas (mejoras, plazos, equipo...): no hay juicio de valor.");
      var tramosReparto = (soloPrecioYResto
        ? [["precio", cr.precio], ["otro", cr.resto]]
        : [["precio", cr.precio], ["formula", cr.formulas], ["juicio", cr.juicio]]).filter(function (x) { return x[1] > 0; });
      criteriosHtml = '<div class="tarjeta__bloque"><h4>Cómo se puntúa</h4>' +
        '<p class="tarjeta__resumen-texto">' + conclusion + "</p>" +
        '<div class="reparto" aria-hidden="true">' + tramosReparto.map(function (x) {
          return '<span class="reparto__tramo reparto__tramo--' + x[0] + '" style="width:' + x[1] + '%"></span>';
        }).join("") + "</div>" +
        '<ul class="tarjeta__criterios">' + cr.detalle.map(function (c) {
          return '<li><span class="tarjeta__criterio-nombre">' + escaparHtml(c.descripcion) + "</span>" +
            '<span class="tarjeta__criterio-tipo tarjeta__criterio-tipo--' + c.tipo + '">' + NOMBRES_CRITERIO[c.tipo] + "</span>" +
            '<span class="dato-numerico">' + numeroEs(c.peso) + " %</span></li>";
        }).join("") + "</ul>" +
        (soloPrecioYResto ? '<p class="tarjeta__nota">' + (t.fuente === "Euskadi" ? "El portal de Euskadi" : "El anuncio europeo") +
          " no indica qué criterios se puntúan con fórmula y cuáles con juicio de valor: está en el pliego.</p>" : "") +
        (cr.por_lotes ? '<p class="tarjeta__nota">Tiene lotes y cada uno puede puntuar distinto: aquí, el primero.' +
          (t.lotes ? " Lo que pesa el precio en cada lote está en la lista de lotes." : " El detalle de cada lote está en el pliego.") + "</p>" : "") +
        "</div>";
    }

    // Lotes: objeto e importe de cada uno y, si la fuente lo dice, lo que
    // pesa el precio (PLACSP y Euskadi).
    var lotesHtml = "";
    if (t.lotes && t.lotes.length) {
      lotesHtml = '<div class="tarjeta__bloque"><h4>Lotes (' + t.lotes.length + ')</h4><ul class="tarjeta__lotes">' +
        t.lotes.map(function (l) {
          return '<li><span class="tarjeta__lote-id">Lote ' + escaparHtml(l.id || "—") + "</span>" +
            '<span class="tarjeta__lote-nombre">' + escaparHtml(l.nombre || "Sin descripción en la fuente") + "</span>" +
            '<span class="tarjeta__lote-precio">' + (l.precio != null ? "Precio " + l.precio + " %" : "") + "</span>" +
            '<span class="dato-numerico">' + (l.importe ? euros(Math.round(l.importe)) : "") + "</span></li>";
        }).join("") + "</ul>" +
        '<p class="tarjeta__nota">Importes sin IVA' + (t.lotes.some(function (l) { return !l.importe; }) ? "; la fuente no publica el de todos los lotes" : "") + ".</p></div>";
    }

    // Pliegos: los que publica la fuente, con su enlace de descarga.
    var NOMBRES_PLIEGO = {
      administrativo: "Pliego de cláusulas administrativas",
      tecnico: "Pliego de prescripciones técnicas",
      caratula: "Carátula (cuadro de características)",
      documentacion: "Documentación de la licitación",
    };
    var pliegosHtml = "";
    if (t.pliegos && t.pliegos.length) {
      pliegosHtml = '<div class="tarjeta__bloque"><h4>' + (esCall ? "Documentos de la convocatoria" : "Pliegos") + '</h4><ul class="tarjeta__pliegos">' +
        t.pliegos.map(function (p) {
          // Calls for proposals: el nombre que le da el portal europeo (en
          // inglés), salvo el documento principal.
          var deConvocatoria = p.tipo === "convocatoria";
          var etiqueta = deConvocatoria
            ? (/^call (document|fiche)/i.test(p.nombre || "") ? "Documento de la convocatoria" : escaparHtml(p.nombre || "Documento"))
            : (NOMBRES_PLIEGO[p.tipo] || "Documento");
          return '<li><a class="enlace" href="' + escaparHtml(p.url) + '" target="_blank" rel="noopener noreferrer">' +
            etiqueta + Nav.icono("externo") + "</a>" +
            (p.nombre && !deConvocatoria ? "<span>" + escaparHtml(p.nombre) + "</span>" : "") + "</li>";
        }).join("") + "</ul>" +
        (esCall && !criteriosHtml ? '<p class="tarjeta__nota">Los criterios de evaluación y su puntuación están en estos documentos (apartado «Award criteria»): el portal europeo no los publica como dato.</p>' : "") +
        "</div>";
    }

    // Actas e informes de valoración de una adjudicación (PLACSP y Euskadi,
    // uno a uno) o, en TED, el enlace a la documentación del expediente. Las
    // actas de PLACSP no tienen título propio: se numeran.
    var NOMBRES_DOCUMENTO = {
      informe_valoracion: "Informe de valoración de las ofertas",
      acta: "Acta de la mesa de contratación",
      informe_anormales: "Informe sobre ofertas anormalmente bajas",
      apertura: "Acto público de apertura de ofertas",
      resolucion: "Resolución de adjudicación",
      expediente: "Documentación del expediente",
    };
    var documentosHtml = "";
    var docs = t.documentos_adjudicacion || [];
    var soloExpediente = docs.length && docs.every(function (d) { return d.tipo === "expediente"; });
    if (docs.length) {
      var porTipo = {};
      docs.forEach(function (d) { porTipo[d.tipo] = (porTipo[d.tipo] || 0) + 1; });
      var vistos = {};
      documentosHtml = '<div class="tarjeta__bloque"><h4>Documentos de la adjudicación</h4><ul class="tarjeta__pliegos">' +
        docs.map(function (d) {
          vistos[d.tipo] = (vistos[d.tipo] || 0) + 1;
          var nombre = NOMBRES_DOCUMENTO[d.tipo] || d.nombre || "Documento";
          // Euskadi dice qué es cada acta ("Apertura sobre B"): se enseña al
          // lado. PLACSP no: se numeran.
          if (NOMBRES_DOCUMENTO[d.tipo] && porTipo[d.tipo] > 1 && !d.detalle) nombre += " (" + vistos[d.tipo] + ")";
          return '<li><a class="enlace" href="' + escaparHtml(d.url) + '" target="_blank" rel="noopener noreferrer">' +
            escaparHtml(nombre) + Nav.icono("externo") + "</a>" +
            (d.detalle ? "<span>" + escaparHtml(d.detalle) + "</span>" : "") + "</li>";
        }).join("") + "</ul>" +
        (soloExpediente ? '<p class="tarjeta__nota">TED no publica las actas ni los informes de valoración: si el organismo los ha subido, están en la documentación del expediente, en su plataforma.</p>' : "") +
        "</div>";
    }

    // Empresas que se presentaron (portal de Euskadi), con enlace a su
    // ficha del histórico cuando está.
    var licitadoresHtml = "";
    if (t.licitadores && t.licitadores.length) {
      licitadoresHtml = '<div class="tarjeta__bloque"><h4>Empresas que se presentaron (' + t.licitadores.length + ")</h4>" +
        '<ul class="tarjeta__principales">' + t.licitadores.map(function (l) {
          var gano = (l.nif && l.nif === t.empresa_nif) || (!l.nif && l.nombre.toLowerCase() === (t.empresa_adjudicataria || "").toLowerCase());
          var nombre = escaparHtml(l.nombre);
          var notas = [];
          if (gano) notas.push("adjudicataria");
          if (l.pyme) notas.push("pyme");
          // Índice de éxito en concursos vascos (licitadoras-data.js).
          var exito = l.nif && (window.LICITADORAS || {})[l.nif];
          if (exito && exito[0] >= 3) notas.push("gana " + exito[1] + " de " + exito[0] + " concursos");
          if (l.provincia) notas.push(escaparHtml(l.provincia));
          return "<li>" + (l.id != null ? '<a class="enlace" href="historico.html#/empresa/' + l.id + '">' + nombre + "</a>" : "<span class=\"tarjeta__licitador\">" + nombre + "</span>") +
            "<span>" + notas.join(" · ") + "</span></li>";
        }).join("") + "</ul></div>";
    }

    var esDirecto = t.enlace_directo !== false;
    var acciones = "";
    if (t.enlace && t.enlace !== NO_PUBLICADO) {
      acciones += '<a class="boton boton--primario" href="' + escaparHtml(t.enlace) + '" target="_blank" rel="noopener noreferrer">' +
        (esDirecto ? "Ver anuncio original" : "Buscar en el portal de Euskadi") + Nav.icono("externo") + "</a>";
    } else {
      acciones += '<span class="chip">Enlace no publicado</span>';
    }
    if (tipo === "licitacion") {
      acciones += estaDescartada(t.id)
        ? '<span class="chip chip--descartada">Descartada: ' + escaparHtml(nombreMotivo(descartadas[t.id].motivo)) + "</span>" +
          '<button type="button" class="boton boton--texto" data-recuperar="' + escaparHtml(t.id) + '">Recuperar</button>'
        : '<details class="descartar"><summary class="boton boton--texto">Descartar</summary><p class="descartar__motivos">Motivo: ' +
          MOTIVOS_DESCARTE.map(function (m) {
            return '<button type="button" class="tarjeta__pregunta" data-descartar="' + escaparHtml(t.id) + '" data-motivo="' + m[0] + '">' + m[1] + "</button>";
          }).join("") + "</p></details>";
    }
    if (esGuardable(t)) {
      acciones += botonGuardar(t.id);
      acciones += '<button type="button" class="boton boton--contorno" data-copiar-ficha="' + escaparHtml(t.id) + '">' +
        Nav.icono("documento") + "<span>Copiar ficha para el asistente</span></button>";
      if (tipo === "licitacion") {
        acciones += '<p class="tarjeta__preguntas">O cópiala con una pregunta: ' + PREGUNTAS_ASISTENTE.map(function (p) {
          return '<button type="button" class="tarjeta__pregunta" data-copiar-ficha="' + escaparHtml(t.id) + '" data-pregunta="' + p.clave + '"><span>' +
            p.boton + "</span></button>";
        }).join("") + "</p>";
      }
    }
    if (conEmpresa && t.empresa_adjudicataria !== NO_PUBLICADO) {
      // Por NIF si el registro lo trae (es como identifica a cada empresa el
      // histórico); el nombre va siempre, por si el NIF no está allí.
      // Si normalizar.py ya la encontró en el histórico, directo a su ficha.
      acciones += '<a class="enlace" href="historico.html#/' + (he ? "empresa/" + he.id : "empresas?" +
        (nifPublicable(t.empresa_nif) ? "nif=" + encodeURIComponent(t.empresa_nif) + "&" : "") + "q=" + encodeURIComponent(t.empresa_adjudicataria)) +
        '">Historial de la empresa' + Nav.icono("flecha") + "</a>";
    }
    if (!esCall && esOrganismoEspanol(t)) {
      acciones += '<a class="enlace" href="historico.html#/' + (ho ? "organismo/" + ho.id : "organismos?q=" + encodeURIComponent(t.organismo)) +
        '">Quién gana en este organismo' + Nav.icono("flecha") + "</a>";
    }

    var codigoHtml = "";
    if (!esDirecto && t.codigo_expediente) {
      codigoHtml =
        '<p class="tarjeta__aviso-codigo">Este portal no permite enlazar directamente al anuncio — ' +
        "pega este código en \"Código del expediente\" del buscador: " +
        '<code class="tarjeta__codigo">' + escaparHtml(t.codigo_expediente) + "</code></p>";
    }

    return (
      '<details class="tarjeta" data-id="' + escaparHtml(t.id) + '"' + (abierta ? " open" : "") + ">" +
        '<summary class="tarjeta__fila">' +
          // Dentro de <summary> solo cabe contenido de frase (y un título):
          // por eso son <span> con display de bloque y no <div>/<p>.
          '<span class="tarjeta__principal">' +
            '<span class="tarjeta__chips">' + chips + "</span>" +
            '<h3 class="tarjeta__titulo">' + escaparHtml(t.titulo) + "</h3>" +
            '<span class="tarjeta__organismo">' + escaparHtml(t.organismo) + "</span>" +
            '<span class="tarjeta__lugar">' + Nav.icono("lugar") + escaparHtml(textoLugar(t)) + "</span>" +
            '<span class="tarjeta__pie">' + pie + "</span>" +
          "</span>" +
          '<span class="tarjeta__lateral">' +
            '<span class="tarjeta__etiqueta-dato">' + (conEmpresa ? "Importe adjudicado" : "Presupuesto") + "</span>" +
            '<span class="tarjeta__dato' + (importeLateral ? "" : " tarjeta__dato--vacio") + '">' + (importeLateral || "No publicado") + "</span>" +
            '<span class="tarjeta__ver">Detalle' + Nav.icono("chevron", "tarjeta__chevron") + "</span>" +
          "</span>" +
        "</summary>" +
        '<div class="tarjeta__detalle">' +
          '<div class="datos">' +
            grupo("info", "Información general", general) +
            '<div class="datos__columna">' +
              grupo("calendario", "Fechas", fechas) +
              grupo("euro", conEmpresa ? "Adjudicación" : "Importes", importes) +
            "</div>" +
          "</div>" +
          '<div class="tarjeta__bloque"><h4>Descripción</h4><p class="tarjeta__resumen-texto">' + escaparHtml(t.resumen) + "</p></div>" +
          encajeHtml +
          previsionHtml +
          lotesHtml +
          criteriosHtml +
          siguienteHtml +
          pliegosHtml +
          documentosHtml +
          licitadoresHtml +
          historialHtml +
          parecidasHtml +
          '<div class="tarjeta__bloque"><h4>Categorías de servicio</h4><div class="tarjeta__categorias">' + categoriasHtml + revisarHtml + "</div>" + porQueHtml + "</div>" +
          codigoHtml +
          '<div class="tarjeta__acciones">' + acciones + "</div>" +
        "</div>" +
      "</details>"
    );
  }

  function botonGuardar(id) {
    var si = estaGuardada(id);
    return '<button type="button" class="boton boton--contorno boton--guardar" data-guardar="' + escaparHtml(id) + '" aria-pressed="' + si + '">' +
      Nav.icono("marcador") + "<span>" + (si ? "Guardada" : "Guardar") + "</span></button>";
  }

  // Guardadas que ya no están en los datos del radar: se enseñan aparte, con
  // su enlace, hasta que pasa su fecha límite.
  function bloqueGuardadasFuera() {
    var fuera = Object.keys(guardadas).filter(function (id) { return !porId[id]; });
    if (!fuera.length) return "";
    fuera.sort(function (a, b) { return (guardadas[a].fecha_limite || "").localeCompare(guardadas[b].fecha_limite || ""); });
    return '<section class="guardadas-fuera"><h3>Guardadas que ya no están en el radar</h3>' +
      "<p>La fuente las ha retirado o les ha cambiado el identificador. Se quitan solas al pasar su fecha límite.</p><ul>" +
      fuera.map(function (id) {
        var g = guardadas[id];
        var titulo = g.enlace && g.enlace !== NO_PUBLICADO
          ? '<a href="' + escaparHtml(g.enlace) + '" target="_blank" rel="noopener noreferrer">' + escaparHtml(g.titulo) + "</a>"
          : escaparHtml(g.titulo);
        return "<li>" + titulo + " · " + escaparHtml(g.organismo) + " · Fecha límite: " + fechaLarga(g.fecha_limite, "no publicada") +
          ' <button type="button" class="boton boton--texto" data-guardar="' + escaparHtml(id) + '">Quitar</button></li>';
      }).join("") + "</ul></section>";
  }

  // Texto con lo que necesita el asistente de licitaciones (skill
  // comunicacion-publica-licitaciones) para arrancar la carpeta y el plan:
  // se pega en un chat nuevo. Solo datos que ya enseña la tarjeta.
  var TIPOS_CRITERIO = { precio: "precio", formula: "fórmula", juicio: "juicio de valor" };

  // Preguntas sugeridas para el chat de la licitación: se copian detrás de
  // la ficha. Piden lo que la ficha no puede saber sin leer los pliegos.
  var PREGUNTAS_ASISTENTE = [
    { clave: "solvencia", boton: "¿Cumplimos la solvencia?",
      texto: "Lee los pliegos (PCAP y PPT) y dime si la agencia cumple la solvencia económica y técnica, las certificaciones y el equipo mínimo que piden, " +
        "con los datos de la biblioteca de la agencia. Para cada requisito: cumple, no cumple o pendiente, con el documento que lo acredita; si falta un dato " +
        "de la agencia, «pendiente», nunca estimado. Termina con una línea: GO, GO CONDICIONADO, NO-GO o PENDIENTE, y la fecha límite para decidir en días laborables." },
    { clave: "antecedentes", boton: "Antecedentes y rebaja ganadora",
      texto: "Busca las ediciones anteriores de este contrato (actas, informes de valoración y resoluciones): quién se presentó, quién ganó, con qué puntuación técnica " +
        "y con qué rebaja. Con eso y con lo que diga el pliego sobre ofertas anormalmente bajas, propón un rango de rebaja para ganar sin caer en baja anormal." },
    { clave: "memoria", boton: "Estructura de la memoria",
      texto: "Lee los criterios de adjudicación y propón la estructura de la memoria técnica: un apartado por criterio y subcriterio, con su peso, " +
        "la extensión y el formato que permite el pliego y qué hay que demostrar en cada uno para sacar la máxima puntuación." },
  ];

  function fichaAsistente(t, pregunta) {
    var lineas = ["Licitación para preparar con el asistente de licitaciones (skill comunicacion-publica-licitaciones).", ""];
    var anadir = function (etiqueta, valor) { if (valor) lineas.push("- " + etiqueta + ": " + valor); };
    anadir("Título", t.titulo);
    anadir("Organismo", t.organismo);
    anadir("Expediente", t.codigo_expediente);
    anadir("Fuente", t.fuente);
    anadir("Anuncio", t.enlace && t.enlace !== NO_PUBLICADO ? t.enlace : "");
    anadir("Fecha límite", fechaLarga(t.fecha_limite, "no publicada") + (t.hora_limite ? ", " + t.hora_limite : "") +
      " (" + infoUrgencia(t.fecha_limite, t).texto + ")");
    anadir("Presupuesto", importeTexto(t.presupuesto_display));
    anadir("Duración sin prórrogas", t.duracion_meses ? duracionTexto(t.duracion_meses) : "");
    anadir("Solvencia económica que pueden pedir", t.solvencia ? textoSolvencia(t.solvencia, false) : "");
    if (t.prevision) {
      anadir("Previsión de ofertas", t.prevision.ofertas ? numeroEs(t.prevision.ofertas.valor) + " (" + basePrevision(t.prevision.ofertas) + ")" : "");
      anadir("Previsión de rebaja", t.prevision.rebaja ? numeroEs(t.prevision.rebaja.valor) + " % (" + basePrevision(t.prevision.rebaja) + ")" : "");
    }
    anadir("Lugar", textoLugar(t));
    anadir("Tipo de contrato", t.tipo_contrato);
    anadir("Categorías", (t.categorias || []).join(", "));
    var c = t.criterios;
    if (c) {
      anadir("Criterios", "precio " + c.precio + " %" + (c.juicio ? ", juicio de valor " + c.juicio + " %" : "") +
        (c.formulas ? ", otras fórmulas " + c.formulas + " %" : "") + (c.resto != null ? ", resto " + c.resto + " %" : ""));
      (c.detalle || []).forEach(function (d) {
        lineas.push("  - " + d.descripcion + ": " + d.peso + " %" + (TIPOS_CRITERIO[d.tipo] ? " (" + TIPOS_CRITERIO[d.tipo] + ")" : ""));
      });
    }
    if (t.lotes && t.lotes.length) {
      lineas.push("- Lotes:");
      t.lotes.forEach(function (l) {
        lineas.push("  - " + (l.nombre || "Lote " + l.id) + (l.importe ? ": " + euros(l.importe) : "") +
          (l.precio != null ? " (precio " + l.precio + " %)" : ""));
      });
    }
    if (t.pliegos && t.pliegos.length) {
      lineas.push("- Pliegos y documentos:");
      t.pliegos.forEach(function (p) { lineas.push("  - " + (p.nombre || p.tipo) + ": " + p.url); });
    }
    if (t.antecedentes && t.antecedentes.length) {
      lineas.push("- Contratos anteriores parecidos del organismo:");
      t.antecedentes.forEach(function (a) {
        var empresas = (a.empresas || []).map(function (e) { return e.nombre; }).join(", ");
        lineas.push("  - " + [a.anio, a.titulo, empresas ? "ganó " + empresas : "", a.importe ? euros(Math.round(a.importe)) : "",
          a.ofertas ? cuantos(a.ofertas, "oferta", "ofertas") : "", a.rebaja != null ? "rebaja " + String(a.rebaja).replace(".", ",") + " %" : "", a.enlace].filter(Boolean).join(" · "));
      });
      if (t.antecedentes_resumen) lineas.push("  - " + resumenAntecedentes(t, function (s) { return s; }));
      if (t.habituales) lineas.push("  - " + textoHabituales(t, function (e) { return e.nombre; }));
    }
    if (t.encaje) {
      anadir("Encaje con la agencia", t.encaje.nota + "/10" +
        (t.encaje.motivos.length ? ". A favor: " + t.encaje.motivos.join("; ") : "") +
        (t.encaje.riesgos.length ? ". Riesgos: " + t.encaje.riesgos.join("; ") : ""));
    }
    anadir("En el radar", location.origin + location.pathname + "#/" + RUTA_POR_TIPO[t.tipo_registro] + "?id=" + encodeURIComponent(t.id));
    var p = PREGUNTAS_ASISTENTE.filter(function (x) { return x.clave === pregunta; })[0];
    if (p) lineas.push("", p.texto);
    return lineas.join("\n");
  }

  function copiarTexto(texto) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(texto);
    // Sin API de portapapeles (http sin cifrar): el método antiguo.
    var area = document.createElement("textarea");
    area.value = texto;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    var ok = document.execCommand("copy");
    document.body.removeChild(area);
    return ok ? Promise.resolve() : Promise.reject(new Error("copia no disponible"));
  }

  var conteosNav = {};

  function actualizarConteoGuardadas() {
    conteosNav.guardadas = Object.keys(guardadas).length;
    Nav.guardarConteos(conteosNav);
  }

  function contarFiltrosActivos() {
    var n = 0;
    if (estado.fuente) n++;
    if (estado.categoria) n++;
    if (estado.pais) n++;
    if (estado.lugar) n++;
    if (estado.presupuestoMin > 0) n++;
    if (estado.presupuestoMax !== null && estado.presupuestoMax !== "") n++;
    if (estado.soloRevisarManual) n++;
    if (estado.soloPropuesta) n++;
    return n;
  }

  function aplicarFiltros() {
    var subconjunto = subconjuntoActivo();
    var recorrido = recorrerFiltros(subconjunto);
    var filtrados = recorrido.filtrados;
    filtrados.sort(comparar);
    actualizarConteos(recorrido.conteos);

    // "Publicadas recientemente" tendrá pocas tarjetas casi siempre (es una
    // ventana de tres días), así que se muestran ya desplegadas: no compensa
    // el gesto de abrir cada una cuando hay un puñado en vez de cientos.
    var abiertas = estado.tipoRegistro === "recientes";

    elConteo.textContent = filtrados.length + " de " + subconjunto.length + " " + ETIQUETAS_CONTEO[estado.tipoRegistro];
    pintarFranja(filtrados);
    pintarBotonDescartadas();
    var esGuardadas = estado.tipoRegistro === "guardadas";
    var enTabla = modoTabla && estado.tipoRegistro !== "convocatoria_ue" && filtrados.length > 0;
    elContenedor.innerHTML = enTabla
      ? plantillaTabla(filtrados) + (esGuardadas ? bloqueGuardadasFuera() : "")
      : filtrados.map(function (t) { return plantillaTarjeta(t, abiertas); }).join("") + (esGuardadas ? bloqueGuardadasFuera() : "");
    pintarSelectorColumnas();
    elSinResultados.textContent = esGuardadas && subconjunto.length === 0
      ? "Todavía no has guardado ninguna licitación. Abre una y pulsa «Guardar»: aparecerá aquí hasta su fecha límite."
      : TEXTO_SIN_RESULTADOS;
    elSinResultados.hidden = filtrados.length > 0;

    var activos = contarFiltrosActivos();
    elFiltrosActivos.hidden = activos === 0;
    elFiltrosActivos.textContent = activos;
  }

  // ---------- Cifras de la búsqueda y tabla ----------

  function enEuros(t, campo) {
    var display = campo === "presupuesto_valor" ? t.presupuesto_display : t.importe_adjudicado_display;
    return t[campo] && /EUR$/.test(display || "") ? t[campo] : null;
  }

  function media(lista) {
    return lista.length ? lista.reduce(function (s, x) { return s + x; }, 0) / lista.length : null;
  }

  function cifraCorta(valor) {
    if (valor >= 1e6) return numeroEs(Math.round(valor / 1e5) / 10) + " M€";
    if (valor >= 1e4) return miles(Math.round(valor / 1e3)) + " k€";
    return euros(Math.round(valor));
  }

  // Franja sobre el listado: lo que suman las licitaciones que se ven y la
  // competencia y rebaja que cabe esperar (media de sus previsiones).
  function pintarFranja(filtrados) {
    var tipo = estado.tipoRegistro;
    var importe = IMPORTE_POR_TIPO[tipo];
    if (!importe || !filtrados.length) { elFranja.hidden = true; return; }
    var importes = filtrados.map(function (t) { return enEuros(t, importe.campo); }).filter(function (x) { return x; });
    var total = importes.reduce(function (s, x) { return s + x; }, 0);
    var cifras = [[importe.nombre + " total", importes.length ? cifraCorta(total) : "—",
      "Suma de " + cuantos(importes.length, "importe publicado", "importes publicados") + " en euros, sin IVA"],
      [importe.nombre + " medio", importes.length ? cifraCorta(total / importes.length) : "—", "Media de los importes publicados"]];
    var ofertas, rebajas;
    if (tipo === "adjudicacion") {
      ofertas = filtrados.map(function (t) { return t.ofertas; }).filter(function (x) { return x; });
      rebajas = filtrados.map(function (t) { return t.rebaja; }).filter(function (x) { return x; });
      cifras.push(["Ofertas por concurso", ofertas.length ? numeroEs(Math.round(10 * media(ofertas)) / 10) : "—", "Media de las " + cuantos(ofertas.length, "adjudicación", "adjudicaciones") + " que publican cuántas ofertas recibieron"]);
      cifras.push(["Rebaja de la ganadora", rebajas.length ? numeroEs(Math.round(10 * media(rebajas)) / 10) + " %" : "—", "Media de las " + cuantos(rebajas.length, "adjudicación", "adjudicaciones") + " con rebaja calculable"]);
    } else if (tipo !== "contrato_menor_venciendo") {
      ofertas = filtrados.map(function (t) { return t.prevision && t.prevision.ofertas && t.prevision.ofertas.valor; }).filter(function (x) { return x; });
      rebajas = filtrados.map(function (t) { return t.prevision && t.prevision.rebaja && t.prevision.rebaja.valor; }).filter(function (x) { return x; });
      if (ofertas.length) {
        cifras.push(["Competencia prevista", numeroEs(Math.round(10 * media(ofertas)) / 10) + " ofertas",
          "Media de la previsión de ofertas de " + cuantos(ofertas.length, "licitación", "licitaciones") + " (ver «Previsión» en cada una)"]);
      }
      if (rebajas.length) {
        cifras.push(["Rebaja prevista", numeroEs(Math.round(10 * media(rebajas)) / 10) + " %",
          "Media de la previsión de rebaja de " + cuantos(rebajas.length, "licitación", "licitaciones")]);
      }
    }
    elFranja.innerHTML = cifras.map(function (c) {
      return '<div title="' + escaparHtml(c[2]) + '"><dt>' + c[0] + "</dt><dd>" + c[1] + "</dd></div>";
    }).join("");
    elFranja.hidden = false;
  }

  // Columnas de la vista de tabla.
  var COLUMNAS_TABLA = {
    general: [
      ["Título", function (t) { return t.titulo; }], ["Organismo", function (t) { return t.organismo; }],
      ["Fuente", function (t) { return t.fuente; }], ["Expediente", function (t) { return t.codigo_expediente; }],
      ["Provincia", function (t) { return t.provincia; }], ["Comunidad", function (t) { return t.comunidad; }],
      ["País", function (t) { return t.pais_territorio; }], ["Fecha límite", function (t) { return t.fecha_limite; }],
      ["Presupuesto", function (t) { return enEuros(t, "presupuesto_valor"); }],
      ["Duración (meses)", function (t) { return t.duracion_meses; }],
      ["Encaje", function (t) { return t.encaje && t.encaje.nota; }],
      ["Precio (%)", function (t) { return t.criterios && t.criterios.precio; }],
      ["Ofertas previstas", function (t) { return t.prevision && t.prevision.ofertas && t.prevision.ofertas.valor; }],
      ["Rebaja prevista (%)", function (t) { return t.prevision && t.prevision.rebaja && t.prevision.rebaja.valor; }],
      ["Categorías", function (t) { return (t.categorias || []).join(", "); }],
      ["Descartada", function (t) { return estaDescartada(t.id) ? nombreMotivo(descartadas[t.id].motivo) : ""; }],
      ["Anuncio", function (t) { return t.enlace !== NO_PUBLICADO ? t.enlace : ""; }],
    ],
    adjudicacion: [
      ["Título", function (t) { return t.titulo; }], ["Organismo", function (t) { return t.organismo; }],
      ["Empresa", function (t) { return t.empresa_adjudicataria; }],
      ["NIF", function (t) { return nifPublicable(t.empresa_nif) ? t.empresa_nif : ""; }],
      ["Fecha de adjudicación", function (t) { return t.fecha_adjudicacion; }],
      ["Importe adjudicado", function (t) { return enEuros(t, "importe_adjudicado_valor"); }],
      ["Ofertas", function (t) { return t.ofertas; }], ["Rebaja (%)", function (t) { return t.rebaja; }],
      ["Provincia", function (t) { return t.provincia; }], ["Anuncio", function (t) { return t.enlace !== NO_PUBLICADO ? t.enlace : ""; }],
    ],
  };

  // ---------- Vista de tabla (opcional) ----------
  // Cuáles se ven se recuerda en el navegador.
  var CLAVE_MODO = "radar-modo-listado";
  var modoTabla = (function () { try { return localStorage.getItem(CLAVE_MODO) === "tabla"; } catch (e) { return false; } })();
  var COLUMNAS_POR_DEFECTO = {
    general: ["Organismo", "Provincia", "Fecha límite", "Presupuesto", "Encaje", "Precio (%)"],
    adjudicacion: ["Organismo", "Empresa", "Fecha de adjudicación", "Importe adjudicado", "Ofertas", "Rebaja (%)"],
  };
  function grupoColumnas() { return COLUMNAS_TABLA[estado.tipoRegistro] ? estado.tipoRegistro : "general"; }
  function columnasVisibles() {
    try {
      var v = JSON.parse(localStorage.getItem("radar-columnas-" + grupoColumnas()));
      if (Array.isArray(v)) return v;
    } catch (e) { /* sin almacenamiento: las de por defecto */ }
    return COLUMNAS_POR_DEFECTO[grupoColumnas()];
  }
  function celdaTabla(nombre, v) {
    if (v == null || v === "" || v === NO_PUBLICADO) return "<td>—</td>";
    if (/^(Presupuesto|Importe)/.test(nombre)) return '<td class="num">' + euros(Math.round(v)) + "</td>";
    if (/^Fecha/.test(nombre)) return '<td class="num">' + fechaLarga(v) + "</td>";
    if (typeof v === "number") return '<td class="num">' + numeroEs(v) + (/%/.test(nombre) ? " %" : "") + "</td>";
    if (/^https?:/.test(v)) return '<td><a href="' + escaparHtml(v) + '" target="_blank" rel="noopener noreferrer">Abrir</a></td>';
    return "<td>" + escaparHtml(v) + "</td>";
  }
  function plantillaTabla(filas) {
    var visibles = columnasVisibles();
    var cols = (COLUMNAS_TABLA[estado.tipoRegistro] || COLUMNAS_TABLA.general).filter(function (c) {
      return c[0] !== "Título" && visibles.indexOf(c[0]) !== -1;
    });
    var numerica = function (c) { return /^(Presupuesto|Importe|Fecha|Encaje|Ofertas|Duración)|%/.test(c[0]); };
    return '<div class="tabla-listado"><table class="tabla-radar"><thead><tr><th scope="col">Título</th>' +
      cols.map(function (c) { return '<th scope="col"' + (numerica(c) ? ' class="num"' : "") + ">" + c[0] + "</th>"; }).join("") +
      "</tr></thead><tbody>" + filas.map(function (t) {
        return '<tr><td><a href="#" data-abrir="' + escaparHtml(t.id) + '">' + escaparHtml(t.titulo) + "</a></td>" +
          cols.map(function (c) { return celdaTabla(c[0], c[1](t)); }).join("") + "</tr>";
      }).join("") + "</tbody></table></div>";
  }
  function pintarSelectorColumnas() {
    var selector = document.getElementById("selector-columnas");
    var boton = document.getElementById("boton-modo");
    boton.textContent = modoTabla ? "Ver como tarjetas" : "Ver como tabla";
    boton.setAttribute("aria-pressed", modoTabla ? "true" : "false");
    boton.hidden = estado.tipoRegistro === "convocatoria_ue";
    selector.hidden = !modoTabla || boton.hidden;
    var visibles = columnasVisibles();
    document.getElementById("columnas-lista").innerHTML = (COLUMNAS_TABLA[estado.tipoRegistro] || COLUMNAS_TABLA.general)
      .filter(function (c) { return c[0] !== "Título"; }).map(function (c) {
        return '<label><input type="checkbox" value="' + escaparHtml(c[0]) + '"' + (visibles.indexOf(c[0]) !== -1 ? " checked" : "") + ">" + c[0] + "</label>";
      }).join("");
  }

  function pintarPestanas(rutaActiva) {
    var esLicitaciones = VISTAS[rutaActiva].nav === "licitaciones";
    elPestanas.hidden = !esLicitaciones;
    if (!esLicitaciones) return;
    elPestanas.innerHTML = PESTANAS_LICITACIONES.map(function (p) {
      return '<a class="pestana" href="#/' + p[0] + '"' + (p[0] === rutaActiva ? ' aria-current="page"' : "") + ">" +
        p[1] + ' <span class="pestana__conteo">' + deTipo(p[2]).length + "</span></a>";
    }).join("");
  }

  // ---------- Rutas ----------

  function mostrarTarjeta(id) {
    var tarjeta = null;
    Array.prototype.forEach.call(elContenedor.children, function (el) {
      if (el.getAttribute("data-id") === id) tarjeta = el;
    });
    if (!tarjeta) return false;
    tarjeta.open = true;
    tarjeta.classList.add("tarjeta--destacada");
    tarjeta.scrollIntoView({ block: "start" });
    window.scrollBy(0, -72);
    return true;
  }

  function navegar(esCargaInicial) {
    var leida = Nav.leerRuta();
    // Sin ruta, o una que ya no existe (p. ej. la antigua #/inicio): se
    // entra en las licitaciones publicadas recientemente.
    var ruta = leida.ruta;
    if (!VISTAS[ruta]) ruta = "licitaciones/recientes";
    var vista = VISTAS[ruta];

    elVistaListado.hidden = false;

    var p = leida.params;
    estado.tipoRegistro = vista.tipo;
    estado.texto = sinTildes((p.q || "").trim());
    estado.fuente = p.fuente || "";
    estado.categoria = CATEGORIAS_CONOCIDAS.indexOf(p.cat) !== -1 ? p.cat : "";
    estado.pais = "";
    // La provincia elegida se conserva al cambiar de vista: quien mira
    // Bizkaia en licitaciones quiere seguir en Bizkaia en adjudicaciones.
    // construirControles la descarta si en la vista nueva no existe.
    estado.soloRevisarManual = false;
    estado.soloPropuesta = false;
    estado.verDescartadas = false;
    elTexto.value = p.q || "";

    Nav.activar(vista.nav);
    document.title = vista.titulo + " — Radar de licitaciones";
    elTitulo.textContent = vista.titulo;
    pintarPestanas(ruta);
    construirControlesDeVista();
    construirControles();
    // Filtros de un enlace compartido: solo si la
    // opción existe en esta vista.
    var desdeEnlace = function (el, valor, poner) {
      if (!valor) return;
      var antes = el.value;
      el.value = valor;
      if (el.value === valor) poner(valor);
      else el.value = antes;  // opción que no existe en esta vista: se queda lo que había
    };
    desdeEnlace(elPais, p.pais, function (v) { estado.pais = v; });
    desdeEnlace(elLugar, p.lugar, function (v) { estado.lugar = v; });
    desdeEnlace(elPresupuestoMin, p.min, function (v) { estado.presupuestoMin = Number(v) || 0; });
    desdeEnlace(elPresupuestoMax, p.max, function (v) { estado.presupuestoMax = v; });
    desdeEnlace(elOrden, p.orden, function (v) { estado.orden = v; });
    if (p.propuesta === "1" && !elBotonPropuesta.hidden) {
      estado.soloPropuesta = true;
      elBotonPropuesta.setAttribute("aria-pressed", "true");
    }
    // Un enlace a una licitación concreta (correo, «Copiar ficha»,
    // enlace compartido) la abre siempre: en tarjetas y aunque esté
    // descartada en este navegador.
    if (p.id) {
      modoTabla = false;
      if (estaDescartada(p.id)) estado.verDescartadas = true;
    }
    aplicarFiltros();

    if (p.id && mostrarTarjeta(p.id)) return;

    window.scrollTo(0, 0);
    if (!esCargaInicial) elContenido.focus({ preventScroll: true });
  }

  function inicializar() {
    if (DATOS.length === 0) {
      elVistaListado.hidden = false;
      elConteo.textContent = "No hay datos cargados todavía.";
      elSinResultados.hidden = false;
      elSinResultados.textContent =
        "dashboard/tenders-data.js está vacío o no existe. Ejecuta los scrapers, clasificar.py y normalizar.py (ver README.md).";
      return;
    }

    document.getElementById("filtros-icono").outerHTML = Nav.icono("filtro");
    // En pantallas estrechas los filtros van encima de los resultados:
    // empiezan plegados para que la lista se vea sin desplazarse.
    if (window.matchMedia("(max-width: 900px)").matches) elFiltros.open = false;

    purgarGuardadas();
    purgarDescartadas();
    conteosNav = {
      licitaciones: deTipo("licitacion").length,
      calls: deTipo("convocatoria_ue").length,
      menores: deTipo("contrato_menor_venciendo").length,
      adjudicaciones: deTipo("adjudicacion").length,
    };
    actualizarConteoGuardadas();

    // Guardar / quitar, en cualquier tarjeta. En la vista
    // de guardadas se repinta para que la que se quita desaparezca; en las
    // demás solo cambian el botón y la etiqueta, sin cerrar la tarjeta.
    elContenido.addEventListener("click", function (ev) {
      var copiar = ev.target.closest && ev.target.closest("[data-copiar-ficha]");
      if (copiar) {
        var registro = porId[copiar.getAttribute("data-copiar-ficha")];
        var etiqueta = copiar.querySelector("span");
        var original = etiqueta.textContent;
        if (!registro) return;
        copiarTexto(fichaAsistente(registro, copiar.getAttribute("data-pregunta"))).then(function () {
          etiqueta.textContent = "Copiada: pégala en un chat nuevo";
        }, function () {
          etiqueta.textContent = "No se pudo copiar";
        });
        setTimeout(function () { etiqueta.textContent = original; }, 3000);
        return;
      }
      if (ev.target.closest && ev.target.closest("[data-facturacion]")) {
        var actual = facturacionGuardada();
        var dato = window.prompt("Facturación anual de tu empresa (mejor de los tres últimos ejercicios, en euros). Se guarda solo en este navegador; déjalo vacío para borrarla.", actual ? String(actual) : "");
        if (dato === null) return;
        var numero = Number(String(dato).replace(/[^\d]/g, ""));
        try {
          if (numero) localStorage.setItem(CLAVE_FACTURACION, String(numero)); else localStorage.removeItem(CLAVE_FACTURACION);
        } catch (e) { /* sin almacenamiento */ }
        aplicarFiltros();
        return;
      }
      var descarte = ev.target.closest && ev.target.closest("[data-descartar], [data-recuperar]");
      if (descarte) {
        var idD = descarte.getAttribute("data-descartar") || descarte.getAttribute("data-recuperar");
        var regD = porId[idD];
        if (descarte.hasAttribute("data-recuperar")) delete descartadas[idD];
        else if (regD) descartadas[idD] = { motivo: descarte.getAttribute("data-motivo"), fecha_limite: regD.fecha_limite, titulo: regD.titulo,
          fecha: new Date().toISOString().slice(0, 10) };
        escribirDescartadas();
        if (estado.verDescartadas && !deTipo(estado.tipoRegistro).some(function (t) { return estaDescartada(t.id); })) estado.verDescartadas = false;
        construirControles(); aplicarFiltros();
        return;
      }
      var boton = ev.target.closest && ev.target.closest("[data-guardar]");
      if (!boton) return;
      var id = boton.getAttribute("data-guardar");
      alternarGuardada(id);
      actualizarConteoGuardadas();
      if (estado.tipoRegistro === "guardadas" && !elVistaListado.hidden) {
        aplicarFiltros();
        return;
      }
      var si = estaGuardada(id);
      boton.setAttribute("aria-pressed", si ? "true" : "false");
      boton.querySelector("span").textContent = si ? "Guardada" : "Guardar";
      var tarjeta = boton.closest(".tarjeta");
      var chip = tarjeta && tarjeta.querySelector(".chip--guardada");
      if (chip) chip.hidden = !si;
    });

    // No hay marca de tiempo de generación en los datos: la referencia es
    // el día en que entró el último registro.
    var ultima = DATOS.reduce(function (max, t) { return t.fecha_primera_aparicion > max ? t.fecha_primera_aparicion : max; }, "");
    var textoActualizado = "Última incorporación de datos: " + fechaLarga(ultima, "—") + ".";
    Nav.actualizado(textoActualizado);
    elFechaGeneracion.textContent = textoActualizado + " " + miles(DATOS.length) + " registros en el radar.";

    elTexto.addEventListener("input", function () {
      estado.texto = sinTildes(elTexto.value.trim());
      aplicarFiltros();
    });
    elCategoria.addEventListener("change", function () {
      estado.categoria = elCategoria.value;
      aplicarFiltros();
    });
    elPais.addEventListener("change", function () {
      estado.pais = elPais.value;
      aplicarFiltros();
    });
    elLugar.addEventListener("change", function () {
      estado.lugar = elLugar.value;
      aplicarFiltros();
    });
    elPresupuestoMin.addEventListener("change", function () {
      estado.presupuestoMin = Number(elPresupuestoMin.value) || 0;
      aplicarFiltros();
    });
    elPresupuestoMax.addEventListener("change", function () {
      estado.presupuestoMax = elPresupuestoMax.value || null;
      aplicarFiltros();
    });
    elOrden.addEventListener("change", function () {
      estado.orden = elOrden.value;
      aplicarFiltros();
    });
    elBotonRevisar.addEventListener("click", function () {
      estado.soloRevisarManual = !estado.soloRevisarManual;
      elBotonRevisar.setAttribute("aria-pressed", estado.soloRevisarManual ? "true" : "false");
      aplicarFiltros();
    });
    elBotonPropuesta.addEventListener("click", function () {
      estado.soloPropuesta = !estado.soloPropuesta;
      elBotonPropuesta.setAttribute("aria-pressed", estado.soloPropuesta ? "true" : "false");
      aplicarFiltros();
    });
    elReset.addEventListener("click", function () {
      estado.texto = "";
      estado.fuente = "";
      estado.categoria = "";
      estado.pais = "";
      estado.lugar = "";
      estado.soloRevisarManual = false;
      estado.soloPropuesta = false;
      elTexto.value = "";
      elCategoria.value = "";
      elPais.value = "";
      elLugar.value = "";
      construirControlesDeVista();  // importe y orden, a sus valores por defecto
      elBotonRevisar.setAttribute("aria-pressed", "false");
      marcarFuente();
      aplicarFiltros();
    });

    document.getElementById("boton-modo").addEventListener("click", function () {
      modoTabla = !modoTabla;
      try { localStorage.setItem(CLAVE_MODO, modoTabla ? "tabla" : "tarjetas"); } catch (e) { /* sin almacenamiento */ }
      aplicarFiltros();
    });
    document.getElementById("columnas-lista").addEventListener("change", function () {
      var marcadas = Array.prototype.map.call(document.querySelectorAll("#columnas-lista input:checked"), function (i) { return i.value; });
      try { localStorage.setItem("radar-columnas-" + grupoColumnas(), JSON.stringify(marcadas)); } catch (e) { /* sin almacenamiento */ }
      var abierto = document.getElementById("selector-columnas").open;
      aplicarFiltros();
      document.getElementById("selector-columnas").open = abierto;
    });
    elContenedor.addEventListener("click", function (ev) {
      var a = ev.target.closest && ev.target.closest("[data-abrir]");
      if (!a) return;
      ev.preventDefault();
      modoTabla = false;
      try { localStorage.setItem(CLAVE_MODO, "tarjetas"); } catch (e) { /* sin almacenamiento */ }
      aplicarFiltros();
      mostrarTarjeta(a.getAttribute("data-abrir"));
    });
    document.getElementById("boton-descartadas").addEventListener("click", function () {
      estado.verDescartadas = !estado.verDescartadas;
      construirControles();
      aplicarFiltros();
    });

    window.addEventListener("hashchange", function () { navegar(false); });
    navegar(true);
  }

  inicializar();
})();
