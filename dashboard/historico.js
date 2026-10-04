(function () {
  "use strict";

  // Formato compacto generado por scrapers/historico_adjudicaciones.py
  // (_publicar): diccionarios + filas por columnas.
  //   exp:   [organismo, euskadi, tipo, procedimiento, menor, mascara_categorias, lugar]
  //   lotes: [exp, empresa, fecha, importe, ofertas, pyme]
  //   dic.lugar:   [provincia, comunidad] (null si la fuente no lo publica)
  //   dic.empresa: [nif, nombre] o, si la ficha se fusionó con otra por ser
  //                la misma empresa, [null, nombre, id de la ficha buena]
  // El título y el enlace de cada expediente no vienen aquí (son el 75% del
  // peso): están en historico-detalle/NN.js, repartidos por empresa, y se
  // cargan al abrir la ficha de una empresa.
  var Nav = window.RadarNav;
  var H = window.HISTORICO;
  if (!H || !H.exp || !H.exp.length) {
    document.getElementById("herramientas").hidden = true;
    document.getElementById("sin-datos").hidden = false;
    Nav.activar("mercado");
    return;
  }

  var D = H.dic;
  var CATEGORIAS = H.categorias;
  var TOP_EMPRESAS = 20;
  var UMBRAL_GRANDE = 1000000;
  var TOP_ORGANISMOS = 12;
  var TOP_FICHA = 10;
  var MAX_CONTRATOS_FICHA = 150;
  var FILAS_POR_PAGINA = 50;
  var MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

  // Vistas de esta página, por primer segmento de la ruta de hash.
  var VISTAS = {
    mercado: {
      nav: "mercado",
      titulo: "Análisis de mercado",
      descripcion: "Adjudicaciones de organismos públicos españoles (Estado y Euskadi) desde 2021 ganadas por empresas españolas (incluidas las vascas), incluidos contratos menores, filtradas por categoría de servicio de agencia. Fuentes: PLACSP (perfiles propios y plataformas autonómicas agregadas), el portal de contratación de Euskadi para los contratos menores de organismos vascos y TED para lo que solo se publica allí. Importes sin IVA; en los acuerdos marco con varias empresas adjudicatarias, el importe se reparte a partes iguales entre ellas. Cada lote adjudicado cuenta como una adjudicación. El filtro de importe se aplica al importe de cada adjudicación y deja fuera las que no lo publican. Se actualiza cada día.",
      buscar: "Buscar empresa, NIF u organismo…",
    },
    empresas: {
      nav: "empresas",
      titulo: "Empresas",
      descripcion: "Todas las empresas españolas que han ganado contratos de servicios de agencia a organismos públicos españoles desde 2021. Los filtros (ámbito, tipo de adjudicación, año, categoría, provincia e importe) recalculan las cifras de cada empresa. Pulsa una empresa para ver su ficha.",
      buscar: "Buscar empresa o NIF…",
    },
    organismos: {
      nav: "organismos",
      titulo: "Organismos",
      descripcion: "Todos los organismos públicos españoles que han adjudicado contratos de servicios de agencia desde 2021. Los filtros (ámbito, tipo de adjudicación, año, categoría, provincia e importe) recalculan las cifras de cada organismo. Pulsa un organismo para ver qué empresas ganan en él.",
      buscar: "Buscar organismo…",
    },
    empresa: { nav: "empresas" },
    organismo: { nav: "organismos" },
  };

  // Con punto de millar siempre: Intl en "es-ES" no agrupa los números de
  // cuatro cifras ("6014 organismos", "6471,3 M€").
  function miles(n, decimales) {
    var partes = n.toFixed(decimales || 0).split(".");
    partes[0] = partes[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return partes.join(",").replace(/,0+$/, "");
  }

  function euros(v) {
    if (!v) return "—";
    if (v >= 1e6) return miles(v / 1e6, 1) + " M€";
    if (v >= 1e4) return miles(v / 1e3) + " k€";
    return miles(v) + " €";
  }

  function fechaLarga(str) {
    var p = (str || "").split("-");
    if (p.length !== 3) return "—";
    return Number(p[2]) + " " + MESES[Number(p[1]) - 1] + " " + p[0];
  }

  // NIF que se puede enseñar: el de una sociedad. El de una persona física
  // está enmascarado ("***4567**", "XXXXX155F") y no se enseña (ver nif.py).
  function nifPublicable(nif) {
    return nif && nif.indexOf("*") === -1 && nif.indexOf("XXX") !== 0 ? nif : null;
  }

  // Texto de las fuentes dentro de HTML, también dentro de atributos
  // (title, href): por eso se escapan las comillas, no solo < > &.
  var ENTIDADES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  function escaparHtml(str) {
    return (str == null ? "" : String(str)).replace(/[&<>"']/g, function (c) { return ENTIDADES[c]; });
  }

  function enlaceCompleto(enlace) {
    if (!enlace) return null;
    return enlace.indexOf("http") === 0 ? enlace : H.prefijo_enlace + enlace;
  }

  // Fragmento de detalle (títulos y enlaces) de una empresa: se descarga una
  // sola vez, la primera vez que se abre una ficha de ese fragmento.
  var cargasDetalle = {};
  function cargarDetalle(idEmpresa) {
    var n = idEmpresa % H.fragmentos;
    if (!cargasDetalle[n]) {
      cargasDetalle[n] = new Promise(function (resolver, rechazar) {
        var s = document.createElement("script");
        s.src = "historico-detalle/" + (n < 10 ? "0" : "") + n + ".js?v=" + encodeURIComponent(H.actualizado);
        s.onload = function () { resolver(window.HISTORICO_DETALLE[n]); };
        s.onerror = function () { delete cargasDetalle[n]; rechazar(new Error("sin detalle")); };
        document.head.appendChild(s);
      });
    }
    return cargasDetalle[n];
  }

  // Una fila por lote con lo necesario para filtrar y agregar, calculada
  // una sola vez (son decenas de miles; se recorren en cada cambio de filtro).
  // Lugar de cada expediente (provincia y comunidad), con el mismo criterio
  // que el radar: lugar de ejecución del contrato y, si no, sede del
  // organismo. Los expedientes procesados antes de octubre de 2026 no lo
  // traen hasta que se vuelve a leer su fichero.
  var LUGARES = D.lugar || [];
  var SIN_LUGAR = [null, null];
  var FILAS = H.lotes.map(function (l) {
    var e = H.exp[l[0]];
    var lugar = LUGARES[e[6]] || SIN_LUGAR;
    return {
      exp: l[0], empresa: l[1], anio: l[2] ? l[2].slice(0, 4) : "", fecha: l[2] || "",
      importe: l[3] || 0, ofertas: l[4], pyme: l[5],
      organismo: e[0], euskadi: e[1] === 1, procedimiento: e[3], menor: e[4] === 1, mascara: e[5],
      provincia: lugar[0], comunidad: lugar[1],
    };
  });
  // Texto en minúsculas, sin tildes ni puntuación, y con las siglas juntas:
  // "uniprex sau" encuentra "UNIPREX, S.A.U." (cada fuente escribe la forma
  // jurídica a su manera).
  function normalizar(str) {
    return String(str || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9ñ*]+/g, " ").replace(/\b([a-z]) (?=[a-z]\b)/g, "$1").trim();
  }
  // Texto buscable por empresa (nombre + NIF) y organismo.
  var NOMBRE_EMPRESA = D.empresa.map(function (x) { return normalizar(x[1]); });
  var TEXTO_EMPRESA = D.empresa.map(function (x, i) { return NOMBRE_EMPRESA[i] + " " + normalizar(x[0]); });
  var TEXTO_ORGANISMO = D.organismo.map(normalizar);

  var estado = {
    texto: "", ambito: "", menor: "", anio: "", categoria: -1,
    // "" | "c:<comunidad>" | "p:<provincia>" | "sin" (como en el radar)
    lugar: "",
    // Importe de cada adjudicación, en euros; 0 = sin límite.
    importeMin: 0, importeMax: 0,
    metricaEvolucion: "importe", metricaEmpresas: "importe",
    vista: "mercado", id: null,
    ordenDirectorio: "importe", pagina: 0,
  };

  var elCabecera = document.getElementById("cabecera-vista");
  var elContenido = document.getElementById("contenido");
  var elTexto = document.getElementById("filtro-texto");
  var elCampoTexto = document.getElementById("campo-texto");
  var elVistas = {
    mercado: document.getElementById("vista-mercado"),
    directorio: document.getElementById("vista-directorio"),
    ficha: document.getElementById("vista-ficha"),
  };

  // ---------- Controles ----------

  function segmented(id, opciones, clave) {
    var el = document.getElementById(id);
    opciones.forEach(function (par) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "segmented__opcion";
      b.textContent = par[1];
      b.setAttribute("aria-pressed", estado[clave] === par[0] ? "true" : "false");
      b.addEventListener("click", function () {
        estado[clave] = par[0];
        estado.pagina = 0;
        Array.prototype.forEach.call(el.children, function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
        pintar();
      });
      el.appendChild(b);
    });
  }

  segmented("segmented-ambito", [["", "Todos"], ["Estado", "Estado"], ["Euskadi", "Euskadi"]], "ambito");
  segmented("segmented-menor", [["", "Todo"], ["licitacion", "Licitaciones"], ["menor", "Contratos menores"]], "menor");
  segmented("metrica-evolucion", [["importe", "Importe"], ["numero", "Nº"]], "metricaEvolucion");
  segmented("metrica-empresas", [["importe", "Importe"], ["numero", "Nº"]], "metricaEmpresas");

  var elAnio = document.getElementById("filtro-anio");
  var anios = {};
  FILAS.forEach(function (f) { if (f.anio >= "2021") anios[f.anio] = true; });
  elAnio.innerHTML = '<option value="">Todos los años</option>' + Object.keys(anios).sort().reverse()
    .map(function (a) { return '<option value="' + a + '">' + a + "</option>"; }).join("");
  elAnio.addEventListener("change", function () { estado.anio = elAnio.value; estado.pagina = 0; pintar(); });

  var elCategoria = document.getElementById("filtro-categoria");
  elCategoria.innerHTML = '<option value="-1">Todas las categorías</option>' + CATEGORIAS
    .map(function (c, i) { return '<option value="' + i + '">' + escaparHtml(c) + "</option>"; }).join("");
  elCategoria.addEventListener("change", function () { estado.categoria = parseInt(elCategoria.value, 10); estado.pagina = 0; pintar(); });

  // Provincia: comunidades con adjudicaciones y, dentro, sus provincias; una
  // comunidad de una sola provincia es una opción suelta (igual que en el
  // radar). El desplegable no se enseña mientras menos de la mitad de las
  // adjudicaciones tengan lugar: filtraría sobre una parte pequeña de los
  // datos sin que se notara.
  var elLugar = document.getElementById("filtro-lugar");
  (function () {
    var comunidades = {};
    var conLugar = 0;
    FILAS.forEach(function (f) {
      if (!f.comunidad) return;
      conLugar++;
      var com = comunidades[f.comunidad] || (comunidades[f.comunidad] = {});
      if (f.provincia) com[f.provincia] = true;
    });
    if (conLugar < FILAS.length / 2) { elLugar.hidden = true; return; }
    var opcion = function (valor, texto) { return '<option value="' + escaparHtml(valor) + '">' + escaparHtml(texto) + "</option>"; };
    var html = opcion("", "Todas las provincias");
    Object.keys(comunidades).sort(function (a, b) { return a.localeCompare(b, "es"); }).forEach(function (nombre) {
      var provincias = Object.keys(comunidades[nombre]).sort(function (a, b) { return a.localeCompare(b, "es"); });
      if (provincias.length === 0 || (provincias.length === 1 && provincias[0] === nombre)) {
        html += opcion("c:" + nombre, nombre);
        return;
      }
      html += '<optgroup label="' + escaparHtml(nombre) + '">' + opcion("c:" + nombre, nombre + ": todas") +
        provincias.map(function (p) { return opcion("p:" + p, p); }).join("") + "</optgroup>";
    });
    if (conLugar < FILAS.length) html += opcion("sin", "Sin provincia publicada");
    elLugar.innerHTML = html;
    elLugar.addEventListener("change", function () { estado.lugar = elLugar.value; estado.pagina = 0; pintar(); });
  })();

  // Importe de cada adjudicación. Los tramos van de lo que cabe en un
  // contrato menor de servicios (15.000 €) a los contratos de varios
  // millones, que casi nunca son de agencia (ver README).
  var TRAMOS_IMPORTE = [5000, 15000, 50000, 100000, 500000, 1000000, 5000000];
  var elImporteMin = document.getElementById("filtro-importe-min");
  var elImporteMax = document.getElementById("filtro-importe-max");
  elImporteMin.innerHTML = '<option value="0">Importe mínimo</option>' + TRAMOS_IMPORTE
    .map(function (v) { return '<option value="' + v + '">Desde ' + euros(v) + "</option>"; }).join("");
  elImporteMax.innerHTML = '<option value="0">Importe máximo</option>' + TRAMOS_IMPORTE
    .map(function (v) { return '<option value="' + v + '">Hasta ' + euros(v) + "</option>"; }).join("");
  elImporteMin.addEventListener("change", function () { estado.importeMin = Number(elImporteMin.value); estado.pagina = 0; pintar(); });
  elImporteMax.addEventListener("change", function () { estado.importeMax = Number(elImporteMax.value); estado.pagina = 0; pintar(); });
  document.getElementById("boton-sin-grandes").addEventListener("click", function () {
    estado.importeMax = UMBRAL_GRANDE;
    elImporteMax.value = String(UMBRAL_GRANDE);
    estado.pagina = 0;
    pintar();
  });

  var temporizador;
  elTexto.addEventListener("input", function () {
    clearTimeout(temporizador);
    temporizador = setTimeout(function () { estado.texto = normalizar(elTexto.value); estado.pagina = 0; pintar(); }, 180);
  });

  // Filtros de ámbito, tipo, año, categoría, provincia e importe (sin el texto).
  function pasaFiltros(f) {
    if (estado.anio && f.anio !== estado.anio) return false;
    if (!estado.anio && f.anio < "2021") return false;
    if (estado.ambito && (estado.ambito === "Euskadi") !== f.euskadi) return false;
    if (estado.menor && (estado.menor === "menor") !== f.menor) return false;
    if (estado.categoria >= 0 && !(f.mascara & (1 << estado.categoria))) return false;
    if (estado.lugar) {
      if (estado.lugar === "sin") {
        if (f.comunidad) return false;
      } else if (estado.lugar.charAt(0) === "c") {
        if (f.comunidad !== estado.lugar.slice(2)) return false;
      } else if (f.provincia !== estado.lugar.slice(2)) {
        return false;
      }
    }
    if (estado.importeMin || estado.importeMax) {
      // Sin importe publicado no se puede saber si entra en el rango: fuera.
      if (!f.importe) return false;
      if (estado.importeMin && f.importe < estado.importeMin) return false;
      if (estado.importeMax && f.importe > estado.importeMax) return false;
    }
    return true;
  }

  // En el análisis de mercado el texto busca a la vez en empresa y organismo.
  function pasaTexto(f) {
    return !estado.texto || TEXTO_EMPRESA[f.empresa].indexOf(estado.texto) !== -1 ||
      TEXTO_ORGANISMO[f.organismo].indexOf(estado.texto) !== -1;
  }

  // ---------- Agregación ----------

  function agrupar(filas, clave) {
    var g = {};
    filas.forEach(function (f) {
      var k = clave(f);
      if (k == null) return;
      var x = g[k] || (g[k] = { clave: k, numero: 0, importe: 0 });
      x.numero++;
      x.importe += f.importe;
    });
    return Object.keys(g).map(function (k) { return g[k]; });
  }

  function ordenar(lista, metrica) {
    return lista.sort(function (a, b) { return b[metrica] - a[metrica] || b.numero - a.numero; });
  }

  function porCategoria(filas) {
    var g = CATEGORIAS.map(function (c, i) { return { clave: i, numero: 0, importe: 0 }; });
    filas.forEach(function (f) {
      for (var i = 0; i < CATEGORIAS.length; i++) {
        if (f.mascara & (1 << i)) { g[i].numero++; g[i].importe += f.importe; }
      }
    });
    return ordenar(g.filter(function (x) { return x.numero; }), "numero");
  }

  function porProcedimiento(filas) {
    return ordenar(agrupar(filas, function (f) { return f.menor ? "menor" : f.procedimiento; }), "numero");
  }

  function nombreProcedimiento(x) {
    return x.clave === "menor" ? "Contrato menor" : D.procedimiento[x.clave];
  }

  // ---------- Pintado ----------

  // Barras horizontales. Con `enlace`, cada fila es un enlace a una ficha.
  function barras(el, lista, metrica, etiqueta, enlace) {
    var max = lista.reduce(function (m, x) { return Math.max(m, x[metrica]); }, 0) || 1;
    if (!lista.length) {
      el.innerHTML = '<li class="barras__vacio">Sin datos con estos filtros.</li>';
      return;
    }
    el.innerHTML = lista.map(function (x) {
      var detalle = metrica === "importe"
        ? euros(x.importe) + ' <span class="barras__sec">· ' + miles(x.numero) + "</span>"
        : miles(x.numero) + ' <span class="barras__sec">· ' + euros(x.importe) + "</span>";
      var nombre = escaparHtml(etiqueta(x));
      var contenido =
        '<span class="barras__nombre" title="' + nombre + '">' + nombre + "</span>" +
        '<span class="barras__pista"><span class="barras__relleno" style="width:' + (100 * x[metrica] / max).toFixed(1) + '%"></span></span>' +
        '<span class="barras__valor">' + detalle + "</span>";
      return '<li class="barras__fila">' +
        (enlace ? '<a class="barras__boton" href="' + enlace(x) + '">' + contenido + "</a>" : contenido) + "</li>";
    }).join("");
  }

  function pintarKpis(el, items) {
    el.innerHTML = items.map(function (k) {
      return '<div class="kpi"><span class="kpi__etiqueta">' + k[0] + '</span><span class="kpi__valor">' + k[1] + "</span>" +
        (k[2] ? '<span class="kpi__nota">' + k[2] + "</span>" : "") + "</div>";
    }).join("");
  }

  function resumen(filas) {
    var r = { importe: 0, conImporte: 0, empresas: {}, organismos: {}, ofertas: 0, conOfertas: 0, pymes: 0, conPyme: 0, menores: 0, anios: [] };
    var anios = {};
    filas.forEach(function (f) {
      if (f.importe) { r.importe += f.importe; r.conImporte++; }
      r.empresas[f.empresa] = true;
      r.organismos[f.organismo] = true;
      if (f.ofertas) { r.ofertas += f.ofertas; r.conOfertas++; }
      if (f.pyme != null) { r.conPyme++; r.pymes += f.pyme; }
      if (f.menor) r.menores++;
      if (f.anio) anios[f.anio] = true;
    });
    r.anios = Object.keys(anios).sort();
    r.numEmpresas = Object.keys(r.empresas).length;
    r.numOrganismos = Object.keys(r.organismos).length;
    r.importeMedio = r.conImporte ? euros(r.importe / r.conImporte) : "—";
    r.ofertasMedia = r.conOfertas ? (r.ofertas / r.conOfertas).toLocaleString("es-ES", { maximumFractionDigits: 1 }) : "—";
    r.periodo = r.anios.length ? (r.anios.length > 1 ? r.anios[0] + "–" + r.anios[r.anios.length - 1] : r.anios[0]) : "—";
    return r;
  }

  function evolucion(filas) {
    var lista = agrupar(filas, function (f) { return f.anio >= "2021" ? f.anio : null; })
      .sort(function (a, b) { return a.clave < b.clave ? -1 : 1; });
    var m = estado.metricaEvolucion;
    var max = lista.reduce(function (acc, x) { return Math.max(acc, x[m]); }, 0) || 1;
    document.getElementById("grafico-evolucion").innerHTML = lista.map(function (x) {
      var valor = m === "importe" ? euros(x.importe) : miles(x.numero);
      return '<div class="columnas__col"><span class="columnas__valor">' + valor + "</span>" +
        '<span class="columnas__pista"><span class="columnas__relleno" style="height:' + (100 * x[m] / max).toFixed(1) + '%"></span></span>' +
        '<span class="columnas__etiqueta">' + x.clave + "</span></div>";
    }).join("") || '<p class="barras__vacio">Sin datos con estos filtros.</p>';
  }

  function pintarMercado() {
    var filas = FILAS.filter(function (f) { return pasaFiltros(f) && pasaTexto(f); });
    var r = resumen(filas);
    pintarKpis(document.getElementById("kpis"), [
      ["Adjudicaciones", miles(filas.length)],
      ["Importe adjudicado", euros(r.importe)],
      ["Empresas distintas", miles(r.numEmpresas)],
      ["Organismos", miles(r.numOrganismos)],
      ["Importe medio", r.importeMedio],
      ["Ofertas por licitación", r.ofertasMedia],
      ["Ganadas por pymes", r.conPyme ? Math.round(100 * r.pymes / r.conPyme) + " %" : "—"],
      ["Contratos menores", filas.length ? Math.round(100 * r.menores / filas.length) + " %" : "—"],
    ]);
    evolucion(filas);

    var m = estado.metricaEmpresas;
    var todas = ordenar(agrupar(filas, function (f) { return f.empresa; }), m);
    var total = todas.reduce(function (s, x) { return s + x[m]; }, 0);
    var top10 = todas.slice(0, 10).reduce(function (s, x) { return s + x[m]; }, 0);
    document.getElementById("nota-concentracion").textContent = total
      ? "Las 10 primeras se llevan el " + Math.round(100 * top10 / total) + " % del " +
        (m === "importe" ? "importe adjudicado" : "número de adjudicaciones") + " (" + miles(todas.length) + " empresas en total)."
      : "";
    // Cuánto pesan las adjudicaciones de más de 1 M€ en lo que se está
    // viendo: unas pocas suman buena parte del importe y deciden el orden
    // por importe. El botón las deja fuera con el filtro de importe máximo.
    var grandes = filas.filter(function (f) { return f.importe > UMBRAL_GRANDE; });
    var elGrandes = document.getElementById("nota-grandes");
    elGrandes.hidden = !grandes.length || !r.importe || estado.importeMin >= UMBRAL_GRANDE;
    if (!elGrandes.hidden) {
      var importeGrandes = grandes.reduce(function (s, f) { return s + f.importe; }, 0);
      document.getElementById("nota-grandes-texto").textContent =
        (grandes.length === 1 ? "1 adjudicación de más de " + euros(UMBRAL_GRANDE) + " suma" : miles(grandes.length) + " adjudicaciones de más de " + euros(UMBRAL_GRANDE) + " suman") +
        " el " + Math.round(100 * importeGrandes / r.importe) + " % del importe adjudicado (" + euros(importeGrandes) + ").";
    }
    barras(document.getElementById("grafico-empresas"), todas.slice(0, TOP_EMPRESAS), m,
      function (x) { return D.empresa[x.clave][1]; }, function (x) { return "#/empresa/" + x.clave; });

    barras(document.getElementById("grafico-categorias"), porCategoria(filas), "numero",
      function (x) { return CATEGORIAS[x.clave]; });
    barras(document.getElementById("grafico-organismos"),
      ordenar(agrupar(filas, function (f) { return f.organismo; }), "numero").slice(0, TOP_ORGANISMOS), "numero",
      function (x) { return D.organismo[x.clave]; }, function (x) { return "#/organismo/" + x.clave; });
    barras(document.getElementById("grafico-procedimientos"), porProcedimiento(filas), "numero", nombreProcedimiento);
    var tramos = [[1, 1, "1 oferta"], [2, 2, "2 ofertas"], [3, 5, "3 a 5"], [6, 10, "6 a 10"], [11, 1e9, "Más de 10"]];
    barras(document.getElementById("grafico-ofertas"),
      tramos.map(function (t, i) {
        var x = { clave: i, numero: 0, importe: 0 };
        filas.forEach(function (f) { if (f.ofertas >= t[0] && f.ofertas <= t[1]) { x.numero++; x.importe += f.importe; } });
        return x;
      }).filter(function (x) { return x.numero; }), "numero",
      function (x) { return tramos[x.clave][2]; });
  }

  // ---------- Directorios ----------

  // Columnas ordenables del directorio: [clave, etiqueta, secundaria].
  var COLUMNAS_DIRECTORIO = [
    ["numero", "Adjudicaciones", false],
    ["importe", "Importe", false],
    ["medio", "Importe medio", true],
    ["otros", "", true],  // la etiqueta depende del directorio
    ["ultima", "Última", true],
  ];

  function pintarDirectorio() {
    var deEmpresas = estado.vista === "empresas";
    var campo = deEmpresas ? "empresa" : "organismo";
    var campoOtro = deEmpresas ? "organismo" : "empresa";
    var textos = deEmpresas ? TEXTO_EMPRESA : TEXTO_ORGANISMO;

    var grupos = {};
    FILAS.forEach(function (f) {
      if (!pasaFiltros(f)) return;
      var k = f[campo];
      if (estado.texto && textos[k].indexOf(estado.texto) === -1) return;
      var g = grupos[k] || (grupos[k] = { clave: k, numero: 0, importe: 0, conImporte: 0, vistos: {}, otros: 0, ultima: "" });
      g.numero++;
      if (f.importe) { g.importe += f.importe; g.conImporte++; }
      if (!g.vistos[f[campoOtro]]) { g.vistos[f[campoOtro]] = true; g.otros++; }
      if (f.fecha > g.ultima) g.ultima = f.fecha;
    });
    var lista = Object.keys(grupos).map(function (k) {
      var g = grupos[k];
      g.medio = g.conImporte ? g.importe / g.conImporte : 0;
      return g;
    });
    var col = estado.ordenDirectorio;
    lista.sort(function (a, b) {
      if (col === "ultima") return a.ultima < b.ultima ? 1 : (a.ultima > b.ultima ? -1 : b.importe - a.importe);
      return b[col] - a[col] || b.importe - a.importe || b.numero - a.numero;
    });

    var total = lista.length;
    var paginas = Math.max(1, Math.ceil(total / FILAS_POR_PAGINA));
    if (estado.pagina >= paginas) estado.pagina = paginas - 1;
    var desde = estado.pagina * FILAS_POR_PAGINA;
    var visibles = lista.slice(desde, desde + FILAS_POR_PAGINA);

    document.getElementById("directorio-conteo").textContent = total
      ? miles(desde + 1) + "–" + miles(desde + visibles.length) + " de " + miles(total) + (deEmpresas ? " empresas" : " organismos")
      : "";
    document.getElementById("directorio-vacio").hidden = total > 0;
    document.querySelector("#vista-directorio .tabla-envoltorio").hidden = total === 0;

    var elPag = document.getElementById("directorio-paginacion");
    elPag.hidden = paginas < 2;
    elPag.innerHTML = "<span>Página " + (estado.pagina + 1) + " de " + miles(paginas) + "</span>" +
      '<button type="button" class="boton boton--contorno" data-paso="-1"' + (estado.pagina === 0 ? " disabled" : "") + ">Anterior</button>" +
      '<button type="button" class="boton boton--contorno" data-paso="1"' + (estado.pagina >= paginas - 1 ? " disabled" : "") + ">Siguiente</button>";

    var cabecera = '<th class="col-posicion" scope="col">#</th><th scope="col">' + (deEmpresas ? "Empresa" : "Organismo") + "</th>" +
      COLUMNAS_DIRECTORIO.map(function (c) {
        var etiqueta = c[0] === "otros" ? (deEmpresas ? "Organismos" : "Empresas") : c[1];
        // "Adjudicaciones" no cabe en la tabla de un móvil: ahí, "Nº".
        if (c[0] === "numero") etiqueta = '<span class="solo-ancho">' + etiqueta + '</span><abbr class="solo-estrecho" title="Adjudicaciones">Nº</abbr>';
        return '<th scope="col" class="num' + (c[2] ? " col-secundaria" : "") + '"' + (c[0] === col ? ' aria-sort="descending"' : "") + ">" +
          '<button type="button" class="tabla__orden" data-col="' + c[0] + '">' + etiqueta + Nav.icono("chevron") + "</button></th>";
      }).join("");

    var cuerpo = visibles.map(function (g, i) {
      var nombre, sub = "";
      if (deEmpresas) {
        nombre = D.empresa[g.clave][1];
        if (nifPublicable(D.empresa[g.clave][0])) sub = '<span class="tabla__sub">NIF ' + escaparHtml(D.empresa[g.clave][0]) + "</span>";
      } else {
        nombre = D.organismo[g.clave];
      }
      return '<tr><td class="col-posicion">' + miles(desde + i + 1) + "</td>" +
        '<td><a href="#/' + campo + "/" + g.clave + '">' + escaparHtml(nombre) + "</a>" + sub + "</td>" +
        '<td class="num">' + miles(g.numero) + "</td>" +
        '<td class="num">' + euros(g.importe) + "</td>" +
        '<td class="num col-secundaria">' + euros(g.medio) + "</td>" +
        '<td class="num col-secundaria">' + miles(g.otros) + "</td>" +
        '<td class="num col-secundaria">' + fechaLarga(g.ultima) + "</td></tr>";
    }).join("");

    document.getElementById("directorio-tabla").innerHTML = "<thead><tr>" + cabecera + "</tr></thead><tbody>" + cuerpo + "</tbody>";
  }

  document.getElementById("directorio-tabla").addEventListener("click", function (ev) {
    var b = ev.target.closest(".tabla__orden");
    if (!b) return;
    estado.ordenDirectorio = b.getAttribute("data-col");
    estado.pagina = 0;
    pintarDirectorio();
  });
  document.getElementById("directorio-paginacion").addEventListener("click", function (ev) {
    var b = ev.target.closest("button[data-paso]");
    if (!b || b.disabled) return;
    estado.pagina += Number(b.getAttribute("data-paso"));
    pintarDirectorio();
    document.getElementById("herramientas").scrollIntoView({ block: "start" });
  });

  // ---------- Fichas ----------

  function panelBarras(titulo, id) {
    return '<section class="panel"><h2>' + titulo + '</h2><ol class="barras" id="' + id + '"></ol></section>';
  }

  function porAnio(filas) {
    return agrupar(filas, function (f) { return f.anio || null; }).sort(function (a, b) { return a.clave < b.clave ? 1 : -1; });
  }

  function recientes(filas) {
    return filas.slice().sort(function (a, b) { return a.fecha < b.fecha ? 1 : (a.fecha > b.fecha ? -1 : 0); }).slice(0, MAX_CONTRATOS_FICHA);
  }

  function tituloContratos(filas) {
    return "Adjudicaciones" + (filas.length > MAX_CONTRATOS_FICHA ? " (las " + MAX_CONTRATOS_FICHA + " más recientes de " + miles(filas.length) + ")" : "");
  }

  function etiquetaTipo(f) {
    return f.menor ? "Contrato menor" : (D.procedimiento[f.procedimiento] || "—");
  }

  // Las fichas respetan ámbito/tipo/año/categoría, pero no el texto de
  // búsqueda (que solo sirve para encontrar la empresa o el organismo).
  function pintarFichaEmpresa(idEmpresa) {
    var filas = FILAS.filter(function (f) { return f.empresa === idEmpresa && pasaFiltros(f); });
    var r = resumen(filas);
    pintarKpis(document.getElementById("ficha-kpis"), [
      ["Adjudicaciones", miles(filas.length)],
      ["Importe adjudicado", euros(r.importe)],
      ["Importe medio", r.importeMedio],
      ["Organismos distintos", miles(r.numOrganismos)],
      ["Contratos menores", filas.length ? Math.round(100 * r.menores / filas.length) + " %" : "—", miles(r.menores) + " de " + miles(filas.length)],
      ["Periodo", r.periodo],
    ]);

    document.getElementById("ficha-bloques").innerHTML =
      panelBarras("Organismos a los que vende", "ficha-b1") + panelBarras("Categorías", "ficha-b2") +
      panelBarras("Procedimiento", "ficha-b3") + panelBarras("Por año", "ficha-b4");
    barras(document.getElementById("ficha-b1"), ordenar(agrupar(filas, function (f) { return f.organismo; }), "numero").slice(0, TOP_FICHA), "numero",
      function (x) { return D.organismo[x.clave]; }, function (x) { return "#/organismo/" + x.clave; });
    barras(document.getElementById("ficha-b2"), porCategoria(filas), "numero", function (x) { return CATEGORIAS[x.clave]; });
    barras(document.getElementById("ficha-b3"), porProcedimiento(filas), "numero", nombreProcedimiento);
    barras(document.getElementById("ficha-b4"), porAnio(filas), "numero", function (x) { return x.clave; });

    document.getElementById("ficha-contratos-titulo").textContent = tituloContratos(filas);
    document.getElementById("ficha-contratos-nota").hidden = true;
    var destino = document.getElementById("ficha-contratos");
    if (!filas.length) {
      destino.innerHTML = '<p class="barras__vacio" style="padding:12px 20px 20px">Sin adjudicaciones con estos filtros.</p>';
      return;
    }
    destino.innerHTML = '<p class="barras__vacio" style="padding:12px 20px 20px">Cargando contratos…</p>';
    var contratos = recientes(filas);

    cargarDetalle(idEmpresa).then(function (detalle) {
      // Si entretanto se ha cambiado de ficha, no se pinta.
      if (estado.vista !== "empresa" || estado.id !== idEmpresa) return;
      destino.innerHTML =
        '<table class="tabla tabla--contratos"><thead><tr><th scope="col">Fecha</th><th scope="col">Contrato</th><th scope="col">Organismo</th><th scope="col" class="num">Importe</th></tr></thead><tbody>' +
        contratos.map(function (f) {
          var d = detalle[f.exp] || ["(título no disponible)", ""];
          var enlace = enlaceCompleto(d[1]);
          var titulo = escaparHtml(d[0]);
          return '<tr><td class="col-fecha">' + fechaLarga(f.fecha) + "</td><td>" +
            (enlace ? '<a href="' + escaparHtml(enlace) + '" target="_blank" rel="noopener noreferrer">' + titulo + "</a>" : titulo) +
            (f.menor ? ' <span class="ficha__etiqueta">menor</span>' : "") +
            "</td><td>" + escaparHtml(D.organismo[f.organismo]) + '</td><td class="num">' + euros(f.importe) + "</td></tr>";
        }).join("") + "</tbody></table>";
    }).catch(function () {
      if (estado.vista !== "empresa" || estado.id !== idEmpresa) return;
      destino.innerHTML = '<p class="barras__vacio" style="padding:12px 20px 20px">No se ha podido cargar el detalle de los contratos. Recarga la página para reintentar.</p>';
    });
  }

  function pintarFichaOrganismo(idOrganismo) {
    var filas = FILAS.filter(function (f) { return f.organismo === idOrganismo && pasaFiltros(f); });
    var r = resumen(filas);
    pintarKpis(document.getElementById("ficha-kpis"), [
      ["Adjudicaciones", miles(filas.length)],
      ["Importe adjudicado", euros(r.importe)],
      ["Importe medio", r.importeMedio],
      ["Empresas distintas", miles(r.numEmpresas)],
      ["Ofertas por licitación", r.ofertasMedia],
      ["Periodo", r.periodo],
    ]);

    document.getElementById("ficha-bloques").innerHTML =
      panelBarras("Empresas que más ganan aquí", "ficha-b1") + panelBarras("Categorías", "ficha-b2") +
      panelBarras("Procedimiento", "ficha-b3") + panelBarras("Por año", "ficha-b4");
    barras(document.getElementById("ficha-b1"), ordenar(agrupar(filas, function (f) { return f.empresa; }), "importe").slice(0, TOP_FICHA), "importe",
      function (x) { return D.empresa[x.clave][1]; }, function (x) { return "#/empresa/" + x.clave; });
    barras(document.getElementById("ficha-b2"), porCategoria(filas), "numero", function (x) { return CATEGORIAS[x.clave]; });
    barras(document.getElementById("ficha-b3"), porProcedimiento(filas), "numero", nombreProcedimiento);
    barras(document.getElementById("ficha-b4"), porAnio(filas), "numero", function (x) { return x.clave; });

    document.getElementById("ficha-contratos-titulo").textContent = tituloContratos(filas);
    var nota = document.getElementById("ficha-contratos-nota");
    nota.hidden = false;
    nota.textContent = "El título y el enlace de cada contrato están en la ficha de la empresa adjudicataria.";
    document.getElementById("ficha-contratos").innerHTML = filas.length
      ? '<table class="tabla tabla--contratos"><thead><tr><th scope="col">Fecha</th><th scope="col">Empresa adjudicataria</th><th scope="col">Tipo</th><th scope="col" class="num">Ofertas</th><th scope="col" class="num">Importe</th></tr></thead><tbody>' +
        recientes(filas).map(function (f) {
          return '<tr><td class="col-fecha">' + fechaLarga(f.fecha) + '</td><td><a href="#/empresa/' + f.empresa + '">' + escaparHtml(D.empresa[f.empresa][1]) + "</a></td><td>" +
            escaparHtml(etiquetaTipo(f)) + '</td><td class="num">' + (f.ofertas ? miles(f.ofertas) : "—") + '</td><td class="num">' + euros(f.importe) + "</td></tr>";
        }).join("") + "</tbody></table>"
      : '<p class="barras__vacio" style="padding:12px 20px 20px">Sin adjudicaciones con estos filtros.</p>';
  }

  // ---------- Rutas ----------

  function pintarCabecera() {
    var v = VISTAS[estado.vista];
    var html;
    if (estado.vista === "empresa") {
      var e = D.empresa[estado.id];
      html = '<nav class="migas" aria-label="Ruta"><a href="#/empresas">Empresas</a><span aria-hidden="true">›</span><span>Ficha de empresa</span></nav>' +
        '<header class="pagina__cabecera"><div class="pagina__titulo"><h1>' + escaparHtml(e[1]) + "</h1>" +
        '<p class="pagina__descripcion">' + (nifPublicable(e[0]) ? "NIF " + escaparHtml(e[0]) + " · " : "") + "Contratos de servicios de agencia ganados a organismos públicos españoles desde 2021. Las cifras cambian con los filtros seleccionados (ámbito, tipo, año, categoría, provincia e importe).</p></div></header>";
      document.title = e[1] + " — Radar de licitaciones";
    } else if (estado.vista === "organismo") {
      var nombre = D.organismo[estado.id];
      html = '<nav class="migas" aria-label="Ruta"><a href="#/organismos">Organismos</a><span aria-hidden="true">›</span><span>Ficha de organismo</span></nav>' +
        '<header class="pagina__cabecera"><div class="pagina__titulo"><h1>' + escaparHtml(nombre) + "</h1>" +
        '<p class="pagina__descripcion">Contratos de servicios de agencia que este organismo ha adjudicado a empresas españolas desde 2021. Las cifras cambian con los filtros seleccionados (tipo, año, categoría, provincia e importe).</p></div></header>';
      document.title = nombre + " — Radar de licitaciones";
    } else {
      html = '<header class="pagina__cabecera"><div class="pagina__titulo"><h1>' + v.titulo + '</h1><p class="pagina__descripcion">' + v.descripcion + "</p></div></header>";
      document.title = v.titulo + " — Radar de licitaciones";
    }
    elCabecera.innerHTML = html;
  }

  function pintar() {
    var esDirectorio = estado.vista === "empresas" || estado.vista === "organismos";
    var esFicha = estado.vista === "empresa" || estado.vista === "organismo";
    elVistas.mercado.hidden = estado.vista !== "mercado";
    elVistas.directorio.hidden = !esDirectorio;
    elVistas.ficha.hidden = !esFicha;
    elCampoTexto.hidden = esFicha;

    if (estado.vista === "mercado") pintarMercado();
    else if (esDirectorio) pintarDirectorio();
    else if (estado.vista === "empresa") pintarFichaEmpresa(estado.id);
    else pintarFichaOrganismo(estado.id);
  }

  // Coincidencia exacta de nombre ya normalizado: la usan los enlaces que
  // llegan desde el radar ("Historial de la empresa", "Quién gana en este
  // organismo") para abrir directamente la ficha.
  function idPorNombre(nombres, texto) {
    var encontrado = -1;
    for (var i = 0; i < nombres.length; i++) {
      if (nombres[i] === texto) {
        if (encontrado !== -1) return -1;  // nombre repetido: mejor el directorio filtrado
        encontrado = i;
      }
    }
    return encontrado;
  }

  // Mismo formato que guarda el histórico: sin separadores ni prefijo "ES".
  function idPorNif(nif) {
    nif = String(nif).toUpperCase().replace(/[^A-Z0-9*]/g, "").replace(/^ES(?=[A-Z0-9]\d{7}[A-Z0-9]$)/, "");
    // Un NIF enmascarado ("***9688**") lo comparten personas distintas.
    if (!nif || nif.indexOf("*") !== -1 || nif.indexOf("XXX") === 0) return -1;
    for (var i = 0; i < D.empresa.length; i++) {
      if (D.empresa[i][0] === nif) return i;
    }
    return -1;
  }

  function navegar(esCargaInicial) {
    var leida = Nav.leerRuta();
    var partes = leida.ruta.split("/");
    var vista = VISTAS[partes[0]] ? partes[0] : "mercado";
    var id = null;

    if (vista === "empresa" || vista === "organismo") {
      id = parseInt(partes[1], 10);
      var diccionario = vista === "empresa" ? D.empresa : D.organismo;
      if (!(id >= 0 && id < diccionario.length)) { vista = vista + "s"; id = null; }
      // Ficha fusionada con otra: un enlace antiguo lleva a la buena.
      else if (vista === "empresa" && D.empresa[id].length > 2) {
        location.replace("#/empresa/" + D.empresa[id][2]);
        return;
      }
    }

    var q = (leida.params.q || "").trim();
    if (vista === "empresas" || vista === "organismos") {
      var exacto = -1;
      if (vista === "empresas" && leida.params.nif) exacto = idPorNif(leida.params.nif);
      if (exacto === -1 && q) exacto = idPorNombre(vista === "empresas" ? NOMBRE_EMPRESA : TEXTO_ORGANISMO, normalizar(q));
      if (exacto !== -1) {
        location.replace("#/" + vista.slice(0, -1) + "/" + exacto);
        return;
      }
    }

    estado.vista = vista;
    estado.id = id;
    estado.pagina = 0;
    estado.texto = normalizar(q);
    elTexto.value = q;
    if (VISTAS[vista].buscar) {
      elTexto.placeholder = VISTAS[vista].buscar;
      elTexto.setAttribute("aria-label", VISTAS[vista].buscar.replace("…", ""));
    }

    Nav.activar(VISTAS[vista].nav);
    pintarCabecera();
    pintar();
    window.scrollTo(0, 0);
    if (!esCargaInicial) elContenido.focus({ preventScroll: true });
  }

  var textoActualizado = "Histórico actualizado el " + fechaLarga(H.actualizado) + ".";
  Nav.actualizado(textoActualizado);
  document.getElementById("fecha-generacion").textContent = textoActualizado;

  window.addEventListener("hashchange", function () { navegar(false); });
  navegar(true);
})();
