// Navegación común a las dos páginas (index.html: radar; historico.html:
// competencia). Pinta la barra lateral, marca la sección activa y gestiona el
// cajón en móvil. Las secciones de cada página son rutas de hash (#/ruta),
// así que cada vista tiene su propia URL y el botón "atrás" funciona.
(function () {
  "use strict";

  function svg(contenido, clase) {
    return '<svg class="' + (clase || "icono") + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + contenido + "</svg>";
  }

  var ICONOS = {
    radar: '<circle cx="12" cy="12" r="2"/><path d="M16.2 7.8a6 6 0 0 1 0 8.4M7.8 16.2a6 6 0 0 1 0-8.4M19.1 4.9a10 10 0 0 1 0 14.2M4.9 19.1a10 10 0 0 1 0-14.2"/>',
    inicio: '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
    documento: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
    globo: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    reloj: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    premio: '<circle cx="12" cy="9" r="6"/><path d="M8.5 14 7 22l5-3 5 3-1.5-8"/>',
    grafico: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    edificio: '<rect x="5" y="3" width="14" height="18" rx="1.5"/><path d="M9 7h2M13 7h2M9 11h2M13 11h2M9 15h2M13 15h2"/>',
    institucion: '<path d="M3 21h18M5 21V10M9.5 21V10M14.5 21V10M19 21V10M12 3 3 8h18z"/>',
    menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
    cerrar: '<path d="M6 6l12 12M18 6 6 18"/>',
    chevron: '<path d="M6 9l6 6 6-6"/>',
    flecha: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    externo: '<path d="M14 5h5v5M19 5l-8 8M18 14v4a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h4"/>',
    lugar: '<path d="M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
    calendario: '<rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M8 3v4M16 3v4M3.5 10h17"/>',
    euro: '<path d="M18 6.5A7 7 0 1 0 18 17.5M4 10h9M4 14h9"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
    filtro: '<path d="M4 5h16l-6 7.5V19l-4-2v-4.5z"/>',
  };

  function icono(nombre, clase) { return svg(ICONOS[nombre], clase); }

  // [clave, etiqueta, página, ruta, icono]
  var GRUPOS = [
    { items: [["inicio", "Inicio", "index.html", "#/inicio", "inicio"]] },
    {
      titulo: "Oportunidades",
      items: [
        ["licitaciones", "Licitaciones", "index.html", "#/licitaciones/recientes", "documento"],
        ["calls", "Calls for proposals UE", "index.html", "#/calls", "globo"],
      ],
    },
    {
      titulo: "Prospección comercial",
      items: [["menores", "Contratos menores por vencer", "index.html", "#/menores", "reloj"]],
    },
    {
      titulo: "Competencia",
      items: [
        ["adjudicaciones", "Adjudicaciones recientes", "index.html", "#/adjudicaciones", "premio"],
        ["mercado", "Análisis de mercado", "historico.html", "#/mercado", "grafico"],
        ["empresas", "Empresas", "historico.html", "#/empresas", "edificio"],
        ["organismos", "Organismos", "historico.html", "#/organismos", "institucion"],
      ],
    },
    {
      titulo: "Sobre el radar",
      items: [["filtro", "Cómo se filtra", "filtro.html", "", "filtro"]],
    },
  ];

  var CLAVE_CONTEOS = "radar-conteos";
  var esHistorico = /historico(\.html)?$/.test(location.pathname);
  var paginaActual = esHistorico ? "historico.html" : /filtro(\.html)?$/.test(location.pathname) ? "filtro.html" : "index.html";

  // Los recuentos del radar solo se pueden calcular en index.html (es la
  // única página que carga tenders-data.js); se guardan para que la barra
  // lateral los muestre también en historico.html.
  function leerConteos() {
    try { return JSON.parse(localStorage.getItem(CLAVE_CONTEOS)) || {}; } catch (e) { return {}; }
  }

  function guardarConteos(conteos) {
    try { localStorage.setItem(CLAVE_CONTEOS, JSON.stringify(conteos)); } catch (e) { /* sin almacenamiento: no pasa nada */ }
    pintarConteos(conteos);
  }

  function pintarConteos(conteos) {
    Array.prototype.forEach.call(document.querySelectorAll(".nav__conteo"), function (el) {
      var n = conteos[el.getAttribute("data-clave")];
      el.textContent = n == null ? "" : String(n);
    });
  }

  function enlace(pagina, ruta) {
    // En la misma página, solo el hash: así cambiar de sección no recarga.
    return pagina === paginaActual ? ruta : pagina + ruta;
  }

  var elLateral = document.getElementById("lateral");
  var elAbrir = document.getElementById("abrir-menu");

  function pintar() {
    var html =
      '<a class="marca" href="' + enlace("index.html", "#/inicio") + '">' +
        '<span class="marca__simbolo">' + icono("radar", "") + "</span>" +
        '<span class="marca__texto"><span class="marca__nombre">Radar de licitaciones</span>' +
        '<span class="marca__lema">Marketing digital y publicidad</span></span>' +
      "</a>" +
      '<nav class="nav" aria-label="Secciones">';
    GRUPOS.forEach(function (grupo) {
      if (grupo.titulo) html += '<p class="nav__grupo">' + grupo.titulo + "</p>";
      grupo.items.forEach(function (it) {
        html += '<a class="nav__enlace" data-clave="' + it[0] + '" href="' + enlace(it[2], it[3]) + '">' +
          icono(it[4]) + "<span>" + it[1] + '</span><span class="nav__conteo" data-clave="' + it[0] + '"></span></a>';
      });
    });
    html += "</nav>" +
      '<p class="lateral__pie">Fuentes: TED, PLACSP, portal de contratación de Euskadi y EU Funding &amp; Tenders.<br><span id="lateral-actualizado"></span></p>';
    elLateral.innerHTML = html;
    pintarConteos(leerConteos());

    var velo = document.createElement("button");
    velo.type = "button";
    velo.className = "velo";
    velo.setAttribute("aria-label", "Cerrar menú");
    velo.tabIndex = -1;
    document.body.appendChild(velo);

    function abrir(si) {
      elLateral.setAttribute("data-abierto", si ? "true" : "false");
      velo.setAttribute("data-abierto", si ? "true" : "false");
      if (elAbrir) elAbrir.setAttribute("aria-expanded", si ? "true" : "false");
      if (si) {
        var primero = elLateral.querySelector('.nav__enlace[aria-current="page"]') || elLateral.querySelector(".nav__enlace");
        if (primero) primero.focus();
      }
    }
    function cerrarYDevolverFoco() {
      if (elLateral.getAttribute("data-abierto") !== "true") return;
      abrir(false);
      if (elAbrir) elAbrir.focus();
    }

    if (elAbrir) {
      elAbrir.innerHTML = icono("menu");
      elAbrir.addEventListener("click", function () { abrir(elLateral.getAttribute("data-abierto") !== "true"); });
    }
    velo.addEventListener("click", cerrarYDevolverFoco);
    document.addEventListener("keydown", function (ev) { if (ev.key === "Escape") cerrarYDevolverFoco(); });
    elLateral.addEventListener("click", function (ev) {
      if (ev.target.closest && ev.target.closest("a")) abrir(false);
    });
  }

  function activar(clave) {
    Array.prototype.forEach.call(elLateral.querySelectorAll(".nav__enlace"), function (a) {
      if (a.getAttribute("data-clave") === clave) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
  }

  // Ruta de hash: "#/licitaciones/abiertas?cat=SEO" -> { ruta, params }.
  function leerRuta() {
    var hash = location.hash.replace(/^#\/?/, "");
    var corte = hash.indexOf("?");
    var params = {};
    if (corte !== -1) {
      hash.slice(corte + 1).split("&").forEach(function (par) {
        var i = par.indexOf("=");
        if (i > 0) {
          try { params[par.slice(0, i)] = decodeURIComponent(par.slice(i + 1)); } catch (e) { /* parámetro mal formado: se ignora */ }
        }
      });
      hash = hash.slice(0, corte);
    }
    return { ruta: hash.replace(/\/$/, ""), params: params };
  }

  function actualizado(texto) {
    var el = document.getElementById("lateral-actualizado");
    if (el) el.textContent = texto;
  }

  pintar();

  window.RadarNav = {
    icono: icono,
    activar: activar,
    guardarConteos: guardarConteos,
    leerRuta: leerRuta,
    actualizado: actualizado,
  };
})();
