# Estado del rediseño

Actualizado: 2026-10-02.

## Proyecto

- **Tipo**: herramienta interna de datos (panel SaaS) para una agencia de marketing
  digital. HTML/CSS/JS estático en Vercel, alimentado por un pipeline diario.
- **Escala**: estándar. Contenido real y estructurado (759 registros vivos en el
  radar, 136.000 adjudicaciones en el histórico), una referencia externa y una
  base de código que hay que respetar.
- **Objetivo de esta ronda**: reordenar la plataforma para que sea fácil encontrar
  cada cosa y darle un aspecto de producto SaaS, tomando Tendios como referencia.

## Fuera del alcance de esta ronda

- No se quita ni se resume ninguna información que ya se mostraba.
- No se añaden funciones que necesiten cuentas de usuario o servidor (alertas,
  guardar licitaciones, seguimiento).
- No se cambia la taxonomía ni qué registros entran en el radar.
- No se introduce ningún framework ni proceso de compilación.

## Fases

| Fase | Estado | Artefacto |
|---|---|---|
| Análisis de la referencia | Hecho | `REFERENCE-AUDIT.md` |
| Arquitectura de información | Aprobada y publicada | `INFORMATION-ARCHITECTURE.md` |
| Sistema de diseño | Aprobado y publicado | `DESIGN-SYSTEM.md` |
| Construcción | Hecha | `dashboard/` |
| Comprobación funcional | Hecha (escritorio y móvil) | ver abajo |
| Publicación | Hecha el 2026-10-02 | https://licitacionesmarketing.vercel.app |
| Segunda ronda: ampliación de información | Aprobada y publicada el 2026-10-02 | `INFORMATION-ARCHITECTURE.md`, `ANALISIS-INFOCONCURSO.md` |
| Tercera ronda: competencia y detalle de cada licitación | Aprobada y publicada el 2026-10-02 | `INFORMATION-ARCHITECTURE.md`, README |

## Segunda ronda: ampliación de información

Esta ronda sí cambia qué registros entran en el radar (la primera no lo hacía).
Cinco piezas:

1. Taxonomía en catalán, gallego y euskera, y expresiones en castellano que
   faltaban.
2. Provincia y comunidad en cada registro español, con filtro.
3. Resumen del organismo y de la empresa (histórico) dentro de cada tarjeta.
4. Pestaña "Sistemas dinámicos y plazo largo", con una búsqueda semanal nueva en
   el buscador de PLACSP.
5. Plataformas autonómicas agregadas en PLACSP (`sindicacion_1044`) para las
   licitaciones abiertas y las adjudicaciones recientes.

Probada con el pipeline real sobre una copia: de 812 a 995 registros; las
licitaciones de organismos españoles pasan de 102 a 154.

Decisiones del usuario (2026-10-02): filtro por provincia sin zona destacada;
no se añaden materias nuevas (actividades culturales, concursos de ideas) hasta
preguntar a la agencia; las alertas por correo se aplazan.

Respuesta de la agencia (2026-10-02): de momento **no** quiere actividades
culturales ni concursos de ideas en el radar. El alcance se queda como está.

## Tercera ronda: competencia y detalle de cada licitación

Construida el 2026-10-02 sobre los pendientes de las dos anteriores. Estado:
**aprobada y publicada el 2026-10-02**.

1. **Empresas duplicadas en el histórico.** El mismo NIF llegaba con y sin el
   prefijo "ES" o con puntos, comas y guiones, y la empresa salía en dos
   fichas (36 casos). Ahora el NIF se guarda limpio y las fichas se
   fusionan sin mover los índices de las demás: la ficha sobrante redirige a
   la buena. De paso: los NIF de relleno ("A00000000", "0") dejan de agrupar
   a empresas sin relación, y un NIF enmascarado ("***9688**") ya no junta a
   dos personas distintas.
2. **Contratos enormes que no son de agencia.** No se quita nada: Competencia
   gana un filtro de importe mínimo y máximo por adjudicación, y el análisis
   de mercado dice cuánto pesan las adjudicaciones de más de 1 M€ (el 66 %
   del importe con 1.084 de 146.000) con un botón para dejarlas fuera.
3. **Provincia en Competencia.** El histórico guarda la provincia y la
   comunidad de cada expediente, con el criterio del radar. El filtro aparece
   solo cuando más de la mitad de las adjudicaciones tienen lugar, es decir,
   después de la reconstrucción completa.
4. **Hora de cierre.** PLACSP (perfiles propios y plataformas autonómicas) y
   TED publican la hora a la que cierra el plazo; la tarjeta la enseña y el
   día de cierre dice "Cierra hoy a las 14:00". La API de Euskadi no da una
   hora fiable y no se enseña.
5. **Pliegos.** Enlaces directos al pliego administrativo y al técnico
   (PLACSP) o a la documentación de la licitación (TED) dentro de la tarjeta.
6. **Menos minutos de Actions.** El scraper de convocatorias de la UE guarda
   los detalles de una noche a otra y solo pide los nuevos y un séptimo de
   los conocidos: de unos 15 minutos a unos 2 por noche.

Probada con el pipeline real sobre una copia (ZIP de septiembre y octubre):
132 de las 164 licitaciones españolas con hora de cierre y 104 con pliegos.

Reconstrucción completa del histórico: programada para la madrugada del
domingo 2026-10-04 (03:23 UTC), con todas las fuentes. Hay que quitar la
programación del workflow después.

## Decisiones tomadas (para revisar)

1. Navegación en barra lateral por propósito: Oportunidades, Prospección comercial,
   Competencia. Nueva página de Inicio.
2. "Publicadas recientemente" y "Licitaciones abiertas" pasan a ser dos pestañas de
   la sección Licitaciones.
3. La ficha de empresa deja de ser una ventana emergente y pasa a ser una página
   con dirección propia. Nuevos directorios de empresas y de organismos, y ficha
   de organismo.
4. Un solo color de acento (azul `#00509D`); se retira el color por pestaña. El
   código de urgencia rojo/ámbar/verde se mantiene.
5. Tipografía Inter en lugar de Fira Sans / Fira Code.
6. Al ordenar por fecha, lo ya vencido va al final.
7. `normalizar.py` añade `empresa_nif` a adjudicaciones y contratos menores para
   enlazar con la ficha de la empresa.

La dirección visual venía dada por la referencia ("copia el sistema de diseño"),
así que no se ha abierto una fase de dirección de arte: se han medido los estilos
reales de la referencia y se han aplicado.

## Comprobaciones hechas

- Las cinco vistas de listado: mismos registros que antes, cada criterio de orden
  ordena de verdad, los recuentos de fuente y categoría coinciden con lo que se
  lista, el filtro de importe filtra, "Quitar todos los filtros" restaura.
- Enlaces con parámetros (`?id=`, `?cat=`, `?q=`, `?nif=`) y ruta inexistente.
- Histórico: cifras, directorios (orden, paginación, búsqueda, vacío), fichas de
  empresa y de organismo, identificador no válido.
- Sin desbordamiento horizontal a 375 px en ninguna vista. Sin errores en consola.

## Pendiente

- Reconstruir el histórico con la taxonomía nueva (aprobado). Hecho el
  2026-10-02 para las plataformas autonómicas (`fuentes=agregadas`): de
  127.996 a 134.576 expedientes. El resto (unos 12 GB) está programado para
  la madrugada del domingo 2026-10-04, fuera del horario en que PLACSP sirve
  a GitHub a 0,1 MB/s y sin coincidir con la actualización diaria. Después:
  comprobar el resultado en producción y quitar el bloque `schedule` de
  `historico-adjudicaciones.yml`.
- Unos 230 registros de PLACSP acumulados de agosto no tienen provincia, y
  las licitaciones abiertas que no se actualicen en octubre no tendrán hora
  de cierre ni pliegos. La relectura de agosto y septiembre dentro de la
  actualización diaria se retiró el 2026-10-03: triplicó la descarga y esa
  noche no se publicó nada. Si se quiere rellenar, con una ejecución aparte.
- Revisión visual independiente (`impeccable`) sobre la versión publicada.
- Minutos de Actions antes de que el repositorio vuelva a ser privado: la
  actualización diaria tardaba unos 37 minutos (unos 1.100 al mes de los
  2.000 gratuitos). Con la caché del scraper de la UE debería bajar a unos
  25; comprobarlo en las ejecuciones de la semana.
- De la comparación con el servicio de alertas quedan sin hacer favoritos,
  afinidad y licitaciones parecidas.
