# Sistema de diseño

Fecha: 2026-10-02. Implementado en `dashboard/style.css` (común) y
`dashboard/historico.css` (vistas de competencia). Estado: **pendiente de
aprobación**.

## Dirección

Aplicación SaaS de datos, al estilo de la referencia (ver `REFERENCE-AUDIT.md`):
lienzo gris claro, tarjetas blancas con borde fino y sombra mínima, un único azul
de acento, tipografía Inter, mucha información por pantalla sin decoración. El
usuario pidió copiar ese sistema; aquí se documenta de dónde sale cada valor.

Dos decisiones propias, que no vienen de la referencia:

- **El código de urgencia** (rojo / ámbar / verde / gris) se mantiene: es la señal
  funcional del radar y significa lo mismo en todas las vistas. Va siempre con
  texto ("Quedan 12 días"), nunca solo color.
- **Un solo acento.** La versión anterior daba un color a cada pestaña; la
  referencia es monocroma con azul. Se sigue a la referencia.

Marca propia: nombre "Radar de licitaciones" y un símbolo de ondas de radar. No se
usa nada de la marca de la referencia.

## Fundamentos

### Color

| Token | Valor | Uso | Origen |
|---|---|---|---|
| `--color-background` | `#F3F4F6` | Lienzo | Capturas del usuario (gris `#F0F0F0`), ajustado a la familia de grises de la web de referencia |
| `--color-surface` | `#FFFFFF` | Tarjetas, barra lateral | Medido |
| `--color-surface-soft` | `#F9FAFB` | Columna de importe, cabecera de tabla | Token extraído (`surface-2`) |
| `--color-border` | `#E5E7EB` | Bordes | Token extraído |
| `--color-border-strong` | `#D1D5DB` | Borde al pasar el ratón | Derivado |
| `--color-ink` | `#14213D` | Títulos y cifras | Token extraído (azul marino de marca) |
| `--color-foreground` | `#1F2937` | Texto | Derivado |
| `--color-muted` | `#5B6472` | Texto secundario (6:1 sobre blanco) | Derivado, comprobado el contraste |
| `--color-primary` | `#00509D` | Botón principal, pestaña activa, enlaces, barras | Token extraído y muestreado en las capturas (`#005098`). 8,2:1 sobre blanco |
| `--color-primary-hover` | `#003F7D` | Estado hover | Token extraído (`gradient-4`) |
| `--color-primary-soft` | `#E8F1FA` | Elemento activo de la barra lateral, categorías | Derivado |
| urgencia roja | `#991B1B` sobre `#FEE2E2` | Cierra en ≤ 7 días, vence en ≤ 30 | Propio |
| urgencia ámbar | `#92400E` sobre `#FEF3C7` | Cierra en ≤ 21 días, vence en ≤ 60; "Revisar" | Propio |
| urgencia verde | `#166534` sobre `#DCFCE7` | Resto con fecha | Propio |

Todos los pares texto/fondo superan 4,5:1.

### Tipografía

Inter (400, 500, 600, 700), la de la referencia. Monoespaciada del sistema solo
para códigos de expediente. Cifras con `tabular-nums`.

| Rol | Tamaño / peso | Origen |
|---|---|---|
| Título de página | 22 px / 600 | Referencia: 20 px / 600 |
| Título de tarjeta | 16 px / 700 | Referencia: 18 px / 700; se baja un punto porque aquí las listas son más largas |
| Título de panel | 15 px / 600 | — |
| Texto | 14 px / 400, interlineado 1,5 | Medido |
| Organismo | 13,5 px / 600 | Medido: 14 px / 600 |
| Secundario | 12–13 px | Medido: 12 px |
| Etiqueta de dato | 11 px / 500 | Medido: 10 px; se sube a 11 por legibilidad |
| Cifra destacada (KPI) | 26 px / 700 | Captura del panel |

### Forma y profundidad

| Token | Valor | Origen |
|---|---|---|
| `--radius-sm` | 6 px (insignias, opciones) | Medido: 4–8 px |
| `--radius-md` | 8 px (botones, campos) | Medido |
| `--radius-lg` | 12 px (tarjetas, paneles) | Token extraído (web 12 px; aplicación 14 px) |
| `--shadow-xs` | `0 1px 2px rgba(0,0,0,.05)` | Medido en botones y campos |
| `--shadow-card` | `0 1px 2px rgba(20,35,61,.04), 0 2px 6px rgba(20,35,61,.05)` | Token extraído (`shadow-1`) |
| `--shadow-hover` | `0 2px 4px rgba(20,35,61,.04), 0 8px 20px rgba(20,35,61,.07)` | Token extraído (`shadow-6`) |

Espaciado en múltiplos de 4 px. Barra lateral de 256 px (referencia: 240). Ancho
máximo del contenido: 1.240 px.

### Movimiento

Una sola familia: 120 / 200 / 320 ms con `cubic-bezier(0.16, 1, 0.3, 1)`. Solo en
cambios de estado (hover, pestaña, despliegue de tarjeta, cajón del menú). Se
anula con `prefers-reduced-motion`.

## Componentes

| Componente | Clase | Notas |
|---|---|---|
| Barra lateral | `.lateral`, `.nav__enlace` | La pinta `nav.js`. Por debajo de 1.024 px es un cajón que se abre desde la barra superior |
| Cabecera de página | `.pagina__cabecera` | Título, descripción del criterio y cifras de la vista (`.resumen`) |
| Buscador | `.campo-busqueda` | 46 px de alto |
| Panel de filtros | `.filtros` | Fijo al desplazar; en pantallas estrechas va plegado encima de los resultados |
| Opciones de fuente | `.opciones` | Lista vertical con recuento |
| Pestañas | `.pestanas`, `.pestana` | Activa en azul sólido |
| Tarjeta | `.tarjeta` | Chips y urgencia · título · organismo · lugar · pie con fechas / columna de importe. Se despliega con el detalle |
| Detalle | `.datos`, `.datos__par` | Pares dato/valor en tres grupos: información general, fechas, importes |
| Insignia / chip | `.insignia`, `.chip` | Insignia: estado con color. Chip: metadato neutro |
| Botones | `.boton--primario`, `--contorno`, `--texto` | 36 px (44 en móvil) |
| KPI | `.kpi` | Etiqueta, cifra y nota; puede ser enlace |
| Panel | `.panel` | Contenedor de gráficos y listas |
| Barras / columnas | `.barras`, `.columnas` | Gráficos en CSS, sin librerías |
| Tabla | `.tabla` | Directorios y contratos; cabeceras ordenables |
| Fila compacta | `.fila` | Listas de Inicio |

Estados cubiertos: hover, foco visible (anillo azul de 2 px), activo, deshabilitado,
vacío ("Sin datos con estos filtros", "Ningún resultado…") y cargando (contratos de
una ficha).

## Adaptación a pantallas

| Ancho | Cambio |
|---|---|
| ≥ 1.024 px | Barra lateral fija |
| < 1.024 px | Barra superior con botón de menú; la barra lateral es un cajón |
| < 900 px | Filtros encima de los resultados, plegados; Inicio en una columna |
| < 640 px | La columna de importe de la tarjeta baja a una franja inferior; KPIs en dos columnas; controles de 44 px; los directorios muestran solo nombre, número e importe |

## Accesibilidad

Enlace "Saltar al contenido", navegación completa con teclado, foco visible,
`aria-current` en la sección activa, grupos de filtros con nombre, recuentos
anunciados con `aria-live`, objetivos táctiles de 44 px en móvil, sin información
transmitida solo por color.

## Sin dependencias

HTML, CSS y JavaScript sin librerías ni proceso de compilación, como hasta ahora.
Los iconos son SVG en línea (trazos al estilo Lucide) definidos en `nav.js`.
