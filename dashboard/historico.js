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
      buscar: "Buscar empresa, NIF u organismo…",
    },
    empresas: {
      nav: "empresas",
      titulo: "Empresas",
      buscar: "Buscar empresa o NIF…",
    },
    organismos: {
      nav: "organismos",
      titulo: "Organismos",
      buscar: "Buscar organismo…",
    },
    competencia: {
      nav: "competencia",
      titulo: "Nuestra competencia",
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

  // Rebaja de la ganadora sobre el presupuesto (sin IVA los dos). Solo con
  // un lote por expediente (con varios, el presupuesto es del expediente
  // entero), fuera de contratos menores y acuerdos marco. null = no se puede
  // calcular; 0 = adjudicado por el presupuesto, lo normal en negociados y
  // contratos a precios unitarios, donde la rebaja real no se ve. Por encima
  // del 80 %, casi siempre importes en unidades distintas (anual/total).
  var REBAJA_MAX = 0.8;
  var LOTES_POR_EXP = [];
  H.lotes.forEach(function (l) { LOTES_POR_EXP[l[0]] = (LOTES_POR_EXP[l[0]] || 0) + 1; });
  var ES_ACUERDO_MARCO = D.procedimiento.map(function (p) { return /acuerdo marco/i.test(p || ""); });
  function rebajaDe(e, l) {
    var presupuesto = e[7];
    if (!presupuesto || !l[3] || e[4] === 1 || LOTES_POR_EXP[l[0]] !== 1 || ES_ACUERDO_MARCO[e[3]]) return null;
    var r = 1 - l[3] / presupuesto;
    if (r < -0.001 || r > REBAJA_MAX) return null;
    return r < 0.0005 ? 0 : r;
  }

  // Si la ganadora es pyme: en los contratos de la plataforma de Euskadi el
  // dato no es fiable (casi siempre llega «no»: de las empresas que la ficha
  // de Euskadi da como pyme, 86 contratos vascos decían «no» y 19 «sí»,
  // medido el 2026-10-20). Se toma como «sin dato».
  var FILAS = H.lotes.map(function (l) {
    var e = H.exp[l[0]];
    var lugar = LUGARES[e[6]] || SIN_LUGAR;
    return {
      exp: l[0], empresa: l[1], anio: l[2] ? l[2].slice(0, 4) : "", fecha: l[2] || "",
      importe: l[3] || 0, ofertas: l[4], pyme: e[1] === 1 ? null : l[5], rebaja: rebajaDe(e, l),
      organismo: e[0], euskadi: e[1] === 1, procedimiento: e[3], menor: e[4] === 1, mascara: e[5],
      provincia: lugar[0], comunidad: lugar[1],
    };
  });

  // Fecha del primer contrato de cada empresa en todo el histórico (sin
  // filtros): para saber cuántas entran nuevas al mercado.
  var PRIMERA_FECHA = [];
  FILAS.forEach(function (f) {
    if (f.fecha && (!PRIMERA_FECHA[f.empresa] || f.fecha < PRIMERA_FECHA[f.empresa])) PRIMERA_FECHA[f.empresa] = f.fecha;
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
    // Nuestra competencia: "todas" las que ganan con los filtros o "sigo".
    competencia: "todas", ordenRanking: "numero",
    // Sin emisoras, periódicos y demás medios a los que se compra espacio:
    // no compiten con la agencia (ver ES_MEDIO).
    sinMedios: true,
  };

  var elCabecera = document.getElementById("cabecera-vista");
  var elContenido = document.getElementById("contenido");
  var elTexto = document.getElementById("filtro-texto");
  var elCampoTexto = document.getElementById("campo-texto");
  var elVistas = {
    mercado: document.getElementById("vista-mercado"),
    directorio: document.getElementById("vista-directorio"),
    ficha: document.getElementById("vista-ficha"),
    competencia: document.getElementById("vista-competencia"),
  };

  // ---------- Empresas que se siguen ----------
  // {nif: nombre} en el navegador. Por NIF y no por id: los ids del
  // histórico cambian cuando se vuelve a generar.
  var CLAVE_SEGUIDAS = "radar-competencia";
  function leerSeguidas() {
    try { return JSON.parse(localStorage.getItem(CLAVE_SEGUIDAS)) || {}; } catch (e) { return {}; }
  }
  function escribirSeguidas(s) {
    try { localStorage.setItem(CLAVE_SEGUIDAS, JSON.stringify(s)); } catch (e) { /* sin almacenamiento: no se recuerda */ }
  }
  function alternarSeguida(nif, nombre) {
    var s = leerSeguidas();
    if (s[nif]) delete s[nif]; else s[nif] = nombre;
    escribirSeguidas(s);
    return !!s[nif];
  }

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
  segmented("segmented-competencia", [["todas", "Todas las que compiten"], ["sigo", "Las que sigo"]], "competencia");

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
        : metrica === "rebaja"
          ? porcentaje(x.rebaja) + ' <span class="barras__sec">· ' + miles(x.numero) + " contratos</span>"
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

  function mediana(lista) {
    if (!lista.length) return null;
    var s = lista.slice().sort(function (a, b) { return a - b; });
    var m = s.length >> 1;
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  }

  // "1 contrato", "16 contratos".
  function cuantos(n, uno, varios) {
    return miles(n) + " " + (n === 1 ? uno : varios);
  }

  function porcentaje(fraccion) {
    return miles(100 * fraccion, fraccion < 0.1 ? 1 : 0) + " %";
  }

  function resumen(filas) {
    var r = { importe: 0, conImporte: 0, empresas: {}, organismos: {}, ofertas: 0, conOfertas: 0, pymes: 0, conPyme: 0, menores: 0, anios: [],
      listaOfertas: [], rebajas: [], conRebaja: 0, sinRebaja: 0 };
    var anios = {};
    filas.forEach(function (f) {
      if (f.importe) { r.importe += f.importe; r.conImporte++; }
      r.empresas[f.empresa] = true;
      r.organismos[f.organismo] = true;
      // Los contratos menores no tienen concurso: PLACSP los publica con
      // "1 oferta" y hundían la media (en el 77 % de lo que publica el número
      // de ofertas "solo se presentó una").
      if (f.ofertas && !f.menor) { r.ofertas += f.ofertas; r.conOfertas++; r.listaOfertas.push(f.ofertas); }
      if (f.rebaja != null) {
        r.conRebaja++;
        if (f.rebaja > 0) r.rebajas.push(f.rebaja); else r.sinRebaja++;
      }
      if (f.pyme != null) { r.conPyme++; r.pymes += f.pyme; }
      if (f.menor) r.menores++;
      if (f.anio) anios[f.anio] = true;
    });
    r.anios = Object.keys(anios).sort();
    r.numEmpresas = Object.keys(r.empresas).length;
    r.numOrganismos = Object.keys(r.organismos).length;
    r.importeMedio = r.conImporte ? euros(r.importe / r.conImporte) : "—";
    r.ofertasMedia = r.conOfertas ? (r.ofertas / r.conOfertas).toLocaleString("es-ES", { maximumFractionDigits: 1 }) : "—";
    r.rebajaMediana = mediana(r.rebajas);
    r.rebajaTexto = r.rebajaMediana == null ? "—" : porcentaje(r.rebajaMediana);
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
    repartoProcedimientos(document.getElementById("grafico-procedimientos"), porProcedimiento(filas));
    var porOfertas = TRAMOS_OFERTAS.map(function (t, i) {
      var x = { clave: i, numero: 0 };
      filas.forEach(function (f) { if (!f.menor && f.ofertas >= t[0] && f.ofertas <= t[1]) x.numero++; });
      return x;
    });
    columnasReparto(document.getElementById("grafico-ofertas"), porOfertas, function (x) { return TRAMOS_OFERTAS[x.clave][2]; });
    // Rebaja de la ganadora: cuántos contratos se ganaron con cada tramo de
    // rebaja, con la mitad central (del primer al tercer cuartil) resaltada.
    var q1 = cuantil(r.rebajas, 0.25), q3 = cuantil(r.rebajas, 0.75);
    var porRebaja = TRAMOS_REBAJA.map(function (t, i) {
      return { clave: i, numero: r.rebajas.filter(function (x) { return x >= t[0] && x < t[1]; }).length,
        central: q1 != null && t[0] <= q3 && t[1] > q1 };
    });
    columnasReparto(document.getElementById("grafico-rebaja"), r.rebajas.length >= MIN_CONTRATOS_TRAMO ? porRebaja : [],
      function (x) { return TRAMOS_REBAJA[x.clave][2]; });

    pintarConclusiones(filas, r);
  }

  var TRAMOS_OFERTAS = [[1, 1, "1 oferta"], [2, 2, "2 ofertas"], [3, 5, "3 a 5"], [6, 10, "6 a 10"], [11, 1e9, "Más de 10"]];
  // Con menos contratos, una mediana o un reparto bailan demasiado.
  var MIN_CONTRATOS_TRAMO = 20;

  function cuantil(lista, p) {
    if (!lista.length) return null;
    var s = lista.slice().sort(function (a, b) { return a - b; });
    var i = (s.length - 1) * p, base = Math.floor(i);
    return s[base] + (s[Math.min(base + 1, s.length - 1)] - s[base]) * (i - base);
  }

  // Columnas con el porcentaje de cada tramo sobre el total. Las marcadas
  // `central` se pintan en el color fuerte y el resto, en uno suave.
  function columnasReparto(el, lista, etiqueta) {
    var total = lista.reduce(function (s, x) { return s + x.numero; }, 0);
    if (!total) {
      el.innerHTML = '<p class="barras__vacio">Sin datos suficientes con estos filtros.</p>';
      return;
    }
    var max = lista.reduce(function (m, x) { return Math.max(m, x.numero); }, 0);
    var conCentral = lista.some(function (x) { return x.central; });
    el.innerHTML = lista.map(function (x) {
      return '<div class="columnas__col" title="' + cuantos(x.numero, "contrato", "contratos") + '"><span class="columnas__valor">' + porcentaje(x.numero / total) + "</span>" +
        '<span class="columnas__pista"><span class="columnas__relleno' + (conCentral && !x.central ? " columnas__relleno--suave" : "") +
        '" style="height:' + (100 * x.numero / max).toFixed(1) + '%"></span></span>' +
        '<span class="columnas__etiqueta">' + escaparHtml(etiqueta(x)) + "</span></div>";
    }).join("");
  }

  // Reparto por procedimiento en una sola barra: los cuatro más frecuentes
  // y el resto juntos.
  var MAX_TRAMOS_REPARTO = 4;
  function repartoProcedimientos(el, lista) {
    var total = lista.reduce(function (s, x) { return s + x.numero; }, 0);
    if (!total) {
      el.innerHTML = '<p class="barras__vacio">Sin datos con estos filtros.</p>';
      return;
    }
    var tramos = lista.slice(0, MAX_TRAMOS_REPARTO).map(function (x) { return { nombre: nombreProcedimiento(x), numero: x.numero }; });
    var resto = lista.slice(MAX_TRAMOS_REPARTO).reduce(function (s, x) { return s + x.numero; }, 0);
    if (resto) tramos.push({ nombre: "Otros", numero: resto });
    el.innerHTML = '<div class="reparto reparto--alto" aria-hidden="true">' + tramos.map(function (x, i) {
      return '<span class="reparto__tramo reparto__tramo--s' + i + '" style="width:' + (100 * x.numero / total).toFixed(2) + '%"></span>';
    }).join("") + "</div>" +
      '<ul class="leyenda">' + tramos.map(function (x, i) {
        return '<li><span class="leyenda__muestra reparto__tramo--s' + i + '"></span><span class="leyenda__nombre">' + escaparHtml(x.nombre) + "</span>" +
          '<span class="leyenda__valor">' + porcentaje(x.numero / total) + ' <span class="barras__sec">· ' + miles(x.numero) + "</span></span></li>";
      }).join("") + "</ul>";
  }

  // Lo que dicen los datos, en frases: la conclusión antes que el gráfico.
  // Se recalcula con los filtros (una categoría, una provincia, un año...).
  function pintarConclusiones(filas, r) {
    var frases = [];
    var empresasPorImporte = ordenar(agrupar(filas, function (f) { return f.empresa; }), "importe");

    if (r.importe && empresasPorImporte.length >= 20) {
      var top10 = empresasPorImporte.slice(0, 10).reduce(function (s, x) { return s + x.importe; }, 0) / r.importe;
      frases.push((top10 >= 0.5 ? "<strong>Mercado concentrado.</strong> " : "<strong>Mercado repartido.</strong> ") +
        "Las 10 empresas que más facturan se llevan el " + porcentaje(top10) + " del importe, entre " +
        miles(empresasPorImporte.length) + " empresas que han ganado algo.");
    }

    if (r.listaOfertas.length >= MIN_CONTRATOS_TRAMO) {
      var unaSola = r.listaOfertas.filter(function (o) { return o === 1; }).length / r.listaOfertas.length;
      var tipicas = mediana(r.listaOfertas);
      frases.push("<strong>Competencia.</strong> Se presentan de mediana " + miles(tipicas, 1) + (tipicas === 1 ? " empresa" : " empresas") +
        " por licitación, y en el " + porcentaje(unaSola) + " solo se presentó una.");
    }

    // Quien licita no sabe cuántas empresas se van a presentar: el precio
    // se cuenta como la franja en la que suelen ganar, no según las ofertas.
    if (r.rebajas.length >= MIN_CONTRATOS_TRAMO) {
      frases.push("<strong>Precio.</strong> La mitad de las ganadoras rebajó el presupuesto entre un " + porcentaje(cuantil(r.rebajas, 0.25)) +
        " y un " + porcentaje(cuantil(r.rebajas, 0.75)) + " (mediana, " + porcentaje(r.rebajaMediana) + "); un cuarto ganó con menos rebaja y otro cuarto, con más. " +
        "En el " + porcentaje(r.sinRebaja / r.conRebaja) +
        " de los contratos se adjudica por el presupuesto (negociados y precios unitarios, donde la rebaja no se ve).");
    }

    if (r.conPyme >= MIN_CONTRATOS_TRAMO) {
      frases.push("<strong>Pymes.</strong> Ganan el " + porcentaje(r.pymes / r.conPyme) + " de las adjudicaciones que dicen si la ganadora es pyme.");
    }

    // Empresas que ganan su primer contrato en los 12 meses anteriores a la
    // última actualización.
    var hace12 = String(Number(H.actualizado.slice(0, 4)) - 1) + H.actualizado.slice(4, 10);
    var activas = {};
    filas.forEach(function (f) { if (f.fecha > hace12) activas[f.empresa] = true; });
    var numActivas = Object.keys(activas).length;
    var nuevas = Object.keys(activas).filter(function (k) { return PRIMERA_FECHA[k] > hace12; }).length;
    if (numActivas >= MIN_CONTRATOS_TRAMO) {
      frases.push("<strong>Entrada.</strong> En el último año " + miles(nuevas) + " empresas ganaron un contrato por primera vez desde 2021: el " +
        porcentaje(nuevas / numActivas) + " de las que ganaron algo en ese tiempo.");
    }

    if (filas.length >= MIN_CONTRATOS_TRAMO && r.menores) {
      frases.push("<strong>Contratos menores.</strong> Son el " + porcentaje(r.menores / filas.length) +
        " de las adjudicaciones (hasta 15.000 € sin IVA en servicios, sin concurso): la vía de entrada más directa a un organismo.");
    }

    var el = document.getElementById("conclusiones");
    el.innerHTML = frases.length
      ? frases.map(function (f) { return "<li>" + f + "</li>"; }).join("")
      : '<li class="barras__vacio">Pocos contratos con estos filtros para sacar conclusiones.</li>';
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

    var seguidas = deEmpresas ? leerSeguidas() : {};
    var cabecera = '<th class="col-posicion" scope="col">#</th><th scope="col">' + (deEmpresas ? "Empresa" : "Organismo") + "</th>" +
      COLUMNAS_DIRECTORIO.map(function (c) {
        var etiqueta = c[0] === "otros" ? (deEmpresas ? "Organismos" : "Empresas") : c[1];
        // "Adjudicaciones" no cabe en la tabla de un móvil: ahí, "Nº".
        if (c[0] === "numero") etiqueta = '<span class="solo-ancho">' + etiqueta + '</span><abbr class="solo-estrecho" title="Adjudicaciones">Nº</abbr>';
        return '<th scope="col" class="num' + (c[2] ? " col-secundaria" : "") + '"' + (c[0] === col ? ' aria-sort="descending"' : "") + ">" +
          '<button type="button" class="tabla__orden" data-col="' + c[0] + '">' + etiqueta + Nav.icono("chevron") + "</button></th>";
      }).join("") +
      (deEmpresas ? '<th scope="col" class="col-seguir"><span class="visualmente-oculto">Seguir</span></th>' : "");

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
        '<td class="num col-secundaria">' + fechaLarga(g.ultima) + "</td>" +
        (deEmpresas ? '<td class="col-seguir">' + botonSeguir(D.empresa[g.clave], seguidas) + "</td>" : "") + "</tr>";
    }).join("");

    document.getElementById("directorio-tabla").innerHTML = "<thead><tr>" + cabecera + "</tr></thead><tbody>" + cuerpo + "</tbody>";
  }

  // Marcador para seguir una empresa desde la lista (también en su ficha).
  // Sin NIF publicable (personas físicas) no se puede seguir.
  function botonSeguir(empresa, seguidas) {
    var nif = nifPublicable(empresa[0]);
    if (!nif) return "";
    var sigue = !!seguidas[nif];
    return '<button type="button" class="boton-icono boton-seguir" data-seguir-lista="' + escaparHtml(nif) + '" data-nombre="' + escaparHtml(empresa[1]) + '"' +
      ' aria-pressed="' + sigue + '" title="' + (sigue ? "Dejar de seguir" : "Seguir: aparecerá en Nuestra competencia") + '" aria-label="' +
      (sigue ? "Dejar de seguir a " : "Seguir a ") + escaparHtml(empresa[1]) + '">' + Nav.icono("marcador") + "</button>";
  }

  document.getElementById("directorio-tabla").addEventListener("click", function (ev) {
    var s = ev.target.closest("[data-seguir-lista]");
    if (s) {
      var sigue = alternarSeguida(s.getAttribute("data-seguir-lista"), s.getAttribute("data-nombre"));
      s.setAttribute("aria-pressed", sigue ? "true" : "false");
      s.title = sigue ? "Dejar de seguir" : "Seguir: aparecerá en Nuestra competencia";
      s.setAttribute("aria-label", (sigue ? "Dejar de seguir a " : "Seguir a ") + s.getAttribute("data-nombre"));
      return;
    }
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

  // Índice de éxito en concursos vascos (licitadoras-data.js, ver
  // euskadi.indice_exito): a cuántos se presentó y cuántos ganó. No depende
  // de los filtros. Solo con al menos MIN_CONCURSOS_EXITO concursos: con
  // menos, un porcentaje dice poco.
  var LICITADORAS = window.LICITADORAS || {};
  var MIN_CONCURSOS_EXITO = 3;
  function kpiExito(nif) {
    var x = nif && LICITADORAS[nif];
    if (!x || x[0] < MIN_CONCURSOS_EXITO) return [];
    return [["Éxito en concursos vascos", Math.round(100 * x[1] / x[0]) + " %",
      "gana " + miles(x[1]) + " de " + miles(x[0]) + (x[2] ? " desde " + x[2].slice(0, 4) : "")]];
  }

  // ---------- Concursos vascos: a qué se presenta y cara a cara ----------
  // concursos-data.js (ver euskadi.concursos): cada concurso del portal de
  // Euskadi con quién se presentó y quién ganó. Se descarga la primera vez
  // que se abre una ficha de empresa. Las personas físicas vienen como null.
  var URL_CONCURSO_EUSKADI = "https://www.contratacion.euskadi.eus/webkpe00-kpeperfi/es/contenidos/anuncio_contratacion/";
  var MAX_CONCURSOS_FICHA = 100;
  var TOP_RIVALES = 15;
  var cargaConcursos = null;
  function cargarConcursos() {
    if (!cargaConcursos) {
      cargaConcursos = new Promise(function (resolver, rechazar) {
        var s = document.createElement("script");
        s.src = "concursos-data.js?v=" + encodeURIComponent(H.actualizado);
        s.onload = function () { resolver(window.CONCURSOS_EUSKADI); };
        s.onerror = function () { cargaConcursos = null; rechazar(new Error("sin concursos")); };
        document.head.appendChild(s);
      });
    }
    return cargaConcursos;
  }

  var ID_POR_NIF = null;
  function idEmpresaPorNif(nif) {
    if (!ID_POR_NIF) {
      ID_POR_NIF = {};
      D.empresa.forEach(function (e, i) { if (e[0] && e.length === 2) ID_POR_NIF[e[0]] = i; });
    }
    return Object.prototype.hasOwnProperty.call(ID_POR_NIF, nif) ? ID_POR_NIF[nif] : -1;
  }

  // Nombre de una licitadora, con enlace a su ficha si ha ganado algo.
  function empresaConcurso(C, nif) {
    if (!nif) return "una persona física";
    var id = idEmpresaPorNif(nif);
    var nombre = escaparHtml((C.empresas && C.empresas[nif]) || (id !== -1 ? D.empresa[id][1] : "NIF " + nif));
    return id !== -1 ? '<a href="#/empresa/' + id + '">' + nombre + "</a>" : nombre;
  }

  function analizarConcursos(C, nif) {
    var suyos = C.concursos.filter(function (c) { return c[5].indexOf(nif) !== -1; });
    var porAnio = {};
    var rivales = {};
    suyos.forEach(function (c) {
      var gana = c[4].indexOf(nif) !== -1;
      var anio = (c[0] || "").slice(0, 4) || "—";
      var a = porAnio[anio] || (porAnio[anio] = { clave: anio, numero: 0, ganadas: 0 });
      a.numero++;
      a.ganadas += gana ? 1 : 0;
      var vistos = {};
      c[5].forEach(function (otra) {
        if (!otra || otra === nif || vistos[otra]) return;
        vistos[otra] = true;
        var r = rivales[otra] || (rivales[otra] = { nif: otra, veces: 0, ganaEsta: 0, ganaOtra: 0, tercera: 0 });
        r.veces++;
        if (gana) r.ganaEsta++;
        else if (c[4].indexOf(otra) !== -1) r.ganaOtra++;
        else r.tercera++;
      });
    });
    return {
      suyos: suyos,
      porAnio: Object.keys(porAnio).sort().reverse().map(function (k) { return porAnio[k]; }),
      rivales: Object.keys(rivales).map(function (k) { return rivales[k]; })
        .sort(function (a, b) { return b.veces - a.veces || b.ganaOtra - a.ganaOtra; }),
    };
  }

  function resultadoConcurso(C, c, nif) {
    if (c[4].indexOf(nif) !== -1) return '<span class="ficha__resultado--ganada">Ganada</span>';
    if (!c[4].length) return "Sin adjudicataria conocida";
    return "Perdida · ganó " + c[4].map(function (g) { return empresaConcurso(C, g); }).join(", ");
  }

  function tablaSimple(cabeceras, filas) {
    return '<div class="tabla-envoltorio tabla-envoltorio--interna"><table class="tabla"><thead><tr>' +
      cabeceras.map(function (c) { return '<th scope="col"' + (c[1] ? ' class="num"' : "") + ">" + c[0] + "</th>"; }).join("") +
      "</tr></thead><tbody>" + filas.join("") + "</tbody></table></div>";
  }

  function pintarConcursos(idEmpresa) {
    var panel = document.getElementById("ficha-concursos");
    var cuerpo = document.getElementById("ficha-concursos-cuerpo");
    var nif = nifPublicable(D.empresa[idEmpresa][0]);
    panel.hidden = true;
    if (!nif) return;
    cargarConcursos().then(function (C) {
      if (estado.vista !== "empresa" || estado.id !== idEmpresa || !C) return;
      var a = analizarConcursos(C, nif);
      if (!a.suyos.length) return;
      var ganadas = a.suyos.filter(function (c) { return c[4].indexOf(nif) !== -1; }).length;
      var exito = function (x, total) { return total ? Math.round(100 * x / total) + " %" : "—"; };
      var num = function (n) { return '<td class="num">' + miles(n) + "</td>"; };
      cuerpo.innerHTML =
        '<p class="panel__nota">Se ha presentado a <strong>' + miles(a.suyos.length) + "</strong> y ha ganado <strong>" + miles(ganadas) +
        "</strong> (" + exito(ganadas, a.suyos.length) + ").</p>" +
        '<h3 class="ficha__subtitulo">Por año</h3>' +
        tablaSimple([["Año"], ["Se presenta", true], ["Gana", true], ["Éxito", true]], a.porAnio.map(function (x) {
          return "<tr><td>" + x.clave + "</td>" + num(x.numero) + num(x.ganadas) + '<td class="num">' + exito(x.ganadas, x.numero) + "</td></tr>";
        })) +
        (a.rivales.length
          ? '<h3 class="ficha__subtitulo">Cara a cara: con quién coincide más</h3>' +
            '<p class="panel__nota">En cuántos concursos coinciden y quién se lo lleva: esta empresa, la rival o ninguna de las dos (gana una tercera o queda sin adjudicar).' +
            (a.rivales.length > TOP_RIVALES ? " Las " + TOP_RIVALES + " con más coincidencias, de " + miles(a.rivales.length) + "." : "") + "</p>" +
            tablaSimple([["Rival"], ["Coinciden", true], ["Gana esta", true], ["Gana la rival", true], ["Ni una ni otra", true]],
              a.rivales.slice(0, TOP_RIVALES).map(function (r) {
                return "<tr><td>" + empresaConcurso(C, r.nif) + "</td>" + num(r.veces) + num(r.ganaEsta) + num(r.ganaOtra) + num(r.tercera) + "</tr>";
              }))
          : "") +
        '<h3 class="ficha__subtitulo">Concursos' + (a.suyos.length > MAX_CONCURSOS_FICHA ? " (los " + MAX_CONCURSOS_FICHA + " más recientes)" : "") + "</h3>" +
        tablaSimple([["Fecha"], ["Concurso"], ["Organismo"], ["Licitadoras", true], ["Resultado"]],
          a.suyos.slice(0, MAX_CONCURSOS_FICHA).map(function (c) {
            var titulo = escaparHtml(c[1] || "Expediente " + c[3]);
            return '<tr><td class="col-fecha">' + (c[0] ? fechaLarga(c[0]) : "—") + '</td><td><a href="' + URL_CONCURSO_EUSKADI + encodeURIComponent(c[3]) +
              '/es_doc/index.html" target="_blank" rel="noopener noreferrer">' + titulo + "</a></td><td>" + escaparHtml(c[2] || "—") +
              "</td>" + num(c[5].length) + "<td>" + resultadoConcurso(C, c, nif) + "</td></tr>";
          }));
      panel.hidden = false;
    }).catch(function () { /* sin el fichero, la ficha sigue sin esta sección */ });
  }

  // ---------- Rebajas de una empresa (al estilo de Gobierto) ----------
  // Solo contratos con rebaja calculable y mayor que cero (ver rebajaDe).
  var MIN_REBAJAS_GRUPO = 3;
  var TRAMOS_REBAJA = [[0, 0.05, "Menos del 5 %"], [0.05, 0.1, "Del 5 al 10 %"], [0.1, 0.2, "Del 10 al 20 %"],
    [0.2, 0.3, "Del 20 al 30 %"], [0.3, 0.45, "Del 30 al 45 %"], [0.45, 1, "45 % o más"]];

  function rebajasPor(filas, clave) {
    var g = {};
    filas.forEach(function (f) {
      if (!(f.rebaja > 0)) return;
      [].concat(clave(f)).forEach(function (k) { (g[k] || (g[k] = [])).push(f.rebaja); });
    });
    return Object.keys(g).filter(function (k) { return g[k].length >= MIN_REBAJAS_GRUPO; })
      .map(function (k) { return { clave: k, numero: g[k].length, rebaja: mediana(g[k]) }; })
      .sort(function (a, b) { return b.numero - a.numero; });
  }

  function tablaPorAnio(filas) {
    var lista = porAnio(filas);
    if (!lista.length) return '<p class="barras__vacio">Sin datos con estos filtros.</p>';
    return '<div class="tabla-envoltorio tabla-envoltorio--interna"><table class="tabla"><thead><tr><th scope="col">Año</th>' +
      '<th scope="col" class="num">Contratos</th><th scope="col" class="num">Importe</th><th scope="col" class="num" title="Rebaja mediana al ganar">Rebaja</th></tr></thead><tbody>' +
      lista.map(function (x) {
        var r = mediana(filas.filter(function (f) { return f.anio === x.clave && f.rebaja > 0; }).map(function (f) { return f.rebaja; }));
        return "<tr><td>" + x.clave + '</td><td class="num">' + miles(x.numero) + '</td><td class="num">' + euros(x.importe) +
          '</td><td class="num">' + (r == null ? "—" : porcentaje(r)) + "</td></tr>";
      }).join("") + "</tbody></table></div>";
  }

  function pintarRebajasEmpresa(filas) {
    document.getElementById("ficha-anios").innerHTML = tablaPorAnio(filas);
    var conRebaja = filas.filter(function (f) { return f.rebaja > 0; });
    barras(document.getElementById("ficha-tramos"), TRAMOS_REBAJA.map(function (t, i) {
      var en = conRebaja.filter(function (f) { return f.rebaja >= t[0] && f.rebaja < t[1]; });
      return { clave: i, numero: en.length, importe: en.reduce(function (s, f) { return s + f.importe; }, 0) };
    }).filter(function (x) { return x.numero; }), "numero", function (x) { return TRAMOS_REBAJA[x.clave][2]; });
    barras(document.getElementById("ficha-rebaja-cat"), rebajasPor(filas, function (f) {
      return CATEGORIAS.map(function (c, i) { return i; }).filter(function (i) { return f.mascara & (1 << i); });
    }).slice(0, TOP_FICHA), "rebaja", function (x) { return CATEGORIAS[x.clave]; });
    barras(document.getElementById("ficha-rebaja-org"), rebajasPor(filas, function (f) { return f.organismo; }).slice(0, TOP_FICHA), "rebaja",
      function (x) { return D.organismo[x.clave]; }, function (x) { return "#/organismo/" + x.clave; });
    ["ficha-rebaja-cat", "ficha-rebaja-org"].forEach(function (id) {
      var el = document.getElementById(id);
      if (!el.querySelector(".barras__fila")) {
        el.innerHTML = '<li class="barras__vacio">Hacen falta al menos ' + MIN_REBAJAS_GRUPO + " contratos con rebaja en el mismo grupo.</li>";
      }
    });
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
      ["Ofertas por licitación", r.ofertasMedia, r.conOfertas ? "en las que gana" : ""],
      ["Rebaja al ganar", r.rebajaTexto, r.rebajas.length ? "mediana de " + cuantos(r.rebajas.length, "contrato", "contratos") : ""],
    ].concat(kpiExito(D.empresa[idEmpresa][0]), [["Periodo", r.periodo]]));

    document.getElementById("ficha-bloques").innerHTML =
      panelBarras("Organismos a los que vende", "ficha-b1") + panelBarras("Categorías", "ficha-b2") +
      panelBarras("Procedimiento", "ficha-b3") + panelBarras("Por año", "ficha-b4") +
      '<section class="panel"><h2>Año a año: importe y rebaja</h2><div id="ficha-anios"></div></section>' +
      panelBarras("Cuánto rebaja al ganar (contratos por tramo)", "ficha-tramos") +
      panelBarras("Rebaja mediana por categoría", "ficha-rebaja-cat") + panelBarras("Rebaja mediana por organismo", "ficha-rebaja-org");
    barras(document.getElementById("ficha-b1"), ordenar(agrupar(filas, function (f) { return f.organismo; }), "numero").slice(0, TOP_FICHA), "numero",
      function (x) { return D.organismo[x.clave]; }, function (x) { return "#/organismo/" + x.clave; });
    barras(document.getElementById("ficha-b2"), porCategoria(filas), "numero", function (x) { return CATEGORIAS[x.clave]; });
    barras(document.getElementById("ficha-b3"), porProcedimiento(filas), "numero", nombreProcedimiento);
    barras(document.getElementById("ficha-b4"), porAnio(filas), "numero", function (x) { return x.clave; });
    pintarRebajasEmpresa(filas);
    pintarConcursos(idEmpresa);

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
    document.getElementById("ficha-concursos").hidden = true;
    var filas = FILAS.filter(function (f) { return f.organismo === idOrganismo && pasaFiltros(f); });
    var r = resumen(filas);
    pintarKpis(document.getElementById("ficha-kpis"), [
      ["Adjudicaciones", miles(filas.length)],
      ["Importe adjudicado", euros(r.importe)],
      ["Importe medio", r.importeMedio],
      ["Empresas distintas", miles(r.numEmpresas)],
      ["Ofertas por licitación", r.ofertasMedia],
      ["Rebaja de la ganadora", r.rebajaTexto, r.rebajas.length ? "mediana de " + cuantos(r.rebajas.length, "contrato", "contratos") : ""],
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

  // Ranking de las empresas que ganan con los filtros puestos (también el
  // año). Con un año elegido, la flecha compara la posición con el año
  // anterior. El % de éxito sale de los concursos vascos en los que figura
  // como licitadora (LICITADORAS): es la única fuente que publica quién se
  // presenta.
  var COLUMNAS_RANKING = [
    ["numero", "Ganadas"], ["importe", "Importe"], ["euskadi", "Euskadi / Estado"],
    ["exito", "Éxito"], ["rebaja", "Rebaja"],
  ];

  // Medios de comunicación: por el nombre (radio, diario, editorial...) o
  // porque al menos el 60 % de lo que ganan es inserción en medios y el
  // nombre no dice que sean una agencia (las centrales de medios sí
  // compiten). Medido el 2026-10-22 sobre las 70 empresas que más ganan.
  var RE_NOMBRE_MEDIO = /\b(radio\w*|irrati\w*|cadena|uniprex|editorial|ediciones|diario|periodico\w*|\w*prensa\w*|\w*prentsa\w*|press|noticias|television|televisio|telebista|tv|emisoras?|publicaciones|grupo de comunicacion|media|eitb)\b/;
  var RE_NOMBRE_AGENCIA = /agencia|agency|publicidad|publicitat|marketing|comunicacion|creativ|estudio|diseno/;
  var ES_MEDIO = (function () {
    var bit = CATEGORIAS.indexOf("Planificación de medios");
    var total = [], enMedios = [];
    FILAS.forEach(function (f) {
      total[f.empresa] = (total[f.empresa] || 0) + 1;
      if (bit !== -1 && f.mascara & (1 << bit)) enMedios[f.empresa] = (enMedios[f.empresa] || 0) + 1;
    });
    return D.empresa.map(function (e, i) {
      var nombre = NOMBRE_EMPRESA[i];
      if (RE_NOMBRE_MEDIO.test(nombre)) return true;
      return (total[i] || 0) >= 20 && (enMedios[i] || 0) / total[i] >= 0.6 && !RE_NOMBRE_AGENCIA.test(nombre);
    });
  })();

  function rankingDe(filas) {
    var g = {};
    filas.forEach(function (f) {
      if (estado.sinMedios && ES_MEDIO[f.empresa]) return;
      var x = g[f.empresa] || (g[f.empresa] = { clave: f.empresa, numero: 0, importe: 0, enEuskadi: 0, rebajas: [] });
      x.numero++;
      x.importe += f.importe;
      if (f.euskadi) x.enEuskadi++;
      if (f.rebaja > 0) x.rebajas.push(f.rebaja);
    });
    return Object.keys(g).map(function (k) { return g[k]; });
  }

  function posiciones(lista) {
    var pos = {};
    lista.slice().sort(function (a, b) { return b.numero - a.numero || b.importe - a.importe; })
      .forEach(function (x, i) { pos[x.clave] = i + 1; });
    return pos;
  }

  function pintarCompetencia() {
    var seguidas = leerSeguidas();
    var soloSeguidas = estado.competencia === "sigo";
    var filas = FILAS.filter(function (f) { return pasaFiltros(f) && pasaTexto(f); });
    var lista = rankingDe(filas);
    var posicion = posiciones(lista);

    // Posición del año anterior, con los mismos filtros.
    var antes = null;
    if (estado.anio) {
      var anio = estado.anio;
      estado.anio = String(Number(anio) - 1);
      antes = posiciones(rankingDe(FILAS.filter(function (f) { return pasaFiltros(f) && pasaTexto(f); })));
      estado.anio = anio;
    }

    lista.forEach(function (x) {
      var e = D.empresa[x.clave];
      x.nif = nifPublicable(e[0]);
      x.seguida = !!(x.nif && seguidas[x.nif]);
      x.euskadi = x.enEuskadi / x.numero;
      var lic = x.nif && LICITADORAS[x.nif];
      x.exitoDatos = lic && lic[0] >= MIN_CONCURSOS_EXITO ? lic : null;
      x.exito = x.exitoDatos ? x.exitoDatos[1] / x.exitoDatos[0] : -1;
      x.rebaja = x.rebajas.length ? mediana(x.rebajas) : -1;
    });

    // Cifras de arriba: del mercado entero con estos filtros.
    var importeTotal = lista.reduce(function (s, x) { return s + x.importe; }, 0);
    var top5 = lista.slice().sort(function (a, b) { return b.importe - a.importe; }).slice(0, 5)
      .reduce(function (s, x) { return s + x.importe; }, 0);
    var nuevas = estado.anio ? lista.filter(function (x) { return (PRIMERA_FECHA[x.clave] || "").slice(0, 4) === estado.anio; }).length : null;
    pintarKpis(document.getElementById("competencia-kpis"), [
      ["Empresas que ganan", miles(lista.length)],
      ["Las 5 primeras se llevan", importeTotal ? porcentaje(top5 / importeTotal) : "—", "del importe adjudicado"],
      nuevas == null
        ? ["Que sigues, entre ellas", miles(lista.filter(function (x) { return x.seguida; }).length)]
        : ["Nuevas en " + estado.anio, miles(nuevas), "primer contrato desde 2021"],
    ]);

    if (soloSeguidas) lista = lista.filter(function (x) { return x.seguida; });
    var col = estado.ordenRanking;
    lista.sort(function (a, b) { return b[col] - a[col] || b.numero - a.numero || b.importe - a.importe; });

    var vacio = document.getElementById("competencia-vacio");
    vacio.hidden = lista.length > 0;
    vacio.innerHTML = soloSeguidas
      ? "Todavía no sigues a ninguna empresa con estos filtros. Pulsa el marcador de una fila en «Todas las que compiten» (o en <a class=\"enlace\" href=\"#/empresas\">Empresas</a>)."
      : "Ninguna empresa gana con estos filtros.";
    var tabla = document.getElementById("competencia-tabla");
    tabla.parentNode.hidden = !lista.length;

    var total = lista.length;
    var paginas = Math.max(1, Math.ceil(total / FILAS_POR_PAGINA));
    if (estado.pagina >= paginas) estado.pagina = paginas - 1;
    var desde = estado.pagina * FILAS_POR_PAGINA;
    var visibles = lista.slice(desde, desde + FILAS_POR_PAGINA);
    document.getElementById("competencia-conteo").textContent = total
      ? miles(desde + 1) + "–" + miles(desde + visibles.length) + " de " + miles(total) + " empresas"
      : "";
    var elPag = document.getElementById("competencia-paginacion");
    elPag.hidden = paginas < 2;
    elPag.innerHTML = "<span>Página " + (estado.pagina + 1) + " de " + miles(paginas) + "</span>" +
      '<button type="button" class="boton boton--contorno" data-paso="-1"' + (estado.pagina === 0 ? " disabled" : "") + ">Anterior</button>" +
      '<button type="button" class="boton boton--contorno" data-paso="1"' + (estado.pagina >= paginas - 1 ? " disabled" : "") + ">Siguiente</button>";
    if (!lista.length) return;

    var maxNumero = lista.reduce(function (m, x) { return Math.max(m, x.numero); }, 0) || 1;
    var maxImporte = lista.reduce(function (m, x) { return Math.max(m, x.importe); }, 0) || 1;
    var celdaBarra = function (texto, fraccion) {
      return '<span class="ranking__cifra">' + texto + '</span><span class="ranking__pista"><span class="ranking__barra" style="width:' +
        (100 * fraccion).toFixed(1) + '%"></span></span>';
    };
    var flecha = function (x) {
      if (!antes) return "";
      var p = antes[x.clave];
      if (!p) return '<span class="ranking__cambio ranking__cambio--nueva" title="No ganó nada el año anterior">nueva</span>';
      var d = p - posicion[x.clave];
      if (!d) return "";
      return '<span class="ranking__cambio ranking__cambio--' + (d > 0 ? "sube" : "baja") + '" title="Puesto ' + p + " el año anterior\">" +
        (d > 0 ? "▲" : "▼") + Math.abs(d) + "</span>";
    };

    tabla.innerHTML = '<thead><tr><th class="col-posicion" scope="col">#</th><th scope="col">Empresa</th>' +
      COLUMNAS_RANKING.map(function (c) {
        return '<th scope="col" class="' + (c[0] === "euskadi" ? "col-reparto" : "num") + (c[0] === "rebaja" ? " col-secundaria" : "") + '"' +
          (c[0] === col ? ' aria-sort="descending"' : "") + '><button type="button" class="tabla__orden" data-orden="' + c[0] + '">' + c[1] + Nav.icono("chevron") + "</button></th>";
      }).join("") + '<th scope="col" class="col-seguir"><span class="visualmente-oculto">Seguir</span></th></tr></thead><tbody>' +
      visibles.map(function (x) {
        var e = D.empresa[x.clave];
        return '<tr' + (x.seguida ? ' class="ranking__seguida"' : "") + '><td class="col-posicion">' + miles(posicion[x.clave]) + flecha(x) + "</td>" +
          '<td><a href="#/empresa/' + x.clave + '">' + escaparHtml(e[1]) + "</a>" + (x.nif ? '<span class="tabla__sub">NIF ' + escaparHtml(x.nif) + "</span>" : "") + "</td>" +
          '<td class="num ranking__celda">' + celdaBarra(miles(x.numero), x.numero / maxNumero) + "</td>" +
          '<td class="num ranking__celda">' + celdaBarra(euros(x.importe), x.importe / maxImporte) + "</td>" +
          '<td class="col-reparto"><span class="ranking__reparto" title="' + porcentaje(x.euskadi) + " en Euskadi, " + porcentaje(1 - x.euskadi) + ' en el Estado">' +
            '<span class="ranking__euskadi" style="width:' + (100 * x.euskadi).toFixed(1) + '%"></span></span>' +
            '<span class="tabla__sub">' + (x.euskadi >= 0.5 ? porcentaje(x.euskadi) + " Euskadi" : porcentaje(1 - x.euskadi) + " Estado") + "</span></td>" +
          '<td class="num"' + (x.exitoDatos ? ' title="Gana ' + x.exitoDatos[1] + " de " + x.exitoDatos[0] + ' concursos a los que se presenta"' : "") + ">" +
            (x.exitoDatos ? porcentaje(x.exito) : "—") + "</td>" +
          '<td class="num col-secundaria">' + (x.rebaja >= 0 ? porcentaje(x.rebaja) : "—") + "</td>" +
          '<td class="col-seguir">' + botonSeguir(e, seguidas) + "</td></tr>";
      }).join("") + "</tbody>";
  }

  document.getElementById("vista-competencia").addEventListener("click", function (ev) {
    var s = ev.target.closest && ev.target.closest("[data-seguir-lista]");
    if (s) {
      alternarSeguida(s.getAttribute("data-seguir-lista"), s.getAttribute("data-nombre"));
      pintarCompetencia();
      return;
    }
    var m = ev.target.closest && ev.target.closest("#boton-sin-medios");
    if (m) {
      estado.sinMedios = !estado.sinMedios;
      m.setAttribute("aria-pressed", estado.sinMedios ? "true" : "false");
      estado.pagina = 0;
      pintarCompetencia();
      return;
    }
    var o = ev.target.closest && ev.target.closest("[data-orden]");
    if (o) {
      estado.ordenRanking = o.getAttribute("data-orden");
      estado.pagina = 0;
      pintarCompetencia();
      return;
    }
    var p = ev.target.closest && ev.target.closest("#competencia-paginacion button[data-paso]");
    if (p && !p.disabled) {
      estado.pagina += Number(p.getAttribute("data-paso"));
      pintarCompetencia();
      document.getElementById("herramientas").scrollIntoView({ block: "start" });
    }
  });

  // ---------- Rutas ----------

  function pintarCabecera() {
    var v = VISTAS[estado.vista];
    var html;
    if (estado.vista === "empresa") {
      var e = D.empresa[estado.id];
      var nifSeguible = nifPublicable(e[0]);
      var seguida = nifSeguible && leerSeguidas()[nifSeguible];
      html = '<nav class="migas" aria-label="Ruta"><a href="#/empresas">Empresas</a><span aria-hidden="true">›</span><span>Ficha de empresa</span></nav>' +
        '<header class="pagina__cabecera"><div class="pagina__titulo"><h1>' + escaparHtml(e[1]) + "</h1>" +
        (nifSeguible ? '<p><button type="button" class="boton boton--contorno" data-seguir="' + escaparHtml(nifSeguible) + '" aria-pressed="' + (seguida ? "true" : "false") + '">' +
          (seguida ? "Siguiendo · dejar de seguir" : "Seguir") + "</button></p>" : "") +
        (nifPublicable(e[0]) ? '<p class="pagina__descripcion">NIF ' + escaparHtml(e[0]) + "</p>" : "") + "</div></header>";
      document.title = e[1] + " — Radar de licitaciones";
    } else if (estado.vista === "organismo") {
      var nombre = D.organismo[estado.id];
      html = '<nav class="migas" aria-label="Ruta"><a href="#/organismos">Organismos</a><span aria-hidden="true">›</span><span>Ficha de organismo</span></nav>' +
        '<header class="pagina__cabecera"><div class="pagina__titulo"><h1>' + escaparHtml(nombre) + "</h1></div></header>";
      document.title = nombre + " — Radar de licitaciones";
    } else {
      html = '<header class="pagina__cabecera"><div class="pagina__titulo"><h1>' + v.titulo + "</h1></div></header>";
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
    elVistas.competencia.hidden = estado.vista !== "competencia";
    elCampoTexto.hidden = esFicha;

    if (estado.vista === "mercado") pintarMercado();
    else if (estado.vista === "competencia") pintarCompetencia();
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

    // Filtros que llegan del radar («Análisis de mercado con estos
    // filtros»): categoría por nombre, lugar y ámbito con los mismos valores.
    var pr = leida.params;
    if (pr.cat && CATEGORIAS.indexOf(pr.cat) !== -1) {
      estado.categoria = CATEGORIAS.indexOf(pr.cat);
      elCategoria.value = String(estado.categoria);
    }
    if (pr.lugar) {
      elLugar.value = pr.lugar;
      // Un lugar que no existe aquí no se aplica, y el selector vuelve a
      // enseñar el filtro que sigue activo.
      if (elLugar.value === pr.lugar) estado.lugar = pr.lugar;
      else elLugar.value = estado.lugar;
    }
    if (pr.ambito === "Estado" || pr.ambito === "Euskadi") {
      estado.ambito = pr.ambito;
      Array.prototype.forEach.call(document.getElementById("segmented-ambito").children, function (b) {
        b.setAttribute("aria-pressed", b.textContent === pr.ambito ? "true" : "false");
      });
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

  elCabecera.addEventListener("click", function (ev) {
    var b = ev.target.closest && ev.target.closest("[data-seguir]");
    if (!b) return;
    var sigue = alternarSeguida(b.getAttribute("data-seguir"), D.empresa[estado.id][1]);
    b.setAttribute("aria-pressed", sigue ? "true" : "false");
    b.textContent = sigue ? "Siguiendo · dejar de seguir" : "Seguir";
  });

  window.addEventListener("hashchange", function () { navegar(false); });
  navegar(true);
})();
