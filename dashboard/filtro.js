// Página "Cómo se filtra": el embudo de la última actualización y los
// descartes revisables. Los datos los genera normalizar._publicar_filtro
// (filtro-data.js) a partir de lo que apunta clasificar.py.
(function () {
  "use strict";

  var Nav = window.RadarNav;
  var D = window.FILTRO_DATA;
  var el = document.getElementById("filtro");
  Nav.activar("filtro");

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function miles(n) { return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, "."); }
  function num(n) { return n == null ? "—" : miles(n); }
  var MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  function fecha(s) {
    var p = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || "");
    return p ? Number(p[3]) + " " + MESES[Number(p[2]) - 1] + " " + p[1] : "Sin plazo publicado";
  }

  if (!D) {
    el.innerHTML = '<p class="sin-resultados">Todavía no hay datos del filtro: aparecen tras la próxima actualización.</p>';
    return;
  }
  Nav.actualizado("Filtro del " + fecha(D.fecha));

  var TIPOS = [
    ["licitacion", "Licitaciones"],
    ["convocatoria_ue", "Calls for proposals UE"],
    ["adjudicacion", "Adjudicaciones"],
    ["contrato_menor_venciendo", "Contratos menores"],
  ];
  // Qué mira cada fuente antes del texto (columna "Otros filtros").
  var OTROS = {
    placsp: "expedientes que ya no están en plazo (evaluación, adjudicados, anulados)",
    placsp_agregadas: "lo mismo, y lo de la plataforma de Euskadi, que llega por su propia API",
  };

  function filaEmbudo(e) {
    if (e.sin_datos_nuevos) {
      return "<tr><th scope=\"row\">" + esc(e.etiqueta) + '</th><td colspan="4" class="tabla-embudo__aviso">Sin datos nuevos esta noche: se reutiliza lo de la última vez que respondió</td>' +
        '<td class="tabla-embudo__entra" data-etiqueta="Entran">' + num(e.relevantes) + "</td></tr>";
    }
    // data-etiqueta: en móvil cada fila se apila y la cifra lleva su nombre.
    return "<tr><th scope=\"row\">" + esc(e.etiqueta) + "</th>" +
      '<td data-etiqueta="Traídas">' + num(e.extraidas) + "</td>" +
      '<td data-etiqueta="Fuera por estado u origen"' + (OTROS[e.prefijo] && e.otros_filtros ? ' title="' + esc(OTROS[e.prefijo]) + '"' : "") + ">" + num(e.otros_filtros) + "</td>" +
      '<td data-etiqueta="Sin palabra clave">' + num(e.sin_categoria) + "</td>" +
      '<td data-etiqueta="Servicio no ofrecido">' + num(e.servicio_no_ofrecido) + "</td>" +
      '<td class="tabla-embudo__entra" data-etiqueta="Entran">' + num(e.relevantes_nuevas) +
      (e.conservadas ? '<span class="tabla-embudo__extra"> + ' + num(e.conservadas) + " de días anteriores</span>" : "") + "</td></tr>";
  }

  function tablaTipo(tipo, nombre) {
    var filas = D.embudo.filter(function (e) { return e.tipo === tipo; });
    if (!filas.length) return "";
    var et = D.etapas || {};
    function etapa(k) { return (et[k] || {})[tipo] || 0; }
    var clasificadas = etapa("clasificadas");
    var extranjeras = clasificadas - etapa("empresas_espanolas");
    var fueraVentana = etapa("empresas_espanolas") - etapa("en_ventana");
    var duplicadas = etapa("en_ventana") - etapa("publicadas");
    // Qué quita la ventana de tiempo en cada tipo (normalizar._FILTROS_VENTANA).
    var VENTANA = {
      licitacion: ["fuera de plazo", "fuera de plazo"],
      convocatoria_ue: ["ya cerrada", "ya cerradas"],
      adjudicacion: ["de hace más de 30 días", "de hace más de 30 días"],
      contrato_menor_venciendo: ["que no vence en los próximos 90 días", "que no vencen en los próximos 90 días"],
    }[tipo];
    var despues = [
      extranjeras ? cuantos(extranjeras, "ganada por una empresa extranjera", "ganadas por empresas extranjeras") : "",
      fueraVentana ? cuantos(fueraVentana, VENTANA[0], VENTANA[1]) : "",
      duplicadas ? cuantos(duplicadas, "repetida", "repetidas") + (tipo === "convocatoria_ue" ? "" : " (la misma en dos fuentes)") : "",
    ].filter(Boolean);
    return '<section class="panel panel--ancho filtro__seccion"><div class="seccion__cabecera"><h2>' + nombre + "</h2>" +
      '<span class="filtro__total">' + num(etapa("publicadas")) + " en el radar</span></div>" +
      '<div class="tabla-embudo__marco"><table class="tabla-embudo"><thead><tr><th scope="col">Fuente</th><th scope="col">Traídas</th>' +
      '<th scope="col">Fuera por estado u origen</th><th scope="col">Sin palabra clave</th><th scope="col">Servicio no ofrecido</th><th scope="col">Entran</th></tr></thead><tbody>' +
      filas.map(filaEmbudo).join("") + "</tbody></table></div>" +
      '<p class="tarjeta__nota">Después, de las ' + num(clasificadas) + " que entran" +
      (despues.length ? " se quitan " + despues.join(", ") : " no se quita ninguna") +
      ". Quedan " + num(etapa("publicadas")) + ".</p></section>";
  }

  function cuantos(n, uno, varios) { return miles(n) + " " + (n === 1 ? uno : varios); }

  var lic = TIPOS.map(function (t) { return tablaTipo(t[0], t[1]); }).join("");

  // Descartes revisables.
  var noOfrecido = D.descartes.filter(function (d) { return d.motivo === "servicio_no_ofrecido"; });
  var sinPalabra = D.descartes.filter(function (d) { return d.motivo === "sin_categoria"; });
  function filaDescarte(d) {
    var datos = [d.fuente, esc(d.organismo), "Plazo: " + fecha(d.fecha_limite)];
    if (d.motivo === "servicio_no_ofrecido") datos.unshift("Por «" + esc(d.termino) + "»");
    else if (d.cpv && d.cpv.length) datos.push("CPV " + d.cpv.map(esc).join(", "));
    return "<li>" + (d.enlace && /^https?:/.test(d.enlace)
      ? '<a class="enlace" href="' + esc(d.enlace) + '" target="_blank" rel="noopener">' + esc(d.titulo) + "</a>"
      : esc(d.titulo)) +
      '<span class="tarjeta__antecedente-datos">' + datos.join(" · ") + "</span></li>";
  }
  function bloqueDescartes(titulo, texto, lista, vacio) {
    return '<section class="panel panel--ancho filtro__seccion"><div class="seccion__cabecera"><h2>' + titulo + " (" + lista.length + ")</h2></div>" +
      '<p class="tarjeta__resumen-texto">' + texto + "</p>" +
      (lista.length ? '<ul class="tarjeta__antecedentes">' + lista.map(filaDescarte).join("") + "</ul>" : '<p class="barras__vacio">' + vacio + "</p>") +
      "</section>";
  }

  el.innerHTML =
    '<section class="panel panel--ancho filtro__seccion"><h2>Cómo decide</h2><ul class="filtro__reglas">' +
      "<li><strong>Por el texto, no por el CPV.</strong> Entra lo que en el título dice algo de agencia: hay una lista de palabras clave por categoría de servicio (en castellano, catalán, gallego y euskera). El CPV solo sirve para pedir a TED lo que puede interesar: como código es demasiado grueso.</li>" +
      "<li><strong>Servicio no ofrecido.</strong> Si el título también habla de imprenta, impresión, rotulación, papelería o señalética, se descarta aunque el resto sea de agencia.</li>" +
      "<li><strong>Revisar.</strong> Si mezcla la agencia con limpieza, obra, catering, vigilancia… entra, marcada para revisar a mano.</li>" +
      "<li><strong>TED.</strong> TED pone delante del título el país y el tipo de servicio que sale del CPV («Alemania – Servicios de marketing – …»), y el filtro lo usa para dejar entrar: así llegan licitaciones con el título en su idioma. Para descartar (imprenta, mezclas) solo cuenta el título. El tipo genérico «Servicios a empresas: legislación, mercadotecnia… imprenta y seguridad» no basta para entrar: ahí el título tiene que decirlo. En cada ficha se dice si entró por el título o por el tipo de servicio.</li>" +
      "<li><strong>Después</strong> se quitan las licitaciones fuera de plazo, las adjudicaciones de hace más de 30 días o ganadas por empresas extranjeras, los contratos menores que no vencen pronto y lo que llega repetido por dos fuentes.</li>" +
    "</ul></section>" +
    lic +
    bloqueDescartes("Con CPV de publicidad o marketing pero sin palabra clave",
      "Licitaciones en plazo que el organismo clasifica con un CPV de publicidad, marketing, web, audiovisual o atención al público, pero cuyo título no dice nada que el filtro reconozca. Muchas no son de agencia (encuestas, telecomunicaciones, mantenimiento de software); las que sí lo sean apuntan a palabras que faltan en la lista. De TED, solo organismos españoles.",
      sinPalabra, "Ninguna esta noche.") +
    bloqueDescartes("Descartadas por servicio no ofrecido",
      "Licitaciones en plazo que sí eran de agencia pero también hablan de imprenta, impresión, rotulación o papelería. Junto a cada una, la palabra que la descartó.",
      noOfrecido, "Ninguna esta noche.");
})();
