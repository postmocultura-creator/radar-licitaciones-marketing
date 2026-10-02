# Auditoría de la referencia: Tendios

Fecha: 2026-10-02. Referencia aportada por el usuario: https://tendios.com/ y tres
capturas de su aplicación (ficha de licitación, panel y buscador). La instrucción
fue explícita: analizar cómo estructura la información y **copiar su sistema de
diseño** para aplicarlo al radar.

La evidencia (DESIGN.md, tokens y capturas de `design-md-extractor`, más las tres
capturas del usuario) está en `references/tendios.com/`. Esa carpeta no se sube al
repositorio: son capturas de un producto de terceros.

## Qué se ha mirado

| Fuente | Qué aporta |
|---|---|
| `tendios.com` (web comercial, 6 páginas extraídas) | Tipografía, paleta de marca, sombras, radios |
| `bid.tendios.com/public/search` (buscador público, la aplicación real) | Estructura de navegación, anatomía de la tarjeta, filtros, pestañas. Estilos medidos con el navegador |
| `bid.tendios.com/public/tender/…` (ficha pública de una licitación) | Cómo ordena el detalle: cronograma, pares dato/valor por grupos |
| `tendios.com/adjudicatarios/…` (perfil de una empresa adjudicataria) | Qué enseña de un competidor |
| Capturas del usuario | La versión con azul de marca que le gusta; colores muestreados de la imagen |

## Cómo estructura la información (OBSERVADO)

Barra lateral con grupos, en este orden:

- **Inicio**, Vera (asistente de IA), Tareas, Herramientas
- **Descubrir**: Buscar, Alertas
- **Gestión comercial**: Oportunidades, Organizaciones, Contactos
- **Estudio de mercado**: Listas
- **Directorios**: Empresas, Organismos, CPVs

El buscador tiene cuatro pestañas sobre la misma lista: **Todas · En plazo ·
Adjudicaciones · Vencimientos**. Es decir, los mismos cuatro estados que ya maneja
el radar (abiertas, adjudicadas, contratos a punto de vencer).

Página de listado: buscador a todo el ancho arriba; debajo, panel de filtros a la
izquierda (secciones plegables: más comunes, CPV, órgano, localización, estados,
importes, fechas, tipo de contrato, contratos menores…) y resultados a la derecha
con recuento y "Ordenar".

Tarjeta de resultado, de izquierda a derecha:

1. Bloque principal: código de expediente (chip monoespaciado), chip "Hoy",
   insignia de estado a la derecha; título en negrita; organismo; localización con
   icono; pie separado por una línea con "Fin presentación".
2. Columna gris con "Presupuesto" (etiqueta pequeña, cifra en negrita).
3. Columna de acciones (guardar, descartar, analizar con IA, vista previa).

Ficha de licitación: cabecera (expediente, título, lugar, estado), pestañas
(Resumen, Documentos, Fuentes, Actividad, Análisis), columna izquierda con
cronograma (publicación → fin de presentación → adjudicación), mapa y CPV; columna
derecha con "Información relevante" en grupos de pares dato/valor: información
general, fechas, importes.

Perfil de adjudicatario: nombre, dirección y NIF; tabla de licitaciones ganadas
(objeto, presupuesto, expediente); enlaces a organismos con los que trabaja,
sectores, CPV frecuentes y competencia directa.

## Servicios que ofrece (OBSERVADO en su web)

Agregador de más de 50 portales, alertas personalizadas, histórico de
adjudicaciones (2, 4 u 8 años según plan), seguimiento de vencimientos, análisis
de pliegos con IA, gestión de licitaciones en equipo (responsable, estado, plazo),
inteligencia de mercado (quién gana, a qué precio, con qué baja), redacción
automática de propuestas, integraciones (CRM, Slack, Teams…) y API. Planes desde
168 €/mes (3 usuarios) y 345 €/mes (4 usuarios).

## Qué se toma y qué no

**Se toma** (estructura y sistema visual):

- Navegación en barra lateral por grupos, con una página de inicio.
- Listado con buscador arriba, filtros a la izquierda y pestañas de estado.
- Anatomía de la tarjeta y columna de importe.
- Detalle en grupos de pares dato/valor (información general, fechas, importes).
- Directorios de empresas y organismos con ficha propia.
- Paleta, tipografía, radios, sombras y densidad (ver `DESIGN-SYSTEM.md`).

**No se toma**:

- Nombre, logotipo, formas de marca (amarillo y azul claro del símbolo) ni textos.
- Funciones que el radar no tiene y que no se van a simular: alertas, tareas,
  guardar/descartar, IA, mapa, documentos. Una interfaz con botones que no hacen
  nada sería peor que no tenerlos. Ver "Ideas para más adelante" en
  `INFORMATION-ARCHITECTURE.md`.

## Diferencias de contexto (INTERPRETACIÓN)

Tendios es un buscador generalista sobre millones de licitaciones: su problema es
encontrar. El radar es una selección ya filtrada por la taxonomía de servicios de
agencia (unos cientos de registros vivos): su problema es **priorizar el día** —
qué es nuevo, qué cierra antes, qué contrato vence— y **conocer a los
competidores**. Por eso el radar conserva dos cosas que Tendios no tiene en su
buscador: la explicación del criterio de cada vista y el código de urgencia por
colores.
