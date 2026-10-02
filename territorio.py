# -*- coding: utf-8 -*-
"""
Provincia y comunidad autónoma de un registro español.

Las fuentes dan el lugar de tres formas distintas y ninguna con el nombre de
la provincia tal cual:

  - Código NUTS del lugar de ejecución o del organismo (PLACSP, TED y los
    poderes adjudicadores de Euskadi): "ES213" = Bizkaia, "ES21" = País
    Vasco, "ES" = todo el territorio.
  - Código postal del organismo (PLACSP): los dos primeros dígitos son la
    provincia.

Este módulo solo traduce esos códigos. No deduce el lugar a partir del
nombre del organismo ni del título: si la fuente no da código, el registro
se queda sin provincia.

En Canarias y Baleares la NUTS 3 es la isla, no la provincia: se agrupan en
su provincia (Las Palmas / Santa Cruz de Tenerife / Illes Balears).
"""

from __future__ import annotations

# Dos primeros dígitos del código postal -> provincia.
PROVINCIA_POR_CP = {
    "01": "Álava", "02": "Albacete", "03": "Alicante", "04": "Almería",
    "05": "Ávila", "06": "Badajoz", "07": "Illes Balears", "08": "Barcelona",
    "09": "Burgos", "10": "Cáceres", "11": "Cádiz", "12": "Castellón",
    "13": "Ciudad Real", "14": "Córdoba", "15": "A Coruña", "16": "Cuenca",
    "17": "Girona", "18": "Granada", "19": "Guadalajara", "20": "Gipuzkoa",
    "21": "Huelva", "22": "Huesca", "23": "Jaén", "24": "León",
    "25": "Lleida", "26": "La Rioja", "27": "Lugo", "28": "Madrid",
    "29": "Málaga", "30": "Murcia", "31": "Navarra", "32": "Ourense",
    "33": "Asturias", "34": "Palencia", "35": "Las Palmas",
    "36": "Pontevedra", "37": "Salamanca", "38": "Santa Cruz de Tenerife",
    "39": "Cantabria", "40": "Segovia", "41": "Sevilla", "42": "Soria",
    "43": "Tarragona", "44": "Teruel", "45": "Toledo", "46": "Valencia",
    "47": "Valladolid", "48": "Bizkaia", "49": "Zamora", "50": "Zaragoza",
    "51": "Ceuta", "52": "Melilla",
}

# NUTS 3 -> provincia (nomenclatura NUTS 2021).
PROVINCIA_POR_NUTS3 = {
    "ES111": "A Coruña", "ES112": "Lugo", "ES113": "Ourense",
    "ES114": "Pontevedra", "ES120": "Asturias", "ES130": "Cantabria",
    "ES211": "Álava", "ES212": "Gipuzkoa", "ES213": "Bizkaia",
    "ES220": "Navarra", "ES230": "La Rioja", "ES241": "Huesca",
    "ES242": "Teruel", "ES243": "Zaragoza", "ES300": "Madrid",
    "ES411": "Ávila", "ES412": "Burgos", "ES413": "León",
    "ES414": "Palencia", "ES415": "Salamanca", "ES416": "Segovia",
    "ES417": "Soria", "ES418": "Valladolid", "ES419": "Zamora",
    "ES421": "Albacete", "ES422": "Ciudad Real", "ES423": "Cuenca",
    "ES424": "Guadalajara", "ES425": "Toledo", "ES431": "Badajoz",
    "ES432": "Cáceres", "ES511": "Barcelona", "ES512": "Girona",
    "ES513": "Lleida", "ES514": "Tarragona", "ES521": "Alicante",
    "ES522": "Castellón", "ES523": "Valencia",
    "ES531": "Illes Balears", "ES532": "Illes Balears",
    "ES533": "Illes Balears",
    "ES611": "Almería", "ES612": "Cádiz", "ES613": "Córdoba",
    "ES614": "Granada", "ES615": "Huelva", "ES616": "Jaén",
    "ES617": "Málaga", "ES618": "Sevilla", "ES620": "Murcia",
    "ES630": "Ceuta", "ES640": "Melilla",
    "ES703": "Santa Cruz de Tenerife", "ES704": "Las Palmas",
    "ES705": "Las Palmas", "ES706": "Santa Cruz de Tenerife",
    "ES707": "Santa Cruz de Tenerife", "ES708": "Las Palmas",
    "ES709": "Santa Cruz de Tenerife",
}

# NUTS 2 -> comunidad autónoma.
COMUNIDAD_POR_NUTS2 = {
    "ES11": "Galicia", "ES12": "Asturias", "ES13": "Cantabria",
    "ES21": "País Vasco", "ES22": "Navarra", "ES23": "La Rioja",
    "ES24": "Aragón", "ES30": "Madrid", "ES41": "Castilla y León",
    "ES42": "Castilla-La Mancha", "ES43": "Extremadura", "ES51": "Cataluña",
    "ES52": "Comunitat Valenciana", "ES53": "Illes Balears",
    "ES61": "Andalucía", "ES62": "Murcia", "ES63": "Ceuta",
    "ES64": "Melilla", "ES70": "Canarias",
}

COMUNIDAD_POR_PROVINCIA = {
    provincia: COMUNIDAD_POR_NUTS2[nuts[:4]]
    for nuts, provincia in PROVINCIA_POR_NUTS3.items()
}

# Orden en que el dashboard lista las comunidades y, dentro, las provincias.
PROVINCIAS_POR_COMUNIDAD: dict[str, list[str]] = {}
for _provincia, _comunidad in sorted(COMUNIDAD_POR_PROVINCIA.items(), key=lambda par: (par[1], par[0])):
    PROVINCIAS_POR_COMUNIDAD.setdefault(_comunidad, []).append(_provincia)


def desde_nuts(codigo: str | None) -> tuple[str | None, str | None]:
    """(provincia, comunidad) de un código NUTS español.

    "ES213" -> ("Bizkaia", "País Vasco"); "ES21" -> (None, "País Vasco");
    "ES", "ESZZZ" (sin región asignada) o un código de otro país ->
    (None, None)."""
    codigo = (codigo or "").strip().upper()
    if not codigo.startswith("ES"):
        return None, None
    provincia = PROVINCIA_POR_NUTS3.get(codigo[:5])
    if provincia:
        return provincia, COMUNIDAD_POR_PROVINCIA[provincia]
    return None, COMUNIDAD_POR_NUTS2.get(codigo[:4])


def desde_cp(codigo_postal: str | None) -> tuple[str | None, str | None]:
    """(provincia, comunidad) de un código postal español de cinco dígitos."""
    cp = (codigo_postal or "").strip()
    if len(cp) != 5 or not cp.isdigit():
        return None, None
    provincia = PROVINCIA_POR_CP.get(cp[:2])
    return (provincia, COMUNIDAD_POR_PROVINCIA[provincia]) if provincia else (None, None)


def lugar(nuts_ejecucion: str | None = None, nuts_organismo: str | None = None,
          cp_organismo: str | None = None) -> tuple[str | None, str | None]:
    """Mejor dato disponible, por este orden: lugar de ejecución del
    contrato, región del organismo, código postal del organismo. Si el lugar
    de ejecución solo da la comunidad ("ES21"), se intenta afinar la
    provincia con el organismo siempre que caiga en esa misma comunidad.
    Si el lugar de ejecución es "ES" (todo el territorio), no se le pone la
    provincia del organismo: un contrato estatal no es "de Madrid" porque
    el ministerio tenga allí la sede."""
    if (nuts_ejecucion or "").strip().upper() == "ES":
        return None, None
    provincia, comunidad = desde_nuts(nuts_ejecucion)
    if provincia:
        return provincia, comunidad
    for candidata in (desde_nuts(nuts_organismo), desde_cp(cp_organismo)):
        prov_org, com_org = candidata
        if comunidad:
            if prov_org and com_org == comunidad:
                return prov_org, comunidad
        elif prov_org or com_org:
            if prov_org:
                return prov_org, com_org
            comunidad = com_org
    return None, comunidad
