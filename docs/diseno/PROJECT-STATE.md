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
| Arquitectura de información | Implementada, pendiente de aprobación | `INFORMATION-ARCHITECTURE.md` |
| Sistema de diseño | Implementado, pendiente de aprobación | `DESIGN-SYSTEM.md` |
| Construcción | Hecha en local | `dashboard/` |
| Comprobación funcional | Hecha (escritorio y móvil) | ver abajo |
| Publicación | **Pendiente de la aprobación del usuario** | — |

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

- Aprobación del usuario y publicación.
- Revisión visual independiente (`impeccable`) sobre la versión publicada.
- Detectado al construir, sin tocar: en el histórico hay empresas duplicadas por
  variantes del mismo NIF (por ejemplo con y sin el prefijo "ES"), lo que reparte
  sus adjudicaciones entre varias fichas.
