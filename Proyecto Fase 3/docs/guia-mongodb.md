# Guía paso a paso — Fase 3: base de datos de Olimpiadas en MongoDB

**Proyecto Fase 3 · Sistemas de Bases de Datos 2 · USAC · 2do. semestre 2026**

Esta guía explica, con los comandos exactos y las salidas reales de la ejecución, cómo se migró la base
de la Fase 1 a MongoDB, cómo se crean las colecciones y los índices, cómo se cargan los datos y cómo se
usan las dos consultas pedidas (por atleta y por país). Todas las salidas mostradas son de la corrida del
2026-10-21 (bitácoras en `logs/`).

Todos los comandos se ejecutan desde la carpeta `Proyecto Fase 3/`.

> Esta guía usa MongoDB en Docker. Para hacerlo en un cluster de **MongoDB Atlas** (nube), ver la sección 10.

---

## 1. Qué pide el enunciado y dónde se cubre

| Inciso | Pide | Dónde |
|---|---|---|
| a | Cargar los datos de la Fase 1 a MongoDB, completos y con lo que falló en la carga relacional **corregido** | `scripts/01_corregir_datos.py` + `scripts/03_cargar_mongo.py`; reporte en `docs/reporte-correcciones.md` |
| b | Todos los scripts de creación de documentos/colecciones/índices y de carga, con sus archivos fuente; documentación con fecha y hora de ejecución | `scripts/` (numerados), `datos/fase1/` (fuentes), `logs/` (bitácoras con fecha y hora) |
| c | Consulta por **nombre de atleta** con toda su información; filtros opcionales (deporte, país, año) | `scripts/consulta_atleta.sh` |
| d | Consulta por **país**: participaciones, medallas, resultados, años de participación y si fue sede | `scripts/consulta_pais.sh` |
| Nota | El día de la calificación se hacen consultas en el momento y no deben tardar | Respuesta en 28–160 ms en local (ver "Cómo están optimizadas las consultas" y §8) |

---

## 2. Requisitos e instalación

Solo hace falta **Docker con Docker Compose v2**. No se instala MongoDB ni Python en el equipo: MongoDB
corre en un contenedor y el cargador (Python + `pymongo`) en otro contenedor.

```bash
cd "Proyecto Fase 3"
cp .env.example .env          # usuario/clave de MongoDB y puerto (27018); ajustar la clave
scripts/cargar_todo.sh        # ejecuta los 6 pasos de las secciones 3.1 a 3.7 (~65 s)
```

> **Sobre las credenciales.** No se obtienen de ninguna página de MongoDB: **usted las elige** en `.env`
> (`MONGO_USER`, `MONGO_PASSWORD`) y el contenedor las crea la **primera vez** que arranca con un volumen vacío.
> Si después cambia `MONGO_PASSWORD`, MongoDB seguirá exigiendo la anterior (`Authentication failed`). Hay dos
> salidas: volver a poner la clave original, o recrear el volumen con `docker compose down -v`.

Para repetir todo desde cero (borra la base y vuelve a crearla):
```bash
docker compose down -v        # borra el volumen de datos de MongoDB
scripts/cargar_todo.sh
```

---

## 3. Pasos detallados

### 3.1 Levantar MongoDB

```bash
docker compose up -d --wait mongo
docker compose ps              # estado: healthy
```
[`docker-compose.yml`](../docker-compose.yml) define:
- **Imagen** `mongo:7.0`, contenedor `olimpiadas-mongo-f3`, puerto **27018** del equipo → 27017 del contenedor
  (no choca con Postgres de las Fases 1 y 2 ni con un MongoDB local).
- **Autenticación**: usuario y clave de `.env` (`MONGO_USER`, `MONGO_PASSWORD`).
- **Almacenamiento persistente**: volumen `olimpiadas_f3_mongodata` montado en `/data/db`. Los datos sobreviven
  a `docker compose down`; solo `down -v` los borra.
- **Zona horaria** `America/Guatemala`, para que los logs muestren la hora local.
- **Healthcheck** con `db.adminCommand('ping')` y `--wait`, para no cargar hasta que MongoDB responda.

### 3.2 Conectarse a la base

| Forma | Comando / datos |
|---|---|
| Consola `mongosh` (recomendada) | `scripts/ejecutar.sh shell` |
| Un script `.js` | `scripts/ejecutar.sh js 05_validar.js` |
| MongoDB Compass u otro cliente | URI `mongodb://olimpiadas_app:<clave>@localhost:27018/olimpiadas?authSource=admin` |

Una vez dentro de `mongosh`:
```javascript
show collections                         // las 6 colecciones
db.participaciones.countDocuments()      // 221204
db.atletas.findOne({nombre_normalizado: "usain bolt"})
```

### 3.3 Corregir los datos de la Fase 1  (`scripts/01_corregir_datos.py`)

```bash
scripts/ejecutar.sh py 01_corregir_datos.py
```
Lee los CSV de `datos/fase1/` (los mismos que se cargaron a PostgreSQL) y escribe los corregidos en
`datos/corregidos/`, más el reporte `docs/reporte-correcciones.md`.

**El defecto de la Fase 1 y su corrección.** El ETL de la Fase 1 agrupaba las filas de resultados por
(evento, NOC, puesto, medalla, empate). En un evento **individual**, dos atletas del mismo país con el mismo
puesto —o sin puesto (DNS/DNF)— quedaban fundidos en **una sola "participación de equipo"**. Ejemplo real: en los
100 m masculinos de 1928, Eduardo Albe y Juan Bautista Pina (Argentina, ambos puesto 6, series distintas) eran
una única participación con dos atletas. Como consecuencia, eventos individuales como el maratón o los 100 m
quedaron marcados `es_por_equipos = true`.

| Corrección | Efecto |
|---|---|
| **C1** separar las participaciones individuales fundidas | 6 400 participaciones → +8 828 nuevas; total **212 376 → 221 204**; cada una guarda `participacion_origen_id` |
| **C2** recalcular `es_por_equipos` del evento con evidencia de los datos | 119 eventos corregidos (95 pasan a individual, 24 a equipo) |
| **C3** `participacion.es_por_equipos` coherente con su evento | consistente con la decisión D-012 de la Fase 1 |
| **C4** NOC: 13 comités disueltos marcados como históricos (FRG, SCG, AHO, BOH, ANZ, WIF, YAR, YMD, UAR, RHO, NBO, NFL, CRT) y 28 nombres de comité corregidos (URS → *Soviet Union*, GDR → *East Germany*...). El original queda en `nombre_comite_fase1` | las búsquedas por "Soviet Union" o "East Germany" funcionan |
| **C5** país: "Boliva" → "Bolivia"; nombre en español en 64 países | se puede consultar "Alemania", "Francia", "Estados Unidos" |

Salida real:
```
[2026-10-21 18:05:49] Corrección de datos de Fase 1 -> /app/datos/corregidos
  participaciones: 212,376 -> 221,204 (separadas 6,400)
  eventos con flag cambiado: 119 | NOC históricos: 13 | nombres NOC: 28
```
El script termina con comprobaciones (`assert`): no queda ningún evento individual con varios atletas y no se
pierde ninguna fila de `participacion_atleta` (314 679 antes y después).

### 3.4 Crear las colecciones con validación  (`scripts/02_crear_colecciones.js`)

```bash
scripts/ejecutar.sh js 02_crear_colecciones.js
```
Crea 6 colecciones y a cada una le asigna un **validador `$jsonSchema`** (`validationLevel: "strict"`,
`validationAction: "error"`): campos obligatorios, tipos y valores permitidos.

```
  colección creada: comites / paises / ediciones / eventos / atletas / participaciones
```
Prueba de que el validador funciona (intento de insertar un documento incompleto):
```javascript
db.participaciones.insertOne({ _id: 999999999, es_por_equipos: false })
// RECHAZADO: código 121 — Document failed validation
```

### 3.5 Cargar los documentos  (`scripts/03_cargar_mongo.py`)

```bash
scripts/ejecutar.sh py 03_cargar_mongo.py
```
Construye los documentos desde los CSV corregidos y los inserta por lotes de 5 000 (`insert_many`). Salida real:
```
[2026-10-21 18:05:55]   comites: 236 documentos
[2026-10-21 18:05:55]   ediciones: 63 documentos
[2026-10-21 18:05:55]   paises: 205 documentos
[2026-10-21 18:05:55]   eventos: 1,761 documentos
[2026-10-21 18:06:02]   participaciones: 221,204 documentos
[2026-10-21 18:06:09]   atletas: 239,678 documentos
```
El modelo (qué se embebe, qué se referencia y por qué) está en [`modelo-mongodb.md`](modelo-mongodb.md).

### 3.6 Crear los índices  (`scripts/04_indices.js`)

```bash
scripts/ejecutar.sh js 04_indices.js
```
18 índices (más el `_id` de cada colección). Cada uno responde a un patrón de las consultas:

| Colección | Índice | Para qué |
|---|---|---|
| `atletas` | `{ nombre_normalizado: 1 }` | búsqueda por nombre |
| `atletas` | `{ "resumen.total_medallas": -1 }` | ordenar atletas por medallas |
| `participaciones` | `{ "atletas._id": 1, "edicion.anio": 1 }` | **consulta por atleta** (índice *multikey* sobre el arreglo embebido) |
| `participaciones` | `{ "noc.codigo": 1, "edicion.anio": 1, "edicion.temporada": 1, "deporte.nombre": 1, medalla: 1 }` (`cubre_resumen_pais`) | **consulta por país**: índice *cubriente*, el resumen se calcula leyendo solo el índice, sin tocar los documentos (`docsExamined: 0`) |
| `participaciones` | `{ "pais._id": 1, medalla_orden: 1 }` | medallero por país |
| `participaciones` | `{ "deporte.nombre": 1, "edicion.anio": 1 }` | filtro por deporte |
| `participaciones` | `{ medalla_orden: 1, "noc.codigo": 1 }` *(parcial: solo con medalla)* | listar medallas ocupando poco espacio |
| `participaciones` | `{ "edicion._id": 1 }`, `{ evento_edicion_id: 1 }` | cruces por edición/evento |
| `comites`, `paises`, `ediciones`, `eventos` | por nombre/código/año (únicos donde corresponde) | resolver el texto del país o la edición |

Comprobación con `explain` (la consulta usa el índice y examina solo lo necesario):
```javascript
db.participaciones.find({"atletas._id": 105512, "edicion.anio": 2012}).explain("executionStats")
// índice usado: atletas._id_1_edicion.anio_1   keysExamined: 3   docsExamined: 3   nReturned: 3
db.participaciones.aggregate([{ $match: {"noc.codigo": {$in: ["GER","FRG","GDR","SAA"]}} },
  { $group: { _id: {a: "$edicion.anio", t: "$edicion.temporada", n: "$noc.codigo"}, p: {$sum: 1} } }], { explain: "executionStats" })
// plan: IXSCAN(cubre_resumen_pais)   keysExamined: 11 831   docsExamined: 0   (consulta cubierta por el índice)
```

Si ya tenía la base cargada con una versión anterior, aplique el índice nuevo (reemplaza al anterior `noc.codigo + edicion.anio`):
```bash
scripts/ejecutar.sh js 04_indices.js
```

### 3.7 Validar la carga  (`scripts/05_validar.js`)

```bash
scripts/ejecutar.sh js 05_validar.js
```
Hace cuatro grupos de comprobaciones; la salida real fue **todo `[OK]`**:

1. **Conteos**: comites 236, paises 205, ediciones 63, eventos 1 761, atletas 239 678, participaciones 221 204.
2. **Integridad**: toda participación tiene atletas; todo atleta embebido existe en `atletas`; todo NOC y
   toda edición referenciados existen; ninguna participación individual tiene más de un atleta.
3. **Medalleros contra datos conocidos** (una medalla de equipo cuenta **una** vez):

   | Comprobación | Resultado | Oficial |
   |---|---|---|
   | Francia 2024 | 16 / 26 / 22 | 16 / 26 / 22 |
   | Guatemala | 1 / 1 / 1 | 1 / 1 / 1 |
   | Michael Phelps | 23 / 3 / 2 | 23 / 3 / 2 |
   | Usain Bolt | 8 oros | 8 |
   | Rugby Sevens Francia 2024 | 1 oro | 1 (en Fase 1 contaba 13) |
4. **Correcciones**: el maratón masculino es individual; FRG es histórico y se llama *West Germany*.

### 3.8 Todo de una vez

```bash
scripts/cargar_todo.sh
```
Ejecuta los pasos 3.1 a 3.7 y guarda la bitácora con fecha y hora en `logs/carga_AAAAMMDD_HHMMSS.log`:
```
Fase 3 — carga completa a MongoDB. Inicio: 2026-10-21 18:05:48 CST
######## PASO 1/6: levantar MongoDB — 18:05:48 ########
######## PASO 2/6: corregir datos de Fase 1 — 18:05:49 ########
######## PASO 3/6: crear colecciones — 18:05:53 ########
######## PASO 4/6: cargar documentos — 18:05:54 ########
######## PASO 5/6: crear índices — 18:06:10 ########
######## PASO 6/6: validar — 18:06:13 ########
Fin: 2026-10-21 18:06:52 CST   Duración total: 64 s
```

---

## 4. Consulta (c): por atleta

```bash
scripts/consulta_atleta.sh "<nombre>" [deporte] [pais] [anio] [temporada] [medalla]
```
- El **nombre** es obligatorio y se busca ignorando mayúsculas, acentos y el orden de las palabras
  (`"Nadia Comaneci"` encuentra *Nadia Comăneci*). Si coinciden varios atletas, se detallan los más relevantes
  (por medallas) y se listan los demás.
- Los filtros opcionales aceptan `""` para omitir uno intermedio. El **país** se reconoce por nombre
  (inglés o español), código NOC o nombre de comité.

Ejemplos:
```bash
scripts/consulta_atleta.sh "Usain Bolt"
scripts/consulta_atleta.sh "Michael Phelps" Swimming "" 2012
scripts/consulta_atleta.sh "Bolt" Athletics JAM
LIMITE=3 scripts/consulta_atleta.sh "Bolt"        # cuántos atletas detallar si el nombre coincide con varios
```
Salida real de `scripts/consulta_atleta.sh "Usain Bolt"` (130 ms):
```
ATLETA: Usain Bolt   [id 105512]
Sexo: M  |  Nacimiento: 1986-08-21, Sherwood Content, Trelawny, Jamaica
Estatura: 196 cm  |  Peso: 95 kg
Trayectoria: 10 participaciones, 2004–2016, deportes: Athletics
MEDALLAS (carrera): Oro 8 | Plata 0 | Bronce 0 | Total 8

AÑO  TEMPORADA DEPORTE   EVENTO                       NOC  PUESTO  MEDALLA EQUIPO
2004 Verano    Athletics 200 metres M                 JAM  5       -
2008 Verano    Athletics 100 metres M                 JAM  1       Oro
2012 Verano    Athletics 4 × 100 metres Relay M       JAM  1       Oro     Jamaica (5 integrantes)
...
```
Muestra: biografía (sexo, nacimiento, lugar, defunción, estatura, peso), trayectoria, medallas de carrera (y
**con los filtros** cuando se usan), cada participación (edición, deporte/disciplina, evento, NOC, puesto,
medalla, equipo) y las fuentes de donde salió el atleta.

### Cómo están optimizadas las consultas

Medido: en MongoDB el servidor resuelve cada consulta en milisegundos; lo que cuesta, sobre todo en un cluster remoto,
son los **viajes por la red** (cada uno ≈ 120 ms en Atlas) y la **cantidad de datos que viajan**. Por eso:

| Técnica | Dónde |
|---|---|
| **Pocos viajes**: el país y sus NOC/sedes llegan en una sola consulta (`$lookup`); los cálculos del país salen juntos; las participaciones de **todos** los atletas que coinciden se piden de una vez, no una por atleta | ambas consultas |
| **Índice cubriente** `cubre_resumen_pais`: participaciones, medallas por año/NOC/deporte se calculan solo con el índice (0 documentos leídos) | país |
| **Datos recortados**: de cada equipo viajan el número de integrantes y 3 nombres, no la lista completa; las fuentes viajan como texto corto | ambas |
| **Menos cálculo**: atletas distintos con `$unwind`+`$group` en lugar de `$addToSet`+`$reduce` | país |
| **Paralelismo**: los 4 cálculos independientes del país salen a la vez (`PARALELO=0` los serializa) | país |

Resultado en Atlas (mediana de 5 corridas, plan gratuito M0, 2026-10-21) y en local:

| Consulta | Atlas antes | Atlas ahora | Local antes | Local ahora |
|---|---|---|---|---|
| Atleta: Usain Bolt | 372 ms | 373 ms | 116 ms | 119 ms |
| Atleta: Phelps (natación, 2012) | 512 ms | 358 ms | — | — |
| Atleta: "Bolt" (49 coincidencias) | 4 291 ms | **489 ms** | 167 ms | 133 ms |
| País: Guatemala | 591 ms | 375 ms | 31 ms | 28 ms |
| País: Francia 2024 | 947 ms | 896 ms | — | — |
| País: Alemania | 2 036 ms | 1 829 ms | 229 ms | **137 ms** |
| País: USA | 1 915 ms | 1 453 ms | 239 ms | **156 ms** |

El plan gratuito de Atlas es compartido y sus tiempos varían mucho de una corrida a otra (en Alemania, entre 1.2 y 2.8 s);
en local son estables. La salida impresa es idéntica a la de antes (comparada línea por línea en 23 casos) salvo un
error corregido: con el filtro de medalla (`scripts/consulta_pais.sh USA "" Verano Swimming Oro`), el desglose
"medallas por deporte" ignoraba el filtro y mostraba todas las medallas. Además, los deportes con igual número de
medallas ahora salen en orden alfabético.

## 5. Consulta (d): por país

```bash
scripts/consulta_pais.sh "<pais>" [anio] [temporada] [deporte] [medalla]
```
El país acepta nombre en inglés o español, código NOC (`USA`, `GUA`, `URS`) o nombre de comité
(`"Soviet Union"`). Muestra:

1. **Comités (NOC)** del país, incluidos los disueltos (Alemania → GER, FRG, GDR, SAA).
2. **Si fue sede** y en qué años y ciudades.
3. **Resumen**: participaciones (entradas a un evento), atletas distintos, ediciones.
4. **Medallero** (oro/plata/bronce; un equipo cuenta una vez), por comité, por edición y por deporte.
5. **Resultados** con medalla (por defecto) o todos (`DETALLE=1` o al usar filtros).

```bash
scripts/consulta_pais.sh Guatemala
scripts/consulta_pais.sh Francia 2024
scripts/consulta_pais.sh USA "" Verano Swimming Oro
DETALLE=1 TOPE=500 scripts/consulta_pais.sh Guatemala     # todas las participaciones
```
Salida real de `scripts/consulta_pais.sh Guatemala` (37 ms):
```
PAÍS: Guatemala
Comités (NOC): GUA Guatemala
Sede de los Juegos: no ha sido sede

RESUMEN: 390 participaciones (entradas a un evento) | 267 atletas distintos | 17 ediciones
MEDALLERO: Oro 1 | Plata 1 | Bronce 1 | Total 3   (un equipo cuenta una sola medalla)

RESULTADOS CON MEDALLA:
2012 Athletics  20 kilometres Race Walk M  GUA  2  Plata   Érick Barrondo
2024 Shooting   Trap F                     GUA  -  Oro     Adriana Ruano
2024 Shooting   Trap M                     GUA  -  Bronce  Pierre Brol
```
Alemania muestra el desglose por comité y las sedes (1936 Invierno en Garmisch-Partenkirchen, 1936 Verano en
Berlín, 1972 Verano en Múnich):
```
POR COMITÉ:
  GER   participaciones   7591   Oro  355  Plata  374  Bronce  362
  FRG   participaciones   2247   Oro   67  Plata   82  Bronce   94
  GDR   participaciones   1912   Oro  192  Plata  165  Bronce  162
  SAA   participaciones     77   Oro    0  Plata    0  Bronce    0
```

> Los resultados de París 2024 no traen puesto (`-`), solo medalla: la fuente (F3) no lo incluye.

### Evidencias generadas
```bash
scripts/generar_evidencias.sh        # 10 consultas de ejemplo -> logs/consulta_*.log (con fecha y hora)
```

---

## 6. Comandos de MongoDB para verificar y explicar (útiles el día de la calificación)

Dentro de `scripts/ejecutar.sh shell`:

```javascript
// ¿qué hay en la base?
show collections
db.getCollectionNames().forEach(c => print(c, db[c].countDocuments()))

// ver un documento completo
db.atletas.findOne({ nombre_normalizado: "usain bolt" })
db.participaciones.findOne({ "noc.codigo": "FRA", "edicion.anio": 2024, medalla: "Oro", es_por_equipos: true })

// índices de una colección
db.participaciones.getIndexes()

// medallero de un país (una medalla por entrada, no por atleta)
db.participaciones.aggregate([
  { $match: { "noc.codigo": "GUA", medalla: { $exists: true } } },
  { $group: { _id: "$medalla", total: { $sum: 1 } } }
])

// medallas de un atleta
db.participaciones.aggregate([
  { $match: { "atletas._id": 105512, medalla: { $exists: true } } },
  { $group: { _id: "$medalla", total: { $sum: 1 } } }
])

// ¿usa el índice? (buscar "IXSCAN" en el plan ganador)
db.participaciones.find({ "atletas._id": 105512 }).explain("executionStats")
```

---

## 7. Estructura del proyecto

```
Proyecto Fase 3/
├── docker-compose.yml      MongoDB 7 (volumen persistente, auth) + cargador Python
├── Dockerfile.loader       Python 3.12 + pymongo
├── .env.example            plantilla de credenciales (copiar a .env)
├── datos/
│   ├── fase1/              archivos FUENTE: los 13 CSV de la Fase 1 + medalla.csv y fuente.csv
│   └── corregidos/         (generado, no versionado) CSV tras las correcciones
├── scripts/
│   ├── 01_corregir_datos.py        correcciones de la carga relacional
│   ├── 02_crear_colecciones.js     colecciones + validadores $jsonSchema
│   ├── 03_cargar_mongo.py          carga de documentos
│   ├── 04_indices.js               índices
│   ├── 05_validar.js               conteos, integridad y medalleros
│   ├── consultas/                  lib.js, consulta_atleta.js, consulta_pais.js
│   ├── consulta_atleta.sh          método de consulta (c)
│   ├── consulta_pais.sh            método de consulta (d)
│   ├── ejecutar.sh                 ayudante: js | py | shell
│   ├── cargar_todo.sh              los 6 pasos con bitácora
│   └── generar_evidencias.sh       consultas de ejemplo con log
├── logs/                   bitácoras con fecha y hora (carga y consultas)
└── docs/                   esta guía, modelo-mongodb.md y reporte-correcciones.md
```

## 8. Resultados de la corrida (2026-10-21)

| Paso | Tiempo |
|---|---|
| Corregir datos | 4 s |
| Crear colecciones | 1 s |
| Cargar 221 204 participaciones + 239 678 atletas + catálogos | 16 s |
| Crear 18 índices | 3 s |
| Validar | 39 s |
| **Total** | **64 s** |

| Consulta | Tiempo |
|---|---|
| Atleta: Usain Bolt / Phelps 2012 / Comăneci / Barrondo | 119–130 ms |
| Atleta: "Bolt" (49 coincidencias) | 133 ms |
| País: Guatemala | 28 ms |
| País: Alemania / USA (15 034 participaciones) | 137 / 156 ms |

Tamaño en disco: `atletas` 159 MB, `participaciones` 119 MB, índices ≈ 19 MB.

## 9. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `port is already allocated` (27018) | otro proceso usa el puerto | cambiar `MONGO_PORT` en `.env` y `docker compose up -d` |
| `Authentication failed` | se cambió `MONGO_PASSWORD` en `.env` después de crear el volumen | devolver la clave original en `.env`, o `docker compose down -v` y volver a cargar (la clave se fija al crear el volumen) |
| `Document failed validation` al cargar | un documento no cumple el `$jsonSchema` | revisar `scripts/02_crear_colecciones.js`; es el comportamiento buscado |
| `No existe ... datos/corregidos` | no se ejecutó el paso 1 | `scripts/ejecutar.sh py 01_corregir_datos.py` |
| La consulta no encuentra el país | nombre no reconocido | probar el código NOC (`USA`) o el nombre en inglés/español |
| Una colección quedó vacía | se corrió el paso 2 sin el paso 4 | `scripts/cargar_todo.sh` |

---

## 10. Opción en la nube: MongoDB Atlas

Atlas es el servicio de MongoDB en la nube (mongodb.com/atlas). Sirve para demostrar el mismo trabajo en un
**cluster** en lugar de Docker. Los scripts funcionan igual contra Atlas: basta definir `MONGO_URI` en `.env`.

> **Estado de la prueba.** El modo nube se probó contra un servidor MongoDB remoto simulado (carga completa,
> índices, validación y consultas: todo igual que en local, 63 s) y la copia con `mongodump`/`mongorestore`
> (restauró los 463 147 documentos y los 8 índices). No se ha probado contra una cuenta real de Atlas, por lo que
> los pasos de la interfaz web pueden variar ligeramente.

### 10.1 Crear el cluster gratuito (una sola vez, en la web)

1. Entrar a **mongodb.com/atlas** → *Try Free* y crear la cuenta (correo o Google).
2. Crear una **organización** y un **proyecto** (nombres libres, p. ej. `BD2`).
3. En el proyecto: **Create** (o *Build a Database*) → plan **M0 Free** → proveedor (AWS) y región cercana →
   nombre del cluster (p. ej. `Cluster0`) → **Create**. Tarda 1–3 minutos.
4. **Usuario de base de datos** (*Database Access* → *Add New Database User*):
   método *Password*, usuario y clave a elección, rol **Atlas admin** (o *Read and write to any database*).
   Guardar la clave: no se vuelve a mostrar.
5. **Acceso de red** (*Network Access* → *Add IP Address*):
   - *Add Current IP Address* para su equipo; o
   - *Allow Access from Anywhere* (`0.0.0.0/0`) si la calificación será en otra red. Úselo solo para la demostración,
     con una clave fuerte, y elimine la regla después.
6. **Cadena de conexión**: en el cluster, **Connect** → *Drivers* (o *Shell*) → copiar la URI:
   `mongodb+srv://USUARIO:<password>@cluster0.xxxxx.mongodb.net/`
   Reemplazar `<password>` por la clave (sin los `< >`).

### 10.2 Apuntar el proyecto al cluster

En `.env` agregar la URI **con el nombre de la base al final**:
```
MONGO_URI=mongodb+srv://USUARIO:CLAVE@cluster0.xxxxx.mongodb.net/olimpiadas
```
Si la clave tiene `@`, `:`, `/` o `%`, escribirlos codificados (`@` → `%40`, `:` → `%3A`, `/` → `%2F`, `%` → `%25`).
Con `MONGO_URI` definida los scripts **no usan el MongoDB local**.

### 10.3 Cargar los datos en Atlas (dos métodos)

**Método A — con los mismos scripts** (genera todo en el cluster):
```bash
scripts/cargar_todo.sh        # corrige, crea colecciones, carga, indexa y valida en Atlas
```
**Método B — copiar la base ya cargada en local** (más rápido si la conexión es lenta; los clusters gratuitos
limitan las operaciones por segundo, y la carga directa puede tardar más que en local):
```bash
set -a; source .env; set +a
URI_LOCAL="mongodb://$MONGO_USER:$MONGO_PASSWORD@localhost:27017/olimpiadas?authSource=admin"
# 1) exportar (3 s, 26 MB comprimido)
docker compose exec -T mongo mongodump --uri="$URI_LOCAL" --archive --gzip > olimpiadas.archive.gz
# 2) importar al cluster (copia colecciones, índices y validadores)
docker compose exec -T mongo mongorestore --uri="$MONGO_URI" --archive --gzip --nsInclude="olimpiadas.*" < olimpiadas.archive.gz
```
(El archivo `olimpiadas.archive.gz` no debe subirse al repositorio.)

### 10.4 Consultas y verificación en Atlas

Los mismos comandos funcionan sin cambios:
```bash
scripts/consulta_atleta.sh "Usain Bolt"
scripts/consulta_pais.sh Guatemala
scripts/ejecutar.sh js 05_validar.js
scripts/ejecutar.sh shell            # mongosh interactivo contra Atlas
```
También se puede verificar desde la web: en el cluster, **Browse Collections** (*Data Explorer*) permite ver las
colecciones, los documentos, los índices y ejecutar filtros como `{"noc.codigo": "GUA"}`.

El tamaño en disco de la base es de **74 MB** (datos comprimidos + índices), muy por debajo de los 512 MB del plan
gratuito M0.

### 10.5 Alternar entre local y nube
- **Volver a local:** quitar o comentar `MONGO_URI` en `.env`.
- **Sin editar `.env`:** anteponer `MONGO_MODO=local` a cualquier comando, p. ej. `MONGO_MODO=local scripts/consulta_pais.sh Guatemala`. Usa el usuario y la clave del contenedor local (`MONGO_USER`/`MONGO_PASSWORD`, los que tenía cuando se creó el volumen).

### 10.6 ¿Local o Atlas para la calificación?

| | Docker local | Atlas (nube) |
|---|---|---|
| Depende de internet | No | **Sí**, también en el lugar de la calificación |
| Preparación | `docker compose up -d` | cuenta, cluster, usuario, red y URI |
| Riesgo | casi ninguno | red bloqueada, IP no permitida, cluster pausado por inactividad |
| Latencia de las consultas | 30–240 ms | 0.4–2 s (cada viaje ≈ 120 ms y el plan gratuito es compartido; ver tabla de optimización) |
| Lo que demuestra | el trabajo completo, con control total | además, despliegue en un cluster real |

**Recomendación:** tener la base cargada en **ambos** y llevar el entorno local como respaldo. Antes de la
calificación, ejecutar `scripts/consulta_atleta.sh "Usain Bolt"` en cada uno para confirmar que responden.
