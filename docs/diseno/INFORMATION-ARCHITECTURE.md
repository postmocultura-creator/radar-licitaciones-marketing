# Arquitectura de información

Fecha: 2026-10-02. Estado: **publicada** el 2026-10-02, igual que la segunda
ronda ("Ampliación de información", al final).

## Qué había y qué problema tenía

Dos páginas sueltas:

- `index.html`: cinco pestañas al mismo nivel (Publicadas recientemente,
  Licitaciones abiertas, Adjudicaciones, Contratos menores por vencer, Calls for
  proposals UE).
- `historico.html`: el histórico de adjudicaciones, al que solo se llegaba por un
  botón de la cabecera.

Problemas:

1. **Tres propósitos distintos mezclados al mismo nivel.** Las pestañas no decían
   para qué sirve cada una: unas son oportunidades a las que presentarse, otra es
   prospección comercial y otra es información sobre competidores.
2. **"Publicadas recientemente" es un subconjunto de "Licitaciones abiertas"**
   (mismas licitaciones, solo las españolas de los últimos tres días), pero
   aparecía como una pestaña hermana.
3. **Las adjudicaciones estaban partidas en dos sitios sin relación**: los últimos
   30 días en una pestaña, y desde 2021 en otra página.
4. **No había vista de conjunto.** Se entraba directamente a una lista; para saber
   qué cerraba esta semana o qué contrato vencía había que ir pestaña por pestaña.
5. **Nada estaba enlazado.** Desde una adjudicación no se podía saltar a la ficha
   de la empresa ganadora; desde una licitación no se podía ver quién gana en ese
   organismo. Y en el histórico solo se veían las 20 primeras empresas: las otras
   27.000 solo aparecían si se buscaban por nombre.
6. La ficha de empresa era una ventana emergente sin dirección propia: no se podía
   compartir ni volver a ella con el botón "atrás".

## Estructura nueva

Barra lateral común a toda la plataforma, por propósito:

```
Inicio                                   index.html#/inicio

OPORTUNIDADES
  Licitaciones                           index.html#/licitaciones/recientes
     pestañas: Publicadas recientemente · Licitaciones abiertas
                                         index.html#/licitaciones/abiertas
  Calls for proposals UE                 index.html#/calls

PROSPECCIÓN COMERCIAL
  Contratos menores por vencer           index.html#/menores

COMPETENCIA
  Adjudicaciones recientes               index.html#/adjudicaciones
  Análisis de mercado                    historico.html#/mercado
  Empresas                               historico.html#/empresas
     ficha de empresa                    historico.html#/empresa/<id>
  Organismos                             historico.html#/organismos
     ficha de organismo                  historico.html#/organismo/<id>
```

Cada vista tiene su propia dirección (ruta de hash), así que se puede enlazar,
guardar en marcadores y recorrer con "atrás/adelante".

### Qué se conserva, qué se mueve y qué es nuevo

| Antes | Ahora |
|---|---|
| Pestaña "Publicadas recientemente" | Licitaciones → pestaña "Publicadas recientemente" (sigue siendo lo primero que se ve al entrar en Licitaciones). También encabeza Inicio |
| Pestaña "Licitaciones abiertas" | Licitaciones → pestaña "Licitaciones abiertas" |
| Pestaña "Calls for proposals UE" | Oportunidades → Calls for proposals UE |
| Pestaña "Contratos menores por vencer" | Prospección comercial → Contratos menores por vencer |
| Pestaña "Adjudicaciones" | Competencia → Adjudicaciones recientes |
| `historico.html` (panel) | Competencia → Análisis de mercado |
| Ficha de empresa (ventana emergente) | Página propia, con dirección |
| Cifras de la cabecera (total, en plazo, a revisar…) | Junto al título de cada vista |
| Texto explicativo de cada pestaña | Bajo el título de cada vista (mismo texto) |
| Filtros en una barra + "Más filtros" | Panel de filtros a la izquierda, todos visibles; "Ordenar por" junto al recuento |
| — | **Inicio**: cinco cifras, lo publicado recientemente, lo que cierra en 7 días, los contratos menores que vencen antes, las últimas adjudicaciones y el reparto por categoría |
| — | **Empresas**: directorio completo, ordenable y paginado |
| — | **Organismos**: directorio completo y ficha de organismo (qué empresas ganan en él) |
| — | Enlaces cruzados: de una adjudicación a la ficha de la empresa y de cualquier registro español al organismo |

### Información que se añade a cada tarjeta

Ya estaba en los datos y no se mostraba: código de expediente, CPV, fecha en que
entró en el radar (con chip "Nuevo hoy / ayer"), presupuesto de licitación en las
adjudicaciones. Las fechas se escriben "19 oct 2026" en vez de "2026-10-19" y los
importes en formato español ("865.200 €" en vez de "865,200 EUR").

No se ha quitado ningún dato.

### Comportamiento que cambia

- Al ordenar por fecha límite o por vencimiento, lo que ya ha pasado (plazo
  cerrado, contrato vencido) va al final y no al principio.
- Las búsquedas no distinguen tildes ("comunicacion" encuentra "Comunicación") y,
  en el histórico, tampoco la puntuación ("uniprex sau" encuentra "UNIPREX,
  S.A.U.").
- La identidad de color por pestaña (verde azulado, violeta, rosa, índigo)
  desaparece: un solo azul de acento, como en la referencia. El código de
  urgencia rojo/ámbar/verde se mantiene.

## Enlaces entre el radar y el histórico

- "Historial de la empresa" → `historico.html#/empresas?nif=…&q=…`. Si el NIF o el
  nombre coinciden con una sola empresa del histórico, abre su ficha; si no, el
  directorio filtrado por ese nombre.
- "Quién gana en este organismo" → `historico.html#/organismos?q=…`, igual.

Medido con los datos del 2026-10-01: los organismos coinciden por nombre en el 97 %
de los registros; las empresas, en torno al 72 %. Por eso `normalizar.py` añade
ahora `empresa_nif` a adjudicaciones y contratos menores (se verá a partir de la
siguiente ejecución del pipeline).

## Limitaciones conocidas

- La ficha de organismo no muestra el título de cada contrato: los títulos se
  publican troceados por empresa (`historico-detalle/NN.js`) y un organismo los
  tendría repartidos por los 32 fragmentos. Cada fila enlaza a la ficha de la
  empresa, donde sí están.
- Los recuentos de la barra lateral se calculan en `index.html` y se recuerdan en
  el navegador para mostrarlos también en `historico.html`.

## Ampliación de información (segunda ronda, 2026-10-02)

Sale de comparar el radar con un servicio comercial de alertas
(`ANALISIS-INFOCONCURSO.md`). No cambia la estructura: añade una pestaña y
datos a lo que ya había.

- **Tercera pestaña en Licitaciones: "Sistemas dinámicos y plazo largo"**
  (`index.html#/licitaciones/plazo-largo`). Licitaciones abiertas a las que les
  quedan más de 60 días de plazo: sistemas dinámicos de adquisición,
  homologaciones y acuerdos marco que admiten solicitudes durante meses o años.
  Es un subconjunto de "Licitaciones abiertas", igual que "Publicadas
  recientemente". El radar no las veía: se publicaron hace mucho y no se
  actualizan, así que ni el feed ni la búsqueda diaria las traen. Ahora
  `placsp_web.py` las pide una vez a la semana. Su urgencia se rotula "Abierta
  hasta 2030" en lugar de "Quedan 1.365 días", y no cuentan como publicadas
  recientemente aunque el radar las vea por primera vez.
- **Provincia.** La tarjeta dice "Bizkaia · País Vasco" donde antes decía
  "España", y hay un filtro "Provincia" agrupado por comunidad en todas las
  vistas con registros españoles. La elección se conserva al cambiar de vista.
  Sin zona destacada: se decidió filtro simple.
- **Resumen del histórico dentro de la tarjeta.** Dos bloques nuevos en el
  detalle: "Este organismo en el histórico" (adjudicaciones de servicios de
  agencia desde 2021, a cuántas empresas, por qué importe y las tres que más
  suman, enlazadas a su ficha) y, en adjudicaciones y contratos menores, lo
  mismo de la empresa más cuántas veces ha ganado en ese organismo. En
  prospección es el dato que faltaba: se ve de un vistazo si quien tiene el
  contrato menor es un proveedor habitual de ese organismo.
- **Taxonomía en catalán, gallego y euskera**, y expresiones en castellano que
  faltaban (ver README).
- **Plataformas autonómicas.** Las licitaciones y adjudicaciones que los
  organismos publican en la plataforma de su comunidad (Cataluña, Andalucía,
  Madrid, Galicia, Navarra, La Rioja) entran ahora también por el feed de
  PLACSP que las agrega. No añade ninguna vista: aparecen en las de siempre,
  con su provincia.

No se ha quitado ningún dato.

## Competencia y detalle de cada licitación (tercera ronda, 2026-10-02)

Tampoco cambia la estructura. Estado: publicada el 2026-10-02.

- **Filtros de Competencia.** A los que había (ámbito, tipo de adjudicación,
  año y categoría) se suman la **provincia**, con el mismo desplegable
  agrupado por comunidad que el radar, y el **importe mínimo y máximo de cada
  adjudicación**. Valen para el análisis de mercado, los dos directorios y
  las fichas. Con un filtro de importe quedan fuera las adjudicaciones que
  no publican importe, igual que en el radar. El de provincia no se enseña
  mientras menos de la mitad de las adjudicaciones tengan lugar (hasta la
  reconstrucción del histórico).
- **Adjudicaciones de más de 1 M€.** Bajo "Empresas que más ganan" hay una
  línea que dice cuántas son y qué parte del importe suman con los filtros
  puestos, y un botón que pone el importe máximo en 1 M€. Son las que
  deciden el orden por importe y casi nunca son contratos de agencia; no se
  ocultan por defecto.
- **Fichas de empresa fusionadas.** Cuando dos fichas resultan ser la misma
  empresa (el mismo NIF escrito de dos formas), se queda una y la dirección
  de la otra (`historico.html#/empresa/<id>`) lleva a ella.
- **Hora de cierre en la tarjeta.** "Fin de presentación: 19 oct 2026,
  14:00" y, el último día, "Cierra hoy a las 14:00" (o "Cerró hoy a las
  14:00" si ya ha pasado). Solo donde la fuente la publica: PLACSP y TED
  (en TED, hora local del organismo).
- **Bloque "Pliegos" en el detalle.** Enlaces al pliego de cláusulas
  administrativas y al de prescripciones técnicas, con el nombre del fichero
  tal como lo subió el organismo, o a la documentación de la licitación
  cuando la fuente solo da esa dirección.

No se ha quitado ningún dato.

## Ideas para más adelante (no implementadas)

Tomadas de la referencia; cada una necesita algo que hoy la plataforma no tiene
(guardar estado por usuario, o un servicio que envíe correos):

- **Alertas** por correo con las licitaciones nuevas del día (aplazado por
  decisión del 2026-10-02; se retomará más adelante).
- **Seguimiento**: marcar una licitación como "interesa / descartada / en
  preparación / presentada", con responsable.
- **Análisis del pliego** (los enlaces a los pliegos ya están en la tarjeta;
  leerlos y resumirlos enlaza con la fase prevista de ayuda a la redacción
  de propuestas).
