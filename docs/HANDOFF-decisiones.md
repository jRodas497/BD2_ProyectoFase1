# Handoff — Bitácora de decisiones de diseño
**Proyecto:** Fase 1 — Base de datos unificada de Olimpiadas
**Curso:** Sistemas de Bases de Datos 2, 2do. Semestre 2026 — USAC, Facultad de Ingeniería
**Iniciado:** 2026-08-30

Este documento registra **cada decisión de diseño con su justificación**, para poder defenderla
el día de la calificación (19-SEP-2026) y para alimentar la documentación final.

---

## 0. Inventario de fuentes (verificado, no asumido)

| # | Fuente | Archivo(s) | Volumen | Cobertura | Aporte único |
|---|--------|-----------|---------|-----------|--------------|
| F1 | Olympedia vía repo KeithGalli | `sources/keithgalli/clean-data/bios.csv`, `results.csv` | 145,500 atletas · 308,408 resultados | 1896–2022, Verano **+ Invierno** | `born_date/city/region/country`, `died_date`, `height_cm`, `weight_kg`, **`place` (puesto, no solo medalla)**, `tied`, 94 disciplinas |
| F2 | Kaggle `120-years-of-olympic-history` | `data/raw/athlete_events.csv`, `noc_regions.csv` | 271,116 filas · 230 NOCs | 1896–2016, Verano + Invierno | `age`/`height`/`weight` por edición, ciudad sede, nombres de `Team`, catálogo NOC→región |
| F3 | Kaggle `summer-olympics-medals-1896-2024` | `data/raw/olympics_dataset.csv` | 252,565 filas | 1896–**2024**, **solo Verano** (31 ediciones) | **Tokio 2020 y París 2024**, ausentes en F1 y F2 |
| F4 | DataCamp DataLab `r-olympics` | `datalab_export_2026-08-30 22_52_41.csv` | 100 filas | muestra | **Ninguno** — es un subconjunto literal de F2 (mismas columnas + `index`) |
| F5 | olympics.com | — | — | — | Referencia de **verificación de calidad**, no de carga |

### D-000 — F4 se carga pero no aporta datos nuevos
**Decisión:** Registrar F4 en el catálogo `fuente` y procesarla por el mismo ETL, pero se espera
que el 100% de sus filas haga match con F2 y no genere atletas ni participaciones nuevas.
**Por qué:** El enunciado exige extraer de las 4 fuentes listadas. Procesarla y demostrar
con una consulta que aportó 0 filas nuevas es evidencia de que el ETL deduplica correctamente,
que es más valioso que ignorarla.

### D-001 — Hallazgo de calidad: `noc_regions.csv` (F2) usa saltos de línea CR (Mac clásico)
**Decisión:** Normalizar a LF en la etapa de staging antes de cargar.
**Por qué:** `wc -l` reporta 0 líneas; un `COPY` directo cargaría el archivo entero como una sola fila.

---

## 1. Decisiones de arquitectura

### D-002 — Motor: PostgreSQL
**Decisión:** PostgreSQL como RDBMS de la entrega.
**Por qué:** `COPY` maneja el volumen de staging (~700k filas crudas) sin fricción; tipos estrictos
y `CHECK` para las reglas de calidad; los SPs de los incisos (d) y (e) se resuelven con
`RETURNS TABLE` / `refcursor`.
**Alternativas descartadas:** MySQL (SPs con múltiples `SELECT` son más simples, pero tipado laxo);
Oracle y SQL Server (más ceremonia de setup sin ganancia para este alcance).

### D-003 — Identidad de atleta: Olympedia como espina dorsal + matching, con trazabilidad
**Decisión:** El atleta canónico proviene de F1 (Olympedia, 145,500 registros, es la única fuente
con fecha de nacimiento). F2, F3 y F4 se reconcilian contra esa espina por
`nombre normalizado + sexo + NOC + año + evento`. Lo que no hace match entra como atleta nuevo.
Se conserva la tabla `atleta_fuente` con el ID original de cada fuente, el método de match y un
nivel de confianza.
**Por qué:**
- Los tres datasets usan IDs mutuamente incompatibles (`athlete_id` de Olympedia, `ID` de Kaggle,
  `player_id`), así que la unificación *tiene* que ser por atributos.
- Olympedia es la fuente más profunda (fecha de nacimiento desambigua homónimos, y trae puesto
  además de medalla), por eso es la espina y no una fuente más.
- `atleta_fuente` permite, en la calificación, responder "¿de dónde salió este dato?" y auditar
  cualquier fusión dudosa sin rehacer la carga.
**Alternativas descartadas:** (a) no fusionar y marcar procedencia — los SPs devolverían el mismo
atleta 2–3 veces y se incumple "base de datos unificada"; (b) fusión agresiva solo por nombre —
colapsa homónimos, de los que hay cientos en el dataset.

### D-004 — Alcance del modelo: se incluyen sedes/país anfitrión y equipos
**Decisión:** Además del núcleo, el modelo incluye **sedes y país anfitrión** y **equipos /
eventos por equipo**.
**Por qué:**
- Sedes: el inciso (e) exige explícitamente "si ha sido sede en alguna ocasión y qué años".
- Equipos: sin una entidad de participación por *entrada* (no por atleta), una medalla de
  baloncesto contaría 12 veces para el país y el medallero saldría inflado.
**Excluidos por decisión explícita del usuario:** antropometría por edición (edad/talla/peso
*en* cada juegos, de F2) y geo de nacimiento + población histórica (F1).
**Consecuencia a vigilar:** al no modelar antropometría por edición, `estatura_cm` / `peso_kg`
quedan como atributos fijos del atleta tomados de F1; se pierde la variación entre ediciones que
F2 sí registra. Es una simplificación consciente, no un olvido.

### D-005 — Secuencia de entrega
**Decisión:** Primero modelo + diagrama ER en `.drawio` editable; revisión del usuario; recién
después DDL, ETL y stored procedures.
**Por qué:** El inciso (a) vence el 2-SEP-2026; el resto el 19-SEP-2026. Corregir el modelo antes
de escribir DDL y ETL evita rehacer la carga.

### D-006 — Formato del diagrama: `.drawio` nativo
**Decisión:** Entregar `diagramas/modelo-er-olimpiadas.drawio` como XML de draw.io sin comprimir.
**Por qué:** El usuario trabaja con la extensión draw.io de VS Code y necesita mover cajas y editar
atributos a mano. XML plano (no `compressed="true"`) también permite versionar y hacer diff.

---

### D-007 — `PARTICIPACION` tiene grano de *entrada al evento*, no de atleta
**Decisión:** Una fila de `PARTICIPACION` = una entrada a un `EVENTO_EDICION` (un atleta individual o
un equipo completo). Los atletas se cuelgan por `PARTICIPACION_ATLETA` (M:N).
**Por qué:** Los CSV vienen a grano atleta × evento. Cargados así, el oro de baloncesto de EE.UU. 1992
son 12 filas con medalla y el medallero del inciso (e) sale inflado en miles de medallas. Con este
grano el medallero es `COUNT(*)` sobre participaciones y da 1 oro.
**Alternativa descartada:** grano atleta × evento con una columna `es_medalla_de_equipo` para
descontar — requiere lógica correctiva en cada consulta en lugar de arreglarlo en el modelo.

### D-008 — Jerarquía deportiva de tres niveles: Deporte > Disciplina > Evento
**Decisión:** `DEPORTE` → `DISCIPLINA` → `EVENTO` → `EVENTO_EDICION`.
**Por qué:** F2/F3 dan `Sport` (66 valores) y F1 da `Discipline` (94). No son el mismo nivel: es la
jerarquía real del COI (*Acuáticos* es deporte; *Natación*, *Clavados*, *Waterpolo* son disciplinas).
Modelarla reconcilia ambas fuentes sin forzar una a la otra. `EVENTO_EDICION` además registra qué
eventos se disputaron en cada juegos, lo que habilita consultas sobre eventos desaparecidos
(tira de cuerda, natación con obstáculos de 1900).

### D-009 — `SEDE` como tabla puente, no FK simple en `EDICION`
**Decisión:** `SEDE(edicion_id, ciudad_id, es_principal)`.
**Por qué:** tres casos reales rompen el FK simple — la hípica de Melbourne 1956 se celebró en
Estocolmo; Milán–Cortina 2026 tiene dos ciudades sede; varias ediciones tienen sedes secundarias.
Cuesta una tabla y hace que "¿ha sido sede y en qué años?" del inciso (e) sea un JOIN exacto.

### D-010 — No existe tabla `RESULTADO` separada
**Decisión:** `puesto`, `puesto_texto`, `empatado` y `medalla_id` son atributos de `PARTICIPACION`.
**Por qué:** una tabla `RESULTADO` sería 1:1 con `PARTICIPACION` y con la misma clave — dos tablas
para un solo hecho, sin ganancia. El resultado *es* un atributo de la participación.

### D-011 — Se conservan `puesto` (numérico) y `puesto_texto` (original) juntos
**Decisión:** dos columnas para el mismo dato.
**Por qué:** el crudo trae `"=17"`, `"DNF"`, `"DNS"`, `"AC"`. El numérico permite ordenar e indexar;
el texto no pierde abandonos ni descalificaciones, que el enunciado engloba en "resultados".

### D-012 — Única desnormalización deliberada: `PARTICIPACION.es_por_equipos`
**Decisión:** duplicar el flag que ya vive en `EVENTO`.
**Por qué:** hay eventos que cambiaron de individuales a por equipos entre ediciones, y evita un JOIN
de tres saltos en la consulta más frecuente (el medallero). Queda documentada como desnormalización
consciente para poder defenderla si preguntan por 3FN.

### D-013 — Banderas `fue_cancelada` y `es_intercalada` en `EDICION`
**Decisión:** modelar 1916/1940/1944 (canceladas) y Atenas 1906 (intercalada, no reconocida por el COI
pero presente en Olympedia) como filas con bandera, no como ausencias.
**Por qué:** permite incluirlas o excluirlas en las consultas del día de la calificación sin recargar
datos, y deja explícito que la ausencia de participaciones en esos años es un hecho histórico y no un
fallo de carga.

### D-014 — `ATLETA.nombre_normalizado` como columna materializada
**Decisión:** almacenar el nombre sin acentos y en minúsculas como columna propia, indexada.
**Por qué:** es la clave de matching del ETL (D-003) y del SP del inciso (d). Calcularla al vuelo en
cada consulta impediría usar índice sobre 145k+ atletas.

---

## 3. Entregables producidos

| Fecha | Inciso | Archivo |
|---|---|---|
| 2026-08-30 | (a) | `diagramas/modelo-er-olimpiadas.drawio` — 15 entidades, 16 relaciones, XML plano editable |
| 2026-08-30 | (a) | `docs/modelo-de-datos.md` — diccionario de datos, cardinalidades, normalización, índices |

---

## 4. Pendientes / a decidir

- **Inciso (b)/(c):** definir si el ETL corre en Python (pandas/psycopg) sobre tablas de staging o
  en SQL puro con `COPY` + transformaciones. Pendiente hasta que el modelo esté aprobado.
- **Umbral de confianza del matching (D-003):** decidir a partir de qué valor una fusión se acepta
  automáticamente y a partir de cuál se deja como atleta nuevo.
- **Mapeo Deporte→Disciplina (D-008):** las fuentes no traen el nivel "deporte" explícito; hay que
  construir el catálogo de 66–94 valores a mano o con reglas. Estimar esfuerzo.
