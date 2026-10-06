# quipu · Design system para slides

Basado en la landing de Quipu: fondo petróleo oscuro con retícula de puntos, tipografía grotesca grande y apretada, acentos menta y azul, y un **quipu radial** (cuerdas con nudos) como elemento memorable.

## Principio
Una sola cosa llamativa por slide: un titular enorme **o** el quipu radial **o** una cifra. Todo lo demás, sobrio.

## Color
| Token | Hex | Uso |
|---|---|---|
| `--q-ink` | #071316 | Fondo de todas las slides |
| `--q-ink-2` | #0D1D21 | Tarjetas y superficies |
| `--q-ink-3` | #12302F | Superficie destacada, núcleo del quipu |
| `--q-line` | #1F3A3D | Bordes, retícula, divisores |
| `--q-text` | #EAF4F0 | Texto principal |
| `--q-muted` | #9DB3AF | Texto secundario |
| `--q-faint` | #5E7A77 | Notas, fuentes, numeración |
| `--q-teal` | #5CC8B4 | Acento principal: Quipu, acción, resultado |
| `--q-teal-deep` | #3E9B8A | Acento secundario |
| `--q-blue` | #6D9EE6 | Datos y comparaciones |
| `--q-alert` | #E8846B | Solo para el dolor o el riesgo, con moderación |

Proporción aproximada: 85% fondo oscuro, 10% texto, 5% acentos.

## Tipografía
- **Geist** (600 en titulares, 400–500 en texto). Interletrado negativo en tamaños grandes.
- **Geist Mono**: solo para nombres de herramientas (`data_lookup`), ejes (000°) y numeración de página.

| Estilo | Tamaño | Interletrado | Uso |
|---|---|---|---|
| Display | 168 px | −0.055em | Portada o cierre, máximo 4 palabras |
| H1 | 96 px | −0.045em | Pregunta gancho |
| H2 | 64 px | −0.035em | Título de slide (una frase) |
| H3 | 40 px | −0.02em | Título de tarjeta |
| Lead | 34 px | normal | Bajada, máximo 30–40 caracteres por línea |
| Body | 28 px | normal | Texto de tarjeta |
| Small / Note | 22 / 18 px | normal | Tablas, fuentes de datos |

Titulares en minúscula inicial (sentence case), sin mayúsculas sostenidas y sin colorear una sola palabra.

## Layout (1920 × 1080)
- Margen de 120 px. Barra superior con logo a la izquierda y numeración `n / 6` en mono a la derecha.
- Todo alineado a la izquierda. El quipu radial va a la derecha, centrado verticalmente.
- Retícula de 2 o 3 columnas con separación de 48 px.

```
┌──────────────────────────────────────────┐
│ ✺ quipu                           1 / 6 │
│                                          │
│ (badge)                     ╲ │ ╱        │
│ Titular grande            ─  ◯  ─        │
│ bajada gris                 ╱ │ ╲        │
│ [botón] [botón]                          │
└──────────────────────────────────────────┘
```

## Componentes (en slides.css)
- `.q-badge`: píldora con punto menta para contexto.
- `.q-btn--solid` / `.q-btn--ghost`: CTA claro con brillo, y CTA con borde.
- `.q-card`: superficie con borde de 1.5 px y radio de 32 px.
- `.q-stat`: cifra de 120 px con su etiqueta debajo.
- `.q-chat`: diálogo Tú / Quipu, como en la landing.
- `.q-tag` / `.q-tag--on`: herramientas usadas, en mono.
- `.q-table`: tabla de métricas sin fondo, solo con líneas.
- `.q-flow`: pasos del flujo (es una secuencia real, por eso lleva flechas).
- `.q-radial`: el quipu radial, completo (`.q-radial`) o como marca de agua (`.q-radial--ghost`).

## Recetas de las 6 slides
1. **Gancho:** badge, H1 con la pregunta, 3 estadísticas y el quipu radial a la derecha.
2. **Por qué:** H2 y 3 tarjetas con cifras (menta, azul, blanco), más una bajada.
3. **Solución:** a la izquierda H2, bajada y CTAs; a la derecha la tarjeta de chat con tags.
4. **Arquitectura:** H2, flujo de 4 tarjetas y tags de controles.
5. **Resultados:** tabla de métricas y los límites de los datos.
6. **Cierre:** frase en Display, el quipu como marca de agua y CTAs.

## Qué evitar
- Fondos claros o degradados de colores.
- Más de un acento fuerte por slide.
- Párrafos de más de 3 líneas.
- Usar `--q-alert` fuera de las cifras de dolor.
