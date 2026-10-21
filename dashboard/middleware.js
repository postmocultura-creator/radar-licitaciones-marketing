// Acceso con contraseña a toda la web (Routing Middleware de Vercel: se
// ejecuta antes de servir cualquier archivo, también los datos .js).
//
// La contraseña no está en el código: sale de la variable de entorno
// RADAR_CLAVE del proyecto en Vercel (Settings → Environment Variables).
// Para dejar fuera a quien tenga la antigua basta con cambiarla y volver a
// desplegar. El usuario es RADAR_USUARIO (por defecto «radar»).
//
// Si RADAR_CLAVE no está configurada, la web no se sirve: es preferible a
// quedar abierta por un olvido.

export const config = {
  runtime: "nodejs",
};

function iguales(a, b) {
  // Comparación en tiempo constante, para no dar pistas por lo que tarda.
  if (a.length !== b.length) return false;
  var diferencia = 0;
  for (var i = 0; i < a.length; i++) diferencia |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diferencia === 0;
}

function pedirClave() {
  return new Response("Hace falta usuario y contraseña para ver el radar.", {
    status: 401,
    headers: {
      "WWW-Authenticate": 'Basic realm="Radar de licitaciones", charset="UTF-8"',
      "Cache-Control": "no-store",
      "Content-Type": "text/plain; charset=utf-8",
    },
  });
}

export default function middleware(request) {
  var clave = process.env.RADAR_CLAVE || "";
  var usuario = process.env.RADAR_USUARIO || "radar";
  if (!clave) {
    return new Response("El acceso al radar no está configurado (falta RADAR_CLAVE).", {
      status: 503,
      headers: { "Cache-Control": "no-store", "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  var cabecera = request.headers.get("authorization") || "";
  if (!cabecera.startsWith("Basic ")) return pedirClave();
  var texto;
  try {
    texto = Buffer.from(cabecera.slice(6), "base64").toString("utf8");
  } catch (e) {
    return pedirClave();
  }
  var corte = texto.indexOf(":");
  if (corte < 0) return pedirClave();
  var okUsuario = iguales(texto.slice(0, corte), usuario);
  var okClave = iguales(texto.slice(corte + 1), clave);
  if (!(okUsuario && okClave)) return pedirClave();
  // Sin devolver nada, Vercel sirve el archivo pedido.
}
