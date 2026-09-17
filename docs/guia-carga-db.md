# Guía: levantar la base de datos y cargar los 15 CSV desde cero (inciso b/c)

Guía paso a paso para levantar el contenedor de PostgreSQL desde cero, comprobar que quedó
funcional, y subir los datos de las **15 tablas** del modelo en el orden que respeta las llaves
foráneas. Sirve tanto para la primera carga como para repetirla si algo sale mal.

De las 15 tablas, **2 no se cargan desde CSV**: `medalla` (3 filas) y `fuente` (4 filas) ya
quedan sembradas automáticamente por `db/init/04-seed.sql` la primera vez que se crea el
contenedor. Las otras **13 sí se cargan desde los CSV de `staging/`**, generados por
`scripts/generar_csv_carga.py`.

---

## 1. Requisitos previos

- Docker y Docker Compose instalados.
- Un archivo `.env` en la raíz del repo (si no existe, se copia de `.env.example`):

  ```bash
  cp .env.example .env
  ```

- Los 15 CSV generados en `staging/`. Si no están, se generan con:

  ```bash
  ./scripts/preparar-fuentes.sh        # reconstruye data/raw/ y sources/ (no se versionan)
  python3 scripts/generar_csv_carga.py # escribe los 13 CSV en staging/
  ```

---

## 2. Levantar la base de datos desde cero

Si ya existía un contenedor/volumen de una corrida anterior y se quiere arrancar limpio:

```bash
docker compose down -v   # borra el contenedor y el volumen (todo lo cargado hasta ahora)
```

Levantar el contenedor:

```bash
docker compose up -d
docker compose ps
```

`docker compose ps` debe mostrar el servicio `db` como `Up (healthy)`. Al crear el volumen por
primera vez, Postgres ejecuta automáticamente todo lo que hay en `db/init/`, en orden:
`01-extensions.sql` → `02-schema.sql` → `03-indices.sql` → `04-seed.sql`. Esto crea las 15
tablas, sus índices, y siembra `medalla` y `fuente`.

Para ver el progreso o depurar un arranque que no queda `healthy`:

```bash
docker compose logs -f db
```

---

## 3. Verificar que quedó funcional

```bash
docker compose exec -T db psql -U olimpiadas_app -d olimpiadas -c "\dt"
```

Deben listarse las 15 tablas. Luego confirma que el esquema y las semillas están bien, **antes**
de cargar nada más:

```sql
SELECT count(*) FROM medalla;   -- 3
SELECT count(*) FROM fuente;    -- 4
SELECT count(*) FROM pais;      -- 0 (todavía no se ha cargado nada)
```

Si vas a conectarte desde **dBeaver**, los parámetros salen del `.env`:

| Campo | Valor |
|---|---|
| Host | `localhost` |
| Puerto | el valor de `POSTGRES_PORT` (por defecto `5434`) |
| Base de datos | el valor de `POSTGRES_DB` (`olimpiadas`) |
| Usuario / contraseña | `POSTGRES_USER` / `POSTGRES_PASSWORD` del `.env` |

---

## 4. Orden de carga de los 13 CSV

El orden **no es arbitrario**: cada tabla de la lista solo puede cargarse después de que sus
llaves foráneas ya existan en la tabla padre. `medalla` y `fuente` no aparecen aquí porque ya
quedaron sembradas en el paso 2 — son las otras 2 de las 15 tablas del modelo.

| # | Archivo | Depende de (ya debe estar cargado) |
|---|---|---|
| 1 | `pais.csv` | — |
| 2 | `noc.csv` | pais |
| 3 | `ciudad.csv` | pais |
| 4 | `edicion.csv` | — |
| 5 | `sede.csv` | edicion, ciudad |
| 6 | `deporte.csv` | — |
| 7 | `disciplina.csv` | deporte |
| 8 | `evento.csv` | disciplina |
| 9 | `evento_edicion.csv` | evento, edicion |
| 10 | `atleta.csv` | pais (nacimiento, opcional) |
| 11 | `participacion.csv` | evento_edicion, noc, medalla *(ya sembrada en el paso 2)* |
| 12 | `participacion_atleta.csv` | participacion, atleta |
| 13 | `atleta_fuente.csv` | atleta, fuente *(ya sembrada en el paso 2)* |

Sigue este orden estrictamente: si se carga un archivo antes que su(s) dependencia(s), la carga
falla por llave foránea (ver sección 7).

### Opción A — Import Data de dBeaver

Por cada archivo, en el orden de la tabla: clic derecho sobre la tabla en el árbol → **Import
Data** → **CSV** → selecciona el archivo correspondiente en `staging/`. En la pantalla de mapeo
de columnas revisa:

- **Encoding**: UTF-8.
- **Null string**: vacío (celda vacía = NULL, así están escritos los CSV).
- **Boolean values**: `true` / `false` (ya vienen en ese formato).
- **Date format**: `yyyy-MM-dd`.
- Que cada columna del CSV quede mapeada 1:1 a la columna del mismo nombre en la tabla (dBeaver
  lo hace automático si los encabezados coinciden, que es el caso).

Nota de rendimiento: `atleta.csv` (~240k filas), `participacion.csv` (~215k) y sobre todo
`atleta_fuente.csv` (~517k) pueden tardar varios minutos por el wizard de dBeaver al insertar
fila por fila. Si algún archivo se queda pegado mucho tiempo, la Opción B es la salida rápida
para ese archivo puntual sin perder lo ya cargado por dBeaver.

### Opción B — `\copy` desde psql (más rápido, útil como respaldo)

Ejecutar desde la raíz del repo (las rutas `staging/*.csv` son relativas al directorio desde
donde se corre el comando):

```bash
docker compose exec -T db psql -U olimpiadas_app -d olimpiadas <<'SQL'
\copy pais                  FROM 'staging/pais.csv'                  CSV HEADER
\copy noc                   FROM 'staging/noc.csv'                   CSV HEADER
\copy ciudad                FROM 'staging/ciudad.csv'                CSV HEADER
\copy edicion                FROM 'staging/edicion.csv'               CSV HEADER
\copy sede                   FROM 'staging/sede.csv'                  CSV HEADER
\copy deporte                 FROM 'staging/deporte.csv'               CSV HEADER
\copy disciplina              FROM 'staging/disciplina.csv'            CSV HEADER
\copy evento                  FROM 'staging/evento.csv'                CSV HEADER
\copy evento_edicion           FROM 'staging/evento_edicion.csv'         CSV HEADER
\copy atleta                  FROM 'staging/atleta.csv'                CSV HEADER
\copy participacion            FROM 'staging/participacion.csv'          CSV HEADER
\copy participacion_atleta      FROM 'staging/participacion_atleta.csv'    CSV HEADER
\copy atleta_fuente             FROM 'staging/atleta_fuente.csv'           CSV HEADER
SQL
```

---

## 5. Resincronizar las secuencias `SERIAL`

Los 13 CSV traen los `*_id` explícitos (para que sean consistentes entre archivos), así que las
secuencias internas de Postgres se quedan atrasadas después de la carga. Adelántalas una sola
vez, **después de cargar los 13 archivos**:

```sql
SELECT setval('pais_pais_id_seq',                     (SELECT max(pais_id)             FROM pais));
SELECT setval('ciudad_ciudad_id_seq',                  (SELECT max(ciudad_id)           FROM ciudad));
SELECT setval('edicion_edicion_id_seq',                (SELECT max(edicion_id)          FROM edicion));
SELECT setval('deporte_deporte_id_seq',                (SELECT max(deporte_id)          FROM deporte));
SELECT setval('disciplina_disciplina_id_seq',          (SELECT max(disciplina_id)       FROM disciplina));
SELECT setval('evento_evento_id_seq',                  (SELECT max(evento_id)           FROM evento));
SELECT setval('evento_edicion_evento_edicion_id_seq',  (SELECT max(evento_edicion_id)   FROM evento_edicion));
SELECT setval('atleta_atleta_id_seq',                  (SELECT max(atleta_id)           FROM atleta));
SELECT setval('participacion_participacion_id_seq',    (SELECT max(participacion_id)    FROM participacion));
```

(`noc`, `sede`, `participacion_atleta`, `atleta_fuente` no tienen secuencia — sus llaves no son
`SERIAL`; `fuente` y `medalla` ya quedaron sincronizadas por el seed inicial del paso 2.)

---

## 6. Verificación final

Conteos esperados si las 13 tablas se cargaron completas y en orden:

```sql
SELECT 'pais' t, count(*) FROM pais                    -- 206
UNION ALL SELECT 'noc',                  count(*) FROM noc                   -- 236
UNION ALL SELECT 'ciudad',               count(*) FROM ciudad                -- 42
UNION ALL SELECT 'edicion',              count(*) FROM edicion               -- 63
UNION ALL SELECT 'sede',                 count(*) FROM sede                  -- 54
UNION ALL SELECT 'deporte',              count(*) FROM deporte               -- 59
UNION ALL SELECT 'disciplina',           count(*) FROM disciplina            -- 90
UNION ALL SELECT 'evento',               count(*) FROM evento                -- 1761
UNION ALL SELECT 'evento_edicion',       count(*) FROM evento_edicion        -- 8123
UNION ALL SELECT 'atleta',               count(*) FROM atleta                -- 239678
UNION ALL SELECT 'participacion',        count(*) FROM participacion         -- 215318
UNION ALL SELECT 'participacion_atleta', count(*) FROM participacion_atleta  -- 314680
UNION ALL SELECT 'atleta_fuente',        count(*) FROM atleta_fuente;        -- 517009
```

Si algún número no calza, casi siempre es porque un archivo se cargó dos veces o se saltó uno
del medio — revisa la sección de problemas comunes.

Sanity check de integridad end-to-end (medallero por país, valida que las 4 tablas centrales
quedaron bien enlazadas):

```sql
SELECT n.nombre_comite, count(*) AS medallas
FROM participacion p
JOIN noc n ON n.noc_codigo = p.noc_codigo
WHERE p.medalla_id IS NOT NULL
GROUP BY n.nombre_comite
ORDER BY medallas DESC
LIMIT 5;
```

Debe devolver 5 filas con nombres de país y conteos razonables (Estados Unidos y la URSS
histórica suelen ir arriba). Si da 0 filas o error, algo quedó mal enlazado antes de esta tabla.

---

## 7. Problemas comunes

- **`violates foreign key constraint`**: se intentó cargar un archivo antes que su tabla padre.
  Revisa la tabla del paso 4 y carga primero la que falta.
- **`duplicate key value violates unique constraint`**: la tabla ya tenía datos de un intento
  anterior. Para reintentar un archivo puntual: `TRUNCATE tabla CASCADE;` y vuelve a cargarlo (y
  todo lo que dependía de él, porque `CASCADE` también vacía las tablas hijas).
- **Se quiere reiniciar todo desde cero otra vez**: repetir el paso 2 completo
  (`docker compose down -v` seguido de `docker compose up -d`) y continuar desde el paso 3.
