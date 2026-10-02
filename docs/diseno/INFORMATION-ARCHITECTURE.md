# Arquitectura de información

Fecha: 2026-10-02. Estado: **implementada en local, pendiente de aprobación** antes
de publicarla.

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

## Ideas para más adelante (no implementadas)

Tomadas de la referencia; cada una necesita algo que hoy la plataforma no tiene
(guardar estado por usuario, o un servicio que envíe correos):

- **Alertas** por correo con las licitaciones nuevas del día.
- **Seguimiento**: marcar una licitación como "interesa / descartada / en
  preparación / presentada", con responsable.
- **Ficha de licitación con pliegos** y análisis del pliego (enlaza con la fase
  prevista de ayuda a la redacción de propuestas).
