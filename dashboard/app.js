(function () {
  "use strict";

  var Nav = window.RadarNav;
  var DATOS = (window.TENDERS_DATA || []).slice();

  // Vistas de listado de esta página, por ruta de hash. "recientes" y
  // "licitacion" son dos pestañas de la misma sección (Licitaciones): la
  // primera es un subconjunto de la segunda (españolas, vistas por primera
  // vez en los últimos tres días).
  var VISTAS = {
    "licitaciones/recientes": { tipo: "recientes", nav: "licitaciones", titulo: "Licitaciones" },
    "licitaciones/abiertas": { tipo: "licitacion", nav: "licitaciones", titulo: "Licitaciones" },
    "calls": { tipo: "convocatoria_ue", nav: "calls", titulo: "Calls for proposals UE" },
    "menores": { tipo: "contrato_menor_venciendo", nav: "menores", titulo: "Contratos menores por vencer" },
    "adjudicaciones": { tipo: "adjudicacion", nav: "adjudicaciones", titulo: "Adjudicaciones recientes" },
  };
  var RUTA_POR_TIPO = {};
  Object.keys(VISTAS).forEach(function (ruta) { RUTA_POR_TIPO[VISTAS[ruta].tipo] = ruta; });

  var PESTANAS_LICITACIONES = [
    ["licitaciones/recientes", "Publicadas recientemente", "recientes"],
    ["licitaciones/abiertas", "Licitaciones abiertas", "licitacion"],
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
    recientes: ["Estado", "Euskadi"],
    licitacion: ["Estado", "Euskadi", "UE"],
    adjudicacion: ["Estado", "Euskadi", "UE"],
    contrato_menor_venciendo: ["Estado", "Euskadi"],
    convocatoria_ue: ["UE-subvenciones"],
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
  // El filtro de país solo existe en "Licitaciones abiertas", la única
  // vista con licitaciones de otros países. En las demás solo ofrecía
  // "España / País Vasco" (o "UE"), que duplica el filtro Estado/Euskadi -y
  // mal: una licitación vasca que llega por TED figura como "España"-.
  var PAISES_POR_TIPO = {
    licitacion: PAISES_TED,
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
    ],
    licitacion: [
      ["plazo", "Fecha límite (más próxima)"],
      ["fecha-desc", "Publicación (más reciente)"],
      ["importe-desc", "Presupuesto (mayor primero)"],
    ],
    contrato_menor_venciendo: [
      ["vencimiento", "Vencimiento (más próximo)"],
      ["importe-desc", "Importe adjudicado (mayor primero)"],
      ["fecha-desc", "Adjudicación (más reciente)"],
    ],
    convocatoria_ue: [
      ["plazo", "Fecha límite de solicitud (más próxima)"],
      ["fecha-desc", "Apertura (más reciente)"],
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

  var EXPLICACION_TIPO = {
    recientes:
      "Licitaciones de organismos públicos españoles (Estado y Euskadi) que han aparecido por primera vez en el radar en los últimos tres días, ordenadas por fecha de publicación de la más reciente a la más antigua. Incluye las publicadas en PLACSP, en el portal de contratación de Euskadi y las de organismos españoles publicadas en TED.",
    licitacion:
      "Concursos públicos con plazo de presentación todavía abierto, de TED (UE), PLACSP (Estado) y el portal de contratación de Euskadi. Se recogen los publicados en los últimos 30 días o con plazo aún vigente, filtrados por categoría de servicio de agencia (marketing, publicidad, diseño, redes sociales...).",
    adjudicacion:
      "Qué empresa se ha llevado cada contrato en los últimos 30 días, en las mismas tres fuentes, solo cuando la adjudicataria es una empresa española (incluidas las vascas), según su NIF o el país que publica TED. Sin corte por importe: entra tanto un contrato menor como una licitación grande si se adjudicó recientemente y encaja con la categoría de servicio de agencia.",
    contrato_menor_venciendo:
      "Contratos menores (adjudicados directamente, sin concurso, según la definición legal) del Estado y Euskadi cuya duración estimada vence en los próximos 90 días.",
    convocatoria_ue:
      "Convocatorias de subvención de la Comisión Europea (Horizon Europe, Digital Europe...) abiertas o próximas a abrir, filtradas por las que incluyen un componente de comunicación o difusión en su descripción. Título y resumen traducidos automáticamente del inglés (la fuente no los publica en español).",
  };

  var ETIQUETAS_CONTEO = {
    recientes: "publicadas recientemente",
    licitacion: "licitaciones",
    adjudicacion: "adjudicaciones",
    contrato_menor_venciendo: "contratos menores",
    convocatoria_ue: "calls for proposals",
  };

  var estado = {
    tipoRegistro: "recientes",
    texto: "",
    fuente: "",
    categoria: "",
    pais: "",
    soloRevisarManual: false,
    presupuestoMin: 0,
    presupuestoMax: null,
    orden: ordenPorDefecto("recientes"),
  };

  var NO_PUBLICADO = "no publicado";
  var MS_DIA = 24 * 60 * 60 * 1000;
  var MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  var MAX_FILAS_INICIO = 6;
  var MAX_TARJETAS_INICIO = 5;

  var elVistaInicio = document.getElementById("vista-inicio");
  var elVistaListado = document.getElementById("vista-listado");
  var elContenido = document.getElementById("contenido");
  var elTitulo = document.getElementById("titulo-pagina");
  var elExplicacionTipo = document.getElementById("explicacion-tipo");
  var elPestanas = document.getElementById("pestanas-vista");
  var elTexto = document.getElementById("filtro-texto");
  var elFiltros = document.getElementById("filtros");
  var elFiltrosActivos = document.getElementById("filtros-activos");
  var elCampoFuente = document.getElementById("campo-fuente");
  var elSegmentedFuente = document.getElementById("segmented-fuente");
  var elCategoria = document.getElementById("filtro-categoria");
  var elCampoPais = document.getElementById("campo-pais");
  var elPais = document.getElementById("filtro-pais");
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
  var elBotonRevisar = document.getElementById("boton-revisar");
  var elSinResultados = document.getElementById("sin-resultados");
  var elResumenCabecera = document.getElementById("resumen-cabecera");
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

  function infoUrgencia(fechaLimiteStr) {
    var dias = diasRestantes(fechaLimiteStr);
    if (dias === null) {
      return { clase: "urgencia-sin-fecha", texto: "Sin fecha límite" };
    }
    if (dias < 0) {
      return { clase: "urgencia-roja", texto: "Plazo cerrado" };
    }
    if (dias <= 7) {
      return { clase: "urgencia-roja", texto: dias === 0 ? "Cierra hoy" : "Quedan " + dias + " día" + (dias === 1 ? "" : "s") };
    }
    if (dias <= 21) {
      return { clase: "urgencia-ambar", texto: "Quedan " + dias + " días" };
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

  function escaparHtml(str) {
    var div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML;
  }

  // Minúsculas y sin tildes, para que "comunicacion" encuentre "Comunicación".
  function sinTildes(str) {
    return String(str).toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  }

  // Con punto de millar siempre: toLocaleString("es-ES") no agrupa los
  // números de cuatro cifras ("3000 €" junto a "10.000 €").
  function miles(valor) {
    return String(valor).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  }

  function euros(valor) {
    return miles(valor) + " €";
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

  function deTipo(tipo) {
    if (tipo === "recientes") return DATOS.filter(esPublicacionReciente);
    return DATOS.filter(function (t) { return t.tipo_registro === tipo; });
  }

  function subconjuntoActivo() {
    return deTipo(estado.tipoRegistro);
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

  function construirControles() {
    var subconjunto = subconjuntoActivo();
    var esRecientes = estado.tipoRegistro === "recientes";
    var fuentes = {};
    var categorias = {};
    var totalRevisar = 0;
    var paises = {};

    subconjunto.forEach(function (t) {
      var f = esRecientes ? ambitoReciente(t) : t.fuente;
      fuentes[f] = (fuentes[f] || 0) + 1;
      (t.categorias || []).forEach(function (c) {
        categorias[c] = (categorias[c] || 0) + 1;
      });
      paises[t.pais_territorio] = (paises[t.pais_territorio] || 0) + 1;
      if (t.revisar_manual) totalRevisar++;
    });

    // Fuente: "Todas" + las fuentes fijas de la vista (FUENTES_POR_TIPO),
    // aunque alguna esté a 0 ese día: que un filtro desaparezca parecería un
    // fallo, no información.
    var opcionesFuente = [["", "Todas", subconjunto.length]];
    var fuentesVista = conOpcionesFijas(FUENTES_POR_TIPO[estado.tipoRegistro], fuentes);
    fuentesVista.forEach(function (f) {
      opcionesFuente.push([f, f, fuentes[f] || 0]);
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
      boton.innerHTML = "<span>" + escaparHtml(opcion[1]) + '</span><span class="opciones__conteo">' + opcion[2] + "</span>";
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
    elCategoria.innerHTML = '<option value="">Todas las categorías (' + subconjunto.length + ")</option>";
    categoriasOrdenadas.forEach(function (c) {
      var opt = document.createElement("option");
      opt.value = c;
      opt.textContent = c + " (" + (categorias[c] || 0) + ")";
      elCategoria.appendChild(opt);
    });
    elCategoria.value = estado.categoria;

    // Desplegable de país/territorio: solo en las vistas con entrada en
    // PAISES_POR_TIPO; ahí, los fijos aunque estén a 0, alfabético.
    var paisesFijos = PAISES_POR_TIPO[estado.tipoRegistro];
    elCampoPais.hidden = !paisesFijos;
    var paisesOrdenados = !paisesFijos ? [] : conOpcionesFijas(paisesFijos, paises)
      .sort(function (a, b) { return a.localeCompare(b, "es"); });
    elPais.innerHTML = '<option value="">Todos los países (' + subconjunto.length + ")</option>";
    paisesOrdenados.forEach(function (p) {
      var opt = document.createElement("option");
      opt.value = p;
      opt.textContent = p + " (" + (paises[p] || 0) + ")";
      elPais.appendChild(opt);
    });

    elBotonRevisar.hidden = totalRevisar === 0;
    elBotonRevisar.textContent = "Solo pendientes de revisar (" + totalRevisar + ")";
    elBotonRevisar.setAttribute("aria-pressed", estado.soloRevisarManual ? "true" : "false");
  }

  function marcarFuente() {
    Array.prototype.forEach.call(elSegmentedFuente.children, function (b) {
      b.setAttribute("aria-pressed", b.getAttribute("data-valor") === estado.fuente ? "true" : "false");
    });
  }

  function pasaFiltros(t) {
    if (estado.soloRevisarManual && !t.revisar_manual) return false;
    if (estado.fuente) {
      var fuenteComparar = estado.tipoRegistro === "recientes" ? ambitoReciente(t) : t.fuente;
      if (fuenteComparar !== estado.fuente) return false;
    }
    if (estado.categoria && (t.categorias || []).indexOf(estado.categoria) === -1) return false;
    if (estado.pais && t.pais_territorio !== estado.pais) return false;

    if (estado.texto) {
      // Se incluye empresa_adjudicataria (undefined en licitaciones/calls for
      // proposals, de ahí el || "") para poder buscar por el nombre de la
      // empresa ganadora en Adjudicaciones y Contratos menores.
      var pajar = sinTildes(t.titulo + " " + t.organismo + " " + t.resumen + " " + (t.empresa_adjudicataria || "") + " " + (t.codigo_expediente || ""));
      if (pajar.indexOf(estado.texto) === -1) return false;
    }

    var importe = IMPORTE_POR_TIPO[estado.tipoRegistro];
    var minActivo = estado.presupuestoMin > 0;
    var maxActivo = estado.presupuestoMax !== null && estado.presupuestoMax !== "";
    if (importe && (minActivo || maxActivo)) {
      // Sin importe publicado no se puede saber si entra en el rango: fuera.
      var valor = t[importe.campo];
      if (valor === null || valor === undefined) return false;
      if (minActivo && valor < estado.presupuestoMin) return false;
      if (maxActivo && valor > Number(estado.presupuestoMax)) return false;
    }

    return true;
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

  function plantillaTarjeta(t, abierta) {
    var tipo = t.tipo_registro;
    var esAdjudicacion = tipo === "adjudicacion";
    var esMenor = tipo === "contrato_menor_venciendo";
    var esCall = tipo === "convocatoria_ue";
    var conEmpresa = esAdjudicacion || esMenor;

    var urgencia = esMenor ? infoVencimiento(t.fecha_fin_estimada) : (esAdjudicacion ? null : infoUrgencia(t.fecha_limite));
    var empresa = t.empresa_adjudicataria === NO_PUBLICADO ? "Empresa no publicada" : t.empresa_adjudicataria;
    var presupuesto = importeTexto(t.presupuesto_display);
    var adjudicado = importeTexto(t.importe_adjudicado_display);
    var importeLateral = conEmpresa ? adjudicado : presupuesto;
    var finEstimado = fechaLarga(t.fecha_fin_estimada, "No publicado");

    // --- Fila resumen ---
    var chips =
      (t.codigo_expediente ? '<span class="chip chip--codigo" title="Expediente">' + escaparHtml(t.codigo_expediente) + "</span>" : "") +
      '<span class="chip">' + escaparHtml(t.fuente) + "</span>" +
      chipNovedad(t) +
      (t.revisar_manual ? '<span class="chip chip--aviso">Revisar</span>' : "") +
      (urgencia ? '<span class="insignia ' + urgencia.clase + '">' + escaparHtml(urgencia.texto) + "</span>" : "");

    var pie;
    if (esAdjudicacion) {
      pie = '<span class="tarjeta__pie-dato">Adjudicataria: <strong>' + escaparHtml(empresa) + "</strong></span>" +
        "<span>Adjudicada: <strong>" + fechaLarga(t.fecha_adjudicacion) + "</strong></span>";
    } else if (esMenor) {
      pie = '<span class="tarjeta__pie-dato">Lo tiene: <strong>' + escaparHtml(empresa) + "</strong></span>" +
        "<span>Vence (estimado): <strong>" + finEstimado + "</strong></span>";
    } else if (esCall) {
      pie = "<span>Fecha límite de solicitud: <strong>" + fechaLarga(t.fecha_limite) + "</strong></span>" +
        "<span>Apertura: <strong>" + fechaLarga(t.fecha_publicacion) + "</strong></span>";
    } else {
      pie = "<span>Fin de presentación: <strong>" + fechaLarga(t.fecha_limite) + "</strong></span>" +
        "<span>Publicada: <strong>" + fechaLarga(t.fecha_publicacion) + "</strong></span>";
    }

    // --- Detalle ---
    var cpv = (t.cpv || []).filter(function (c, i, lista) { return lista.indexOf(c) === i; });
    var general = [
      par("Organismo", escaparHtml(t.organismo)),
      par("Territorio", escaparHtml(t.pais_territorio)),
      par("Fuente", escaparHtml(t.fuente)),
      par("Tipo de contrato", escaparHtml(t.tipo_contrato === NO_PUBLICADO ? "No publicado" : t.tipo_contrato)),
    ];
    if (t.codigo_expediente) general.push(par("Expediente", escaparHtml(t.codigo_expediente)));
    if (t.programa) general.push(par("Programa", escaparHtml(t.programa)));
    if (cpv.length) general.push(par("CPV", escaparHtml(cpv.join(", ")), true));

    var fechas;
    if (esAdjudicacion) {
      fechas = [par("Fecha de adjudicación", fechaLarga(t.fecha_adjudicacion), true), par("Vigente hasta", finEstimado, true)];
    } else if (esMenor) {
      fechas = [par("Adjudicado el", fechaLarga(t.fecha_adjudicacion), true), par("Vence el (estimado)", finEstimado, true)];
    } else if (esCall) {
      fechas = [par("Apertura", fechaLarga(t.fecha_publicacion), true), par("Fecha límite de solicitud", fechaLarga(t.fecha_limite), true)];
    } else {
      fechas = [par("Publicada", fechaLarga(t.fecha_publicacion), true), par("Fecha límite", fechaLarga(t.fecha_limite), true)];
    }
    fechas.push(par("En el radar desde", fechaLarga(t.fecha_primera_aparicion, "—"), true));

    var importes = [];
    if (conEmpresa) {
      importes.push(par(esMenor ? "Empresa que lo tiene hoy" : "Empresa adjudicataria", escaparHtml(empresa)));
      if (t.empresa_nif) importes.push(par("NIF", escaparHtml(t.empresa_nif), true));
      importes.push(par("Importe adjudicado", adjudicado || "No publicado", true));
      if (presupuesto) importes.push(par("Presupuesto de licitación", presupuesto, true));
    } else {
      importes.push(par("Presupuesto", presupuesto || "No publicado", true));
    }

    var categoriasHtml = (t.categorias || [])
      .map(function (c) { return '<span class="etiqueta-categoria">' + escaparHtml(c) + "</span>"; })
      .join("");
    var revisarHtml = t.revisar_manual
      ? '<span class="etiqueta-revisar">Revisar: mezcla con otros servicios no propios de agencia</span>'
      : "";

    var esDirecto = t.enlace_directo !== false;
    var acciones = "";
    if (t.enlace && t.enlace !== NO_PUBLICADO) {
      acciones += '<a class="boton boton--primario" href="' + escaparHtml(t.enlace) + '" target="_blank" rel="noopener noreferrer">' +
        (esDirecto ? "Ver anuncio original" : "Buscar en el portal de Euskadi") + Nav.icono("externo") + "</a>";
    } else {
      acciones += '<span class="chip">Enlace no publicado</span>';
    }
    if (conEmpresa && t.empresa_adjudicataria !== NO_PUBLICADO) {
      // Por NIF si el registro lo trae (es como identifica a cada empresa el
      // histórico); el nombre va siempre, por si el NIF no está allí.
      acciones += '<a class="enlace" href="historico.html#/empresas?' + (t.empresa_nif ? "nif=" + encodeURIComponent(t.empresa_nif) + "&" : "") +
        "q=" + encodeURIComponent(t.empresa_adjudicataria) + '">Historial de la empresa' + Nav.icono("flecha") + "</a>";
    }
    if (!esCall && esOrganismoEspanol(t)) {
      acciones += '<a class="enlace" href="historico.html#/organismos?q=' + encodeURIComponent(t.organismo) + '">Quién gana en este organismo' + Nav.icono("flecha") + "</a>";
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
            '<span class="tarjeta__lugar">' + Nav.icono("lugar") + escaparHtml(t.pais_territorio) + "</span>" +
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
          '<div class="tarjeta__bloque"><h4>Categorías de servicio</h4><div class="tarjeta__categorias">' + categoriasHtml + revisarHtml + "</div></div>" +
          codigoHtml +
          '<div class="tarjeta__acciones">' + acciones + "</div>" +
        "</div>" +
      "</details>"
    );
  }

  function contarFiltrosActivos() {
    var n = 0;
    if (estado.fuente) n++;
    if (estado.categoria) n++;
    if (estado.pais) n++;
    if (estado.presupuestoMin > 0) n++;
    if (estado.presupuestoMax !== null && estado.presupuestoMax !== "") n++;
    if (estado.soloRevisarManual) n++;
    return n;
  }

  function aplicarFiltros() {
    var subconjunto = subconjuntoActivo();
    var filtrados = subconjunto.filter(pasaFiltros);
    filtrados.sort(comparar);

    // "Publicadas recientemente" tendrá pocas tarjetas casi siempre (es una
    // ventana de tres días), así que se muestran ya desplegadas: no compensa
    // el gesto de abrir cada una cuando hay un puñado en vez de cientos.
    var abiertas = estado.tipoRegistro === "recientes";

    elConteo.textContent = filtrados.length + " de " + subconjunto.length + " " + ETIQUETAS_CONTEO[estado.tipoRegistro];
    elContenedor.innerHTML = filtrados.map(function (t) { return plantillaTarjeta(t, abiertas); }).join("");
    elSinResultados.hidden = filtrados.length > 0;

    var activos = contarFiltrosActivos();
    elFiltrosActivos.hidden = activos === 0;
    elFiltrosActivos.textContent = activos;
  }

  function pintarResumenCabecera() {
    var subconjunto = subconjuntoActivo();
    var totalRevisar = subconjunto.filter(function (t) { return t.revisar_manual; }).length;

    if (estado.tipoRegistro === "adjudicacion") {
      var empresas = {};
      subconjunto.forEach(function (t) { if (t.empresa_adjudicataria !== NO_PUBLICADO) empresas[t.empresa_adjudicataria] = true; });
      elResumenCabecera.innerHTML =
        '<div><strong>' + subconjunto.length + '</strong>adjudicaciones</div>' +
        '<div><strong>' + Object.keys(empresas).length + '</strong>empresas distintas</div>' +
        '<div><strong>' + totalRevisar + '</strong>a revisar</div>';
      return;
    }

    if (estado.tipoRegistro === "contrato_menor_venciendo") {
      var venceEn30 = subconjunto.filter(function (t) {
        var d = diasRestantes(t.fecha_fin_estimada);
        return d !== null && d >= 0 && d <= 30;
      }).length;
      elResumenCabecera.innerHTML =
        '<div><strong>' + subconjunto.length + '</strong>por vencer</div>' +
        '<div><strong>' + venceEn30 + '</strong>en 30 días</div>' +
        '<div><strong>' + totalRevisar + '</strong>a revisar</div>';
      return;
    }

    var totalAbiertas = subconjunto.filter(function (t) {
      var d = diasRestantes(t.fecha_limite);
      return d === null || d >= 0;
    }).length;

    elResumenCabecera.innerHTML =
      '<div><strong>' + subconjunto.length + '</strong>' + ETIQUETAS_CONTEO[estado.tipoRegistro] + '</div>' +
      '<div><strong>' + totalAbiertas + '</strong>en plazo</div>' +
      '<div><strong>' + totalRevisar + '</strong>a revisar</div>';
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

  // ---------- Inicio ----------

  function filaCompacta(t, sub, datoHtml) {
    return '<li><a class="fila" href="#/' + RUTA_POR_TIPO[t.tipo_registro] + "?id=" + encodeURIComponent(t.id) + '">' +
      '<span class="fila__texto"><span class="fila__titulo">' + escaparHtml(t.titulo) + "</span>" +
      '<span class="fila__sub">' + escaparHtml(sub) + "</span></span>" + datoHtml + "</a></li>";
  }

  function panelFilas(titulo, enlace, textoEnlace, filas, vacio) {
    return '<section class="panel"><div class="seccion__cabecera"><h2>' + titulo + "</h2>" +
      '<a class="enlace" href="' + enlace + '">' + textoEnlace + Nav.icono("flecha") + "</a></div>" +
      (filas.length ? '<ul class="filas">' + filas.join("") + "</ul>" : '<p class="barras__vacio">' + vacio + "</p>") +
      "</section>";
  }

  function pintarInicio() {
    var recientes = deTipo("recientes").sort(porFechaDesc);
    var abiertas = deTipo("licitacion");
    var calls = deTipo("convocatoria_ue");
    var menores = deTipo("contrato_menor_venciendo");
    var adjudicaciones = deTipo("adjudicacion").sort(porFechaDesc);

    function entre(lista, campo, min, max) {
      return lista.filter(function (t) {
        var d = diasRestantes(t[campo]);
        return d !== null && d >= min && d <= max;
      });
    }
    function proximas(lista, campo) {
      return lista.slice().sort(function (a, b) { return porFechaProxima(campo, a, b) || porFechaDesc(a, b); });
    }

    var nuevasHoy = recientes.filter(function (t) { return diasRestantes(t.fecha_primera_aparicion) === 0; }).length;
    var cierranSemana = proximas(entre(abiertas, "fecha_limite", 0, 7), "fecha_limite");
    var callsMes = entre(calls, "fecha_limite", 0, 30).length;
    var menoresVigentes = proximas(entre(menores, "fecha_fin_estimada", 0, 9999), "fecha_fin_estimada");
    var menoresMes = entre(menores, "fecha_fin_estimada", 0, 30).length;
    var empresas = {};
    adjudicaciones.forEach(function (t) { if (t.empresa_adjudicataria !== NO_PUBLICADO) empresas[t.empresa_adjudicataria] = true; });

    var kpis = [
      ["#/licitaciones/recientes", "Publicadas recientemente", recientes.length, nuevasHoy + " han entrado hoy"],
      ["#/licitaciones/abiertas", "Licitaciones abiertas", abiertas.length, cierranSemana.length + " cierran en 7 días"],
      ["#/calls", "Calls for proposals UE", calls.length, callsMes + " cierran en 30 días"],
      ["#/menores", "Contratos menores por vencer", menores.length, menoresMes + " vencen en 30 días"],
      ["#/adjudicaciones", "Adjudicaciones recientes", adjudicaciones.length, Object.keys(empresas).length + " empresas distintas"],
    ];
    document.getElementById("inicio-kpis").innerHTML = kpis.map(function (k) {
      return '<a class="kpi" href="' + k[0] + '"><span class="kpi__etiqueta">' + k[1] + '</span><span class="kpi__valor">' + miles(k[2]) +
        '</span><span class="kpi__nota">' + k[3] + "</span></a>";
    }).join("");

    // Columna principal: lo último publicado y el reparto por categoría.
    var porCategoria = {};
    abiertas.forEach(function (t) {
      var d = diasRestantes(t.fecha_limite);
      if (d !== null && d < 0) return;
      (t.categorias || []).forEach(function (c) { porCategoria[c] = (porCategoria[c] || 0) + 1; });
    });
    var categorias = Object.keys(porCategoria).sort(function (a, b) { return porCategoria[b] - porCategoria[a] || a.localeCompare(b, "es"); });
    var maxCategoria = categorias.length ? porCategoria[categorias[0]] : 1;

    document.getElementById("inicio-principal").innerHTML =
      '<section><div class="seccion__cabecera"><h2>Publicadas recientemente</h2>' +
        '<a class="enlace" href="#/licitaciones/recientes">Ver las ' + recientes.length + Nav.icono("flecha") + "</a></div>" +
        (recientes.length
          ? '<div class="lista-tarjetas">' + recientes.slice(0, MAX_TARJETAS_INICIO).map(function (t) { return plantillaTarjeta(t, false); }).join("") + "</div>"
          : '<p class="sin-resultados">No ha aparecido ninguna licitación de organismos españoles en los últimos tres días.</p>') +
      "</section>" +
      '<section class="panel"><div class="seccion__cabecera"><h2>Licitaciones en plazo por categoría</h2>' +
        '<a class="enlace" href="#/licitaciones/abiertas">Ver todas' + Nav.icono("flecha") + "</a></div>" +
        '<ol class="barras">' + categorias.map(function (c) {
          return '<li class="barras__fila"><a class="barras__boton" href="#/licitaciones/abiertas?cat=' + encodeURIComponent(c) + '">' +
            '<span class="barras__nombre">' + escaparHtml(c) + "</span>" +
            '<span class="barras__pista"><span class="barras__relleno" style="width:' + (100 * porCategoria[c] / maxCategoria).toFixed(1) + '%"></span></span>' +
            '<span class="barras__valor">' + porCategoria[c] + "</span></a></li>";
        }).join("") + "</ol>" +
        '<p class="panel__nota">Una licitación puede contar en varias categorías. Pulsa una categoría para ver sus licitaciones.</p>' +
      "</section>";

    // Columna lateral: lo que vence antes.
    document.getElementById("inicio-lateral").innerHTML =
      panelFilas("Cierran en los próximos 7 días", "#/licitaciones/abiertas", "Ver todas",
        cierranSemana.slice(0, MAX_FILAS_INICIO).map(function (t) {
          var u = infoUrgencia(t.fecha_limite);
          return filaCompacta(t, t.organismo, '<span class="insignia ' + u.clase + '">' + u.texto + "</span>");
        }), "Ninguna licitación cierra esta semana.") +
      panelFilas("Contratos menores que vencen antes", "#/menores", "Ver todos",
        menoresVigentes.slice(0, MAX_FILAS_INICIO).map(function (t) {
          var v = infoVencimiento(t.fecha_fin_estimada);
          var empresa = t.empresa_adjudicataria === NO_PUBLICADO ? "Empresa no publicada" : t.empresa_adjudicataria;
          return filaCompacta(t, empresa + " · " + t.organismo, '<span class="insignia ' + v.clase + '">' + v.texto + "</span>");
        }), "No hay contratos menores por vencer.") +
      panelFilas("Últimas adjudicaciones", "#/adjudicaciones", "Ver todas",
        adjudicaciones.slice(0, MAX_FILAS_INICIO).map(function (t) {
          var empresa = t.empresa_adjudicataria === NO_PUBLICADO ? "Empresa no publicada" : t.empresa_adjudicataria;
          var importe = importeTexto(t.importe_adjudicado_display);
          return filaCompacta(t, empresa + " · " + t.organismo, importe ? '<span class="fila__dato">' + importe + "</span>" : "");
        }), "No hay adjudicaciones en los últimos 30 días.");
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
    var ruta = leida.ruta || "inicio";
    if (ruta === "licitaciones") ruta = "licitaciones/recientes";
    var vista = VISTAS[ruta];
    var esInicio = !vista;

    elVistaInicio.hidden = !esInicio;
    elVistaListado.hidden = esInicio;

    if (esInicio) {
      Nav.activar("inicio");
      document.title = "Radar de licitaciones — Marketing digital";
      pintarInicio();
    } else {
      var p = leida.params;
      estado.tipoRegistro = vista.tipo;
      estado.texto = sinTildes((p.q || "").trim());
      estado.fuente = p.fuente || "";
      estado.categoria = CATEGORIAS_CONOCIDAS.indexOf(p.cat) !== -1 ? p.cat : "";
      estado.pais = "";
      estado.soloRevisarManual = false;
      elTexto.value = p.q || "";

      Nav.activar(vista.nav);
      document.title = vista.titulo + " — Radar de licitaciones";
      elTitulo.textContent = vista.titulo;
      elExplicacionTipo.textContent = EXPLICACION_TIPO[vista.tipo];
      pintarPestanas(ruta);
      construirControlesDeVista();
      construirControles();
      pintarResumenCabecera();
      aplicarFiltros();

      if (p.id && mostrarTarjeta(p.id)) return;
    }

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

    Nav.guardarConteos({
      licitaciones: deTipo("licitacion").length,
      calls: deTipo("convocatoria_ue").length,
      menores: deTipo("contrato_menor_venciendo").length,
      adjudicaciones: deTipo("adjudicacion").length,
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
    elReset.addEventListener("click", function () {
      estado.texto = "";
      estado.fuente = "";
      estado.categoria = "";
      estado.pais = "";
      estado.soloRevisarManual = false;
      elTexto.value = "";
      elCategoria.value = "";
      elPais.value = "";
      construirControlesDeVista();  // importe y orden, a sus valores por defecto
      elBotonRevisar.setAttribute("aria-pressed", "false");
      marcarFuente();
      aplicarFiltros();
    });

    window.addEventListener("hashchange", function () { navegar(false); });
    navegar(true);
  }

  inicializar();
})();
