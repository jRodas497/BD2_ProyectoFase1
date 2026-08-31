# Modelo de Datos — Base de Datos Unificada de Olimpiadas

**Universidad de San Carlos de Guatemala** · Facultad de Ingeniería · Escuela de Ciencias y Sistemas
**Sistemas de Bases de Datos 2** — 2do. Semestre 2026 · **Proyecto Fase 1, inciso (a)**
**Fecha:** 2026-08-30 · **Motor:** PostgreSQL
**Diagrama:** [`diagramas/modelo-er-olimpiadas.drawio`](../diagramas/modelo-er-olimpiadas.drawio)

---

## 1. Fuentes de datos

| # | Fuente | Archivos | Volumen | Cobertura |
|---|--------|----------|---------|-----------|
| **F1** | [Olympedia vía KeithGalli/Olympics-Dataset](https://github.com/KeithGalli/Olympics-Dataset) | `clean-data/bios.csv`, `clean-data/results.csv`, `clean-data/noc_regions.csv` | 145,500 atletas · 308,408 resultados | 1896–2022, Verano e Invierno |
| **F2** | [Kaggle — 120 years of Olympic history](https://www.kaggle.com/datasets/heesoo37/120-years-of-olympic-history-athletes-and-results) | `athlete_events.csv`, `noc_regions.csv` | 271,116 filas · 230 NOCs | 1896–2016, Verano e Invierno |
| **F3** | [Kaggle — Summer Olympics Medals 1896-2024](https://www.kaggle.com/datasets/stefanydeoliveira/summer-olympics-medals-1896-2024) | `olympics_dataset.csv` | 252,565 filas · 31 ediciones | 1896–2024, **solo Verano** |
| **F4** | [DataCamp DataLab — r-olympics](https://www.datacamp.com/datalab/datasets/r-olympics) | `datalab_export_*.csv` | 100 filas | muestra de F2 |
| **F5** | [olympics.com](https://www.olympics.com/) | — | — | Referencia de verificación de calidad |

### Complementariedad
Ninguna fuente es superconjunto de otra:

- **F1** es la única con `fecha_nacimiento`, `fecha_defuncion`, lugar de nacimiento y, sobre todo,
  **puesto (`place`) además de medalla** — 264,269 de sus 308,408 resultados no tienen medalla pero
  sí posición final. El enunciado pide "resultados", no solo medallas.
- **F2** aporta la ciudad sede por edición, los nombres de `Team` y el catálogo NOC→región.
- **F3** es la única que cubre **Tokio 2020 y París 2024**.
- **F4** no aporta filas nuevas: es un subconjunto literal de F2 (mismas columnas más un `index`).
  Se procesa igualmente para cumplir el enunciado y para demostrar que la deduplicación funciona.

### Hallazgos de calidad detectados en la exploración
1. `noc_regions.csv` de **F2** usa saltos de línea CR (Mac clásico); `wc -l` reporta 0 líneas. Un
   `COPY` directo cargaría todo el archivo como una sola fila. Se normaliza a LF en staging.
2. Los tres datasets usan **identificadores de atleta mutuamente incompatibles**
   (`athlete_id` en F1, `ID` en F2, `player_id` en F3). La unificación debe hacerse por atributos.
3. **F1** usa `Discipline` (94 valores) donde **F2/F3** usan `Sport` (66 valores). No son el mismo
   nivel de la jerarquía del COI.
4. El campo de puesto viene como `"=17"` (empate) en `results/results.csv` crudo y como
   `place=17, tied=True` en `clean-data/`. También aparecen `DNF`, `DNS`, `AC`.
5. Los CSV crudos están a grano **atleta × evento**, lo que hace que una medalla por equipos
   aparezca repetida una vez por cada integrante.

---

## 2. Decisiones de diseño

Todas las decisiones, con sus alternativas descartadas, están registradas en
[`docs/HANDOFF-decisiones.md`](HANDOFF-decisiones.md). Las cuatro que estructuran el modelo:

### D-003 · Identidad del atleta: Olympedia como espina dorsal
El atleta canónico proviene de **F1**, por ser la única fuente con fecha de nacimiento (indispensable
para desambiguar homónimos, de los que el dataset tiene cientos). F2, F3 y F4 se reconcilian contra
esa espina por `nombre_normalizado + sexo + NOC + año + evento`; lo que no hace match entra como
atleta nuevo. La tabla **`ATLETA_FUENTE`** conserva el ID original de cada fuente, el método de match
y un nivel de confianza, de modo que cualquier fusión sea auditable sin rehacer la carga.

### D-004a · `PARTICIPACION` es una entrada al evento, no un atleta
Es la decisión más importante del modelo. El baloncesto de EE.UU. en 1992 es **una** fila en
`PARTICIPACION` con medalla de oro, y **doce** filas en `PARTICIPACION_ATLETA`. Así el medallero por
país del inciso (e) se calcula contando participaciones y devuelve 1 oro, no 12. Cargar los CSV tal
como vienen —una fila por atleta-evento— infla el medallero de EE.UU. en miles de medallas.

### D-004b · `NOC` separado de `PAIS`
`URS`, `GDR`, `TCH`, `YUG`, `SAA` y `EUN` son comités disueltos que sí tienen medallas en el
histórico. El dato crudo trae el NOC; `noc_regions.csv` da el mapeo al país moderno. Con la
separación, el inciso (e) puede responder por *Alemania* sumando `GER + FRG + GDR + SAA`, o por el
comité individual, según cómo se filtre. `ROT` (refugiados) e `IOA` (atletas independientes) no
tienen país, por lo que `NOC.pais_id` es nullable.

### D-004c · Jerarquía deportiva de tres niveles
`DEPORTE → DISCIPLINA → EVENTO` reconcilia el `Sport` de F2/F3 con el `Discipline` de F1 en vez de
forzar una fuente a la otra: *Acuáticos* es el deporte, *Natación* / *Clavados* / *Waterpolo* son sus
disciplinas. `EVENTO_EDICION` registra qué eventos se disputaron en cada juegos, lo que permite
responder por eventos históricos ya desaparecidos (tira de cuerda, natación con obstáculos de 1900).

---

## 3. Diccionario de entidades

15 entidades. Los grupos corresponden a los colores del diagrama.

### 3.1 Geografía y comités nacionales

**`PAIS`** — país en su acepción moderna; destino de la normalización de NOCs históricos.

| Columna | Tipo | Restricción |
|---|---|---|
| `pais_id` | `SERIAL` | **PK** |
| `nombre` | `VARCHAR(100)` | `NOT NULL`, `UNIQUE` |
| `codigo_iso3` | `CHAR(3)` | `NULL` |

**`NOC`** — Comité Olímpico Nacional. Puede estar disuelto y aun así tener medallas.

| Columna | Tipo | Restricción |
|---|---|---|
| `noc_codigo` | `CHAR(3)` | **PK** |
| `pais_id` | `INT` | **FK** → `PAIS`, `NULL` (refugiados / atletas independientes) |
| `nombre_comite` | `VARCHAR(120)` | `NOT NULL` |
| `es_historico` | `BOOLEAN` | `NOT NULL DEFAULT FALSE` |
| `notas` | `VARCHAR(200)` | `NULL` |

**`CIUDAD`** — ciudades sede.

| Columna | Tipo | Restricción |
|---|---|---|
| `ciudad_id` | `SERIAL` | **PK** |
| `pais_id` | `INT` | **FK** → `PAIS`, `NOT NULL` |
| `nombre` | `VARCHAR(100)` | `NOT NULL` |
| — | — | `UNIQUE (pais_id, nombre)` |

### 3.2 Ediciones y sedes

**`EDICION`** — una celebración de los Juegos.

| Columna | Tipo | Restricción |
|---|---|---|
| `edicion_id` | `SERIAL` | **PK** |
| `anio` | `SMALLINT` | `NOT NULL`, `CHECK (anio BETWEEN 1896 AND 2100)` |
| `temporada` | `VARCHAR(8)` | `NOT NULL`, `CHECK IN ('Verano','Invierno')` |
| `numero_olimpiada` | `SMALLINT` | `NULL` |
| `nombre` | `VARCHAR(60)` | `NOT NULL` (ej. `"1992 Verano"`) |
| `fecha_inicio`, `fecha_fin` | `DATE` | `NULL` |
| `fue_cancelada` | `BOOLEAN` | `NOT NULL DEFAULT FALSE` — 1916, 1940, 1944 |
| `es_intercalada` | `BOOLEAN` | `NOT NULL DEFAULT FALSE` — Atenas 1906 |
| — | — | `UNIQUE (anio, temporada)` |

> `es_intercalada` existe porque el COI no reconoce Atenas 1906 pero Olympedia sí la registra. La
> bandera permite incluirla o excluirla en las consultas del día de la calificación sin recargar datos.

**`SEDE`** — tabla puente `EDICION`↔`CIUDAD`.

| Columna | Tipo | Restricción |
|---|---|---|
| `edicion_id` | `INT` | **PK, FK** → `EDICION` |
| `ciudad_id` | `INT` | **PK, FK** → `CIUDAD` |
| `es_principal` | `BOOLEAN` | `NOT NULL DEFAULT TRUE` |

> Es puente y no una FK simple en `EDICION` por tres casos reales: la hípica de *Melbourne 1956* se
> celebró en Estocolmo; *Milán–Cortina 2026* tiene dos ciudades sede; y varias ediciones registran
> sedes secundarias. El costo es una tabla y a cambio *"¿este país ha sido sede y en qué años?"*
> —requerimiento explícito del inciso (e)— se resuelve con un `JOIN` exacto.

### 3.3 Catálogo deportivo

**`DEPORTE`** → `deporte_id` **PK** · `nombre` `VARCHAR(80) NOT NULL UNIQUE`

**`DISCIPLINA`** → `disciplina_id` **PK** · `deporte_id` **FK** `NOT NULL` · `nombre` `NOT NULL` · `UNIQUE (deporte_id, nombre)`

**`EVENTO`**

| Columna | Tipo | Restricción |
|---|---|---|
| `evento_id` | `SERIAL` | **PK** |
| `disciplina_id` | `INT` | **FK** → `DISCIPLINA`, `NOT NULL` |
| `nombre` | `VARCHAR(200)` | `NOT NULL` |
| `categoria_sexo` | `VARCHAR(10)` | `CHECK IN ('M','F','Mixto','Abierto')` |
| `es_por_equipos` | `BOOLEAN` | `NOT NULL` |
| — | — | `UNIQUE (disciplina_id, nombre, categoria_sexo)` |

**`EVENTO_EDICION`** — el evento tal como se disputó en unos juegos concretos.

| Columna | Tipo | Restricción |
|---|---|---|
| `evento_edicion_id` | `SERIAL` | **PK** |
| `evento_id` | `INT` | **FK** → `EVENTO`, `NOT NULL` |
| `edicion_id` | `INT` | **FK** → `EDICION`, `NOT NULL` |
| — | — | `UNIQUE (evento_id, edicion_id)` |

### 3.4 Núcleo: atletas, participaciones y resultados

**`ATLETA`**

| Columna | Tipo | Restricción |
|---|---|---|
| `atleta_id` | `SERIAL` | **PK** |
| `nombre_completo` | `VARCHAR(200)` | `NOT NULL` |
| `nombre_usado` | `VARCHAR(150)` | `NULL` |
| `nombre_normalizado` | `VARCHAR(150)` | `NOT NULL` — sin acentos, minúsculas; **clave de matching** |
| `sexo` | `CHAR(1)` | `CHECK IN ('M','F','U')` |
| `fecha_nacimiento`, `fecha_defuncion` | `DATE` | `NULL` |
| `ciudad_nacimiento`, `region_nacimiento` | `VARCHAR(120)` | `NULL` |
| `pais_nacimiento_id` | `INT` | **FK** → `PAIS`, `NULL` |
| `estatura_cm` | `SMALLINT` | `NULL`, `CHECK (estatura_cm BETWEEN 100 AND 250)` |
| `peso_kg` | `NUMERIC(5,2)` | `NULL`, `CHECK (peso_kg BETWEEN 25 AND 250)` |

**`MEDALLA`** — catálogo de 3 filas: `1 Oro`, `2 Plata`, `3 Bronce`, con `orden` para ordenar el medallero.

**`PARTICIPACION`** — **una entrada a un evento**: un atleta individual o un equipo completo.

| Columna | Tipo | Restricción |
|---|---|---|
| `participacion_id` | `BIGSERIAL` | **PK** |
| `evento_edicion_id` | `INT` | **FK** → `EVENTO_EDICION`, `NOT NULL` |
| `noc_codigo` | `CHAR(3)` | **FK** → `NOC`, `NOT NULL` |
| `medalla_id` | `SMALLINT` | **FK** → `MEDALLA`, `NULL` (la mayoría no medalla) |
| `nombre_equipo` | `VARCHAR(150)` | `NULL` — ej. `"Netherlands-2"` |
| `es_por_equipos` | `BOOLEAN` | `NOT NULL` |
| `puesto` | `SMALLINT` | `NULL` — numérico, para ordenar |
| `puesto_texto` | `VARCHAR(20)` | `NULL` — original: `"=17"`, `"DNF"`, `"DNS"`, `"AC"` |
| `empatado` | `BOOLEAN` | `NOT NULL DEFAULT FALSE` |

> Se conservan `puesto` y `puesto_texto` juntos: el numérico permite ordenar e indexar, el texto no
> pierde la información de abandonos y descalificaciones que el enunciado engloba en "resultados".

> **No existe una tabla `RESULTADO` aparte.** Sería 1:1 con `PARTICIPACION` y con la misma clave:
> dos tablas para un solo hecho. El resultado son atributos de la participación.

**`PARTICIPACION_ATLETA`** — resuelve el M:N entre entradas y atletas.

| Columna | Tipo | Restricción |
|---|---|---|
| `participacion_id` | `BIGINT` | **PK, FK** → `PARTICIPACION` |
| `atleta_id` | `INT` | **PK, FK** → `ATLETA` |
| `nombre_usado_en_evento` | `VARCHAR(200)` | `NULL` — el `as` de Olympedia (nombre de casada, alias) |

### 3.5 Trazabilidad

**`FUENTE`** → `fuente_id` **PK** · `nombre` · `url` · `fecha_extraccion` · `descripcion`. Se precarga con F1–F4.

**`ATLETA_FUENTE`**

| Columna | Tipo | Restricción |
|---|---|---|
| `atleta_id` | `INT` | **PK, FK** → `ATLETA` |
| `fuente_id` | `SMALLINT` | **PK, FK** → `FUENTE` |
| `id_en_fuente` | `VARCHAR(40)` | **PK** — el ID original del dataset |
| `nombre_en_fuente` | `VARCHAR(200)` | |
| `metodo_match` | `VARCHAR(30)` | `'espina'`, `'exacto'`, `'nombre+noc+anio'`, `'nuevo'` |
| `confianza` | `NUMERIC(3,2)` | `0.00`–`1.00` |

---

## 4. Relaciones y cardinalidades

| # | Relación | Cardinalidad | Obligatoriedad |
|---|---|---|---|
| 1 | `PAIS` — `NOC` | 1 : N | opcional del lado país |
| 2 | `PAIS` — `CIUDAD` | 1 : N | obligatoria |
| 3 | `PAIS` — `ATLETA` (nació en) | 1 : N | opcional |
| 4 | `DEPORTE` — `DISCIPLINA` | 1 : N | obligatoria |
| 5 | `DISCIPLINA` — `EVENTO` | 1 : N | obligatoria |
| 6 | `EVENTO` — `EVENTO_EDICION` | 1 : N | obligatoria |
| 7 | `EDICION` — `EVENTO_EDICION` | 1 : N | obligatoria |
| 8 | `EDICION` — `SEDE` | 1 : N | obligatoria |
| 9 | `CIUDAD` — `SEDE` | 1 : N | obligatoria |
| 10 | `EVENTO_EDICION` — `PARTICIPACION` | 1 : N | obligatoria |
| 11 | `NOC` — `PARTICIPACION` | 1 : N | obligatoria |
| 12 | `MEDALLA` — `PARTICIPACION` | 1 : N | **opcional** (0..1) |
| 13 | `PARTICIPACION` — `PARTICIPACION_ATLETA` | 1 : N | obligatoria |
| 14 | `ATLETA` — `PARTICIPACION_ATLETA` | 1 : N | obligatoria |
| 15 | `ATLETA` — `ATLETA_FUENTE` | 1 : N | obligatoria |
| 16 | `FUENTE` — `ATLETA_FUENTE` | 1 : N | obligatoria |

Las relaciones 13 y 14 juntas implementan el **M:N `ATLETA` ↔ `PARTICIPACION`**, que es lo que
permite que un evento por equipos tenga una sola medalla y varios atletas.

---

## 5. Normalización

El modelo está en **3FN**:

- **1FN** — sin grupos repetitivos ni valores multivaluados. Los CSV traen `Games = "1992 Summer"`
  (año y temporada en un campo) y `Event = "Basketball Men's Basketball"` (disciplina, sexo y evento
  concatenados); ambos se descomponen en columnas atómicas.
- **2FN** — no hay dependencias parciales. En las tablas de clave compuesta (`SEDE`,
  `PARTICIPACION_ATLETA`, `ATLETA_FUENTE`) todos los atributos no clave dependen de la clave completa.
- **3FN** — sin dependencias transitivas. El caso que las fuentes traen mal es
  `atleta → NOC → país`, resuelto separando `NOC` de `PAIS`; y `evento → disciplina → deporte`,
  resuelto con la jerarquía de tres niveles.

**Desnormalización deliberada, una sola:** `PARTICIPACION.es_por_equipos` duplica lo que ya dice
`EVENTO.es_por_equipos`. Se conserva porque hay eventos que cambiaron de individuales a por equipos
entre ediciones, y porque evita un `JOIN` de tres saltos en la consulta más frecuente del medallero.

---

## 6. Índices previstos

| Tabla | Índice | Propósito |
|---|---|---|
| `ATLETA` | `idx_atleta_nombre_norm (nombre_normalizado)` | matching del ETL y búsqueda del SP (d) |
| `ATLETA` | `idx_atleta_nombre_trgm` (GIN, `pg_trgm`) | búsqueda por nombre parcial en el SP (d) |
| `PARTICIPACION_ATLETA` | `idx_pa_atleta (atleta_id)` | SP (d): todas las participaciones de un atleta |
| `PARTICIPACION` | `idx_part_noc (noc_codigo)` | SP (e): todo lo de un país |
| `PARTICIPACION` | `idx_part_medalla (medalla_id) WHERE medalla_id IS NOT NULL` | medallero (índice parcial: solo ~9% de las filas) |
| `PARTICIPACION` | `idx_part_evento_edicion (evento_edicion_id)` | resultados de un evento |
| `EVENTO_EDICION` | `idx_ee_edicion (edicion_id)` | filtro por año |
| `SEDE` | `idx_sede_ciudad (ciudad_id)` | SP (e): "¿ha sido sede?" |
| `ATLETA_FUENTE` | `idx_af_fuente_id (fuente_id, id_en_fuente)` | idempotencia del ETL |

---

## 7. Cómo el modelo satisface los incisos (d) y (e)

**(d) SP por atleta** — `sp_info_atleta(p_nombre, p_deporte, p_pais, p_anio)`:
`ATLETA` → `PARTICIPACION_ATLETA` → `PARTICIPACION` → `EVENTO_EDICION` → `EVENTO` → `DISCIPLINA` →
`DEPORTE`, más `EDICION`, `NOC` y `MEDALLA`. Devuelve datos biográficos, participaciones con su
edición y evento, puesto y medalla. Los parámetros opcionales filtran por deporte, país y año.

**(e) SP por país** — `sp_info_pais(p_pais, p_anio, p_temporada, p_deporte)`:
`PAIS` → `NOC` → `PARTICIPACION` da participaciones, medallero (contando entradas, no atletas) y
resultados; `EDICION` da los años de participación; y `PAIS` → `CIUDAD` → `SEDE` → `EDICION` responde
si ha sido sede y en qué años.

---

## 8. Alcance excluido (decisión explícita)

- **Antropometría por edición.** F2 trae `Age`/`Height`/`Weight` medidos *en cada juegos*. El modelo
  guarda `estatura_cm` y `peso_kg` como atributos fijos del atleta (de F1) y la edad se deriva de
  `fecha_nacimiento` y `EDICION.anio`. Se pierde la variación entre ediciones. Es una simplificación
  consciente; añadirla después es una tabla `ATLETA_EDICION` sin tocar el resto del modelo.
- **Geolocalización de nacimiento y población histórica por país-año** (disponibles en F1). No las
  pide el enunciado.
