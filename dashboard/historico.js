(function () {
  "use strict";

  // Formato compacto generado por scrapers/historico_adjudicaciones.py
  // (_publicar): diccionarios + filas por columnas.
  //   exp:   [organismo, euskadi, tipo, procedimiento, menor, mascara_categorias]
  //   lotes: [exp, empresa, fecha, importe, ofertas, pyme]
  // El título y el enlace de cada expediente no vienen aquí (son el 75% del
  // peso): están en historico-detalle/NN.js, repartidos por empresa, y se
  // cargan al abrir una ficha.
  var H = window.HISTORICO;
  if (!H || !H.exp || !H.exp.length) {
    document.getElementById("sin-datos").hidden = false;
    return;
  }

  var D = H.dic;
  var CATEGORIAS = H.categorias;
  var TOP_EMPRESAS = 20;
  var TOP_ORGANISMOS = 12;
  var MAX_CONTRATOS_FICHA = 150;

  var fmtNumero = new Intl.NumberFormat("es-ES");
  var fmtEuros = new Intl.NumberFormat("es-ES", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });

  function euros(v) {
    if (!v) return "—";
    if (v >= 1e6) return (v / 1e6).toLocaleString("es-ES", { maximumFractionDigits: 1 }) + " M€";
    if (v >= 1e4) return Math.round(v / 1e3).toLocaleString("es-ES") + " k€";
    return fmtEuros.format(v);
  }

  function escaparHtml(str) {
    var div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML;
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
  var FILAS = H.lotes.map(function (l) {
    var e = H.exp[l[0]];
    return {
      exp: l[0], empresa: l[1], anio: l[2] ? l[2].slice(0, 4) : "", fecha: l[2] || "",
      importe: l[3] || 0, ofertas: l[4], pyme: l[5],
      organismo: e[0], euskadi: e[1] === 1, procedimiento: e[3], menor: e[4] === 1, mascara: e[5],
    };
  });
  // Texto buscable por empresa (nombre + NIF) y organismo, en minúsculas.
  var TEXTO_EMPRESA = D.empresa.map(function (x) { return ((x[1] || "") + " " + (x[0] || "")).toLowerCase(); });
  var TEXTO_ORGANISMO = D.organismo.map(function (x) { return x.toLowerCase(); });

  var estado = { texto: "", ambito: "", menor: "", anio: "", categoria: -1, metricaEvolucion: "importe", metricaEmpresas: "importe" };

  // ---------- Controles ----------

  function segmented(id, opciones, clave) {
    var el = document.getElementById(id);
    opciones.forEach(function (par) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "segmented__opcion";
      b.textContent = par[1];
      b.setAttribute("role", "radio");
      b.setAttribute("aria-pressed", estado[clave] === par[0] ? "true" : "false");
      b.addEventListener("click", function () {
        estado[clave] = par[0];
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
  elAnio.addEventListener("change", function () { estado.anio = elAnio.value; pintar(); });

  var elCategoria = document.getElementById("filtro-categoria");
  elCategoria.innerHTML = '<option value="-1">Todas las categorías</option>' + CATEGORIAS
    .map(function (c, i) { return '<option value="' + i + '">' + escaparHtml(c) + "</option>"; }).join("");
  elCategoria.addEventListener("change", function () { estado.categoria = parseInt(elCategoria.value, 10); pintar(); });

  var temporizador;
  document.getElementById("filtro-texto").addEventListener("input", function (ev) {
    clearTimeout(temporizador);
    temporizador = setTimeout(function () { estado.texto = ev.target.value.trim().toLowerCase(); pintar(); }, 180);
  });

  function pasa(f) {
    if (estado.anio && f.anio !== estado.anio) return false;
    if (!estado.anio && f.anio < "2021") return false;
    if (estado.ambito && (estado.ambito === "Euskadi") !== f.euskadi) return false;
    if (estado.menor && (estado.menor === "menor") !== f.menor) return false;
    if (estado.categoria >= 0 && !(f.mascara & (1 << estado.categoria))) return false;
    if (estado.texto && TEXTO_EMPRESA[f.empresa].indexOf(estado.texto) === -1 &&
        TEXTO_ORGANISMO[f.organismo].indexOf(estado.texto) === -1) return false;
    return true;
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

  // ---------- Pintado ----------

  function barras(el, lista, metrica, etiqueta, alPulsar) {
    var max = lista.reduce(function (m, x) { return Math.max(m, x[metrica]); }, 0) || 1;
    el.innerHTML = "";
    if (!lista.length) {
      el.innerHTML = '<li class="barras__vacio">Sin datos con estos filtros.</li>';
      return;
    }
    lista.forEach(function (x) {
      var li = document.createElement("li");
      li.className = "barras__fila";
      var nombre = escaparHtml(etiqueta(x));
      var detalle = metrica === "importe"
        ? euros(x.importe) + ' <span class="barras__sec">· ' + fmtNumero.format(x.numero) + "</span>"
        : fmtNumero.format(x.numero) + ' <span class="barras__sec">· ' + euros(x.importe) + "</span>";
      var contenido =
        '<span class="barras__nombre">' + nombre + "</span>" +
        '<span class="barras__pista"><span class="barras__relleno" style="width:' + (100 * x[metrica] / max).toFixed(1) + '%"></span></span>' +
        '<span class="barras__valor">' + detalle + "</span>";
      if (alPulsar) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "barras__boton";
        b.innerHTML = contenido;
        b.addEventListener("click", function () { alPulsar(x); });
        li.appendChild(b);
      } else {
        li.innerHTML = contenido;
      }
      el.appendChild(li);
    });
  }

  function kpis(filas) {
    var importe = 0, conImporte = 0, empresas = {}, organismos = {}, ofertas = 0, conOfertas = 0, pymes = 0, conPyme = 0;
    filas.forEach(function (f) {
      if (f.importe) { importe += f.importe; conImporte++; }
      empresas[f.empresa] = true;
      organismos[f.organismo] = true;
      if (f.ofertas) { ofertas += f.ofertas; conOfertas++; }
      if (f.pyme != null) { conPyme++; pymes += f.pyme; }
    });
    var items = [
      ["Adjudicaciones", fmtNumero.format(filas.length)],
      ["Importe adjudicado", euros(importe)],
      ["Empresas distintas", fmtNumero.format(Object.keys(empresas).length)],
      ["Organismos", fmtNumero.format(Object.keys(organismos).length)],
      ["Importe medio", conImporte ? euros(importe / conImporte) : "—"],
      ["Ofertas por licitación", conOfertas ? (ofertas / conOfertas).toLocaleString("es-ES", { maximumFractionDigits: 1 }) : "—"],
      ["Ganadas por pymes", conPyme ? Math.round(100 * pymes / conPyme) + " %" : "—"],
    ];
    document.getElementById("kpis").innerHTML = items.map(function (k) {
      return '<div class="kpi"><span class="kpi__valor">' + k[1] + '</span><span class="kpi__etiqueta">' + k[0] + "</span></div>";
    }).join("");
  }

  function evolucion(filas) {
    var lista = agrupar(filas, function (f) { return f.anio >= "2021" ? f.anio : null; })
      .sort(function (a, b) { return a.clave < b.clave ? -1 : 1; });
    var m = estado.metricaEvolucion;
    var max = lista.reduce(function (acc, x) { return Math.max(acc, x[m]); }, 0) || 1;
    document.getElementById("grafico-evolucion").innerHTML = lista.map(function (x) {
      var valor = m === "importe" ? euros(x.importe) : fmtNumero.format(x.numero);
      return '<div class="columnas__col"><span class="columnas__valor">' + valor + "</span>" +
        '<span class="columnas__pista"><span class="columnas__relleno" style="height:' + (100 * x[m] / max).toFixed(1) + '%"></span></span>' +
        '<span class="columnas__etiqueta">' + x.clave + "</span></div>";
    }).join("") || '<p class="barras__vacio">Sin datos con estos filtros.</p>';
  }

  function empresas(filas) {
    var m = estado.metricaEmpresas;
    var todas = ordenar(agrupar(filas, function (f) { return f.empresa; }), m);
    var total = todas.reduce(function (s, x) { return s + x[m]; }, 0);
    var top10 = todas.slice(0, 10).reduce(function (s, x) { return s + x[m]; }, 0);
    document.getElementById("nota-concentracion").textContent = total
      ? "Las 10 primeras se llevan el " + Math.round(100 * top10 / total) + " % del " +
        (m === "importe" ? "importe adjudicado" : "número de adjudicaciones") + " (" + fmtNumero.format(todas.length) + " empresas en total)."
      : "";
    barras(document.getElementById("grafico-empresas"), todas.slice(0, TOP_EMPRESAS), m,
      function (x) { return D.empresa[x.clave][1]; }, function (x) { abrirFicha(x.clave); });
  }

  function categorias(filas) {
    var g = CATEGORIAS.map(function (c, i) { return { clave: i, numero: 0, importe: 0 }; });
    filas.forEach(function (f) {
      for (var i = 0; i < CATEGORIAS.length; i++) {
        if (f.mascara & (1 << i)) { g[i].numero++; g[i].importe += f.importe; }
      }
    });
    barras(document.getElementById("grafico-categorias"),
      ordenar(g.filter(function (x) { return x.numero; }), "numero"), "numero",
      function (x) { return CATEGORIAS[x.clave]; });
  }

  function pintar() {
    var filas = FILAS.filter(pasa);
    kpis(filas);
    evolucion(filas);
    empresas(filas);
    categorias(filas);
    barras(document.getElementById("grafico-organismos"),
      ordenar(agrupar(filas, function (f) { return f.organismo; }), "numero").slice(0, TOP_ORGANISMOS), "numero",
      function (x) { return D.organismo[x.clave]; });
    barras(document.getElementById("grafico-procedimientos"),
      ordenar(agrupar(filas, function (f) { return f.menor ? "menor" : f.procedimiento; }), "numero"), "numero",
      function (x) { return x.clave === "menor" ? "Contrato menor" : D.procedimiento[x.clave]; });
    var tramos = [[1, 1, "1 oferta"], [2, 2, "2 ofertas"], [3, 5, "3 a 5"], [6, 10, "6 a 10"], [11, 1e9, "Más de 10"]];
    barras(document.getElementById("grafico-ofertas"),
      tramos.map(function (t, i) {
        var x = { clave: i, numero: 0, importe: 0 };
        filas.forEach(function (f) { if (f.ofertas >= t[0] && f.ofertas <= t[1]) { x.numero++; x.importe += f.importe; } });
        return x;
      }).filter(function (x) { return x.numero; }), "numero",
      function (x) { return tramos[x.clave][2]; });
  }

  // ---------- Ficha de empresa ----------

  var elFicha = document.getElementById("ficha-empresa");
  document.getElementById("ficha-cerrar").addEventListener("click", function () { elFicha.close(); });
  elFicha.addEventListener("click", function (ev) { if (ev.target === elFicha) elFicha.close(); });

  function listaSimple(titulo, lista, etiqueta) {
    return '<section class="ficha__bloque"><h3>' + titulo + '</h3><ol class="ficha__lista">' +
      lista.map(function (x) {
        return "<li><span>" + escaparHtml(etiqueta(x)) + '</span><span class="ficha__cifra">' +
          fmtNumero.format(x.numero) + " · " + euros(x.importe) + "</span></li>";
      }).join("") + "</ol></section>";
  }

  function abrirFicha(clave) {
    var idEmpresa = Number(clave);  // agrupar() devuelve las claves como texto
    // La ficha respeta año/ámbito/tipo/categoría, pero no la búsqueda de
    // texto (si se busca un organismo, se quiere ver todo lo de la empresa).
    var texto = estado.texto;
    estado.texto = "";
    var filas = FILAS.filter(function (f) { return f.empresa === idEmpresa && pasa(f); });
    estado.texto = texto;

    var empresa = D.empresa[idEmpresa];
    var importe = filas.reduce(function (s, f) { return s + f.importe; }, 0);
    var anios = filas.map(function (f) { return f.anio; }).filter(Boolean).sort();
    document.getElementById("ficha-titulo").textContent = empresa[1];
    document.getElementById("ficha-nif").textContent = (empresa[0] ? "NIF " + empresa[0] + " · " : "") +
      fmtNumero.format(filas.length) + " adjudicaciones · " + euros(importe) +
      (anios.length ? " · " + anios[0] + "–" + anios[anios.length - 1] : "");

    var cats = CATEGORIAS.map(function (c, i) { return { clave: i, numero: 0, importe: 0 }; });
    filas.forEach(function (f) {
      for (var i = 0; i < CATEGORIAS.length; i++) if (f.mascara & (1 << i)) { cats[i].numero++; cats[i].importe += f.importe; }
    });

    var contratos = filas.slice().sort(function (a, b) { return a.fecha < b.fecha ? 1 : -1; }).slice(0, MAX_CONTRATOS_FICHA);
    var html =
      '<div class="ficha__rejilla">' +
      listaSimple("Organismos a los que vende", ordenar(agrupar(filas, function (f) { return f.organismo; }), "numero").slice(0, 10),
        function (x) { return D.organismo[x.clave]; }) +
      listaSimple("Categorías", ordenar(cats.filter(function (x) { return x.numero; }), "numero"),
        function (x) { return CATEGORIAS[x.clave]; }) +
      listaSimple("Procedimiento", ordenar(agrupar(filas, function (f) { return f.menor ? "menor" : f.procedimiento; }), "numero"),
        function (x) { return x.clave === "menor" ? "Contrato menor" : D.procedimiento[x.clave]; }) +
      listaSimple("Por año", agrupar(filas, function (f) { return f.anio || null; }).sort(function (a, b) { return a.clave < b.clave ? 1 : -1; }),
        function (x) { return x.clave; }) +
      "</div>" +
      '<section class="ficha__bloque"><h3>Adjudicaciones' + (filas.length > MAX_CONTRATOS_FICHA ? " (las " + MAX_CONTRATOS_FICHA + " más recientes)" : "") + "</h3>" +
      '<div class="ficha__tabla-envoltorio" id="ficha-contratos" aria-live="polite"><p class="panel__nota">Cargando contratos…</p></div></section>';
    document.getElementById("ficha-cuerpo").innerHTML = html;
    elFicha.showModal();
    document.getElementById("ficha-cuerpo").scrollTop = 0;

    cargarDetalle(idEmpresa).then(function (detalle) {
      // Si entretanto se ha abierto la ficha de otra empresa, no se pinta.
      var destino = document.getElementById("ficha-contratos");
      if (!destino || document.getElementById("ficha-titulo").textContent !== empresa[1]) return;
      destino.innerHTML =
        '<table class="ficha__tabla"><thead><tr><th>Fecha</th><th>Contrato</th><th>Organismo</th><th class="num">Importe</th></tr></thead><tbody>' +
        contratos.map(function (f) {
          var d = detalle[f.exp] || ["(título no disponible)", ""];
          var enlace = enlaceCompleto(d[1]);
          var titulo = escaparHtml(d[0]) + (f.menor ? ' <span class="ficha__etiqueta">menor</span>' : "");
          return "<tr><td class=\"num\">" + escaparHtml(f.fecha) + "</td><td>" +
            (enlace ? '<a href="' + escaparHtml(enlace) + '" target="_blank" rel="noopener">' + titulo + "</a>" : titulo) +
            "</td><td>" + escaparHtml(D.organismo[f.organismo]) + '</td><td class="num">' + euros(f.importe) + "</td></tr>";
        }).join("") + "</tbody></table>";
    }).catch(function () {
      var destino = document.getElementById("ficha-contratos");
      if (destino) destino.innerHTML = '<p class="panel__nota">No se ha podido cargar el detalle de los contratos. Cierra la ficha y vuelve a abrirla para reintentar.</p>';
    });
  }

  document.getElementById("fecha-generacion").textContent = "Histórico actualizado el " + H.actualizado + ".";
  pintar();
})();
