# Radar de licitaciones — agencia de marketing digital

Cada noche reúne de fuentes públicas lo que puede interesar a una agencia de
publicidad, comunicación y marketing digital, y lo enseña en un dashboard
estático (https://licitacionesmarketing.vercel.app):

- **Licitaciones abiertas** de la UE (TED), del Estado (PLACSP, incluidas
  las plataformas autonómicas agregadas) y de Euskadi.
- **Calls for proposals de la UE**: convocatorias cuyo proyecto financiado
  previsiblemente necesitará comunicación o difusión.
- **Contratos menores por vencer**: quién tiene hoy un contrato menor que
  termina en los próximos 90 días, para visitar al organismo antes de que
  lo renueve.
- **Competencia**: adjudicaciones recientes y un histórico desde 2021 de qué
  empresas ganan qué contratos de agencia, en qué organismos y por cuánto.

Este README explica cómo funciona hoy. Por qué es así (qué se probó, qué se
descartó y qué fallos se encontraron con datos reales) está en
[`docs/DECISIONES.md`](docs/DECISIONES.md); el diseño del dashboard, en
`docs/diseno/`.

## Requisitos y ejecución en local

Python 3.12 y `pip install -r requirements.txt` (versiones fijas). Ninguna
fuente pide clave. En el ordenador de desarrollo `python` directo está
bloqueado por el Control de aplicaciones de Windows; se ejecuta con `uv`:

```bash
uv run --python 3.12 --with-requirements requirements.txt -- python scrapers/ted.py
```

Orden completo, desde `licitaciones_marketing/` (es el mismo del workflow):

```bash
python scrapers/ted.py
python scrapers/placsp.py
python scrapers/placsp_web.py          # necesita: python -m playwright install chromium
python scrapers/euskadi.py
python scrapers/eu_grants.py
python scrapers/historico_adjudicaciones.py diario
python clasificar.py
python normalizar.py
```

Para que la ejecución en local parta de lo acumulado (histórico, cachés,
"Nuevo hoy"...), antes hay que traer los datos internos de la rama
`estado` (ver "Datos"):

```bash
git fetch origin estado
git archive origin/estado | tar -x
```

Después, `dashboard/index.html` se abre con doble clic (no necesita
servidor). Si una fuente falla, su scraper deja
`data/raw/<fuente>_..._error.json` con el motivo y el resto sigue:
`clasificar.py` reutiliza lo último bueno de esa fuente.

Pruebas (sin red, con muestras reales anonimizadas en `tests/fixtures/`):

```bash
python -m pytest
```

## Estructura

```
licitaciones_marketing/
├── scrapers/
│   ├── ted.py           API de TED: licitaciones (competition) y adjudicaciones (result)
│   ├── placsp.py        ZIP mensuales de PLACSP: perfiles propios (sindicacion_643),
│   │                    plataformas autonómicas (1044) y contratos menores (1143)
│   ├── placsp_web.py    buscador web de PLACSP (Playwright): lo publicado en los
│   │                    últimos 3 días y, los lunes, las convocatorias de plazo largo
│   ├── euskadi.py       API de Euskadi: avisos, adjudicaciones (con la ficha pública
│   │                    del expediente) y contratos menores por meses
│   ├── eu_grants.py     API SEDIA del portal de la UE: calls for proposals
│   ├── historico_adjudicaciones.py   histórico de adjudicaciones desde 2021
│   ├── peticiones.py    peticiones HTTP con reintentos, comunes a todos
│   └── comun.py         guardado de crudos y errores
├── config.py            taxonomía (categorías, exclusiones, CPV) y ventanas de tiempo
├── clasificar.py        decide qué entra, por tipo de registro
├── normalizar.py        esquema común, deduplicación, filtros de fecha, resumen del histórico
├── nif.py               limpieza de NIF y enmascarado de personas físicas
├── territorio.py        código NUTS o postal -> provincia y comunidad
├── tests/               pruebas de regresión (pytest)
├── data/                ver "Datos" más abajo
└── dashboard/           la web: index.html (radar) e historico.html (competencia)
```

## Cómo decide qué entra

Solo el **texto del título** decide (`clasificar.clasificar_texto`), con las
listas de `config.py`:

- Si no aparece ninguna palabra de `CATEGORIAS` (o su versión en catalán,
  gallego y euskera, `TERMINOS_OTRAS_LENGUAS`), no entra.
- Si aparece un servicio que la agencia no ofrece (`SERVICIOS_NO_OFRECIDOS`:
  imprenta, impresión, artes gráficas...), no entra.
- Si además aparece algo ajeno (`EXCLUSIONES`, p. ej. comunicación y
  limpieza en el mismo contrato), entra marcada "revisar".

Las palabras se comparan completas, sin tildes y sin la jerga del
procedimiento ("negociado sin publicidad" no es publicidad). El CPV solo
acota lo que se pide a TED: como criterio de inclusión colaba demasiado.
Las calls for proposals usan su propia lista en inglés
(`CATEGORIAS_CALLS_UE`) sobre el título y el texto de la convocatoria.

**Ampliar la taxonomía** es tocar esas listas en `config.py`, sin cambiar
código: palabras en minúscula, tal como quedan sin tildes. Los códigos CPV
nuevos se comprueban antes en
[simap.ted.europa.eu/cpv](https://simap.ted.europa.eu/web/simap/cpv).

## Qué enseña cada vista y con qué criterio

- **Licitaciones**: en plazo (fecha límite futura) o, si no publican fecha
  límite, publicadas en los últimos `DIAS_ANTIGUEDAD_MAXIMA` (30) días. En
  PLACSP solo cuentan los expedientes en estado "Publicada": la fecha de
  actualización del feed se toca aunque el contrato lleve años cerrado.
- **Adjudicaciones**: adjudicadas en los últimos 30 días a empresas
  españolas (por NIF, o por el país que publica TED). Con los documentos que
  dicen qué se valoró (informe de valoración, actas de la mesa, resolución)
  cuando la fuente los publica: PLACSP en los perfiles propios y Euskadi en
  la ficha del expediente, que además dice qué empresas se presentaron.
- **Contratos menores por vencer**: fecha de fin entre hoy y 90 días
  (`DIAS_AVISO_CONTRATO_MENOR`). Euskadi la publica; en PLACSP se calcula con
  la fecha de adjudicación y la duración.
- **Calls for proposals UE**: abiertas o próximas, traducidas al español
  (MyMemory, o `data/traducciones_manuales.json`).
- **Cómo se puntúa**: los criterios de adjudicación con su peso, con lo que
  publique cada fuente (`normalizar._criterios`):
  - PLACSP (perfiles propios): precio, otros criterios con fórmula y juicio
    de valor (`placsp._criterios_adjudicacion`). Con lotes se enseña el
    primero. El precio se reconoce por su código o, si el organismo lo marca
    mal, por su nombre.
  - Euskadi: de la ficha pública del expediente (`euskadi._criterios`). Solo
    separa el precio del resto, y solo si las ponderaciones suman 100.
  - TED: del propio aviso (`normalizar._criterios_ted`). También precio y
    resto; con lotes, solo si todos puntúan igual. Una licitación de TED que
    también está en PLACSP se queda con los criterios de PLACSP.
  - Plataformas agregadas y buscador web: no los publican.
  - Calls for proposals: la API no los da como dato; se enlaza el documento
    donde están (ver "Pliegos y documentos").

  El filtro "Puntúa la propuesta, precio hasta el 50 %" deja las que se
  pueden ganar con la propuesta: en PLACSP, con juicio de valor; en Euskadi y
  TED, con algún criterio que no sea el precio.
- **Pliegos y documentos** (`normalizar._hora_y_pliegos`): PLACSP, los pliegos
  administrativo y técnico; Euskadi, esos dos y la carátula, de la pestaña
  "Ficheros" de la ficha (`euskadi.anadir_fichas_licitaciones`, solo de las
  licitaciones en plazo que encajan con la taxonomía); TED, la dirección
  donde están los documentos; calls for proposals, el documento de la
  convocatoria y sus anexos o, en Horizonte Europa, el anexo de los criterios
  y los modelos de solicitud y de evaluación
  (`eu_grants._documentos_convocatoria`), además del presupuesto del tema,
  los proyectos previstos y la subvención máxima (`eu_grants._presupuesto`).
- **Lotes** (`normalizar._lotes`): objeto e importe sin IVA de cada lote y,
  si la fuente lo dice, lo que pesa el precio en ese lote. PLACSP (perfiles
  propios): las tres cosas; plataformas agregadas: solo el objeto. Euskadi:
  de la pestaña "Lotes" de la ficha. TED: título y, si viene uno por lote,
  el valor estimado (los criterios no: los da todos seguidos, sin decir de
  qué lote son). Las calls for proposals no tienen lotes. Una licitación con
  un solo lote no enseña la lista.
- **Contratos anteriores parecidos** (`normalizar._antecedentes`): en cada
  licitación española (Estado, Euskadi y TED de organismos españoles), los
  contratos del mismo organismo con un título parecido que hay en el
  histórico de adjudicaciones, casi siempre ediciones anteriores del mismo
  servicio: año, quién lo ganó, importe, ofertas y rebaja. Parecido = comparten
  al menos el 30 % de las palabras con contenido del título, sin contar las
  del nombre del organismo. Se leen del histórico completo
  (`data/historico_adjudicaciones.json`), que tiene los títulos. Las
  licitaciones extranjeras de TED no tienen histórico.
- **Otras abiertas** (en el dashboard, `otrasAbiertas` de `app.js`): en cada
  licitación, las demás en plazo del mismo organismo; en cada call for
  proposals, las demás del mismo programa (las dos primeras partes del
  código: `HORIZON-CL6`, `CREA-MEDIA`).
- **Alerta diaria por correo** (`alertas.py`, paso "Alerta por correo" de la
  actualización nocturna): solo las licitaciones que no se han enviado
  nunca, en tres bloques por este orden: Euskadi (también las vascas que
  llegan por TED o PLACSP), resto de España y Europa. Ni calls, ni
  adjudicaciones, ni contratos menores. Cada licitación es una tabla de
  etiqueta y dato: objeto, organismo, lugar, presupuesto, fin de plazo,
  cómo se puntúa, lotes y quién ganó el contrato anterior parecido, con
  enlace a su ficha en el radar y al anuncio. Si no hay nada nuevo no se
  manda. Lo enviado se guarda
  en `data/alertas_enviadas.json` (rama `estado`) solo si el correo sale
  bien. Envía por SMTP con los secretos de GitHub `ALERTAS_SMTP_SERVIDOR`,
  `ALERTAS_SMTP_PUERTO`, `ALERTAS_SMTP_USUARIO`, `ALERTAS_SMTP_CLAVE`,
  `ALERTAS_DE` y `ALERTAS_PARA` (destinatarios separados por comas); sin
  ellos el paso no hace nada. Vista previa sin enviar:
  `python alertas.py --prueba` (escribe `data/alerta_prueba.html`).
- **Cómo se filtra** (`dashboard/filtro.html`): el embudo de cada noche por
  fuente (traídas, fuera por estado u origen, sin palabra clave, servicio no
  ofrecido, entran) y por tipo (fuera de plazo, extranjeras, repetidas,
  publicadas), más dos listas de licitaciones en plazo descartadas que
  conviene revisar: las que tienen un CPV de marketing (`config.CPV_RANGOS`)
  pero ninguna palabra clave, y las que cayeron por un servicio no ofrecido,
  con la palabra que las tumbó. `clasificar.py` apunta los descartes
  (`_apuntar_descarte`, en `data/filtro.json`, que no se guarda entre
  ejecuciones) y `normalizar._publicar_filtro` los convierte y escribe
  `dashboard/filtro-data.js`. Cada ficha dice además por qué está en el radar
  (`normalizar._por_que`): las palabras clave que encontró el filtro y, en
  TED, si decidió el tipo de servicio que TED antepone al título.
- **Competencia en cada adjudicación**: ofertas recibidas (PLACSP; en Euskadi,
  las empresas que se presentaron) y rebaja de la ganadora sobre el
  presupuesto, los dos sin IVA (`normalizar._competencia`). La rebaja solo
  sale con un único resultado y cuando la hay: un 0 % suele ser un negociado
  o un contrato a precios unitarios, donde el importe adjudicado es el máximo.
- **Índice de éxito en Euskadi**: a cuántos concursos vascos se presenta cada
  empresa y cuántos gana (`euskadi.indice_exito`, en `licitadoras-data.js`).
  Sale en su ficha de Competencia y junto a cada licitadora de una
  adjudicación vasca, con al menos 3 concursos.
- **La misma licitación en dos fuentes** se fusiona si coinciden título y
  organismo (o, con el mismo plazo, un título es el comienzo del otro). Se
  queda la de TED; después la del feed de PLACSP, la de Euskadi, la de las
  plataformas agregadas y, por último, la del buscador web. La que se queda
  hereda la hora de cierre, los pliegos y los documentos de la otra.

## Datos

| Fichero | Qué es | Quién lo escribe | Dónde se guarda |
|---|---|---|---|
| `data/raw/` | crudo de cada pasada | scrapers | no se guarda |
| `data/clasificado.json` | lo que entra, por fuente | clasificar.py | no se guarda |
| `data/tenders.json` | el radar en JSON (comprobación antes de publicar) | normalizar.py | no se guarda |
| `dashboard/tenders-data.js` | el radar, lo que lee el dashboard | normalizar.py | `main` |
| `dashboard/historico-data.js`, `historico-detalle/` | lo que lee Competencia | historico_adjudicaciones.py | `main` |
| `data/historico_adjudicaciones.json` | histórico completo (base de cada actualización) | historico_adjudicaciones.py | rama `estado` |
| `data/ultimo_bueno_por_fuente.json` | lo último bueno de cada fuente, y lo acumulado de PLACSP (sus ZIP traen solo lo actualizado ese mes) | clasificar.py | rama `estado` |
| `data/primera_aparicion.json` | cuándo vio el radar cada registro por primera vez ("Nuevo hoy") | normalizar.py | rama `estado` |
| `data/placsp_web_acumulado.json` | lo del buscador web, hasta que vence su plazo | placsp_web.py | rama `estado` |
| `data/euskadi_menores_acumulado.json` | menores de Euskadi de agencia, por mes de adjudicación | euskadi.py | rama `estado` |
| `data/euskadi_licitadoras.json` | qué empresas se presentaron a cada concurso vasco (NIF y si es pyme) | euskadi.py | rama `estado` |
| `dashboard/licitadoras-data.js` | índice de éxito por empresa en concursos vascos | euskadi.py | `main` |
| `data/cache/` | detalle de las convocatorias UE y traducciones automáticas | eu_grants.py, normalizar.py | actions/cache |
| `data/traducciones_manuales.json` | traducciones revisadas a mano | a mano | `main` |

**Rama `estado`.** Los datos internos del pipeline pesan unos 60 MB y se
reescriben cada noche: en `main` hacían crecer el repositorio entre 2 y 5 MB
por actualización. Ahora viven en la rama `estado`, que cada noche se
sustituye por un único commit sin historia (`.github/publicar_estado.sh`):
no crece. Los workflows la descargan al empezar (`git archive | tar -x`) y la
vuelven a publicar al terminar; los dos comparten grupo de concurrencia, así
que nunca la escriben a la vez (una reconstrucción del histórico deja en
cola la actualización nocturna hasta que termina). En `main` solo queda el
código y lo que sirve la web.

**Datos personales.** Los DNI y NIE de personas físicas no se guardan nunca
enteros: `nif.py` los enmascara en cuanto llegan, como lo hace PLACSP
(`***4567**`, `****4567*`), también si vienen pegados al nombre. El
dashboard no enseña el NIF de una persona ni lo pone en direcciones. De las
empresas que se presentan a un concurso de Euskadi se guarda nombre, NIF, si
es pyme y provincia, nunca teléfonos ni correos; en el acumulado del índice
de éxito, solo el NIF y si es pyme, y el índice publicado deja fuera a las
personas físicas.

## Automatización

Todo corre en GitHub Actions y se publica en Vercel, sin ningún ordenador
encendido y sin pasar por un modelo de IA.

- **`actualizar-datos.yml`**, cada noche (cron 22:47 UTC; GitHub suele
  arrancarlo hacia la 01:30). Ejecuta los scrapers, el histórico, Clasificar y
  Normalizar. Cada paso tiene su límite de tiempo (TED 10 min, PLACSP 40,
  buscador web 30, Euskadi 25, UE 20, histórico 25, Clasificar 10, Normalizar
  15) y el job, la suma más margen: si una fuente se pasa, ese día se queda
  con lo acumulado y el resto se publica. No publica si el radar sale con
  menos de 100 registros. Las cachés de `data/cache/` se guardan nada más
  terminar el paso que las usa. Una noche normal tarda unos 25-40 minutos.
- **`historico-adjudicaciones.yml`**, a mano: reconstruye o repara el
  histórico (modo "completo", desde 2021, o "reciente"). Ojo: "completo" son
  unos 550 minutos de Actions; con el repositorio privado, calcular antes.
- **`pruebas.yml`**: las pruebas, cada vez que se sube código.
- **Vercel** publica la carpeta `dashboard/` (Root Directory) en cada push.
  `dashboard/vercel.json` añade la cabecera `noindex`: es una herramienta
  interna y no debe aparecer en buscadores.

Las peticiones a las API pasan por `scrapers/peticiones.py`, que reintenta
los cortes de red, los 429 y los 5xx (no los 4xx). Los ZIP de PLACSP no se
reintentan: repetir 300 MB a ciegas puede costar más que el límite del paso.

## Límites conocidos

- **PLACSP va con retraso**: sus ZIP salen de lotes que no se generan todos
  los días laborables (hasta 5 días de retraso). El buscador web cubre lo
  publicado en los últimos 3 días.
- **El buscador web es lo más frágil**: es una aplicación con estado, sin
  API. Si PLACSP cambia la página, falla y el radar sigue con el feed.
- **La ficha de Euskadi también se lee de la página**: si cambia el diseño,
  las adjudicaciones vascas salen sin documentos ni licitadoras, y el
  registro lo avisa.
- **Euskadi no da CPV en los avisos** ni una hora de cierre fiable.
- **Contratos menores**: los de PLACSP se acumulan desde octubre de 2026 (el
  ZIP solo trae lo actualizado ese mes); los de Euskadi tardan unas 7 noches
  en cubrir los 15 meses.
- **Criterios de adjudicación**: las licitaciones de PLACSP ya acumuladas antes
  del cambio los van teniendo a medida que su expediente vuelve a salir en el
  ZIP del mes; las nuevas, desde el primer día.
- **Documentos y presupuesto de las calls for proposals**: el detalle de cada
  convocatoria se guarda en caché; los guardados antes del cambio se vuelven
  a pedir a razón de 60 por noche, así que tardan unas noches en completarse.
- **Índice de éxito en Euskadi**: cada noche se leen hasta 150 fichas de
  concursos vascos del histórico (unos 5 minutos como máximo), así que tarda
  unas 8 noches en cubrir 2021-2026. Solo Euskadi publica quién se presentó;
  PLACSP solo da el número de ofertas.
- **Importes del histórico**: incluyen algún contrato enorme que no es de
  agencia aunque su título encaje (Competencia permite quitar los de más de
  1 M€).
- **El repositorio aún crece algo cada noche** (1-2 MB): los ficheros que
  sirve la web siguen en `main` porque Vercel publica desde git. Para
  quitarlos habría que publicar en Vercel desde Actions.

## Si una fuente cambia de formato

Mira el `_error.json` más reciente en `data/raw/` (o el registro del paso en
Actions) y compara con la fuente real antes de tocar el código:

- **TED**: nombres de campo, en `https://api.ted.europa.eu/swagger`.
- **PLACSP**: namespaces o estructura CODICE; inspecciona un `.atom` real
  antes de tocar `placsp._parsear_entry()`.
- **Euskadi**: el descriptor OpenAPI vivo está en
  `https://opendata.euskadi.eus/contenidos/recurso_tecnico/data_apirest/es_def/adjuntos/procurements.json`.
- **Buscador web de PLACSP y ficha de Euskadi**: abre la página en el
  navegador y compara con los selectores de `placsp_web.py` y `euskadi.leer_ficha()`.

Después, `python -m pytest` para comprobar que no se rompe nada más.

## Dashboard

El porqué de cada decisión de diseño está en `docs/diseno/`: `REFERENCE-AUDIT.md`, `INFORMATION-ARCHITECTURE.md`,
`DESIGN-SYSTEM.md` y `PROJECT-STATE.md`.

Dos páginas, una barra lateral común (`nav.js`) y una ruta de hash por vista,
para que cada una tenga su dirección y funcione el botón "atrás":

| Sección | Vista | Dirección |
|---|---|---|
| — | Inicio (resumen del día) | `index.html#/inicio` |
| Oportunidades | Licitaciones: pestañas "Publicadas recientemente", "Licitaciones abiertas" y "Sistemas dinámicos y plazo largo" | `index.html#/licitaciones/recientes`, `#/licitaciones/abiertas`, `#/licitaciones/plazo-largo` |
| Oportunidades | Calls for proposals UE | `index.html#/calls` |
| Prospección comercial | Contratos menores por vencer | `index.html#/menores` |
| Competencia | Adjudicaciones recientes (30 días) | `index.html#/adjudicaciones` |
| Competencia | Análisis de mercado (histórico desde 2021) | `historico.html#/mercado` |
| Competencia | Empresas y ficha de empresa | `historico.html#/empresas`, `#/empresa/<id>` |
| Competencia | Organismos y ficha de organismo | `historico.html#/organismos`, `#/organismo/<id>` |

`index.html` lee `dashboard/tenders-data.js` (no `data/tenders.json`
directamente): al abrirse con doble clic bajo `file://`, Chrome/Edge bloquean
`fetch()` de un `.json` por CORS, así que `normalizar.py` vuelca los mismos
datos como `window.TENDERS_DATA = [...]` para que funcione sin servidor.
`historico.html` lee `historico-data.js` y, al abrir la ficha de una empresa,
el fragmento de `historico-detalle/` que le toca.

Cómo funciona cada pieza:

- **Inicio** (`pintarInicio()` en `app.js`): cinco cifras enlazadas a su vista,
  las últimas publicadas recientemente, lo que cierra en 7 días, los contratos
  menores que vencen antes, las últimas adjudicaciones y el reparto de las
  licitaciones en plazo por categoría. Todo sale de `tenders-data.js`.
- **Listados** (una sola vista en `index.html` para los cinco tipos; `VISTAS`
  en `app.js` asocia cada ruta a su `tipo_registro`). Cada vista reconstruye sus
  controles: `FUENTES_POR_TIPO`, `PAISES_POR_TIPO` (el país solo existe en
  "Licitaciones abiertas"), `IMPORTE_POR_TIPO` y `ORDENES_POR_TIPO`
  ("Adjudicaciones recientes" no tiene selector de orden: siempre de la más
  reciente a la más antigua). Los filtros muestran siempre todas sus opciones,
  con "(0)" si ese día no hay nada.
- **"Publicadas recientemente"**: solo licitaciones de organismos españoles
  -PLACSP (feed y buscador web), portal de Euskadi y las de organismos españoles
  en TED, que se asignan a Euskadi por región NUTS ES21x- que el radar vio por
  primera vez en los últimos 3 días (`fecha_primera_aparicion`, no
  `fecha_publicacion`: ver normalizar.py), ordenadas por `fecha_publicacion`.
  Desde la reunión del 2026-09-30 con la agencia ya no entran licitaciones de
  otros países ni calls for proposals. No es un `tipo_registro` real: es una
  vista calculada en `app.js` (`esPublicacionReciente()`, `ambitoReciente()`).
  Las fuentes solo dan fecha, no hora, así que la ventana se cuenta en días
  naturales. Sus tarjetas salen ya desplegadas, porque normalmente hay pocas.
- **"Sistemas dinámicos y plazo largo"**: licitaciones abiertas a las que les
  quedan más de 60 días de plazo (`esPlazoLargo()`, vista calculada como la
  anterior). Son sistemas dinámicos de adquisición, homologaciones y acuerdos
  marco que admiten solicitudes durante meses o años. No las traía ninguna
  fuente: se publicaron hace mucho (la búsqueda diaria no las ve) y no se
  actualizan (no vienen en el ZIP mensual). `scrapers/placsp_web.py` las pide
  una vez a la semana con dos búsquedas sin fecha de publicación
  (`_buscar_plazo_largo`): el 2026-10-02 devolvían 186 expedientes de
  servicios, 7 de ellos de agencia. El listado no da la fecha de publicación,
  así que la tarjeta la omite y no cuentan como "publicadas recientemente".
- **Texto explicativo de cada vista** (`EXPLICACION_TIPO` en `app.js`, bajo el
  título): qué aparece y con qué criterio, para que alguien de la agencia
  entienda la vista sin leer este README. Solo criterio, nunca el razonamiento
  interno.
- **Tarjeta** (`plantillaTarjeta()`): código de expediente, fuente, chip "Nuevo
  hoy/ayer" y urgencia; título, organismo y territorio; pie con las fechas o la
  adjudicataria; columna de importe. Se despliega (`<details>/<summary>` nativo,
  accesible por teclado) con el detalle en pares dato/valor: información
  general (incluidos expediente y CPV), fechas (incluida la de entrada en el
  radar) e importes, la descripción, los pliegos, las categorías y los
  enlaces: anuncio original, "Historial de la empresa" y "Quién gana en este
  organismo" (estos dos llevan al histórico).
- **Hora de cierre y pliegos** (`hora_limite` y `pliegos`, solo en
  licitaciones y solo si la fuente los publica; ver "Hora de cierre y
  pliegos"): la fecha límite se escribe "19 oct 2026, 14:00" y el día de
  cierre la urgencia dice "Cierra hoy a las 14:00", o "Cerró hoy a las 14:00"
  si el organismo es español y la hora ya ha pasado en el reloj de quien mira.
  En TED, fuera de España, se añade "(hora local)". El bloque "Pliegos" enlaza
  cada documento y enseña el nombre del fichero que subió el organismo.
- **Código de color por urgencia**: rojo ≤7 días, ámbar ≤21 días, verde el
  resto, gris si no hay fecha límite publicada (en contratos menores: rojo ≤30,
  ámbar ≤60). Es señal funcional, igual en todas las vistas y siempre con
  texto. Al ordenar por fecha, lo ya vencido va al final.
- **"Solo pendientes de revisar (N)"**: solo aparece si hay algo que revisar.
- **Importes**: `normalizar.py` los entrega como "865,200 EUR"; el dashboard los
  pasa a "865.200 €" sin tocar la moneda (TED publica cada licitación en la
  suya: SEK, PLN, RON...).
- **Competencia** (`historico.js`): los filtros de ámbito, tipo, año,
  categoría, provincia e importe son comunes al análisis, a los directorios y
  a las fichas. Los directorios se ordenan por cualquier columna y van
  paginados de 50 en 50. Las búsquedas ignoran tildes y puntuación.
  - *Provincia*: mismo desplegable por comunidad que el radar. No se enseña
    mientras menos de la mitad de las adjudicaciones tengan lugar: filtraría
    sobre una parte pequeña de los datos sin que se notara.
  - *Importe mínimo y máximo* de cada adjudicación (tramos de 5.000 € a
    5 M€). Con alguno puesto, las adjudicaciones sin importe publicado quedan
    fuera.
  - Bajo "Empresas que más ganan", una línea dice cuántas adjudicaciones de
    más de 1 M€ hay con los filtros puestos y qué parte del importe suman, con
    un botón que fija el máximo en 1 M€.
  - Una ficha de empresa fusionada con otra (mismo NIF escrito de dos formas)
    redirige a la que se queda.
- **Enlaces del radar al histórico**: por NIF (`empresa_nif`, que `normalizar.py`
  añade a adjudicaciones y contratos menores) y, si no, por nombre exacto; si no
  hay una única coincidencia, se abre el directorio filtrado. Cuando
  `normalizar.py` ya encontró al organismo o a la empresa en el histórico, el
  enlace va directo a su ficha.
- **Provincia** (`provincia` y `comunidad`, de `normalizar._lugar()` y
  `territorio.py`): salen del código de lugar que publica cada fuente, nunca
  del nombre del organismo. PLACSP da el lugar de ejecución del contrato (NUTS)
  y el código postal del organismo; Euskadi y TED, la región del organismo.
  Lo que solo llega por el buscador web de PLACSP no trae ninguno, y un
  contrato de ámbito estatal ("ES") se queda sin provincia a propósito: no es
  "de Madrid" porque el ministerio tenga allí la sede. La tarjeta muestra
  "Bizkaia · País Vasco" en lugar de "España" y el filtro "Provincia" agrupa por
  comunidad las que tienen registros en la vista; "Sin provincia publicada"
  reúne las españolas sin código. La provincia elegida se conserva al cambiar
  de vista.
- **Resumen del histórico en la tarjeta** (`historial_organismo` e
  `historial_empresa`, de `normalizar._historiales()`): cuántas adjudicaciones
  de servicios de agencia suma el organismo desde 2021, a cuántas empresas, por
  qué importe y cuáles son las tres que más importe acumulan; y, en
  adjudicaciones y contratos menores, lo mismo de la empresa y cuántas veces ha
  ganado en ese organismo. Se calcula en el pipeline a partir de
  `historico-data.js` (el histórico se actualiza justo antes), para que la
  tarjeta no tenga que cargar sus 8 MB. Hereda sus límites: los importes
  incluyen algún contrato enorme que no es de agencia.

Sin dependencias: HTML, CSS y JavaScript sin librerías ni compilación. El único
recurso externo es la tipografía Inter (Google Fonts). `localStorage` se usa
solo para recordar los recuentos de la barra lateral entre las dos páginas.
