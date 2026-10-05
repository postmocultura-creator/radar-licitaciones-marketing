# -*- coding: utf-8 -*-
"""
Alerta diaria por correo: solo las licitaciones nuevas desde el último envío.

Se ejecuta en la actualización nocturna, después de normalizar.py. Lee
data/tenders.json y manda un correo con las licitaciones que no se han
enviado nunca, en tres bloques: Euskadi, resto de España y Europa (lo pidió
así el usuario el 2026-10-05: ni calls, ni adjudicaciones, ni contratos
menores). Cada licitación es una tabla corta de etiqueta y dato, como los
boletines de los radares comerciales. Si no hay nada nuevo, no manda nada.

Qué es "nuevo": un id que no está en data/alertas_enviadas.json (rama
"estado", como el resto del estado interno). Se marca como enviado solo si
el correo sale bien, así que una noche fallida no pierde nada: va en el
correo siguiente. La primera vez, sin ese fichero, cuenta como nuevo lo que
el radar vio por primera vez hoy (fecha_primera_aparicion), para no mandar
de golpe todo lo que hay.

Envío por SMTP (cualquier proveedor: Gmail con contraseña de aplicación,
Brevo, Outlook...). Variables de entorno, en GitHub como secretos:

    ALERTAS_SMTP_SERVIDOR   p. ej. smtp.gmail.com o smtp-relay.brevo.com
    ALERTAS_SMTP_PUERTO     587 (STARTTLS, por defecto) o 465 (SSL)
    ALERTAS_SMTP_USUARIO
    ALERTAS_SMTP_CLAVE
    ALERTAS_DE              remitente, p. ej. "Radar de licitaciones <radar@...>"
    ALERTAS_PARA            destinatarios separados por comas

Si falta alguna, no se envía nada y el paso termina bien: la alerta es
opcional y no debe tumbar la actualización.

Ejecutar:
    python alertas.py            # envía (si hay configuración) y guarda el estado
    python alertas.py --prueba   # escribe data/alerta_prueba.html; no envía ni guarda
    python alertas.py --prueba --hoy 2026-10-04   # como si hoy fuera ese día
"""

from __future__ import annotations

import html
import json
import os
import smtplib
import sys
from datetime import date
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATOS = BASE / "data" / "tenders.json"
DATOS_PUBLICADOS = BASE / "dashboard" / "tenders-data.js"
ENVIADAS = BASE / "data" / "alertas_enviadas.json"
PRUEBA = BASE / "data" / "alerta_prueba.html"
DASHBOARD = "https://licitacionesmarketing.vercel.app/"
NO_PUBLICADO = "no publicado"

RUTA_POR_TIPO = {"licitacion": "licitaciones/abiertas"}
# Cuántas licitaciones como mucho por bloque; el resto, con un enlace al radar.
MAX_POR_SECCION = {"euskadi": 40, "espana": 40, "europa": 20}
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
ESPANA = {"España", "País Vasco"}


# ---------------------------------------------------------------------------
# Qué es nuevo
# ---------------------------------------------------------------------------

def _leer_enviadas() -> set[str] | None:
    if not ENVIADAS.exists():
        return None
    try:
        return set(json.loads(ENVIADAS.read_text(encoding="utf-8"))["ids"])
    except (ValueError, KeyError, TypeError, OSError):
        return None


def novedades(registros: list[dict], enviadas: set[str] | None, hoy: str) -> list[dict]:
    if enviadas is None:
        return [r for r in registros if r.get("fecha_primera_aparicion") == hoy]
    return [r for r in registros if r["id"] not in enviadas]


def _guardar_enviadas(registros: list[dict], enviadas: set[str] | None, nuevas: list[dict]) -> None:
    """Lo enviado que sigue en el radar más lo de hoy. Lo que ya no está se
    olvida (si no, el fichero crecería sin fin). La primera vez se marca todo
    lo que hay: lo anterior a hoy no se enviará nunca, y está bien."""
    vigentes = {r["id"] for r in registros}
    ids = vigentes if enviadas is None else (enviadas & vigentes) | {r["id"] for r in nuevas}
    ENVIADAS.parent.mkdir(parents=True, exist_ok=True)
    ENVIADAS.write_text(json.dumps({"actualizado": date.today().isoformat(), "ids": sorted(ids)}, ensure_ascii=False),
                        encoding="utf-8")


# ---------------------------------------------------------------------------
# Formato
# ---------------------------------------------------------------------------

def _e(texto) -> str:
    return html.escape(str(texto or ""), quote=True)


def _fecha(valor: str | None) -> str | None:
    if not valor or valor == NO_PUBLICADO or len(valor) < 10:
        return None
    try:
        d = date.fromisoformat(valor[:10])
    except ValueError:
        return None
    return f"{d.day} {MESES[d.month - 1]} {d.year}"


def _importe(valor, display: str | None) -> str | None:
    """1234567.0 -> "1.234.567 €"; otra moneda, con su código (TED publica
    cada licitación en la suya: "1.512.990 RON")."""
    if not valor:
        return None
    moneda = (display or "").split()[-1] if display and display != NO_PUBLICADO else "EUR"
    cifra = f"{round(valor):,}".replace(",", ".")
    return f"{cifra} €" if moneda == "EUR" else f"{cifra} {moneda}"


def _enlace_radar(r: dict) -> str:
    return f"{DASHBOARD}#/{RUTA_POR_TIPO[r['tipo_registro']]}?id={r['id']}"


def _dias(fecha_limite: str | None, hoy: date) -> int | None:
    try:
        return (date.fromisoformat(fecha_limite[:10]) - hoy).days
    except (TypeError, ValueError):
        return None


# Cada licitación, una tabla de etiqueta y dato (la etiqueta a la izquierda,
# en una columna de color). Estilos en línea: los clientes de correo ignoran
# las hojas de estilo.
COLOR_MARCA = "#1e3a8a"
ESTILO_TABLA = "border-collapse:collapse;width:100%;margin:0 0 14px;border:1px solid #d1d5db;"
ESTILO_ETIQUETA = ("width:30%;padding:7px 10px;vertical-align:top;font-size:12.5px;font-weight:600;"
                   "color:#1e3a8a;background:#eef2ff;border-bottom:1px solid #e5e7eb;")
ESTILO_VALOR = "padding:7px 10px;vertical-align:top;font-size:13.5px;color:#111827;line-height:1.45;border-bottom:1px solid #e5e7eb;"
ESTILO_ENLACE = "color:#1d4ed8;"


def _fila(r: dict, hoy: date) -> str:
    filas: list[tuple[str, str]] = [
        ("Objeto", f'<a href="{_e(_enlace_radar(r))}" style="{ESTILO_ENLACE}font-weight:600;">{_e(r["titulo"])}</a>'),
    ]
    if r.get("organismo") and r["organismo"] != NO_PUBLICADO:
        filas.append(("Organismo", _e(r["organismo"])))
    if r.get("pais_territorio") in ESPANA:
        lugar = ", ".join(dict.fromkeys(x for x in (r.get("provincia"), r.get("comunidad")) if x))
    else:
        lugar = r.get("pais_territorio")
    if lugar:
        filas.append(("Lugar", _e(lugar)))
    importe = _importe(r.get("presupuesto_valor"), r.get("presupuesto_display"))
    filas.append(("Presupuesto", _e(importe + " (sin IVA)" if importe and importe.endswith("€") else importe or "No publicado")))
    fecha = _fecha(r.get("fecha_limite"))
    if fecha:
        dias = _dias(r.get("fecha_limite"), hoy)
        texto = fecha + (f", {r['hora_limite']}" if r.get("hora_limite") else "")
        if dias is not None and 0 <= dias <= 14:
            texto += " · " + ("cierra hoy" if dias == 0 else "queda 1 día" if dias == 1 else f"quedan {dias} días")
        filas.append(("Fin de plazo", _e(texto)))
    cr = r.get("criterios")
    if cr and cr.get("precio") is not None:
        puntua = cr["precio"] <= 50 and ((cr.get("juicio") or 0) > 0 or (cr.get("resto") or 0) > 0)
        precio = f"Precio {cr['precio']} %" if cr["precio"] else "Sin criterio de precio"
        filas.append(("Cómo se puntúa", _e(precio + (" · puntúa la propuesta" if puntua else ""))))
    if r.get("lotes"):
        filas.append(("Lotes", _e(f"{len(r['lotes'])} lotes")))
    ant = (r.get("antecedentes") or [None])[0]
    if ant and ant.get("empresas"):
        detalle = ", ".join(x for x in (ant.get("anio"), _importe(ant.get("importe"), None)) if x)
        filas.append(("Antes lo ganó", _e(ant["empresas"][0]["nombre"] + (f" ({detalle})" if detalle else ""))))
    enlaces = f'<a href="{_e(_enlace_radar(r))}" style="{ESTILO_ENLACE}">Ficha en el radar</a>'
    if str(r.get("enlace") or "").startswith("http"):
        enlaces += f' · <a href="{_e(r["enlace"])}" style="{ESTILO_ENLACE}">Anuncio original</a>'
    filas.append(("Enlaces", enlaces))
    return (f'<table role="presentation" cellspacing="0" cellpadding="0" style="{ESTILO_TABLA}">'
            + "".join(f'<tr><td style="{ESTILO_ETIQUETA}">{etiqueta}</td><td style="{ESTILO_VALOR}">{valor}</td></tr>'
                      for etiqueta, valor in filas)
            + "</table>")


def _es_euskadi(r: dict) -> bool:
    return r.get("fuente") == "Euskadi" or r.get("comunidad") == "País Vasco" or r.get("pais_territorio") == "País Vasco"


def _secciones(nuevas: list[dict]) -> list[tuple[str, str, list[dict]]]:
    """(clave, título, licitaciones) en el orden del correo: Euskadi, resto
    de España y Europa; dentro de cada bloque, la que cierra antes primero."""
    lic = [r for r in nuevas if r["tipo_registro"] == "licitacion"]
    por_plazo = lambda r: (r.get("fecha_limite") in (None, NO_PUBLICADO), r.get("fecha_limite") or "")  # noqa: E731
    euskadi = [r for r in lic if _es_euskadi(r)]
    espana = [r for r in lic if not _es_euskadi(r) and r.get("pais_territorio") in ESPANA]
    europa = [r for r in lic if not _es_euskadi(r) and r.get("pais_territorio") not in ESPANA]
    return [
        ("euskadi", "Euskadi", sorted(euskadi, key=por_plazo)),
        ("espana", "Resto de España", sorted(espana, key=por_plazo)),
        ("europa", "Europa", sorted(europa, key=por_plazo)),
    ]


def asunto(nuevas: list[dict], hoy: date) -> str:
    n = {clave: len(regs) for clave, _, regs in _secciones(nuevas)}
    partes = [f"{cuantas} en {donde}" for cuantas, donde in
              ((n["euskadi"], "Euskadi"), (n["espana"], "el resto de España"), (n["europa"], "Europa")) if cuantas]
    total = sum(n.values())
    return (f"{total} licitaci{'ón nueva' if total == 1 else 'ones nuevas'}, {hoy.day} {MESES[hoy.month - 1]}: "
            + ", ".join(partes))


def cuerpo_html(nuevas: list[dict], hoy: date) -> str:
    secciones = _secciones(nuevas)
    total = sum(len(regs) for _, _, regs in secciones)
    resumen = " · ".join(f"{titulo}: {len(regs)}" for _, titulo, regs in secciones)
    bloques = []
    for clave, titulo, regs in secciones:
        if not regs:
            continue
        maximo = MAX_POR_SECCION[clave]
        resto = len(regs) - maximo
        bloques.append(
            f'<h2 style="font-size:15px;color:#ffffff;background:{COLOR_MARCA};margin:26px 0 12px;padding:8px 12px;">'
            f"{titulo} · {len(regs)} licitaci{'ón nueva' if len(regs) == 1 else 'ones nuevas'}</h2>"
            + "".join(_fila(r, hoy) for r in regs[:maximo])
            + (f'<p style="font-size:13px;margin:0 0 8px;"><a href="{DASHBOARD}#/licitaciones/recientes" style="{ESTILO_ENLACE}">'
               f"Y {resto} más en el radar</a></p>" if resto > 0 else ""))
    return (
        '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        '<body style="margin:0;padding:0;background:#f3f4f6;">'
        '<div style="max-width:660px;margin:0 auto;padding:24px 16px;font-family:Inter,Segoe UI,Arial,sans-serif;'
        'background:#ffffff;color:#111827;">'
        f'<p style="font-size:13px;color:#6b7280;margin:0;">Radar de licitaciones · {hoy.day} {MESES[hoy.month - 1]} {hoy.year}</p>'
        f'<h1 style="font-size:21px;margin:6px 0 4px;">{total} licitaci{"ón nueva" if total == 1 else "ones nuevas"}</h1>'
        f'<p style="font-size:13.5px;color:#374151;margin:0;">Las que han aparecido desde el último correo. {_e(resumen)}.</p>'
        + "".join(bloques) +
        f'<p style="font-size:12px;color:#6b7280;margin:28px 0 0;">Todo lo que sigue en plazo está en '
        f'<a href="{DASHBOARD}" style="{ESTILO_ENLACE}">el radar</a>; por qué entra cada licitación, en '
        f'<a href="{DASHBOARD}filtro.html" style="{ESTILO_ENLACE}">Cómo se filtra</a>.</p>'
        "</div></body></html>")


def cuerpo_texto(nuevas: list[dict]) -> str:
    lineas = ["Licitaciones nuevas del radar", ""]
    for clave, titulo, regs in _secciones(nuevas):
        if not regs:
            continue
        lineas.append(f"{titulo} ({len(regs)})")
        for r in regs[:MAX_POR_SECCION[clave]]:
            lineas.append(f"- {r['titulo']}\n  {r.get('organismo') or ''}\n  {_enlace_radar(r)}")
        lineas.append("")
    lineas.append(DASHBOARD)
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# Envío
# ---------------------------------------------------------------------------

def _configuracion() -> dict | None:
    claves = ("ALERTAS_SMTP_SERVIDOR", "ALERTAS_SMTP_USUARIO", "ALERTAS_SMTP_CLAVE", "ALERTAS_DE", "ALERTAS_PARA")
    if not all(os.environ.get(c) for c in claves):
        return None
    return {
        "servidor": os.environ["ALERTAS_SMTP_SERVIDOR"],
        "puerto": int(os.environ.get("ALERTAS_SMTP_PUERTO") or 587),
        "usuario": os.environ["ALERTAS_SMTP_USUARIO"],
        "clave": os.environ["ALERTAS_SMTP_CLAVE"],
        "de": os.environ["ALERTAS_DE"],
        "para": [p.strip() for p in os.environ["ALERTAS_PARA"].split(",") if p.strip()],
    }


def enviar(conf: dict, asunto_correo: str, texto: str, html_correo: str) -> None:
    mensaje = EmailMessage()
    nombre, direccion = parseaddr(conf["de"])
    mensaje["From"] = formataddr((nombre or "Radar de licitaciones", direccion))
    mensaje["To"] = ", ".join(conf["para"])
    mensaje["Subject"] = asunto_correo
    mensaje.set_content(texto)
    mensaje.add_alternative(html_correo, subtype="html")
    if conf["puerto"] == 465:
        with smtplib.SMTP_SSL(conf["servidor"], conf["puerto"], timeout=60) as smtp:
            smtp.login(conf["usuario"], conf["clave"])
            smtp.send_message(mensaje)
    else:
        with smtplib.SMTP(conf["servidor"], conf["puerto"], timeout=60) as smtp:
            smtp.starttls()
            smtp.login(conf["usuario"], conf["clave"])
            smtp.send_message(mensaje)


def _leer_registros() -> list[dict] | None:
    """data/tenders.json (lo deja normalizar.py en la misma ejecución) o, si
    no está, lo publicado en dashboard/tenders-data.js: así el flujo "Probar
    alerta" manda el correo sin volver a descargar nada."""
    if DATOS.exists():
        return json.loads(DATOS.read_text(encoding="utf-8"))
    if DATOS_PUBLICADOS.exists():
        texto = DATOS_PUBLICADOS.read_text(encoding="utf-8")
        return json.loads(texto[texto.index("["):].rstrip().rstrip(";"))
    return None


def main() -> None:
    prueba = "--prueba" in sys.argv
    # --sin-guardar: envía de verdad, con "[Prueba]" en el asunto, pero no
    # marca nada como enviado (flujo "Probar alerta").
    sin_guardar = "--sin-guardar" in sys.argv
    datos = _leer_registros()
    if datos is None:
        print("[alertas] No hay datos (data/tenders.json). Ejecuta antes normalizar.py.", file=sys.stderr)
        return
    registros = [r for r in datos if r.get("tipo_registro") in RUTA_POR_TIPO]
    # --hoy AAAA-MM-DD: para probar con datos de otro día.
    hoy = date.fromisoformat(sys.argv[sys.argv.index("--hoy") + 1]) if "--hoy" in sys.argv else date.today()
    enviadas = _leer_enviadas()
    nuevas = novedades(registros, enviadas, hoy.isoformat())
    if sin_guardar and not nuevas and registros:
        # La prueba siempre manda algo: lo del último día con novedades.
        ultimo = max(r.get("fecha_primera_aparicion") or "" for r in registros)
        nuevas = [r for r in registros if r.get("fecha_primera_aparicion") == ultimo]
    if enviadas is None:
        print("[alertas] Primera vez: cuenta como nuevo lo visto hoy por primera vez.")
    print(f"[alertas] {len(nuevas)} novedades")

    if prueba:
        PRUEBA.write_text(cuerpo_html(nuevas, hoy), encoding="utf-8")
        print(f"[alertas] Prueba: {asunto(nuevas, hoy) if nuevas else '(nada nuevo)'} -> {PRUEBA}")
        return

    conf = _configuracion()
    if conf is None:
        # Sin configuración no se marca nada como enviado: el día que se
        # configure, el primer correo trae lo nuevo de ese día.
        print("[alertas] Sin configuración de correo (ALERTAS_*): no se envía nada.")
        if sin_guardar:
            sys.exit(1)
        return
    if nuevas:
        titulo = ("[Prueba] " if sin_guardar else "") + asunto(nuevas, hoy)
        try:
            enviar(conf, titulo, cuerpo_texto(nuevas), cuerpo_html(nuevas, hoy))
        except (smtplib.SMTPException, OSError) as e:
            # Sin guardar: lo de hoy irá en el próximo correo.
            print(f"[alertas] AVISO: no se pudo enviar el correo: {e}", file=sys.stderr)
            if sin_guardar:
                sys.exit(1)  # en la prueba, que el fallo se vea en rojo
            return
        print(f"[alertas] Enviado a {len(conf['para'])} destinatario(s): {titulo}")
    else:
        print("[alertas] Nada nuevo: no se envía correo.")
    if not sin_guardar:
        _guardar_enviadas(registros, enviadas, nuevas)


if __name__ == "__main__":
    main()
