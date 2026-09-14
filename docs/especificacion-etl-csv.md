# Especificación de tablas para generar los 15 CSV de carga (inciso b)

**Objetivo de este documento:** dárselo, junto con los CSV crudos de `data/raw/`, `sources/keithgalli/clean-data/`
y `fuentes/`, a un LLM (o usarlo como referencia para escribir un script) para que produzca **un CSV por
tabla**, ya en el formato exacto que espera el esquema de `db/init/02-schema.sql`.

El modelo completo, con su razonamiento, está en [`modelo-de-datos.md`](modelo-de-datos.md) y
[`HANDOFF-decisiones.md`](HANDOFF-decisiones.md). Aquí solo se resume lo que hace falta para transformar.

---

## 1. Fuentes crudas disponibles (columnas reales, verificadas)

**F1 — Olympedia** (`sources/keithgalli/clean-data/`)

| Archivo | Columnas |
|---|---|
| `bios.csv` | `athlete_id, name, born_date, born_city, born_region, born_country, NOC, height_cm, weight_kg, died_date` |
| `results.csv` | `year, type, discipline, event, as, athlete_id, noc, team, place, tied, medal` |
| `noc_regions.csv` | `NOC, region, notes` |

**F2 — Kaggle 120 years** (`data/raw/`)

| Archivo | Columnas |
|---|---|
| `athlete_events.csv` | `ID, Name, Sex, Age, Height, Weight, Team, NOC, Games, Year, Season, City, Sport, Event, Medal` |
| `noc_regions.csv` | `NOC, region, notes` |

**F3 — Kaggle Summer Medals 1896-2024** (`data/raw/olympics_dataset.csv`)

`player_id, Name, Sex, Team, NOC, Year, Season, City, Sport, Event, Medal`

**F4 — DataCamp DataLab** (`fuentes/datacamp-datalab-r-olympics.csv`)

`index, id, name, sex, age, height, weight, team, noc, games, year, season, city, sport, event, medal`
(subconjunto literal de F2 — ver D-000, no debería aportar filas nuevas)

---

## 2. Reglas de transformación obligatorias

Estas reglas vienen de decisiones ya tomadas y documentadas (no son negociables al generar los CSV):

1. **Grano de `participacion` = entrada al evento, no atleta** (D-004a / D-007). Un evento por equipos
   (ej. baloncesto de EE.UU. 1992) es **una sola fila** en `participacion` con su medalla, y **una fila
   por integrante** en `participacion_atleta`. Los CSV crudos vienen a grano atleta×evento — hay que
   agrupar por `(evento_edicion, noc, team, medal, place)` para reconstruir la entrada real.
2. **`NOC` ≠ `PAIS`** (D-004b). `noc_regions.csv` mapea el código NOC (`URS`, `GDR`, `TCH`, `YUG`, `SAA`,
   `EUN`, `ROT`, `IOA`...) a un país moderno (`region`). `ROT` e `IOA` no tienen país → `pais_id` NULL en
   la tabla `noc`.
3. **Jerarquía `deporte → disciplina → evento`** (D-008). F1 trae `discipline` (94 valores), F2/F3 traen
   `Sport`/`sport` (66 valores). Hay que construir el catálogo `deporte` (nivel COI, ej. "Acuáticos") y
   mapear cada valor de `Sport`/`discipline` a una fila de `disciplina` bajo el deporte correcto.
4. **`Games`/`games` = año + temporada concatenados** (ej. `"1992 Summer"`). Separar en `anio` (SMALLINT)
   y `temporada` (`'Verano'` o `'Invierno'`, traducido desde `Summer`/`Winter`).
5. **`Event`/`event` mezcla disciplina + sexo + nombre** (ej. `"Basketball Men's Basketball"`). Separar
   `categoria_sexo` (`M`/`F`/`Mixto`/`Abierto`) del nombre del evento.
6. **`place`/`Medal` con texto no numérico** (D-011): `"=17"` (empate), `"DNF"`, `"DNS"`, `"AC"`. Separar
   en `puesto` (SMALLINT, NULL si no es numérico) y `puesto_texto` (VARCHAR, el original). `empatado =
   TRUE` si el texto empieza con `=`.
7. **Identidad de atleta: Olympedia (F1) es la espina dorsal** (D-003). F2/F3/F4 se reconcilian contra
   `bios.csv` por `nombre_normalizado + sexo + NOC + año + evento`; lo que no hace match entra como
   atleta nuevo. Cada match (o alta nueva) genera una fila en `atleta_fuente` con `metodo_match` en
   `'espina' | 'exacto' | 'nombre+noc+anio' | 'nuevo'` y una `confianza` de 0 a 1.
8. **F4 no debería aportar filas nuevas** (D-000): si el generador encuentra atletas/participaciones de
   F4 que no matchean con F2, repórtalo como advertencia — probablemente es un error de matching, no un
   dato real nuevo.
9. **`noc_regions.csv` de F2 puede traer saltos de línea CR** (D-001) — ya normalizado por
   `scripts/preparar-fuentes.sh`, no hace falta re-tratarlo si usas `data/raw/noc_regions.csv`.

---

## 3. Orden de carga (respeta las llaves foráneas)

```
1. fuente.csv                  ← YA CARGADO en la base (docs/init/04-seed.sql), generar solo si se re-crea desde cero
2. pais.csv
3. noc.csv                     (FK → pais)
4. ciudad.csv                  (FK → pais)
5. edicion.csv
6. sede.csv                    (FK → edicion, ciudad)
7. deporte.csv
8. disciplina.csv              (FK → deporte)
9. evento.csv                  (FK → disciplina)
10. evento_edicion.csv         (FK → evento, edicion)
11. medalla.csv                ← YA CARGADO en la base (docs/init/04-seed.sql), generar solo si se re-crea desde cero
12. atleta.csv
13. participacion.csv          (FK → evento_edicion, noc, medalla)
14. participacion_atleta.csv   (FK → participacion, atleta)
15. atleta_fuente.csv          (FK → atleta, fuente)
```

`medalla` y `fuente` **ya tienen datos** en la base actual (3 y 4 filas respectivamente) — no hace falta
generarlos de nuevo salvo que se reconstruya el contenedor desde cero (`docker compose down -v`).

---

## 4. Especificación columna por columna

> Todas las columnas `*_id` autonuméricas (`SERIAL`/`BIGSERIAL`) deben venir **explícitas** en el CSV
> con enteros consecutivos empezando en 1, asignados de forma **consistente entre archivos** (el mismo
> `atleta_id` en `atleta.csv` y en `participacion_atleta.csv` debe referirse al mismo atleta). Después
> de cargar con `COPY` habrá que resincronizar las secuencias (`SELECT setval(...)`), eso ya lo maneja
> el que carga, no hace falta que el generador de CSV se preocupe por eso.

### `pais.csv`
| Columna | Tipo | Obligatorio | Fuente / regla |
|---|---|---|---|
| `pais_id` | entero | sí | correlativo generado |
| `nombre` | texto(100) | sí, único | de `region` en `noc_regions.csv`, deduplicado |
| `codigo_iso3` | texto(3) | no | dejar vacío si no se tiene certeza (no inventar) |

### `noc.csv`
| Columna | Tipo | Obligatorio | Fuente / regla |
|---|---|---|---|
| `noc_codigo` | texto(3) | sí (PK, no autonumérico) | el código tal cual (`USA`, `URS`, `ROT`...) |
| `pais_id` | entero | no | FK a `pais.csv` por `region`; vacío si es `ROT`/`IOA` |
| `nombre_comite` | texto(120) | sí | ej. `"United States"`, o `region` si no hay nombre de comité |
| `es_historico` | `true`/`false` | sí | `true` para comités disueltos: `URS, GDR, TCH, YUG, SAA, EUN` |
| `notas` | texto(200) | no | copiar `notes` de `noc_regions.csv` si existe |

### `ciudad.csv`
| Columna | Tipo | Obligatorio | Fuente / regla |
|---|---|---|---|
| `ciudad_id` | entero | sí | correlativo |
| `pais_id` | entero | sí | FK a `pais.csv` — país donde está la ciudad sede (no confundir con el NOC del evento) |
| `nombre` | texto(100) | sí | de `City` (F2/F3) |

### `edicion.csv`
| Columna | Tipo | Obligatorio | Fuente / regla |
|---|---|---|---|
| `edicion_id` | entero | sí | correlativo |
| `anio` | entero 1896-2100 | sí | de `Year`/`year` |
| `temporada` | `Verano`/`Invierno` | sí | de `Season`/`season` (`Summer`→`Verano`, `Winter`→`Invierno`) |
| `numero_olimpiada` | entero | no | dejar vacío si no se calcula |
| `nombre` | texto(60) | sí | ej. `"1992 Verano"` |
| `fecha_inicio` | fecha ISO | no | vacío si no se tiene |
| `fecha_fin` | fecha ISO | no | vacío si no se tiene |
| `fue_cancelada` | `true`/`false` | sí | `true` solo para 1916, 1940, 1944 |
| `es_intercalada` | `true`/`false` | sí | `true` solo para Atenas 1906 |

### `sede.csv`
| Columna | Tipo | Obligatorio | Fuente / regla |
|---|---|---|---|
| `edicion_id` | entero | sí (PK compuesta) | FK a `edicion.csv` |
| `ciudad_id` | entero | sí (PK compuesta) | FK a `ciudad.csv` |
| `es_principal` | `true`/`false` | sí | `true` salvo casos conocidos de sede secundaria (ej. hípica de Melbourne 1956 en Estocolmo) |

### `deporte.csv`
| Columna | Tipo | Obligatorio | Fuente / regla |
|---|---|---|---|
| `deporte_id` | entero | sí | correlativo |
| `nombre` | texto(80) | sí, único | catálogo nivel COI (ej. "Acuáticos", "Atletismo") — construir a mano reconciliando `Sport` (F2/F3) y `discipline` (F1) |

### `disciplina.csv`
| Columna | Tipo | Obligatorio | Fuente / regla |
|---|---|---|---|
| `disciplina_id` | entero | sí | correlativo |
| `deporte_id` | entero | sí | FK a `deporte.csv` |
| `nombre` | texto(80) | sí | de `Sport`/`discipline`, uno por deporte (único por `(deporte_id, nombre)`) |

### `evento.csv`
| Columna | Tipo | Obligatorio | Fuente / regla |
|---|---|---|---|
| `evento_id` | entero | sí | correlativo |
| `disciplina_id` | entero | sí | FK a `disciplina.csv` |
| `nombre` | texto(200) | sí | `Event` sin el prefijo de disciplina/sexo |
| `categoria_sexo` | `M`/`F`/`Mixto`/`Abierto` | no | extraído de `Event` (`Men's`→`M`, `Women's`→`F`) |
| `es_por_equipos` | `true`/`false` | sí | `true` si el evento es por equipos (ej. baloncesto, relevos, remo de equipos) |

### `evento_edicion.csv`
| Columna | Tipo | Obligatorio | Fuente / regla |
|---|---|---|---|
| `evento_edicion_id` | entero | sí | correlativo |
| `evento_id` | entero | sí | FK a `evento.csv` |
| `edicion_id` | entero | sí | FK a `edicion.csv` |

### `atleta.csv`
| Columna | Tipo | Obligatorio | Fuente / regla |
|---|---|---|---|
| `atleta_id` | entero | sí | correlativo — **espina dorsal = un atleta único de `bios.csv` (F1), + altas nuevas de F2/F3/F4 que no matchearon** |
| `nombre_completo` | texto(200) | sí | de `name`/`Name` |
| `nombre_usado` | texto(150) | no | alias si existe |
| `nombre_normalizado` | texto(150) | sí | `nombre_completo` sin acentos, en minúsculas — clave de matching |
| `sexo` | `M`/`F`/`U` | no | de `Sex`/`sex` |
| `fecha_nacimiento` | fecha ISO | no | de `born_date` (solo F1 la tiene) |
| `fecha_defuncion` | fecha ISO | no | de `died_date` (solo F1) |
| `ciudad_nacimiento` | texto(120) | no | de `born_city` (solo F1) |
| `region_nacimiento` | texto(120) | no | de `born_region` (solo F1) |
| `pais_nacimiento_id` | entero | no | FK a `pais.csv`, de `born_country` (solo F1) |
| `estatura_cm` | entero 100-250 | no | de `height_cm`/`Height` |
| `peso_kg` | decimal 25-250 | no | de `weight_kg`/`Weight` |

### `participacion.csv`
| Columna | Tipo | Obligatorio | Fuente / regla |
|---|---|---|---|
| `participacion_id` | entero | sí | correlativo — **una fila por entrada real, no por atleta** (ver regla 1) |
| `evento_edicion_id` | entero | sí | FK a `evento_edicion.csv` |
| `noc_codigo` | texto(3) | sí | FK a `noc.csv` |
| `medalla_id` | entero 1-3 | no | `1`=Oro, `2`=Plata, `3`=Bronce; vacío si no hubo medalla |
| `nombre_equipo` | texto(150) | no | de `team`/`Team` si es evento por equipos (ej. `"Netherlands-2"`) |
| `es_por_equipos` | `true`/`false` | sí | igual al de `evento.csv` para ese evento |
| `puesto` | entero | no | parte numérica de `place`/`Medal` (regla 6) |
| `puesto_texto` | texto(20) | no | original: `"=17"`, `"DNF"`, `"DNS"`, `"AC"` |
| `empatado` | `true`/`false` | sí | `true` si el texto original empezaba con `=` |

### `participacion_atleta.csv`
| Columna | Tipo | Obligatorio | Fuente / regla |
|---|---|---|---|
| `participacion_id` | entero | sí (PK compuesta) | FK a `participacion.csv` |
| `atleta_id` | entero | sí (PK compuesta) | FK a `atleta.csv` |
| `nombre_usado_en_evento` | texto(200) | no | de `as` (F1) — alias/nombre de casada usado en ese evento específico |

### `atleta_fuente.csv`
| Columna | Tipo | Obligatorio | Fuente / regla |
|---|---|---|---|
| `atleta_id` | entero | sí (PK compuesta) | FK a `atleta.csv` |
| `fuente_id` | entero 1-4 | sí (PK compuesta) | `1`=Olympedia, `2`=Kaggle 120 years, `3`=Kaggle Summer Medals, `4`=DataCamp |
| `id_en_fuente` | texto(40) | sí (PK compuesta) | el ID original: `athlete_id` (F1), `ID` (F2), `player_id` (F3), `id` (F4) |
| `nombre_en_fuente` | texto(200) | no | el nombre tal como aparece en esa fuente |
| `metodo_match` | `espina`\|`exacto`\|`nombre+noc+anio`\|`nuevo` | no | cómo se decidió que es el mismo atleta (regla 7) |
| `confianza` | decimal 0.00-1.00 | no | qué tan seguro está el match |

---

## 5. Formato de archivo esperado (para que el `COPY` de carga funcione sin fricción)

- Codificación **UTF-8 sin BOM** (F4 trae BOM — quitarlo).
- Delimitador: coma `,`. Si un valor de texto contiene coma, encerrarlo en comillas dobles.
- **Primera fila = encabezado**, con los nombres de columna **exactamente** como en las tablas de
  arriba (minúsculas, con guion bajo).
- Celda vacía = `NULL` (no escribir la palabra `NULL`, ni `NA`, ni `""` con espacio).
- Fechas en formato `YYYY-MM-DD`.
- Booleanos como `true` / `false` en minúscula.
- Un archivo por tabla, nombrado exactamente `pais.csv`, `noc.csv`, etc.

---

## 6. Advertencia sobre el volumen de datos

F1+F2+F3 suman más de 700,000 filas crudas. Pedirle a un chat de LLM que "pegue" o genere directamente
los 15 CSV completos en la conversación **no va a escalar** ni va a mantener la consistencia de los IDs
correlativos entre archivos. Lo que sí funciona:

1. Pasarle este documento + una **muestra pequeña** (100-500 filas) de cada CSV crudo, y pedirle que
   genere un **script de Python (pandas)** que implemente las reglas de la sección 2 y produzca los 15
   CSV a partir de los archivos completos de `data/raw/`, `sources/keithgalli/clean-data/` y `fuentes/`.
2. Correr ese script localmente sobre los datos completos (no dentro del chat).
3. Verificar con las consultas de conteo (`SELECT count(*) FROM ...`) que ya tienes, antes de cargar a
   la base con `COPY tabla FROM 'archivo.csv' CSV HEADER;`.

Si quieres, puedo ayudarte a escribir ese script de Python directamente en vez de pasar por un CSV
intermedio generado por otro LLM.
