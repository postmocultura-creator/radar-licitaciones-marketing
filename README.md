# Radar de licitaciones — agencia de marketing digital

Monitoriza licitaciones públicas abiertas en tres fuentes (UE / Estado
español / Euskadi) que puedan encajar con los servicios de una agencia de
publicidad y marketing digital, y las muestra en un dashboard estático.

## Requisitos

- Python 3.10+ (se usa sintaxis `str | None`)
- `pip install -r requirements.txt` (`requests` para los scrapers,
  `deep-translator` para que `normalizar.py` traduzca al español el título
  y resumen de las calls for proposals — ver esa sección más abajo, la
  fuente solo las publica en inglés)
- Ningún token ni API key: las fuentes usadas son públicas y sin
  autenticación a día de hoy (ver "Notas por fuente" más abajo), y la
  traducción usa MyMemory, gratuita y sin API key. Si alguna fuente
  empezara a exigir una, se leería de variable de entorno — nunca
  hardcodeada — pero ahora mismo no hace falta configurar nada.

Todo este proyecto se construyó y probó con datos reales usando `uv`
(`uv run --python 3.14 --with requests -- python scrapers/ted.py`, etc.,
y `uv run --python 3.14 --with deep-translator -- python normalizar.py`),
porque en esta máquina `python` directo está bloqueado por una política de
Control de aplicaciones de Windows. Si te pasa lo mismo al ejecutar los
comandos de abajo, usa `uv run --python 3.12 --with requests -- python
<script>` en su lugar (ya tienes `uv` instalado).

## Ejecución completa (de cero a dashboard)

Desde la carpeta `licitaciones_marketing/`:

```bash
pip install -r requirements.txt

python scrapers/ted.py
python scrapers/placsp.py
python scrapers/euskadi.py
python scrapers/eu_grants.py

python clasificar.py
python normalizar.py
```

Después, abre `dashboard/index.html` con doble clic. No necesita servidor.

Si una fuente falla (cambio de formato, caída temporal...), su scraper
termina con código de error y deja un `data/raw/<fuente>_..._error.json`
con el motivo, pero **no interrumpe** la ejecución de las otras fuentes ni
de `clasificar.py`/`normalizar.py` (que simplemente avisan y usan lo
último disponible de esa fuente).

`ted.py` y `euskadi.py` descargan también, en la misma ejecución, las
adjudicaciones y (`euskadi.py`) los contratos menores por vencer (ver
secciones más abajo) — no hace falta ningún comando extra. `placsp.py`
hace lo mismo con las adjudicaciones (mismo feed) y descarga aparte los
contratos menores. `eu_grants.py` (Fase 3) tarda varios minutos: hace una
petición adicional por cada convocatoria para traer su descripción
completa (ver sección "Calls for proposals UE").

## Estructura

```
licitaciones_marketing/
├── scrapers/
│   ├── ted.py         API REST v3 de TED (UE) — licitaciones + adjudicaciones
│   ├── placsp.py      ZIP mensual/CODICE de PLACSP (Estado) — licitaciones y
│   │                  adjudicaciones (sindicacion_643) y contratos menores
│   │                  (sindicacion_1143), ambos como ZIP mensual
│   ├── euskadi.py     API REST de KontratazioA (Euskadi) — avisos,
│   │                  adjudicaciones y contratos menores (endpoint /contracts)
│   └── eu_grants.py   API SEDIA del EU F&T Portal (Fase 3) — calls for proposals
├── config.py          taxonomía de categorías + CPV amplios + keywords
│                      (incluye CATEGORIAS_CALLS_UE, la versión en inglés)
├── clasificar.py      aplica las dos capas de clasificación, por tipo_registro
├── normalizar.py      unifica los 4 tipos de registro en un esquema común
├── data/
│   ├── raw/          respuesta cruda de cada ejecución, con timestamp
│   │                 (ted_adjudicaciones_*, euskadi_adjudicaciones_*,
│   │                 euskadi_menores_*, placsp_menores_*, eu_grants_*)
│   ├── clasificado.json
│   └── tenders.json  dataset final (trazabilidad / reuso)
└── dashboard/
    ├── index.html
    ├── style.css
    ├── app.js
    └── tenders-data.js   generado por normalizar.py — esto es lo que lee el dashboard
```

## Ampliar la taxonomía sin tocar código

Todo vive en `config.py`:

- **`CPV_RANGOS`**: añade una tupla `(desde, hasta, "etiqueta")` para cubrir
  un rango CPV nuevo. Verifica el código en
  [simap.ted.europa.eu/cpv](https://simap.ted.europa.eu/web/simap/cpv)
  antes de añadirlo — no copies rangos de memoria.
- **`CATEGORIAS`**: añade una clave nueva (nombre de categoría) con su
  lista de keywords en minúsculas y sin necesidad de quitar acentos (el
  código ya normaliza el texto antes de comparar). También puedes ampliar
  la lista de una categoría existente con sinónimos que veas en los datos
  reales.
- **`EXCLUSIONES`** y **`TERMINOS_MEZCLA`**: si el título ya tiene una
  categoría confirmada por texto pero además contiene uno de estos
  términos, la licitación se incluye igualmente pero marcada
  `revisar_manual` — es el único motivo por el que algo llega a "revisar
  manualmente" ahora (ver más abajo).

## Cómo decide clasificar.py (y por qué el CPV ya no basta por sí solo)

La primera versión de este proyecto usaba el CPV amplio como criterio de
inclusión ("si el CPV cae en el rango, aunque el texto no lo confirme, se
incluye para revisar a mano"). Se probó con datos reales de las tres
fuentes y se descartó: el CPV público es demasiado grosero — describe la
división/grupo, no el contrato concreto — y esa vía colaba sobre todo
contratos de ISP/banda ancha, consultoría de sistemas genérica y
evaluaciones de políticas públicas. Con esa regla, de ~1100 licitaciones
"relevantes" solo ~320 tenían una categoría de texto confirmada; las otras
~780 eran ruido esperando revisión manual — inviable de revisar a mano.

Ahora **el texto decide siempre**: si el título no confirma con una
keyword de `config.CATEGORIAS` que se trata de un servicio de agencia, la
licitación no entra, tenga el CPV que tenga. El CPV solo se usa para
acotar qué trae cada scraper de su fuente (imprescindible en TED, donde la
búsqueda en servidor lo exige). `revisar_manual` ya no es un cajón de
sastre: solo se activa cuando el título confirma una categoría de agencia
Y ADEMÁS contiene un término de `EXCLUSIONES` o `TERMINOS_MEZCLA` — es
decir, un caso concreto de mezcla de servicios (p. ej. "comunicación
institucional... incluye también imprenta"), no una interpretación dudosa
del CPV. Con esto la bolsa de "revisar manual" pasó de ~780 a 1-2
licitaciones en las pruebas reales.

Contrapartida de este cambio: al exigir siempre confirmación por texto,
alguna licitación relevante cuyo título no use ninguna de las keywords de
`config.CATEGORIAS` no aparecerá. Si detectas casos así, la solución es
ampliar `CATEGORIAS` con esos sinónimos, no reintroducir el filtro por CPV
solo.

### Ronda de ampliación de cobertura (recall)

Con el primer recorte a "solo texto confirmado" se pasó de ~1100 a ~320
licitaciones, y una comparación exhaustiva contra los títulos reales de
TED/Euskadi que se estaban quedando fuera mostró varios huecos reales, no
ruido: la palabra **"marketing" a secas no estaba en ninguna categoría**
(se coló con títulos literales como "Servicio. Marketing"), "publicidad"
con límite de palabra no cazaba las formas adjetivas
(publicitaria/publicitario/-os/-as), y faltaban "relaciones públicas",
"estudios de mercado" y variantes de "diseño de sitios web" con el orden
de palabras cambiado. Se amplió `CATEGORIAS` con todo esto (ver el
histórico de cambios en `config.py`) y la cobertura subió a ~555
licitaciones sin reintroducir ruido masivo (`revisar_manual` subió de 1 a
17, siguen siendo casos concretos de mezcla, no un cajón de sastre).

También se corrigió el rango CPV de "Relaciones públicas"
(`79416000-79417000` → `79416000-79416200`): con datos reales se comprobó
que 79417000 es "Servicios de consultoría en seguridad" (ciberseguridad,
protección de datos, guardias de seguridad), un CPV que no tiene nada que
ver con relaciones públicas — otro caso de verificar el significado real
de un código antes de asumirlo por el rango vecino.

**Limitación conocida y aceptada**: TED traduce automáticamente cada CPV a
una frase española (p. ej. "Servicios de estudios de mercado" para el CPV
79310000), y esa frase no siempre describe fielmente el contenido real —
a veces es un estudio de política pública o de necesidades de formación,
no una investigación de mercado comercial. Al usar esas frases como
keywords se gana cobertura real a cambio de aceptar algún falso positivo
ocasional de este tipo. Es un compromiso consciente, no un descuido.

Después de tocar `config.py` solo hace falta volver a ejecutar
`clasificar.py` y `normalizar.py` (no hace falta re-lanzar los scrapers si
el crudo en `data/raw/` sigue siendo reciente).

### Ronda de "se cuelan licitaciones antiguas ya cerradas" (form-type / estado / contrato menor)

Después de ampliar la cobertura de texto, se detectaron licitaciones de
2024-2025 mostrándose como si fueran de hoy. La causa no era la fecha —
era que el dataset mezclaba tipos de aviso que nunca debieron entrar:

- **TED publica varios TIPOS de aviso bajo la misma búsqueda**: llamada a
  licitación (`form-type=competition`), adjudicación (`result`) y
  modificación de un contrato ya en marcha (`cont-modif`). Sin filtrar por
  esto, ~82% de lo que traía TED eran avisos de adjudicación/modificación
  de contratos ya cerrados, no oportunidades nuevas. `ted.py` ahora añade
  `AND form-type=competition` a la query. (Se probó también añadir
  `form-type=result` como segunda consulta para detectar contratos a
  punto de vencer y anticipar relicitaciones; se quitó a petición del
  usuario — ver "Contratos menores" más abajo — porque en cuanto la
  relicitación se publica de verdad, ya aparece aquí por su cuenta, y la
  señal de "vence pronto" solo añadía ruido.)
- **El campo de fecha límite que se estaba pidiendo casi nunca venía
  relleno**: `deadline-date-lot` está vacío en la mayoría de anuncios
  reales; el campo que sí funciona es `deadline-receipt-tender-date-lot`
  (el BT-131 estándar de eForms). Sin fecha límite, el filtro de vigencia
  caía en la fecha de publicación, y ahí es donde se colaban avisos de
  modificación recientes sobre contratos antiguos. `ted.py` pide ambos
  campos; `normalizar.py` usa el que venga relleno.
- **PLACSP mezcla expedientes en cualquier estado** (`PUB` publicado,
  `EV` en evaluación con el plazo ya cerrado, `RES` resuelto, `ADJ`
  adjudicado, `ANUL` anulado). `clasificar.py` ahora solo admite `PUB`.
- **Euskadi: los "contratos menores" son adjudicaciones directas, no
  licitaciones** — por ley se adjudican a dedo (sin concurso) y solo se
  publican para transparencia, después del hecho. Eran el 66% de los
  "Servicios" de Euskadi y casi todos con fecha límite vacía. Se filtran
  por completo por el campo `minorContract` de la propia API. (Se probó
  más tarde recuperarlos aparte como inteligencia de mercado y se retiró
  de nuevo — ver "Contratos menores — probado y retirado" más abajo.)

El efecto combinado: de ~555 a ~227 licitaciones, pero esta vez las 227
son genuinamente convocatorias abiertas a día de hoy, no ruido histórico.
Si algo de esto vuelve a aparecer, el primer sitio donde mirar es si la
fuente ha añadido un tipo de aviso/estado nuevo que no está en estas
listas.

### Enlaces de Euskadi: por qué a veces no van directos al anuncio

Se comprobó en vivo que la "Búsqueda de anuncios" del portal de Euskadi es
un formulario que solo acepta `POST` — no existe una URL con parámetros
que abra directamente un anuncio concreto (se intentó por GET y el propio
servidor devuelve `HttpRequestMethodNotSupportedException`). La única
excepción real vista en los datos es el portal propio de Bizkaia
(`elicitacion.ebizkaia.eus`), que sí añade `numexpediente=` a su URL.
Por eso cada licitación de Euskadi lleva un campo `enlace_directo`: si es
`false`, el enlace va al buscador público (no al portal de licitación
electrónica, que es para presentar oferta con certificado, no para
consultar) y el dashboard muestra el código de expediente en un recuadro
para copiar y pegar en "Código del expediente".

## Notas por fuente (autocrítica de acceso, verificada en vivo)

### TED (UE) — API REST real
`POST https://api.ted.europa.eu/v3/notices/search`, sin autenticación.
Sintaxis experta `campo=valor` combinable con `AND`/`OR`. El código
construye un `OR` de wildcards `classification-cpv=XXXXXX*` para cada
grupo de 6 dígitos dentro de los rangos de `config.CPV_RANGOS`, combinado
con `AND publication-date>=YYYYMMDD`. Paginación por `iterationNextToken`.
Es la fuente más fiable de las tres: CPV real, JSON estructurado, filtrado
en servidor.

### PLACSP (Estado) — sin API REST, ZIP mensual con extensión CODICE
PLACSP no publica una API REST pública documentada. Lo que existe es un
ZIP mensual de sindicación oficial
(`sindicacion_643/licitacionesPerfilesContratanteCompleto3_{AAAAMM}.zip`)
con ficheros ATOM con extensión CODICE 2.07 dentro — mismo formato y
patrón de URL que el ZIP de contratos menores (`sindicacion_1143`, ver
más abajo). **No admite filtros por URL** (ni CPV ni fecha): siempre trae
el histórico completo del expediente desde 2021 más los ficheros
incrementales del mes en curso. El scraper descarga el ZIP, itera TODOS
sus ficheros y filtra en cliente.

**Importante — ver "El feed de PLACSP iba desfasado ~3 semanas" más
abajo**: hasta que se encontró este ZIP, el scraper leía el feed ATOM
paginado equivalente (`.../licitacionesPerfilesContratanteCompleto3.atom`
+ `<link rel="next">`), que iba con ~3 semanas de retraso estructural
respecto al reloj real y no había forma de evitarlo subiendo el número de
páginas. El ZIP mensual reduce ese retraso a ~5 días. Al no haber forma
de pedir "los últimos 30 días" al servidor, conviene ejecutar este
scraper con cierta frecuencia (a diario, por ejemplo) — `normalizar.py`
deduplica por expediente entre ejecuciones.

### Euskadi — sí tiene API REST real, pero sin CPV
`GET https://api.euskadi.eus/procurements/contracting-notices`, sin
autenticación (documentado en
[opendata.euskadi.eus/api-procurements](https://opendata.euskadi.eus/api-procurements/?api=procurements)
y probado en vivo). Admite filtrar por `contract-type-id`, fechas de
publicación y presupuesto, con paginación normal. **Pero su esquema no
incluye ningún campo CPV** — se comprobó contra el JSON Schema real de la
API. Por eso aquí la capa 1 (CPV) no aplica: todo el filtrado real lo hace
la capa de texto sobre el campo `object` del contrato, acotado primero a
`contract-type-id=2` (Servicios) para no traer también obras y
suministros. También se comprobó que `contract-procedure-status-id` no es
fiable como "en plazo" (hay expedientes marcados "Abierto" con fecha límite
de años atrás), así que el estado se recalcula siempre a partir de
`deadlineDate`, nunca del código de estado del organismo.

Ninguna de las tres integraciones hace scraping de HTML: dos son API REST
y la tercera es un feed de sindicación oficial, no una página web.

## Si una fuente cambia de formato

Cada scraper captura sus propios errores de red/parseo y termina solo — no
tumba a los otros dos. Si `clasificar.py` avisa de "no hay crudo" para una
fuente, revisa el `_error.json` más reciente en `data/raw/` para ver el
motivo. Los cambios de formato más probables:

- **TED**: cambio de nombres de campo (`fields`) — comprobar en
  `https://api.ted.europa.eu/swagger`.
- **PLACSP**: cambio de namespaces CODICE o de estructura del feed —
  volver a inspeccionar un `.atom` real con el navegador antes de tocar
  `_parsear_entry()` en `placsp.py`.
- **Euskadi**: cambio de esquema — el descriptor OpenAPI vivo está en
  `https://opendata.euskadi.eus/contenidos/recurso_tecnico/data_apirest/es_def/adjuntos/procurements.json`.

## Filtro final de vigencia (importante)

`normalizar.py` aplica, tras unificar fechas, un filtro final: se descarta
cualquier licitación con plazo límite conocido ya vencido, **aunque su
fecha de "publicación" parezca reciente**. Esto no es redundante: se
comprobó con datos reales que tanto el feed de PLACSP (campo `<updated>`)
como la API de Euskadi (`publication-date.gt`) devuelven una fecha de
"última actualización del expediente", no la fecha original del anuncio —
un contrato ya resuelto en 2021 puede tener esa fecha marcada como "hoy"
simplemente porque su registro se ha vuelto a tocar. Si se confía solo en
esa fecha, se cuelan contratos cerrados hace años. Por eso el plazo límite
manda siempre que se conoce; la fecha de publicación solo decide cuando no
hay plazo límite publicado.

## Adjudicaciones (quién se está llevando cada contrato)

A petición de la agencia (reunión de septiembre de 2026), el radar incluye
ahora una segunda pestaña, "Adjudicaciones": qué empresa/agencia/consultora
gana cada contrato relevante, para entender competencia real. Usa la MISMA
taxonomía de texto que las licitaciones abiertas (`config.CATEGORIAS`) — no
hace falta mantener dos listas de keywords.

Fuentes, verificadas contra datos reales antes de implementar nada:

- **TED**: avisos `form-type=result` (antes descartados explícitamente,
  ver `_construir_query` en `ted.py`) traen `winner-name` y
  `contract-duration-end-date-lot`. `ted.py` descarga ambos tipos de aviso
  en la misma ejecución (`extraer()` + `extraer_adjudicaciones()`).
- **PLACSP**: el mismo feed general (`sindicacion_643`) que ya se
  descargaba trae, para expedientes `ADJ`/`RES`, un bloque
  `cac:TenderResult` con la empresa ganadora, fecha e importe — no hace
  falta un feed nuevo, solo se amplió `_parsear_entry()` para capturarlo.
- **Euskadi**: existe un endpoint aparte y no usado hasta ahora,
  `/procurements/contracts` (distinto de `/procurements/contracting-notices`,
  el que ya se usaba), que da directamente `socialReason`+`CIF` (empresa),
  `awardDate`, `awardAmount`, `contractEndDate` y **sí expone CPV** (el
  endpoint de avisos no). No da el nombre del organismo inline, solo un
  `href` a `/procurements/contracting-authorities/{id}`; se resuelve con
  una petición aparte cacheada por autoridad (96 autoridades únicas para
  603 contratos en una muestra real, nada costoso).

**Fallo real encontrado y corregido**: la resolución de organismo de
Euskadi funcionaba perfecto en aislado (603/603) pero fallaba a 0/603
dentro de la ejecución completa de `euskadi.py` (después de las ~100
páginas de avisos). No se investigó la causa exacta —probablemente una
conexión reutilizada en mal estado tras muchas peticiones seguidas—; se
resolvió con 3 reintentos con backoff en `_resolver_organismo()`, que lo
hace resiliente sin depender de diagnosticar la causa exacta.

Esquema añadido en `normalizar.py` para `tipo_registro="adjudicacion"`:
`empresa_adjudicataria`, `fecha_adjudicacion`, `fecha_fin_estimada` (cuando
la fuente la da; PLACSP aún no la calcula — ver siguiente sección),
`importe_adjudicado_valor`/`_display`. No hay `fecha_limite` (el contrato
ya está cerrado): `fecha_publicacion` guarda la fecha de adjudicación para
que el orden por defecto y el filtro de ventana temporal (últimos 30 días)
no necesiten un camino aparte.

## Histórico de adjudicaciones (desde 2021)

Sección "Competencia" de la barra lateral (`dashboard/historico.html`: análisis
de mercado, directorios de empresas y organismos y sus fichas): qué empresas ganan los contratos de servicios de agencia, por cuánto,
de qué tipo y a qué organismos. Ámbito decidido con el usuario: Estado +
Euskadi + licitaciones españolas que solo llegan por TED, **incluidos
contratos menores**.

Fuentes (verificadas en vivo el 2026-09-30):

| Fuente | Qué es | Tamaño |
|---|---|---|
| `sindicacion_643` | Perfiles alojados en PLACSP | ZIP anual 0,6-2,2 GB (2021-2025), mensual ~300 MB |
| `sindicacion_1044` | Plataformas autonómicas agregadas (Euskadi, Cataluña, Madrid, Andalucía...) | ZIP anual 75-140 MB |
| `sindicacion_1143` | Contratos menores de PLACSP | ZIP anual 155-300 MB |
| TED | Avisos de resultado de organismos españoles | API (`scope=ALL`) |
| API de Euskadi (`/procurements/contracts`, `minor-contract=true`) | Contratos menores de organismos vascos | ~84.000 al año, 50 por página |

Los menores vascos van aparte porque los organismos vascos los publican en
su plataforma, no en PLACSP: el feed de menores de PLACSP solo traía 896
expedientes vascos en 5 años (UPV/EHU, Autoridad Portuaria) frente a los
~2.000 al año relevantes que da la API, y el feed de plataformas agregadas
excluye los menores. Se publican con meses de retraso, así que la
actualización semanal repasa los últimos 6 meses.

El ZIP mensual NO es una foto completa: el de septiembre de 2026 trae ~41.000
expedientes y el 85% de sus adjudicaciones son de 2026. Hacen falta los
anuales (~8,9 GB para 2021-2025, más ~3 GB de mensuales de 2026).

Cómo se construye (`scrapers/historico_adjudicaciones.py` +
`.github/workflows/historico-adjudicaciones.yml`):

- **Modo completo** (a mano, una vez): un trabajo por fuente y periodo (~50),
  4 en paralelo. Cada uno descarga un ZIP, se queda con la última versión de
  cada expediente, filtra por la taxonomía del radar y sube solo lo
  relevante.
- **Mantenimiento: lo hace el pipeline diario**, no una actualización
  aparte. El paso "Histórico de adjudicaciones" de `actualizar-datos.yml`
  (`historico_adjudicaciones.py diario`) suma cada día las adjudicaciones
  nuevas reutilizando los ZIP del mes que `placsp.py` acaba de descargar
  (`data/raw/zips/`), más lo pequeño: plataformas agregadas del mes, TED del
  año y un mes de menores de Euskadi en rotación (cada mes de los últimos 6
  se repasa cada 6 días, porque se publican con retraso). ~1 minuto más
  Euskadi. El orden de los ficheros es estable (lo nuevo va al final y los
  diccionarios conservan sus índices) para que el commit diario sea pequeño.
- El workflow `historico-adjudicaciones.yml` es **solo manual**, para
  reconstruir o reparar. "completo" cuesta ~550 minutos de Actions: el
  2026-10-01, lanzarlo tres veces agotó los 2.000 minutos gratuitos del mes.
- Se guardan **todos los lotes** de cada expediente (un expediente puede
  tener varias adjudicatarias) con NIF, importe sin IVA, ofertas recibidas
  y si la ganadora es pyme. Las empresas se agrupan por NIF: el nombre se
  escribe de muchas formas ("S.L.", "SL", "SOCIEDAD LIMITADA").
- Plataformas agregadas: no rellenan la fecha de adjudicación del lote ni la
  dirección del organismo. La fecha sale del anuncio de adjudicación
  (`DOC_CAN_ADJ`) o de formalización; Euskadi se detecta por lugar de
  ejecución (NUTS ES21x) o por el enlace a contratacion.euskadi.eus.
- **Acuerdos marco con varias adjudicatarias**: PLACSP repite el importe total
  del acuerdo en cada ganadora (Ingenio Media e Imaxe Intermedia, 6,9 M€
  cada una del mismo acuerdo de Turismo de Galicia). Se reparte a partes
  iguales; si no, los totales por empresa se multiplicaban.
- TED antes de eForms (octubre de 2023) apenas rellena el ganador: aporta
  poco (30 expedientes en 2023). Solo entra lo que no está ya en PLACSP.
- Formato compacto por columnas en `dashboard/historico-data.js`
  (diccionarios de empresas y organismos, categorías como máscara de bits):
  con ~70.000 expedientes, como lista de objetos serían ~70 MB.

Ojo al leer importes: la taxonomía deja entrar algunos contratos enormes que
no son de agencia en sentido estricto (gestión de un canal de televisión
autonómico, 54 M€; derechos de una carrera de motos; centralitas de
emergencias). Inflan los totales en euros; el ranking por número no se ve
afectado.

## Contratos menores — probado, retirado, y por qué se está recuperando

Se probó recuperar los "contratos menores" (adjudicación directa, sin
proceso competitivo) como inteligencia de mercado (quién compra qué a
quién), mostrados aparte de las licitaciones abiertas. Se retiró por
completo a petición del usuario: un contrato menor se publica SIEMPRE ya
adjudicado (es su definición legal — no existe un contrato menor "en
plazo"), así que en el dashboard aparecía el badge "Adjudicado" en el
100% de los casos sin excepción. El usuario lo verificó, confirmó que no
le aportaba valor real («si ya está adjudicada una empresa no me
interesa que aparezca, ya que no es una oportunidad») y se quitó de:
`scrapers/placsp.py` (ya no descarga el feed `sindicacion_1143`),
`clasificar.py` (`clasificar_euskadi` vuelve a excluir `minorContract`
por completo) y todo el dashboard (selector de vista, badges y CSS
asociados). También se había probado antes una señal derivada de "a
punto de vencer" (estimar cuándo acaba un contrato ya adjudicado para
anticipar una relicitación) — se quitó en la ronda anterior por el mismo
motivo: en cuanto la relicitación se publica de verdad, ya aparece sola
en el radar, así que la señal solo añadía ruido.

**Por qué se recuperó (Fase 2, implementada)**: el caso de uso es distinto
al que se descartó. Un contrato menor NUNCA relicita (se renueva a dedo,
otra vez sin concurso), así que no hay redundancia posible con el resto
del radar. El objetivo es prospección comercial: ver qué agencia/consultora
tiene el contrato hoy y cuándo caduca, para visitar al organismo antes de
que lo renueve directamente.

Fuentes:

- **Euskadi**: el endpoint `/procurements/contracts` (ver "Adjudicaciones"
  arriba) ya da `contractEndDate` calculado — se reutiliza la misma
  llamada que las adjudicaciones (`minorContract=true`, sin petición
  aparte).
- **PLACSP**: feed mensual `sindicacion_1143`, un ZIP (~20MB) por mes con
  nombre `contratosMenoresPerfilesContratantes_AAAAMM.zip`. Dentro hay un
  fichero SIN sufijo de fecha y ~70 ficheros con sufijo de fecha (uno o
  varios snapshots por día). `AwardDate` sí viene, pero la fecha fin no: se
  calcula sumando `PlannedPeriod/DurationMeasure` (DAY/MON/ANN, aproximando
  MON=30 días y ANN=365 — suficiente para decidir "está a punto de vencer",
  no para precisión de calendario exacta). Un solo mes de ZIP basta, no
  hace falta descargar meses anteriores (ver el bug de cobertura más abajo
  para los detalles de cuánta profundidad histórica da un solo mes).

Ventana de aviso: `config.DIAS_AVISO_CONTRATO_MENOR` (90 días por defecto,
ajustable). Solo entran contratos cuya fecha fin estimada caiga entre hoy y
esa ventana — un contrato ya vencido no sirve para una visita comercial
"antes de que renueve".

**Bug real encontrado y corregido tras la primera versión**: el primer
despliegue de esta fase reutilizaba, para Euskadi, el mismo crudo que
"Adjudicaciones" (contratos adjudicados en los últimos 30 días,
`config.DIAS_ANTIGUEDAD_MAXIMA`) y solo salía 1 resultado. Es un error de
ventana temporal: "adjudicado hace poco" no tiene nada que ver con "vence
pronto" — un contrato adjudicado hace 10 meses con 1 año de duración vence
pronto igual, y quedaba fuera del crudo de 30 días antes de llegar
siquiera a calcularle la fecha fin. Se añadió `extraer_contratos()` con
una ventana propia y mucho más amplia para contratos menores
(`config.DIAS_HISTORIAL_CONTRATO_MENOR`, ~15 meses: la duración máxima
legal de un contrato menor más el margen de aviso), guardada en un crudo
aparte (`euskadi_menores_*.json`, no el de adjudicaciones). Resultado real:
de 1 a 18 contratos menores por vencer solo con este fix.

**Segundo bug, más grave, encontrado al revisar por qué el Estado casi no
aportaba nada**: `extraer_contratos_menores()` de PLACSP solo leía el
fichero SIN sufijo de fecha del ZIP (`contratosMenoresPerfilesContratantes.atom`),
asumiendo que era "el acumulado". Con datos reales se comprobó que es justo
al revés: ese fichero tiene 222 entradas, una muestra pequeña, mientras que
el ZIP completo (73 ficheros — el resto son snapshots diarios con sufijo
de fecha) suma **36.153 entradas, 31.164 expedientes únicos** tras
deduplicar por expediente. Se estaba leyendo el 0,7% de los datos del
Estado. Se corrigió sumando TODOS los ficheros del ZIP (`extraer_contratos_menores()`
itera `z.namelist()` completo, no solo el fichero sin sufijo), con el
mismo mes bastando: la distribución real de `AwardDate` en los 31.164
expedientes únicos ya da miles de entradas desde 2025 hasta hoy, de sobra
para la ventana de 90 días. Resultado final tras ambos fixes: **de 1 a 174
contratos menores por vencer (156 Estado + 18 Euskadi)**.

## Calls for proposals UE (Fase 3) — subvenciones, no compras públicas

Caso de uso, aclarado explícitamente con la agencia antes de implementar:
**no** es que la agencia se presente como beneficiaria de la subvención.
Es detectar convocatorias cuyo proyecto financiado previsiblemente va a
necesitar contratar comunicación/difusión/marketing como parte de sus
actividades, para ofrecerse como proveedora a quien gane la subvención.

**Fuente**: EU Funding & Tenders Portal, API de búsqueda "SEDIA"
(`https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA`),
documentada oficialmente por la Comisión
(`.../screen/support/apis`). `apiKey=SEDIA` es el identificador público que
documenta esa misma página, no un secreto por cuenta.

**Bug de formato de petición, encontrado antes de escribir una sola línea
del scraper**: la documentación de prosa de la API muestra el filtro como
un body JSON plano (`{"bool":{"must":[...]}}`). Se probó tal cual y el
servidor lo ignoraba silenciosamente, devolviendo millones de resultados
sin filtrar. Se interceptó la petición REAL que hace el propio portal
(parcheando `XMLHttpRequest.prototype.send` en la consola del navegador,
ya que el listado de red del navegador integrado no capturaba la llamada
-va dentro de un web component con Shadow DOM-) y resultó ser
`multipart/form-data` con 4 campos (`query`, `languages`, `displayFields`,
`sort`), cada uno un blob JSON, no un body JSON directo. Sin este formato
exacto el filtro de `type`/`status` no funciona.

**El listado no trae descripción larga**: los campos que sí devuelve
(`displayFields`) no incluyen el texto de "Expected Outcome"/objetivo de
la convocatoria -se comprobó pidiéndolo explícitamente y no vuelve-. Con
solo el título, el recall es demasiado bajo (prueba real: 4 de 100
títulos encajaban con la taxonomía). Hace falta una segunda petición por
convocatoria (servicio "Topic Details", `text="<identifier>"`) que sí
devuelve el texto completo en el campo `descriptionByte` (pese al nombre,
es HTML, no un tamaño en bytes). Son ~500-600 peticiones adicionales por
ejecución, 1 por segundo por respeto a la fuente: el scraper tarda varios
minutos.

**Taxonomía en inglés, con un fallo real de precisión encontrado y
corregido con datos reales**: la primera ronda de `config.CATEGORIAS_CALLS_UE`
incluía términos sueltos como "dissemination", "citizen engagement" y
"stakeholder engagement". Con datos reales, 101 de 162 coincidencias
venían solo de "dissemination" -jerga administrativa obligatoria en casi
cualquier proyecto europeo (todo Horizon Europe exige un plan de
dissemination como entregable formal, sea del tema que sea)-, incluyendo
un caso flagrante: "Fire prevention and mitigation for EVs in confined
areas" (nada que ver con marketing) coló solo por esa palabra. Mismo
problema de fondo que "formacion"/"consultoria" sueltas en la taxonomía en
español (ver más abajo). Se retiraron los términos sueltos genéricos y se
dejaron solo frases específicas ("dissemination and exploitation", "social
media campaign", "stakeholder engagement strategy"...). Resultado: de 162
a 50 coincidencias, bastante más precisas -aunque, a diferencia de la
taxonomía en español, esta es una primera ronda sin el mismo rodaje de
varias iteraciones con revisión real; es esperable que necesite más ajuste
con uso real, igual que le pasó a aquella-.

Esquema en `normalizar.py` para `tipo_registro="convocatoria_ue"`: misma
semántica de fecha que una licitación (`fecha_limite` = fecha límite de
solicitud, con la misma cuenta atrás/urgencia visual), más `programa`
(tipo de acción/programa de financiación). Sin presupuesto: `budgetOverview`
es una estructura anidada por año/acción/lote sin un número único fiable,
así que se deja "no publicado" en vez de inventar una cifra aproximada.

### Traducción al español (a petición del usuario)

A diferencia de TED (que publica oficialmente en español y de ahí se toma
`notice-title.spa`), el EU Funding & Tenders Portal **no** publica sus
convocatorias en español — se comprobó pidiéndolo explícitamente con
`language=es` a la API SEDIA: el título y la descripción vuelven en
inglés igualmente, el campo `language` es un metadato de indexación, no
una traducción real de contenido. Hace falta traducir de verdad.

Se probó `deep-translator` con dos motores gratuitos sin API key:
- **Google Translate**: `TooManyRequests` en la primera petición.
- **MyMemory**: funcionó en una prueba aislada, pero dentro de la
  ejecución real de `normalizar.py` dio `TooManyRequests` de forma
  persistente (no puntual — se reintentó minutos después y seguía
  igual), probablemente por ser una red/IP compartida en este entorno.

Con eso, `normalizar.py` traduce en dos niveles: primero mira
`data/traducciones_manuales.json` (título + resumen de las convocatorias
del momento, traducidos a mano una vez porque el servicio automático no
respondía) y solo si el texto no está ahí intenta MyMemory como última
opción, con 3 reintentos. Si ninguno de los dos funciona para un texto
nuevo, se deja en inglés y `normalizar.py` **avisa por stderr** con el
recuento y un adelanto de qué se quedó sin traducir — nunca en silencio.
Si vuelves a ejecutar el pipeline con convocatorias nuevas que no estén
en el diccionario manual y el servicio automático sigue caído, ese aviso
es la señal de que hay que traducirlas a mano otra vez (o revisar si el
servicio ya responde).

## Servicios que no se ofrecen: exclusión dura de imprenta/impresión

El usuario revisó la pila de "revisar manual" (30 casos) y confirmó que
eran TODOS mezclas con imprenta/impresión/artes gráficas — servicios de
producción física que la agencia no ofrece. Antes, `config.TERMINOS_MEZCLA`
marcaba estos casos como "revisar_manual" (se incluían, con aviso). Ahora
es `config.SERVICIOS_NO_OFRECIDOS` y actúa como exclusión dura: si el
título contiene cualquiera de estos términos, la licitación se descarta
por completo, aunque el resto del contrato sí sea de agencia — no tiene
sentido mostrarla ni para revisión si es un servicio que no se va a
ofrecer. `config.EXCLUSIONES` (limpieza, seguridad, obra civil...) no se
ha tocado: sigue marcando "revisar_manual" en vez de descartar, porque el
usuario no ha pedido cambiar ese comportamiento y en la práctica apenas se
activa.

## Ronda de recall en la taxonomía (a petición del usuario)

Tras la ronda anterior (precisión ante todo), el usuario pidió lo
contrario: **"prefiero que se cuele alguna que no interese a que no
metamos otras que sí puedan ser interesantes"**. `config.CATEGORIAS` se
amplió con muchas más variantes/sinónimos por categoría (ver comentario
en el propio archivo). Se mantiene una única línea roja: palabras sueltas
que en datos reales dieron 50-100% de ruido puro (`formacion`,
`consultoria`, `tecnologia`, `automatizacion`, `inteligencia
artificial`/`ia`) siguen exigiendo frase completa — no por precaución
excesiva, sino porque sin eso la categoría deja de poder navegarse
(cientos de contratos de limpieza, obra civil o cursos de conducción por
cada uno relevante). El resto de términos sí se ha relajado a propósito,
aceptando algún falso positivo ocasional (`influencer`, `marketplace`,
`chatbot` sueltos, por ejemplo).

Verificación adicional con datos reales de Euskadi (muestra de 60 títulos
descartados al azar + búsqueda dirigida sobre palabras candidatas):
`comunicacion` a secas ronda 55-60% de precisión (`"Servicio de gabinete
de comunicacion"`, `"agencia que coordine la comunicación..."` frente a
`"comunicación oral en euskera"` de un programa de idioma) — se acepta
bajo el mismo criterio de recall. `marca` y `agencia` sueltas SÍ se
probaron y se descartaron: `marca` salió dominada por "marca
[fabricante]" en equipamiento (50% falsos) y `agencia` por "agencia de
viajes" (8 de 14 casos) — ningún parecido con "agencia de publicidad".
Añadidas también `gabinete de comunicacion` y `plan integral de
comunicacion` como frases seguras, y el CPV `79822500` ("Servicios de
diseño gráfico", verificado en TED) a `CPV_RANGOS`.

## El feed de PLACSP iba desfasado ~3 semanas — hallazgo crítico (RESUELTO)

Investigando por qué el radar recogía pocas licitaciones (el usuario
esperaba más, recordando un test previo con más volumen), se comprobó
en vivo -con `curl` y parámetros anti-caché, en peticiones separadas por
más de 15 minutos- que la URL base del feed ATOM de licitaciones abiertas
(`sindicacion_643`, página 1 / `rel="self"`) devuelve **siempre el mismo
contenido exacto**, y que `<link rel="next">` avanza hacia atrás en el
tiempo (fechas cada vez más antiguas), no hacia delante. Es decir: la
página 1 no es "lo más reciente ahora mismo" pese a que su cabecera HTTP
`Last-Modified` sugiere que sí — es el extremo más reciente de una
ventana que, en el momento de la comprobación, iba con **~3 semanas de
retraso** respecto al reloj real.

**Primer intento (insuficiente, dejado de usar)**: subir `MAX_PAGINAS` a
100 en `scrapers/placsp.py`. Esto ayudó a que la ventana de 30 días
cubierta desde el ancla desfasada no se quedara corta, y sí aumentó el
número de licitaciones capturadas, pero **no arreglaba el problema de
fondo**: por mucho que se subiera `MAX_PAGINAS`, `rel="next"` retrocede
en el tiempo desde una ancla que seguía fija ~3 semanas por detrás del
reloj real — nunca se llegaba a nada más reciente que esa ancla. El
usuario señaló explícitamente el problema de negocio que esto causaba:
"que el feed llegue con 18 días de retraso nos da 18 días menos para
trabajar una licitación, algunas incluso salen con un plazo menor de
esos días para entregar la documentación" — con el `MAX_PAGINAS=100` el
radar seguía perdiendo sistemáticamente entre 2 y 3 semanas de la
ventana de respuesta real de cada licitación del Estado.

**Solución real, encontrada por analogía con el ZIP de contratos
menores** (más abajo en este documento): `sindicacion_643` (el feed
general, no solo el 1143 de menores) **también publica un ZIP mensual**,
con el mismo patrón de URL que el de menores
(`.../sindicacion_643/licitacionesPerfilesContratanteCompleto3_{AAAAMM}.zip`),
no documentado en ningún sitio de prosa pero confirmado en vivo (HTTP
200, `content-type: application/zip`, ~180 MB). Cada ZIP mensual trae un
fichero histórico completo (con expedientes desde 2021, partido en varias
piezas) más varios ficheros incrementales con timestamp real en el
nombre del propio fichero
(`licitacionesPerfilesContratanteCompleto3_20260923_211008_9.atom`).

Verificado con datos reales del mismo día (25-26 de septiembre de 2026),
comparando el ATOM paginado contra el ZIP mensual sobre el mismo
universo de expedientes:

| | ATOM paginado (100 páginas) | ZIP mensual |
|---|---|---|
| Retraso de la entrada más reciente | ~18 días (máx. observado: 8 sept.) | ~5 días (máx. observado: 21 sept.) |
| Expedientes "PUB" totales | 4.114 | 5.659 |
| "PUB" con plazo todavía abierto **hoy** | 998 | **3.202** |
| Licitaciones de marketing con plazo abierto (tras taxonomía + ventana) | 12 | **42** |

`scrapers/placsp.py` se reescribió para que `extraer()` (licitaciones
abiertas) use el mismo mecanismo que ya tenía `extraer_contratos_menores()`
(`_extraer_zip_mensual()`, ahora compartida por ambas) en vez de la
paginación ATOM. Se eliminó el código de paginación (`MAX_PAGINAS`,
`PETICIONES_POR_SEGUNDO`, el seguimiento de `<link rel="next">`), ya
innecesario.

**Coste operativo**: una sola descarga de ~180 MB por ejecución (en vez
de 100 peticiones HTTP pequeñas), con un `timeout` de 300s. El tiempo
total (descarga + parseo de ~114 ficheros XML) ronda 1-2 minutos según la
conexión — comparable o mejor que el enfoque anterior.

**Lo que esto NO cambia**: el filtro final de vigencia
(`_dentro_de_ventana_temporal` en `normalizar.py`, ver más arriba) sigue
haciendo falta igual: el ZIP también puede traer expedientes "PUB" con
plazo ya vencido en la práctica (algo se toca sin que el estado cambie),
así que la fecha límite real sigue mandando sobre el estado que publica
la fuente.

Euskadi, para comparar, se comprobó en su momento que SÍ está al día (se
verificó en vivo que `publication-date.gt` devuelve expedientes con
`lastPublicationDate` de hace 1-2 días) — el desfase era un problema
específico del feed ATOM paginado de PLACSP, ya resuelto con el cambio a
ZIP mensual.

## Desfase de PLACSP: de dónde sale de verdad (septiembre 2026)

Revisado otra vez el 2026-09-30 con los nombres de los ficheros
incrementales del ZIP (llevan la hora a la que PLACSP generó cada lote):
el ATOM y el ZIP salen **de los mismos lotes de exportación**, así que
cambiar de uno a otro ya no gana nada. Ese día el ATOM estaba al día (última
entrada del 29/09 a las 20:15), no 18-21 días por detrás como cuando se
escribió la sección anterior.

El retraso lo pone la propia exportación: PLACSP genera un lote hacia las
20:15 con lo publicado ese día, pero **no todos los días laborables**, y
luego se pone al día de golpe. En septiembre: lo del 9-11 salió el 14, lo del
18 el 21, lo del 23-25 el 28. Unos 9 de 21 días laborables llegaron con 1-5
días de retraso; el resto, el mismo día (el workflow corre a las 00:47 hora
española, después del lote).

**Solución: `scrapers/placsp_web.py`**, aviso temprano desde el buscador web
de PLACSP, que lee de la base de datos de la plataforma y muestra lo
publicado en el mismo día (291 expedientes de servicios publicados el 30/09
visibles a media tarde, sin lote exportado). Busca día a día (hoy, ayer,
anteayer) los expedientes de "Servicios" en estado "Publicada" con un
Chromium sin interfaz (Playwright): ~800 filas, ~40 páginas, un par de
minutos.

- Cruce con el feed (28-29/09, 544 filas): cuando el enlace permanente
  (`idEvl`) coincide, título y organismo coinciden exactos, así que el id
  (expediente + título) es el mismo y `normalizar.py` los fusiona; gana la
  versión del feed (trae CPV).
- El buscador incluye además las **plataformas autonómicas agregadas**
  (Cataluña, Madrid, Andalucía, Galicia, La Rioja, Euskadi...), que no
  están en `sindicacion_643`: el 28-29/09, 196 de 544 filas solo estaban en
  la web. Por eso lo leído se acumula en `data/placsp_web_acumulado.json`
  (commiteado) hasta que vence el plazo: si no, desaparecerían a los 2 días.
- Al deduplicar tiene la prioridad más baja: si la misma licitación está
  en el feed, en TED o en la API de Euskadi, gana esa.
- Los actores de Apify para PLACSP que se revisaron leen el mismo feed
  (tienen el mismo desfase) y tienen muy poco uso (2-9 usuarios).
- Es la vía más frágil del radar (aplicación JSF con estado de sesión, sin
  API). Si falla, guarda su `_error.json` y el radar sigue con el feed.

## Campo "tipo de contrato" (descripción oficial del CPV)

El usuario, mirando las webs de Euskadi y de la UE, vio que el formulario
de búsqueda oficial tiene un campo "Tipo de contrato" con valores como
"Servicios de publicidad" y preguntó si lo teníamos en cuenta. Verificado
en vivo: en Euskadi ese campo es el genérico que ya usábamos (Obras /
Servicios / Suministros...), no algo específico de publicidad. El campo
específico ("Servicios de publicidad y de marketing", etc.) es en
realidad la descripción oficial del código CPV, publicada por cada
fuente.

Se añadió como campo informativo (`tipo_contrato`) en el esquema final,
tomado del **vocabulario CPV 2008 oficial en español** (9.454 códigos,
descargado del codelist CODICE de PLACSP:
`contrataciondelestado.es/codice/cl/2.04/CPV2008-2.04.gc`, guardado en
`cpv_nombres.json`). Se usa el primer CPV de la licitación; en Euskadi
(que no expone CPV) queda "no publicado", nunca inventado.

**Importante — por qué NO se usa como filtro**: el propio usuario lo
verificó de forma independiente y confirmó lo que ya sabíamos por otra
vía: el CPV real de una licitación de marketing a veces cae en un grupo
genérico ajeno (p. ej. `50000000` = "Servicios de reparación y
mantenimiento" para un contrato de mantenimiento de una web). Filtrar por
"tipo de contrato" dejaría fuera casos reales — la única fuente de verdad
para incluir o no una licitación sigue siendo el texto del título (capa 2
de `clasificar.py`). Se muestra en la tarjeta expandida únicamente como
contexto adicional.

## Ampliación de taxonomía (16 categorías reales de agencia)

Ronda de revisión de cobertura pedida explícitamente por el usuario,
aportando una lista de 16 tipos de servicio reales de una agencia de
marketing digital. Antes de tocar `config.py` se verificaron con datos
reales de TED/Euskadi/PLACSP las palabras candidatas para cada categoría
que faltaba — la misma metodología que ya se usó en la ronda anterior de
ampliación de cobertura (ver más abajo). El resultado confirmó, otra vez,
que las palabras sueltas y genéricas son la trampa: `formacion` (72
coincidencias, ninguna de marketing: formación en seguridad industrial,
conducción segura, pintura...), `consultoria` (96 coincidencias: obra
civil, prevención de riesgos, congresos...), `inteligencia artificial` (13
coincidencias, todas ajenas: ética de la IA, ciberseguridad, educación),
`automatizacion` sola, `influencer` sola (coló un documental titulado
"L'Influencer medieval"), `marketplace` sola (coló "AWS marketplace") y
`tienda online` sola (coló una cata de vinos) fueron descartadas como
keywords sueltas. Por eso las categorías nuevas usan frases completas y
acotadas, aceptando que algunas partan con pocas o cero coincidencias en
la ventana actual — prioriza precisión sobre recall, igual que el resto de
`config.py`.

Categorías nuevas añadidas: **Estrategia de marketing**, **Creación de
contenidos**, **E-commerce**, **Marketing de influencers / creators**,
**Automatización e IA de marketing**, **Marketing B2B**, **Formación y
consultoría de marketing**, **Tecnología y MarTech**. Además, "Email
marketing / marketing automation" se renombró a **"Email marketing y
CRM"**, añadiendo `gestion de relaciones con clientes` (no `crm` a secas:
en datos reales ese término genérico aparece en sistemas de gestión de
relación con CIUDADANOS, no con clientes, sin nada que ver con una
agencia).

## Dashboard

Rediseñado en octubre de 2026 (estructura y sistema de diseño tomando como
referencia la aplicación de Tendios). El porqué de cada decisión está en
`docs/diseno/`: `REFERENCE-AUDIT.md`, `INFORMATION-ARCHITECTURE.md`,
`DESIGN-SYSTEM.md` y `PROJECT-STATE.md`.

Dos páginas, una barra lateral común (`nav.js`) y una ruta de hash por vista,
para que cada una tenga su dirección y funcione el botón "atrás":

| Sección | Vista | Dirección |
|---|---|---|
| — | Inicio (resumen del día) | `index.html#/inicio` |
| Oportunidades | Licitaciones: pestañas "Publicadas recientemente" y "Licitaciones abiertas" | `index.html#/licitaciones/recientes`, `#/licitaciones/abiertas` |
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
- **Texto explicativo de cada vista** (`EXPLICACION_TIPO` en `app.js`, bajo el
  título): qué aparece y con qué criterio, para que alguien de la agencia
  entienda la vista sin leer este README. Solo criterio, nunca el razonamiento
  interno.
- **Tarjeta** (`plantillaTarjeta()`): código de expediente, fuente, chip "Nuevo
  hoy/ayer" y urgencia; título, organismo y territorio; pie con las fechas o la
  adjudicataria; columna de importe. Se despliega (`<details>/<summary>` nativo,
  accesible por teclado) con el detalle en pares dato/valor: información
  general (incluidos expediente y CPV), fechas (incluida la de entrada en el
  radar) e importes, la descripción, las categorías y los enlaces: anuncio
  original, "Historial de la empresa" y "Quién gana en este organismo" (estos
  dos llevan al histórico).
- **Código de color por urgencia**: rojo ≤7 días, ámbar ≤21 días, verde el
  resto, gris si no hay fecha límite publicada (en contratos menores: rojo ≤30,
  ámbar ≤60). Es señal funcional, igual en todas las vistas y siempre con
  texto. Al ordenar por fecha, lo ya vencido va al final.
- **"Solo pendientes de revisar (N)"**: solo aparece si hay algo que revisar.
- **Importes**: `normalizar.py` los entrega como "865,200 EUR"; el dashboard los
  pasa a "865.200 €" sin tocar la moneda (TED publica cada licitación en la
  suya: SEK, PLN, RON...).
- **Competencia** (`historico.js`): los filtros de ámbito, tipo, año y
  categoría son comunes al análisis, a los directorios y a las fichas. Los
  directorios se ordenan por cualquier columna y van paginados de 50 en 50. Las
  búsquedas ignoran tildes y puntuación.
- **Enlaces del radar al histórico**: por NIF (`empresa_nif`, que `normalizar.py`
  añade a adjudicaciones y contratos menores) y, si no, por nombre exacto; si no
  hay una única coincidencia, se abre el directorio filtrado.

Sin dependencias: HTML, CSS y JavaScript sin librerías ni compilación. El único
recurso externo es la tipografía Inter (Google Fonts). `localStorage` se usa
solo para recordar los recuentos de la barra lateral entre las dos páginas.

## Auditoría completa (bugs y mejoras encontrados en septiembre 2026)

A petición del usuario ("hemos hecho y deshecho muchas cosas, puede que
haya algún fallo"), se auditó el proyecto entero (scrapers, `clasificar.py`,
`normalizar.py`, dashboard) contrastando cada sospecha con datos reales, no
solo leyendo código. El hallazgo grande fue el desfase de PLACSP (sección
propia más arriba). El resto, más pequeños pero reales:

- **Filtro de presupuesto roto en 3 de las 4 pestañas**: `presupuesto_valor`
  solo se rellena para `tipo_registro="licitacion"` (adjudicaciones y
  contratos menores usan `importe_adjudicado_valor`, un campo distinto; las
  calls for proposals no tienen presupuesto). El control seguía visible y
  usable en las 4 pestañas, así que aplicarlo fuera de "Licitaciones
  abiertas" daba 0 resultados sin explicación. Arreglado ocultando el
  control (`TIPOS_CON_PRESUPUESTO` en `app.js`) cuando la pestaña activa no
  lo soporta. Al implementarlo apareció un segundo bug: `[hidden]` no
  ocultaba nada porque `.filtros-avanzados__contenido label { display:
  flex }` en `style.css` gana por cascada al `display:none` del user-agent
  para `[hidden]` (el CSS de autor siempre gana al del UA, sea cual sea su
  especificidad) — hubo que añadir explícitamente
  `.filtros-avanzados__contenido label[hidden] { display: none }`.
- **El botón "⚠ N pendientes de revisar" no tenía estado visual activo**:
  el JS hacía `classList.toggle("activo", ...)` pero no existía ninguna
  regla `.activo` en `style.css`. El filtro funcionaba, pero el botón no
  cambiaba de aspecto. Añadida `.enlace-revisar.activo`.
- **En "Adjudicaciones" no se podía buscar por la empresa ganadora**: el
  buscador de texto solo miraba título/organismo/resumen, pese a que el
  objetivo explícito de esa pestaña es ver qué empresa se lleva cada
  contrato. Añadido `empresa_adjudicataria` al pajar de búsqueda.
- **La deduplicación (TED/PLACSP publicando el mismo contrato) solo cubría
  licitaciones, nunca adjudicaciones**: `_clave_dedup` era siempre `""`
  para `tipo_registro="adjudicacion"`, pese a que el mismo contrato sobre
  el umbral UE puede aparecer adjudicado tanto en el aviso "result" de TED
  como en el bloque `TenderResult` del feed general de PLACSP — la misma
  razón que ya justificaba deduplicar licitaciones. Extendido a
  adjudicaciones con la misma heurística (título+organismo normalizados).
  Deliberadamente NO extendido a contratos menores ni a calls for
  proposals: un organismo puede adjudicar varios contratos menores
  genuinamente distintos con título casi idéntico (p. ej. "Servicio de
  diseño gráfico" a proveedores distintos en fechas distintas), y
  deduplicarlos por título+organismo fusionaría contratos reales — el
  error contrario al que la heurística intenta evitar. La clave de
  deduplicación ahora lleva el `tipo_registro` como prefijo para que una
  licitación y una adjudicación con el mismo título+organismo (algo
  normal: el título no cambia entre el anuncio y el resultado) no se
  pisen entre sí al vivir en pestañas distintas.
- **Fichero de depuración huérfano**: `data/_tmp_descartados_placsp.json`
  (137 KB, resto de una investigación anterior) no se referenciaba en
  ningún sitio del código. Borrado.

## Automatización (GitHub Actions + Vercel)

El pipeline completo (scrapers + clasificar + normalizar) no depende de
ningún ordenador encendido: corre a diario en GitHub Actions, gratis, y el
dashboard se sirve desde Vercel sin coste ni intervención manual.

**Por qué no Vercel para la parte de scraping**: sus funciones serverless
gratuitas se cortan a los pocos segundos, y este pipeline tarda varios
minutos (el scraper de calls for proposals hace ~560 peticiones a 1 por
segundo aposta, y el ZIP de PLACSP son ~180 MB). GitHub Actions sí está
pensado para jobs de varios minutos y es gratis para este volumen (2.000
minutos/mes en cuenta personal; este pipeline usa unos 15-20 minutos al día,
~500-600 al mes). Vercel entra solo para la otra mitad: alojar el resultado
estático (HTML/JS/CSS), que es exactamente lo que su plan gratuito hace
mejor.

Piezas:

- **`.github/workflows/actualizar-datos.yml`**: corre los 4 scrapers (cada
  uno con `continue-on-error` — si uno falla, los demás siguen, igual que en
  local), luego `clasificar.py` y `normalizar.py`, y hace commit + push de
  `data/tenders.json` y `dashboard/tenders-data.js` solo si el resultado
  tiene un mínimo razonable de registros (si varias fuentes fallan a la vez
  y el dataset sale sospechosamente vacío, el job falla en vez de publicar y
  pisar los datos buenos del día anterior). Se puede lanzar también a mano
  desde la pestaña "Actions" de GitHub (`workflow_dispatch`).
- **Vercel**: no hace falta build ni config nueva en el repo — el proyecto
  se importa desde la web de Vercel apuntando a este repositorio de GitHub,
  con el único ajuste de poner **"Root Directory" = `dashboard`** al
  importarlo (así Vercel sirve `index.html`/`app.js`/`style.css`/
  `tenders-data.js` tal cual, sin detectar ningún framework ni intentar
  compilar nada). Cada vez que el workflow de arriba actualiza
  `tenders-data.js` con un push, Vercel redespliega solo.
- **`data/raw/` y `data/clasificado.json` no se versionan** (`.gitignore`):
  se regeneran enteros en cada ejecución, tanto en local como en CI —
  versionarlos no aporta nada y en local ya acumulan cientos de MB.

Coste real de esta automatización: **0 tokens de Claude, 0 € de
hosting/CI** — todo el pipeline es Python puro sin ningún paso que pase por
un modelo de IA (ni siquiera la traducción, que usa la API gratuita de
MyMemory). Solo hace falta volver a pedirme algo si en el futuro quieres
cambiar el propio código.

## Sesión de uso habitual (ejecución manual, en local)

```bash
python scrapers/ted.py
python scrapers/placsp.py
python scrapers/euskadi.py
python scrapers/eu_grants.py
python clasificar.py
python normalizar.py
```

Abre `dashboard/index.html`. Si aparece el botón "⚠ N pendientes de
revisar", son casos concretos de mezcla de servicios (p. ej. comunicación
+ imprenta en el mismo contrato) — decide tú si aplican. Si no aparece,
es que no hay ninguno en esta pasada.
