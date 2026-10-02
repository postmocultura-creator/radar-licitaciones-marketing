# Análisis de Infoconcurso

Fecha: 2026-10-02. Analizadas la parte pública de https://www.infoconcurso.com
(el dominio es en singular) y la de usuario registrado: alertas, informes,
favoritos y las licitaciones de los últimos 20 días. No es referencia visual;
interesa por lo que ofrece.

## Qué es

Buscador y servicio de alertas de licitaciones y adjudicaciones en España, de
Infobox Solutions S.L. (teléfono con prefijo de Álava). Generalista: obras,
suministros y servicios de cualquier sector. Clasificación hecha a mano por
personas, según ellos mismos, no automática.

- **Fuentes**: DOUE, BOE, boletines autonómicos y provinciales, PLACSP, las
  plataformas autonómicas de Andalucía, Cataluña, Galicia, Navarra y Comunidad
  Valenciana, y perfiles de contratante de los principales organismos.
- **Precio**: 26 €/mes las alertas de convocatorias y otros 26 €/mes las de
  adjudicaciones (72 €/trimestre o 240 €/año cada una); 15 €/mes por usuario
  adicional; copias a más correos, gratis. Prueba de 20 días.
- **Gratis**: los dos buscadores, pero sin lo publicado en los últimos 20 días.

## Cómo estructura la información (OBSERVADO)

Menú: Inicio · Licitaciones · Adjudicaciones · Actualidad · Informes · Favoritos ·
Alertas por e-mail.

**Listado**: tabla de tres columnas (organismo, objeto, fin de plazo). Filtros a
la izquierda: tipo de licitación en árbol de "materias" con recuento (obras /
suministros / servicios → 56 materias de servicios), localización, estado ("plazo
no cerrado" por defecto), texto, organismo adjudicador, rango de fechas; en
adjudicaciones, además, adjudicatario. Adjudicaciones cubre los últimos 6 meses.

**Ficha de licitación**: organismo, objeto, lugar de ejecución (municipio y
provincia), estado de presentación, plazo con fecha de inicio, fecha y **hora**
de fin y "quedan N días", expediente, presupuesto base; pliegos y anuncios
publicados (solo registrados); botón "Marcar favorito"; materias en las que se ha
clasificado. Y tres bloques de contexto:

- *Informes relacionados*: "En los últimos 5 años [organismo] ha adjudicado N
  licitaciones de [materia] a M adjudicatarios por X euros. Los principales: …".
- *Otras licitaciones parecidas*.
- *Búsquedas parecidas*: licitaciones y adjudicaciones del mismo organismo,
  licitaciones en la misma provincia.

**Ficha de adjudicación**: lo anterior más fecha, tipo (definitiva),
adjudicatarios, importe y un resumen del adjudicatario ("en los últimos 5 años ha
recibido N adjudicaciones de M organismos por X euros").

**Alertas**: dos envíos diarios (mediodía y madrugada). Se configuran por
materias (máximo 5), provincias, palabras clave y organismos, cada criterio con
nivel de interés alto / medio / bajo; cada licitación nueva recibe una afinidad y
las alertas llegan ordenadas por ella. Lo enviado se consulta también en la web
("Seleccionados para Ud."). Los favoritos avisan si la licitación cambia.

## Comparación de cobertura (MEDIDO)

Sus 29 licitaciones abiertas de "Información y publicidad" visibles sin registro
(es decir, publicadas hace más de 20 días) frente al radar tras la ejecución del
2026-10-02:

| | Nº |
|---|---|
| Están en el radar | 7 |
| Descargada pero la taxonomía no la recoge | 1 |
| No están | 21 |

De las 21 que faltan:

- **14 son sistemas dinámicos de adquisición, homologaciones y contratos
  publicados hace meses** con plazo abierto durante mucho tiempo (hasta
  2027–2035). Ejemplos:
  homologación de agencias de publicidad, marketing o comunicación para Cetursa
  Sierra Nevada; SDA de publicidad de la Armada; sistema dinámico de publicidad
  de la marca Turismo de Navarra; SDA de comunicación corporativa de LYMA
  (Getafe); SDA de material promocional de EITB. El radar no las tiene por
  diseño: solo mira lo publicado o actualizado recientemente.
- **7 son licitaciones normales**, cuatro de ellas en catalán y de organismos
  catalanes (Generalitat, Reus, Viladecans, Patronat Costa Brava).

Causas comprobadas en el código:

1. `scrapers/placsp.py` lee los perfiles propios de PLACSP (feed 643) y los
   contratos menores (1143), pero **no el feed de plataformas autonómicas
   agregadas (1044)** para las licitaciones abiertas. Esas solo entran por el
   buscador web (`placsp_web.py`), que mira tres días y existe desde finales de
   septiembre. El histórico sí usa el 1044.
2. El buscador web no trae CPV, así que una licitación en catalán, gallego o
   euskera depende de que el título contenga un término de la taxonomía.
3. No hay ninguna vía para lo publicado hace meses con plazo todavía abierto.

Cautela: es una muestra de una sola materia y, por la limitación de su versión
gratuita, anterior a que existiera nuestro buscador web. La comparación justa
con lo de los últimos 20 días necesita la sesión de usuario.

## Parte privada (sesión de usuario, 2026-10-02)

Revisada solo en lectura, con la cuenta de la agencia.

**Alertas por e-mail.** Un envío al día (15:30) con dos lotes: convocatorias y
adjudicaciones. En los cinco últimos envíos: 55–73 convocatorias y 89–140
adjudicaciones por día. Cada licitación lleva una **afinidad** (80, 60 o 50)
calculada con las preferencias; la página "Alertas por e-mail" guarda el
histórico de envíos. No hay otra vista "de entrada": la bandeja es el correo.

**Preferencias.** Cuatro pestañas: materias (máximo 5, cada una con interés
alto/medio/bajo), provincias (todas las que se quiera, con interés), búsquedas
personalizadas (palabras clave) y organismos. La cuenta revisada usa los tres
primeros criterios y ningún organismo.

**Ficha con sesión.** Añade un enlace a la plataforma de origen ("convocatoria en
Plataforma de contratación pública de Euskadi"). No aloja los pliegos.

**Informes.** Formulario con tres modos (por tipo de concurso, por organismo
adjudicador, por adjudicatario), rango de fechas, texto y materia; el informe se
genera o se envía por correo.

**Favoritos.** Lista con nivel de interés. La cuenta tiene uno solo.

### Qué recibe la agencia frente a lo que le interesa (MEDIDO)

Las 320 convocatorias distintas de los cinco últimos envíos (25 sep – 1 oct),
pasadas por nuestra taxonomía y cruzadas con el radar del 2026-10-02:

| | Nº | % |
|---|---|---|
| Convocatorias recibidas | 320 | 100 % |
| Encajan con nuestra taxonomía | 23 | 7 % |
| … de ellas, ya están en el radar | 21 | 91 % de las 23 |
| Relevantes que nuestra taxonomía descarta (revisión a ojo) | ~13 | 4 % |
| Inserciones sueltas de publicidad en medios, en catalán | ~10 | 3 % |
| Resto: mantenimiento informático, licencias, alumbrado navideño, fiestas, cabalgatas… | ~274 | 86 % |

Conclusiones:

1. **Infoconcurso entrega mucho ruido.** De cada diez avisos, nueve no son
   trabajo de agencia. Viene de que sus materias son genéricas y de palabras
   clave amplias.
2. **En lo reciente, al radar no le faltan fuentes: le faltan palabras.** De lo
   que nuestra taxonomía reconoce, tenemos el 91 %. Lo que se escapa (~13) son
   títulos en catalán o gallego ("serveis comunicació, màrqueting…", "disseny
   gràfic, maquetació…", "campaña de información, difusión e sensibilización
   do…") y expresiones en castellano que la taxonomía no tiene ("presencia
   digital", "desarrollo landing", "realización de un audiovisual",
   "retransmisión o streaming de eventos").
3. Contando esas, la cobertura real del radar sobre lo relevante de sus alertas
   ronda el 60 % (21 de ~36).
4. Estas 320 alertas son una muestra de prueba útil: cualquier cambio en la
   taxonomía se puede medir contra ellas.

Pendiente de confirmar con la agencia: si hay una prioridad geográfica y si
quiere en el radar materias que nuestra taxonomía no cubre como tales. Decisión
del 2026-10-02: de momento no se añaden materias nuevas y la localización se
resuelve con un filtro por provincia, sin zona destacada.

## Qué tienen ellos que el radar no

| Infoconcurso | En el radar | Coste de añadirlo |
|---|---|---|
| Sistemas dinámicos, homologaciones y acuerdos marco abiertos | No | Medio: consulta nueva en el buscador de PLACSP por sistema de contratación |
| Plataformas autonómicas completas | Parcial (3 días) | Bajo: el ZIP ya se descarga para el histórico |
| Alertas por correo, dos al día | No | Medio: necesita un servicio de envío y su clave |
| Resumen del organismo dentro de la ficha (quién ha ganado antes) | Enlace a la ficha del organismo | Bajo: un fichero pequeño generado por el pipeline |
| Resumen del adjudicatario dentro de la adjudicación | Enlace a la ficha de la empresa | Bajo, igual |
| Lugar de ejecución y filtro por provincia | Solo España / País Vasco | Medio: el dato está en el XML de PLACSP |
| Hora del fin de plazo | Solo fecha | Bajo |
| Pliegos y anuncios del expediente | Enlace al anuncio original | Alto |
| Favoritos con aviso de cambios | No | Medio (sin cuentas: solo por navegador) |
| Afinidad: orden por interés | No | Medio |
| Licitaciones parecidas | No | Bajo |

## Qué tiene el radar que ellos no

- Selección ya hecha para una agencia (22 categorías de servicio propias) en vez
  de una materia genérica "Información y publicidad" donde entran patrocinios,
  anuncios en prensa y merchandising.
- Contratos menores a punto de vencer, para prospección.
- Licitaciones del resto de Europa (TED) y convocatorias de subvención de la UE.
- Análisis de mercado: rankings, evolución, concentración, competencia por
  número de ofertas, fichas con desglose.
- Sus resúmenes automáticos tienen ruido visible: el del Consorcio de Aguas de
  Bilbao Bizkaia atribuye a "Información y publicidad" 705 adjudicaciones por
  491 M€ con constructoras como principales adjudicatarias, y otros listan como
  adjudicatario textos como "ver publicación".
