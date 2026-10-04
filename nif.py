# -*- coding: utf-8 -*-
"""NIF de empresas y personas: limpieza, enmascarado y nacionalidad.

Un solo sitio para todo el radar: los scrapers (para no guardar nunca un DNI
completo, ni siquiera en las cachés que se versionan), normalizar.py y el
histórico de adjudicaciones. Antes había cuatro limpiezas distintas, con dos
definiciones diferentes de "NIF de relleno".
"""
from __future__ import annotations

import re

# Formato español. N y W son NIF de entidades EXTRANJERAS (no residentes,
# sucursales): no cuentan como españolas.
ESPANOL = re.compile(
    # Sociedades, entidades y UTE (U). Se tolera un dígito de más o que
    # falte el de control: errores de tecleo reales en PLACSP (Correos con
    # "A083052407", una UTE con "U0002056").
    r"^(?:[ABCDEFGHJPQRSUV]\d{7,9}[0-9A-J]?"
    r"|[0-9X]{8}[A-Z]"   # DNI (Euskadi enmascara así: XXXXX155F)
    r"|[XYZ]\d{7}[A-Z])$"  # NIE (residente en España)
)
_DNI = re.compile(r"^\d{8}[A-Z]$")
_NIE = re.compile(r"^[XYZ]\d{7}[A-Z]$")


def _sin_separadores(nif: str | None) -> str:
    return re.sub(r"[^A-Z0-9*]", "", (nif or "").upper())


def enmascarar_persona(nif: str) -> str:
    """Criterio de la AEPD, el mismo que aplica PLACSP: del DNI 12345678Z
    quedan a la vista las cifras 4.ª a 7.ª ("***4567**") y del NIE X1234567L
    las cuatro anteriores a la letra final ("****4567*"). Los NIF de
    sociedades y entidades (letra inicial A-W) no son datos personales y se
    quedan como están."""
    if _DNI.match(nif):
        return "***" + nif[3:7] + "**"
    if _NIE.match(nif):
        return "****" + nif[4:8] + "*"
    return nif


def limpiar(nif: str | None) -> str | None:
    """NIF tal como se guarda y se compara en todo el radar.

    Sin separadores (cada fuente los pone a su manera: "B-12345678",
    "B12.345.678", "B12345678,") y sin el prefijo de IVA "ES": el mismo NIF
    llegaba como "B28016970" y como "ESB28016970" y la empresa salía dos
    veces en el histórico (24 casos el 2026-10-02: Uniprex, Radio Popular,
    Diario ABC...). El asterisco se conserva: PLACSP enmascara con él.

    El DNI o NIE completo de una persona física no se guarda nunca: se
    enmascara como lo hace PLACSP. Los contratos menores de PLACSP sí los
    publican enteros, y el histórico llegó a servir en la web 7.675
    (decidido con el usuario el 2026-10-04)."""
    limpio = _sin_separadores(nif)
    if limpio.startswith("ES") and ESPANOL.match(limpio[2:]):
        limpio = limpio[2:]
    return enmascarar_persona(limpio) or None


# Pegado a "/", "-", "." o "_" es parte de un código, no un DNI: los
# expedientes de PLACSP acaban a menudo en ocho cifras y una letra
# ("2026/SP03038000/00000545E").
_DNI_EN_TEXTO = re.compile(r"(?<![\w/.\-])(?:\d{8}|[XYZ]\d{7})[A-Z](?![\w/\-])")


def ocultar_en_texto(texto: str | None) -> str | None:
    """Enmascara los DNI y NIE que aparecen dentro de un texto: hay
    organismos que los pegan al nombre del autónomo ("Ana Martín
    Ruiz 12345678Z", visto en el histórico el 2026-10-04)."""
    return _DNI_EN_TEXTO.sub(lambda m: enmascarar_persona(m.group(0)), texto) if texto else texto


def enmascarado(nif: str | None) -> bool:
    """PLACSP publica los NIF de personas físicas con asteriscos
    ("***9688**") y Euskadi con equis ("XXXXX155F"): solo quedan a la vista
    tres o cuatro cifras, así que dos personas distintas pueden compartir el
    mismo NIF enmascarado."""
    return bool(nif) and ("*" in nif or nif.startswith("XXX"))


def es_relleno(nif: str | None) -> bool:
    """NIF que no es de nadie: vacío, "A00000000", "X00000000", "0",
    "NOCONSTITUIDO"... Agrupaban bajo una misma ficha a UTE y personas sin
    relación (unas 70 adjudicaciones el 2026-10-02)."""
    limpio = _sin_separadores(nif)
    return not limpio or bool(re.fullmatch(r"[A-Z]?0+", limpio)) or limpio.startswith("NOCONSTITU")


def es_espanola(nif: str | None, paises_ganador: list[str] | None = None,
                comprador_espanol: bool = False) -> bool:
    """Solo interesan adjudicaciones ganadas por empresas españolas (vascas
    incluidas): la agencia quiere ver a sus competidores, no a una empresa
    francesa que gana un contrato en Francia.

    paises_ganador (TED, ISO3) manda si viene: española si alguna es ESP.
    Si no, el NIF. Sin NIF utilizable, se acepta solo si el contrato es de
    un organismo español (en PLACSP/Euskadi casi siempre hay NIF).

    Verificado contra adjudicaciones reales: lo que queda fuera son IVA
    extranjeros (IE..., FR..., DE..., GB...: Google Ireland, Meta, Ryanair,
    Digimind...), números extranjeros sin letra y NIF N/W."""
    if paises_ganador:
        return "ESP" in paises_ganador
    if es_relleno(nif):
        return comprador_espanol
    limpio = _sin_separadores(nif)
    # Enmascarado con asteriscos (PLACSP, o nosotros): solo se enmascaran
    # NIF españoles.
    if "*" in limpio:
        return len(limpio) == 9
    if limpio.startswith("ES") and ESPANOL.match(limpio[2:]):
        return True
    return bool(ESPANOL.match(limpio))
