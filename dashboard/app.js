(function () {
  "use strict";

  var DATOS = (window.TENDERS_DATA || []).slice();

  var TIPOS_REGISTRO = [
    ["recientes", "Publicadas recientemente"],
    ["licitacion", "Licitaciones abiertas"],
    ["adjudicacion", "Adjudicaciones"],
    ["contrato_menor_venciendo", "Contratos menores por vencer"],
    ["convocatoria_ue", "Calls for proposals UE"],
  ];

  // Lista completa de categorías de la taxonomía (debe reflejar las claves
  // de config.CATEGORIAS en el proyecto Python — el dashboard es JS estático
  // sin acceso a ese archivo, así que se mantiene a mano aquí; tocar los dos
  // sitios si se añade/renombra una categoría). A petición explícita del
  // usuario, el desplegable de categorías siempre las lista TODAS, aunque
  // la pestaña activa no tenga ahora mismo ninguna licitación en alguna de
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

  // Ventana de "recientes": el dato solo tiene fecha (YYYY-MM-DD), no hora,
  // así que "últimos 3 días" se aproxima a nivel de día -publicado hoy,
  // ayer o anteayer- en vez de horas exactas, que no se pueden calcular con
  // lo que publican las fuentes.
  var DIAS_VENTANA_RECIENTES = 2;

  // Solo "licitacion" trae presupuesto_valor poblado: adjudicaciones y
  // contratos menores guardan el importe en importe_adjudicado_valor (otro
  // campo, no filtrable por este control) y las calls for proposals no
  // publican presupuesto por convocatoria. Sin esto, el filtro de
  // presupuesto mostraba 0 resultados sin explicación en esas pestañas
  // (bug real detectado en auditoría: el control seguía visible en las 4
  // pestañas pero solo funcionaba en una).
  var TIPOS_CON_PRESUPUESTO = { licitacion: true };

  var EXPLICACION_TIPO = {
    recientes:
      "Licitaciones de organismos públicos españoles (Estado y Euskadi) que han aparecido por primera vez en el radar en los últimos tres días, ordenadas por fecha de publicación de la más reciente a la más antigua. Incluye las publicadas en PLACSP, en el portal de contratación de Euskadi y las de organismos españoles publicadas en TED.",
    licitacion:
      "Concursos públicos con plazo de presentación todavía abierto, de TED (UE), PLACSP (Estado) y el portal de contratación de Euskadi. Se recogen los publicados en los últimos 30 días o con plazo aún vigente, filtrados por categoría de servicio de agencia (marketing, publicidad, diseño, redes sociales...).",
    adjudicacion:
      "Qué empresa se ha llevado cada contrato en los últimos 30 días, en las mismas tres fuentes. Sin corte por importe: entra tanto un contrato menor como una licitación grande si se adjudicó recientemente y encaja con la categoría de servicio de agencia. Permite ver qué empresas y consultoras se están llevando cada tipo de contrato.",
    contrato_menor_venciendo:
      "Contratos menores (adjudicados directamente, sin concurso, según la definición legal) del Estado y Euskadi cuya duración estimada vence en los próximos 90 días.",
    convocatoria_ue:
      "Convocatorias de subvención de la Comisión Europea (Horizon Europe, Digital Europe...) abiertas o próximas a abrir, filtradas por las que incluyen un componente de comunicación o difusión en su descripción. Título y resumen traducidos automáticamente del inglés (la fuente no los publica en español).",
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
    orden: "plazo",
  };

  var NO_PUBLICADO = "no publicado";
  var MS_DIA = 24 * 60 * 60 * 1000;

  var elTexto = document.getElementById("filtro-texto");
  var elSegmentedTipo = document.getElementById("segmented-tipo");
  var elExplicacionTipo = document.getElementById("explicacion-tipo");
  var elSegmentedFuente = document.getElementById("segmented-fuente");
  var elCategoria = document.getElementById("filtro-categoria");
  var elPais = document.getElementById("filtro-pais");
  var elPresupuestoMin = document.getElementById("filtro-presupuesto-min");
  var elPresupuestoMax = document.getElementById("filtro-presupuesto-max");
  var elCampoPresupuestoMin = document.getElementById("campo-presupuesto-min");
  var elCampoPresupuestoMax = document.getElementById("campo-presupuesto-max");
  var elOrden = document.getElementById("filtro-orden");
  var elReset = document.getElementById("boton-reset");
  var elContenedor = document.getElementById("contenedor-tarjetas");
  var elConteo = document.getElementById("conteo-resultados");
  var elBotonRevisar = document.getElementById("boton-revisar");
  var elSinResultados = document.getElementById("sin-resultados");
  var elResumenCabecera = document.getElementById("resumen-cabecera");
  var elFechaGeneracion = document.getElementById("fecha-generacion");

  var CHEVRON_SVG = '<svg class="tarjeta__chevron" viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M7 5l6 5-6 5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  var ENLACE_SVG = '<svg width="13" height="13" viewBox="0 0 20 20" fill="none" style="vertical-align:-2px;margin-right:3px"><path d="M8 12l7-7M9 5h6v6M15 11v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';

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
      return { clase: "urgencia-roja", texto: dias === 0 ? "Cierra hoy" : dias + " día" + (dias === 1 ? "" : "s") };
    }
    if (dias <= 21) {
      return { clase: "urgencia-ambar", texto: dias + " días" };
    }
    return { clase: "urgencia-verde", texto: dias + " días" };
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
      return { clase: "urgencia-roja", texto: "Vence en " + dias + " días" };
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
    // vez), no fecha_publicacion (la fecha oficial que da la fuente) — con
    // fecha_publicacion, una licitación del Estado prácticamente nunca
    // entraba aquí, porque PLACSP no tiene API en tiempo real y su ZIP de
    // sindicación llega con ~5 días de retraso estructural: para cuando
    // "aparecía" para nosotros, ya tenía más días que la ventana de esta
    // pestaña. fecha_primera_aparicion la calcula normalizar.py y persiste
    // entre ejecuciones, así que no tiene ese problema.
    var dias = diasRestantes(t.fecha_primera_aparicion);
    // diasRestantes da (fecha - hoy); hoy, ayer o anteayer dan 0, -1 o -2.
    return dias !== null && dias <= 0 && dias >= -DIAS_VENTANA_RECIENTES;
  }

  function subconjuntoActivo() {
    if (estado.tipoRegistro === "recientes") {
      return DATOS.filter(esPublicacionReciente);
    }
    return DATOS.filter(function (t) { return t.tipo_registro === estado.tipoRegistro; });
  }

  function actualizarVisibilidadPresupuesto() {
    var soportado = !!TIPOS_CON_PRESUPUESTO[estado.tipoRegistro];
    elCampoPresupuestoMin.hidden = !soportado;
    elCampoPresupuestoMax.hidden = !soportado;
  }

  function construirSegmentedTipo() {
    var conteos = {};
    DATOS.forEach(function (t) {
      conteos[t.tipo_registro] = (conteos[t.tipo_registro] || 0) + 1;
    });
    // "recientes" es una categoría virtual (ningún registro tiene ese
    // tipo_registro literal, se calcula combinando otros dos) — sin esto,
    // conteos["recientes"] siempre sale undefined y el badge de la pestaña
    // marca (0) aunque sí haya elementos dentro.
    conteos.recientes = DATOS.filter(esPublicacionReciente).length;

    elSegmentedTipo.innerHTML = "";
    // "recientes" se muestra siempre, incluso en 0: que desaparezca justo el
    // día que no hay nada nuevo parecería un fallo, no información útil -es
    // la pestaña pensada para mirar primero cada día, con o sin resultados.
    TIPOS_REGISTRO.filter(function (par) { return par[0] === "recientes" || conteos[par[0]] > 0; }).forEach(function (par) {
      var valor = par[0], etiqueta = par[1];
      var boton = document.createElement("button");
      boton.type = "button";
      boton.className = "segmented__opcion";
      boton.setAttribute("data-valor", valor);
      boton.textContent = etiqueta + " (" + (conteos[valor] || 0) + ")";
      boton.setAttribute("role", "radio");
      boton.setAttribute("aria-pressed", valor === estado.tipoRegistro ? "true" : "false");
      boton.addEventListener("click", function () {
        if (estado.tipoRegistro === valor) return;
        estado.tipoRegistro = valor;
        estado.texto = "";
        estado.fuente = "";
        estado.categoria = "";
        estado.pais = "";
        estado.soloRevisarManual = false;
        estado.presupuestoMin = 0;
        estado.presupuestoMax = null;
        estado.orden = "plazo";
        elTexto.value = "";
        elPresupuestoMin.value = "0";
        elPresupuestoMax.value = "";
        elOrden.value = "plazo";
        elBotonRevisar.classList.remove("activo");
        Array.prototype.forEach.call(elSegmentedTipo.children, function (b) {
          b.setAttribute("aria-pressed", b === boton ? "true" : "false");
        });
        elExplicacionTipo.textContent = EXPLICACION_TIPO[valor] || "";
        elExplicacionTipo.setAttribute("data-tipo", valor);
        actualizarVisibilidadPresupuesto();
        construirControles();
        pintarResumenCabecera();
        aplicarFiltros();
      });
      elSegmentedTipo.appendChild(boton);
    });

    elExplicacionTipo.textContent = EXPLICACION_TIPO[estado.tipoRegistro] || "";
    elExplicacionTipo.setAttribute("data-tipo", estado.tipoRegistro);
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

    // Segmented control de fuente: "Todas" + una opción por fuente. En el
    // resto de pestañas, solo las fuentes presentes (dinámico). En
    // "recientes" se fijan siempre Estado y Euskadi aunque alguna esté a 0
    // ese día, igual que la propia pestaña nunca desaparece al llegar a 0:
    // es la vista de uso diario y que un filtro desaparezca parecería un
    // fallo, no información.
    var opcionesFuente = [["", "Todas (" + subconjunto.length + ")"]];
    if (esRecientes) {
      ["Estado", "Euskadi"].forEach(function (f) {
        opcionesFuente.push([f, f + " (" + (fuentes[f] || 0) + ")"]);
      });
    } else {
      Object.keys(fuentes).sort().forEach(function (f) {
        opcionesFuente.push([f, f + " (" + fuentes[f] + ")"]);
      });
    }

    elSegmentedFuente.innerHTML = "";
    opcionesFuente.forEach(function (par) {
      var valor = par[0], etiqueta = par[1];
      var boton = document.createElement("button");
      boton.type = "button";
      boton.className = "segmented__opcion";
      boton.textContent = etiqueta;
      boton.setAttribute("role", "radio");
      boton.setAttribute("aria-pressed", valor === estado.fuente ? "true" : "false");
      boton.addEventListener("click", function () {
        estado.fuente = valor;
        Array.prototype.forEach.call(elSegmentedFuente.children, function (b) {
          b.setAttribute("aria-pressed", "false");
        });
        boton.setAttribute("aria-pressed", "true");
        aplicarFiltros();
      });
      elSegmentedFuente.appendChild(boton);
    });

    // Desplegable de categoría: TODAS las de CATEGORIAS_CONOCIDAS, no solo
    // las presentes en la pestaña activa (ver comentario junto a esa
    // constante) — ordenadas por volumen en esta pestaña, y a igualdad
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

    // Desplegable de país/territorio, alfabético
    var paisesOrdenados = Object.keys(paises).sort(function (a, b) { return a.localeCompare(b, "es"); });
    elPais.innerHTML = '<option value="">Todos los países (' + subconjunto.length + ")</option>";
    paisesOrdenados.forEach(function (p) {
      var opt = document.createElement("option");
      opt.value = p;
      opt.textContent = p + " (" + paises[p] + ")";
      elPais.appendChild(opt);
    });

    if (totalRevisar > 0) {
      elBotonRevisar.hidden = false;
      elBotonRevisar.textContent = "⚠ " + totalRevisar + " pendiente" + (totalRevisar === 1 ? "" : "s") + " de revisar";
      elBotonRevisar.onclick = function () {
        estado.soloRevisarManual = !estado.soloRevisarManual;
        elBotonRevisar.classList.toggle("activo", estado.soloRevisarManual);
        aplicarFiltros();
      };
    } else {
      elBotonRevisar.hidden = true;
    }
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
      // empresa ganadora en Adjudicaciones y Contratos menores — antes solo
      // se podía filtrar por título/organismo/resumen, no por quién se lo
      // llevó, pese a ser justo el dato central de esas dos pestañas.
      var pajar = (t.titulo + " " + t.organismo + " " + t.resumen + " " + (t.empresa_adjudicataria || "")).toLowerCase();
      if (pajar.indexOf(estado.texto) === -1) return false;
    }

    var minActivo = estado.presupuestoMin > 0;
    var maxActivo = estado.presupuestoMax !== null && estado.presupuestoMax !== "";
    if (minActivo || maxActivo) {
      if (t.presupuesto_valor === null || t.presupuesto_valor === undefined) return false;
      if (minActivo && t.presupuesto_valor < estado.presupuestoMin) return false;
      if (maxActivo && t.presupuesto_valor > Number(estado.presupuestoMax)) return false;
    }

    return true;
  }

  function comparar(a, b) {
    // "Contratos menores por vencer": lo más accionable es visitar primero
    // el que caduca antes, así que se ordena ascendente por fecha fin
    // estimada (a diferencia de adjudicaciones, donde lo relevante es la
    // más reciente primero).
    if (estado.tipoRegistro === "contrato_menor_venciendo") {
      var da2 = diasRestantes(a.fecha_fin_estimada);
      var db2 = diasRestantes(b.fecha_fin_estimada);
      if (da2 === null && db2 === null) return 0;
      if (da2 === null) return 1;
      if (db2 === null) return -1;
      return da2 - db2;
    }
    // "Publicadas recientemente": entra en la pestaña por fecha_primera_aparicion
    // (ver esPublicacionReciente), pero se ordena por fecha_publicacion —
    // la oficial de la fuente, mostrada en cada tarjeta— descendente, para
    // que arriba quede siempre lo publicado más recientemente. Ignora el
    // selector "Ordenar por" (igual que "Contratos menores por vencer"
    // arriba ignora el mismo selector para ordenar por fecha fin).
    if (estado.tipoRegistro === "recientes") {
      var ra = a.fecha_publicacion === NO_PUBLICADO ? "" : a.fecha_publicacion;
      var rb = b.fecha_publicacion === NO_PUBLICADO ? "" : b.fecha_publicacion;
      return rb.localeCompare(ra);
    }
    // "Calls for proposals UE" tiene la misma semántica de fecha que una
    // licitación (fecha_limite = fecha límite de solicitud), así que
    // comparte el orden por defecto de más abajo (plazo ascendente). Fuera
    // de esos dos, no hay plazo que ordenar: el orden por defecto es la
    // fecha más relevante en desc (fecha_publicacion guarda la fecha de
    // adjudicación en el tipo "adjudicacion").
    if (estado.tipoRegistro !== "licitacion" && estado.tipoRegistro !== "convocatoria_ue") {
      var xa = a.fecha_publicacion === NO_PUBLICADO ? "" : a.fecha_publicacion;
      var xb = b.fecha_publicacion === NO_PUBLICADO ? "" : b.fecha_publicacion;
      return xb.localeCompare(xa);
    }
    if (estado.orden === "presupuesto-desc") {
      var pa = a.presupuesto_valor === null ? -Infinity : a.presupuesto_valor;
      var pb = b.presupuesto_valor === null ? -Infinity : b.presupuesto_valor;
      return pb - pa;
    }
    if (estado.orden === "publicacion-desc") {
      var fa = a.fecha_publicacion === NO_PUBLICADO ? "" : a.fecha_publicacion;
      var fb = b.fecha_publicacion === NO_PUBLICADO ? "" : b.fecha_publicacion;
      return fb.localeCompare(fa);
    }
    var da = diasRestantes(a.fecha_limite);
    var db = diasRestantes(b.fecha_limite);
    if (da === null && db === null) return 0;
    if (da === null) return 1;
    if (db === null) return -1;
    return da - db;
  }

  function plantillaTarjetaLicitacion(t, grande) {
    var urgencia = infoUrgencia(t.fecha_limite);
    var claseRevisar = t.revisar_manual ? " revisar-manual" : "";
    var claseGrande = grande ? " tarjeta--grande" : "";
    var abierta = grande ? " open" : "";

    var categoriasHtml = (t.categorias || [])
      .map(function (c) { return '<span class="etiqueta-categoria">' + escaparHtml(c) + "</span>"; })
      .join("");
    var revisarHtml = t.revisar_manual
      ? '<span class="etiqueta-revisar">⚠ Revisar: mezcla con otros servicios no propios de agencia</span>'
      : "";

    var esDirecto = t.enlace_directo !== false;
    var enlaceHtml;
    if (t.enlace && t.enlace !== NO_PUBLICADO) {
      var textoEnlace = esDirecto ? "Ver anuncio original" : "Buscar en el portal de Euskadi";
      enlaceHtml = '<a class="tarjeta__enlace" href="' + escaparHtml(t.enlace) + '" target="_blank" rel="noopener noreferrer">' + ENLACE_SVG + textoEnlace + "</a>";
    } else {
      enlaceHtml = '<span class="tarjeta__enlace" style="color:#999">Enlace no publicado</span>';
    }

    var codigoHtml = "";
    if (!esDirecto && t.codigo_expediente) {
      codigoHtml =
        '<p class="tarjeta__aviso-codigo">Este portal no permite enlazar directamente al anuncio — ' +
        "pega este código en \"Código del expediente\" del buscador: " +
        '<code class="tarjeta__codigo">' + escaparHtml(t.codigo_expediente) + "</code></p>";
    }

    return (
      '<details class="tarjeta ' + urgencia.clase + claseRevisar + claseGrande + '"' + abierta + '>' +
        '<summary class="tarjeta__resumen-fila">' +
          CHEVRON_SVG +
          '<div class="tarjeta__info">' +
            '<div class="tarjeta__titulo-compacto">' + escaparHtml(t.titulo) + "</div>" +
            '<div class="tarjeta__meta-compacta">' +
              '<span class="badge-fuente">' + escaparHtml(t.fuente) + "</span>" +
              "<span>" + escaparHtml(t.organismo) + "</span>" +
              "<span>·</span>" +
              "<span>" + escaparHtml(t.pais_territorio) + "</span>" +
            "</div>" +
          "</div>" +
          '<div class="tarjeta__lado-derecho">' +
            '<span class="badge-presupuesto">' + escaparHtml(t.presupuesto_display === NO_PUBLICADO ? "—" : t.presupuesto_display) + "</span>" +
            '<span class="badge-urgencia">' + escaparHtml(urgencia.texto) + "</span>" +
          "</div>" +
        "</summary>" +
        '<div class="tarjeta__detalle">' +
          '<div class="tarjeta__meta">' +
            "<span><strong>Organismo:</strong> " + escaparHtml(t.organismo) + "</span>" +
            "<span><strong>Territorio:</strong> " + escaparHtml(t.pais_territorio) + "</span>" +
            '<span><strong>Fecha límite:</strong> <span class="valor-dato">' + escaparHtml(t.fecha_limite) + "</span></span>" +
            '<span><strong>Publicada:</strong> <span class="valor-dato">' + escaparHtml(t.fecha_publicacion) + "</span></span>" +
            (t.programa ? "<span><strong>Programa:</strong> " + escaparHtml(t.programa) + "</span>" : "") +
            "<span><strong>Tipo de contrato:</strong> " + escaparHtml(t.tipo_contrato === NO_PUBLICADO ? "no publicado" : t.tipo_contrato) + "</span>" +
          "</div>" +
          '<p class="tarjeta__resumen-texto">' + escaparHtml(t.resumen) + "</p>" +
          '<div class="tarjeta__categorias">' + categoriasHtml + revisarHtml + "</div>" +
          codigoHtml +
          enlaceHtml +
        "</div>" +
      "</details>"
    );
  }

  function plantillaTarjetaAdjudicacion(t) {
    var claseRevisar = t.revisar_manual ? " revisar-manual" : "";

    var categoriasHtml = (t.categorias || [])
      .map(function (c) { return '<span class="etiqueta-categoria">' + escaparHtml(c) + "</span>"; })
      .join("");
    var revisarHtml = t.revisar_manual
      ? '<span class="etiqueta-revisar">⚠ Revisar: mezcla con otros servicios no propios de agencia</span>'
      : "";

    var esDirecto = t.enlace_directo !== false;
    var enlaceHtml;
    if (t.enlace && t.enlace !== NO_PUBLICADO) {
      var textoEnlace = esDirecto ? "Ver anuncio original" : "Buscar en el portal de Euskadi";
      enlaceHtml = '<a class="tarjeta__enlace" href="' + escaparHtml(t.enlace) + '" target="_blank" rel="noopener noreferrer">' + ENLACE_SVG + textoEnlace + "</a>";
    } else {
      enlaceHtml = '<span class="tarjeta__enlace" style="color:#999">Enlace no publicado</span>';
    }

    var empresa = t.empresa_adjudicataria === NO_PUBLICADO ? "Empresa no publicada" : t.empresa_adjudicataria;
    var importe = t.importe_adjudicado_display === NO_PUBLICADO ? "—" : t.importe_adjudicado_display;

    return (
      '<details class="tarjeta urgencia-sin-fecha tarjeta--adjudicacion' + claseRevisar + '">' +
        '<summary class="tarjeta__resumen-fila">' +
          CHEVRON_SVG +
          '<div class="tarjeta__info">' +
            '<div class="tarjeta__titulo-compacto">' + escaparHtml(t.titulo) + "</div>" +
            '<div class="tarjeta__meta-compacta">' +
              '<span class="badge-fuente">' + escaparHtml(t.fuente) + "</span>" +
              "<span>" + escaparHtml(t.organismo) + "</span>" +
              "<span>·</span>" +
              "<span>" + escaparHtml(t.pais_territorio) + "</span>" +
            "</div>" +
          "</div>" +
          '<div class="tarjeta__lado-derecho">' +
            '<span class="badge-empresa">' + escaparHtml(empresa) + "</span>" +
            '<span class="badge-presupuesto">' + escaparHtml(importe) + "</span>" +
          "</div>" +
        "</summary>" +
        '<div class="tarjeta__detalle">' +
          '<div class="tarjeta__meta">' +
            "<span><strong>Organismo:</strong> " + escaparHtml(t.organismo) + "</span>" +
            "<span><strong>Territorio:</strong> " + escaparHtml(t.pais_territorio) + "</span>" +
            "<span><strong>Empresa adjudicataria:</strong> " + escaparHtml(empresa) + "</span>" +
            '<span><strong>Fecha de adjudicación:</strong> <span class="valor-dato">' + escaparHtml(t.fecha_adjudicacion) + "</span></span>" +
            '<span><strong>Vigente hasta:</strong> <span class="valor-dato">' + escaparHtml(t.fecha_fin_estimada === NO_PUBLICADO ? "no publicado" : t.fecha_fin_estimada) + "</span></span>" +
            "<span><strong>Tipo de contrato:</strong> " + escaparHtml(t.tipo_contrato === NO_PUBLICADO ? "no publicado" : t.tipo_contrato) + "</span>" +
          "</div>" +
          '<div class="tarjeta__categorias">' + categoriasHtml + revisarHtml + "</div>" +
          enlaceHtml +
        "</div>" +
      "</details>"
    );
  }

  function plantillaTarjetaContratoMenor(t) {
    var vencimiento = infoVencimiento(t.fecha_fin_estimada);
    var claseRevisar = t.revisar_manual ? " revisar-manual" : "";

    var categoriasHtml = (t.categorias || [])
      .map(function (c) { return '<span class="etiqueta-categoria">' + escaparHtml(c) + "</span>"; })
      .join("");
    var revisarHtml = t.revisar_manual
      ? '<span class="etiqueta-revisar">⚠ Revisar: mezcla con otros servicios no propios de agencia</span>'
      : "";

    var esDirecto = t.enlace_directo !== false;
    var enlaceHtml;
    if (t.enlace && t.enlace !== NO_PUBLICADO) {
      var textoEnlace = esDirecto ? "Ver anuncio original" : "Buscar en el portal de Euskadi";
      enlaceHtml = '<a class="tarjeta__enlace" href="' + escaparHtml(t.enlace) + '" target="_blank" rel="noopener noreferrer">' + ENLACE_SVG + textoEnlace + "</a>";
    } else {
      enlaceHtml = '<span class="tarjeta__enlace" style="color:#999">Enlace no publicado</span>';
    }

    var empresa = t.empresa_adjudicataria === NO_PUBLICADO ? "Empresa no publicada" : t.empresa_adjudicataria;

    return (
      '<details class="tarjeta ' + vencimiento.clase + claseRevisar + '">' +
        '<summary class="tarjeta__resumen-fila">' +
          CHEVRON_SVG +
          '<div class="tarjeta__info">' +
            '<div class="tarjeta__titulo-compacto">' + escaparHtml(t.titulo) + "</div>" +
            '<div class="tarjeta__meta-compacta">' +
              '<span class="badge-fuente">' + escaparHtml(t.fuente) + "</span>" +
              "<span>" + escaparHtml(t.organismo) + "</span>" +
              "<span>·</span>" +
              "<span>" + escaparHtml(t.pais_territorio) + "</span>" +
            "</div>" +
          "</div>" +
          '<div class="tarjeta__lado-derecho">' +
            '<span class="badge-empresa">' + escaparHtml(empresa) + "</span>" +
            '<span class="badge-urgencia">' + escaparHtml(vencimiento.texto) + "</span>" +
          "</div>" +
        "</summary>" +
        '<div class="tarjeta__detalle">' +
          '<div class="tarjeta__meta">' +
            "<span><strong>Organismo:</strong> " + escaparHtml(t.organismo) + "</span>" +
            "<span><strong>Territorio:</strong> " + escaparHtml(t.pais_territorio) + "</span>" +
            "<span><strong>Empresa que lo tiene hoy:</strong> " + escaparHtml(empresa) + "</span>" +
            '<span><strong>Adjudicado el:</strong> <span class="valor-dato">' + escaparHtml(t.fecha_adjudicacion) + "</span></span>" +
            '<span><strong>Vence el (estimado):</strong> <span class="valor-dato">' + escaparHtml(t.fecha_fin_estimada === NO_PUBLICADO ? "no publicado" : t.fecha_fin_estimada) + "</span></span>" +
            "<span><strong>Tipo de contrato:</strong> " + escaparHtml(t.tipo_contrato === NO_PUBLICADO ? "no publicado" : t.tipo_contrato) + "</span>" +
          "</div>" +
          '<div class="tarjeta__categorias">' + categoriasHtml + revisarHtml + "</div>" +
          enlaceHtml +
        "</div>" +
      "</details>"
    );
  }

  function plantillaTarjeta(t, grande) {
    if (t.tipo_registro === "adjudicacion") return plantillaTarjetaAdjudicacion(t);
    if (t.tipo_registro === "contrato_menor_venciendo") return plantillaTarjetaContratoMenor(t);
    return plantillaTarjetaLicitacion(t, grande);
  }

  function aplicarFiltros() {
    var subconjunto = subconjuntoActivo();
    var filtrados = subconjunto.filter(pasaFiltros);
    filtrados.sort(comparar);

    // "Publicadas recientemente" tendrá pocas tarjetas casi siempre (es una
    // ventana de 1-2 días), así que se muestran más grandes y ya
    // desplegadas: no compensa el gesto de "colapsar para ver más" cuando
    // hay 3-4 elementos en vez de cientos.
    var grande = estado.tipoRegistro === "recientes";

    var ETIQUETAS_CONTEO = { adjudicacion: "adjudicaciones", contrato_menor_venciendo: "contratos menores", convocatoria_ue: "calls for proposals", recientes: "publicadas recientemente" };
    var etiqueta = ETIQUETAS_CONTEO[estado.tipoRegistro] || "licitaciones";
    elConteo.textContent = filtrados.length + " de " + subconjunto.length + " " + etiqueta;
    elContenedor.innerHTML = filtrados.map(function (t) { return plantillaTarjeta(t, grande); }).join("");
    elSinResultados.hidden = filtrados.length > 0;
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

    var ETIQUETAS_TOTAL = { convocatoria_ue: "calls for proposals", recientes: "publicadas recientemente" };
    var etiquetaTotal = ETIQUETAS_TOTAL[estado.tipoRegistro] || "licitaciones";
    elResumenCabecera.innerHTML =
      '<div><strong>' + subconjunto.length + '</strong>' + etiquetaTotal + '</div>' +
      '<div><strong>' + totalAbiertas + '</strong>en plazo</div>' +
      '<div><strong>' + totalRevisar + '</strong>a revisar</div>';
  }

  function inicializar() {
    if (DATOS.length === 0) {
      elConteo.textContent = "No hay datos cargados todavía.";
      elSinResultados.hidden = false;
      elSinResultados.textContent =
        "dashboard/tenders-data.js está vacío o no existe. Ejecuta los scrapers, clasificar.py y normalizar.py (ver README.md).";
      return;
    }

    construirSegmentedTipo();
    actualizarVisibilidadPresupuesto();
    construirControles();
    pintarResumenCabecera();

    elTexto.addEventListener("input", function () {
      estado.texto = elTexto.value.trim().toLowerCase();
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
    elReset.addEventListener("click", function () {
      estado.texto = "";
      estado.fuente = "";
      estado.categoria = "";
      estado.pais = "";
      estado.soloRevisarManual = false;
      estado.presupuestoMin = 0;
      estado.presupuestoMax = null;
      estado.orden = "plazo";
      elTexto.value = "";
      elCategoria.value = "";
      elPais.value = "";
      elPresupuestoMin.value = "0";
      elPresupuestoMax.value = "";
      elOrden.value = "plazo";
      elBotonRevisar.classList.remove("activo");
      Array.prototype.forEach.call(elSegmentedFuente.children, function (b, i) {
        b.setAttribute("aria-pressed", i === 0 ? "true" : "false");
      });
      aplicarFiltros();
    });

    aplicarFiltros();
  }

  elFechaGeneracion.textContent = "Vista generada: " + new Date().toLocaleString("es-ES");

  inicializar();
})();
