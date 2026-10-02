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

- Reconstruir el histórico con la taxonomía nueva (aprobado, como paso aparte):
  el actual se clasificó con la anterior y los términos nuevos solo se aplican
  a lo que entre desde ahora.
- Unos 230 registros de PLACSP acumulados de agosto no tienen provincia: el
  pipeline solo relee el mes anterior los tres primeros días de cada mes.
- Revisión visual independiente (`impeccable`) sobre la versión publicada.
- Detectado al construir, sin tocar: en el histórico hay empresas duplicadas por
  variantes del mismo NIF (por ejemplo con y sin el prefijo "ES"), lo que reparte
  sus adjudicaciones entre varias fichas.
