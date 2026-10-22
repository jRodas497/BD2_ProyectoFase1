# Modelo de documentos en MongoDB — justificación

**Fase 3 · Sistemas de Bases de Datos 2 · USAC · 2do. semestre 2026**

En MongoDB no se modela por entidades normalizadas sino **por las consultas que hay que responder**. El
proyecto pide dos: la información completa de un **atleta** y la información completa de un **país**. Este
documento explica por qué las 15 tablas de la Fase 1 quedaron en 6 colecciones y qué se embebe o se referencia.

---

## 1. De 15 tablas a 6 colecciones

| Fase 1 (PostgreSQL) | Fase 3 (MongoDB) | Cómo quedó |
|---|---|---|
| `participacion` + `participacion_atleta` + `evento_edicion` + `evento` + `disciplina` + `deporte` + `edicion` + `noc` + `medalla` | **`participaciones`** | un documento por *entrada a un evento*, con edición, deporte, disciplina, evento, NOC y medalla **embebidos**, y sus atletas embebidos |
| `atleta` + `atleta_fuente` | **`atletas`** | biografía + resumen de medallas + trazabilidad de fuentes embebida |
| `pais` + `noc` + `sede` + `ciudad` | **`paises`** y **`comites`** | `paises` embebe sus NOC y los años en que fue sede; `comites` es el catálogo de NOC (incluye los que no tienen país) |
| `edicion` + `sede` + `ciudad` | **`ediciones`** | con sus ciudades sede embebidas |
| `deporte` + `disciplina` + `evento` | **`eventos`** | catálogo; deporte y disciplina embebidos |
| `fuente` | embebida en `atletas.fuentes` | |
| `medalla` | valor `"Oro"/"Plata"/"Bronce"` + `medalla_orden` en `participaciones` | |

## 2. Decisión central: el grano de `participaciones`

Se conserva el grano de la Fase 1: **un documento por entrada a un evento**, no por atleta. Un equipo es **un
documento** con su arreglo `atletas` embebido.

```javascript
{ _id: 208794, edicion: {_id: 63, anio: 2024, temporada: "Verano", nombre: "2024 Verano"},
  deporte: {_id: 43, nombre: "Rugby"}, disciplina: {_id: 65, nombre: "Rugby Sevens"},
  evento: {_id: 1632, nombre: "Men", categoria_sexo: "M"},
  noc: {codigo: "FRA", nombre_comite: "France", es_historico: false}, pais: {_id: 64, nombre: "France"},
  medalla: "Oro", medalla_orden: 1, nombre_equipo: "France", es_por_equipos: true,
  atletas: [ {_id: 133886, nombre: "Stephen Parez"}, {_id: 238163, nombre: "Pascal Barraque"}, ... ] }
```

**Por qué.** Si el documento fuese por atleta, el oro de un equipo de 12 jugadores sumaría 12 medallas al país.
Con este grano el medallero de un país es un simple `count` de documentos con medalla (Francia 2024 = 16/26/22,
igual al oficial; Rugby Sevens cuenta 1 oro y no 13). El arreglo `atletas` es pequeño (promedio 1.4; un equipo, 4.4 en
promedio y hasta 64 en el caso más grande), por lo que embeberlo no se acerca al límite de 16 MB por documento.

## 3. Embeber o referenciar

| Dato | Decisión | Razón |
|---|---|---|
| Edición, deporte, disciplina, evento y NOC dentro de `participaciones` | **Embebido (desnormalizado)** | se leen siempre junto a la participación y casi no cambian; evita `$lookup` en las dos consultas |
| Atletas de una participación | **Embebido** (`_id` + nombre) | mostrar los integrantes de un equipo sin otra consulta; el `_id` permite abrir el atleta |
| Participaciones de un atleta | **Referenciado** (se buscan por `atletas._id`) | un atleta puede tener decenas; cargarlas dentro de `atletas` duplicaría cada participación de equipo |
| Resumen de medallas del atleta | **Precalculado** en `atletas.resumen` | dato de lectura frecuente; se calcula una vez al cargar |
| NOC de un país | **Embebido** en `paises.nocs` | pocos por país (Alemania: 4) |
| Años en que fue sede | **Embebido** en `paises.sedes` | responde "¿ha sido sede?" con una lectura |
| Fuentes de un atleta | **Embebido** (`atletas.fuentes`) | trazabilidad que solo se consulta junto al atleta |

La desnormalización tiene un costo conocido: si cambiara el nombre de un deporte habría que actualizarlo en
todas las participaciones. Aquí los catálogos son históricos y fijos, así que se acepta a cambio de lecturas
de un solo paso.

## 4. Índices y consultas

| Consulta | Operación | Índice |
|---|---|---|
| (c) buscar atleta por nombre | `atletas.find({nombre_normalizado: /palabra/ ...})` (todas las palabras, sin acentos) | `nombre_normalizado` |
| (c) participaciones del atleta | `participaciones.find({"atletas._id": id, ...filtros})` | `{atletas._id, edicion.anio}` (multikey) |
| (d) resolver el país | `comites.find({$or: [_id, nombre_comite, pais, pais_es]})` | índices de `comites` |
| (d) participaciones y medallero | `participaciones.aggregate([{$match: {"noc.codigo": {$in: [...]}}}, {$group: ...}])` | `{noc.codigo, edicion.anio, edicion.temporada, deporte.nombre, medalla}` (**cubriente**: se resuelve solo con el índice) |
| (d) sedes | `paises.findOne({_id})` → `sedes[]` | `_id` |
| filtros de deporte / año | sobre `participaciones` | `{deporte.nombre, edicion.anio}`, `{edicion.anio}` |

Comprobado con `explain("executionStats")`: la búsqueda por atleta y año examina 3 claves y 3 documentos para
devolver 3; la de Guatemala examina 390 y devuelve 390.

## 5. Búsqueda de nombres

`atletas.nombre_normalizado` guarda el nombre en minúsculas y sin acentos (ya venía así de la Fase 1). La consulta
normaliza el texto igual y exige que aparezcan **todas** las palabras, en cualquier orden. Así `"Nadia Comaneci"`
encuentra *Nadia Comăneci* y `"bolt usain"` encuentra *Usain Bolt*. Es un recorrido de las claves del índice
(≈ 120 ms para 239 678 atletas); un índice de texto no mejora la búsqueda parcial de subcadenas.

## 6. Validación de esquema

Cada colección tiene un validador `$jsonSchema` estricto (campos obligatorios, tipos, valores permitidos como
`temporada ∈ {Verano, Invierno}` o `medalla ∈ {Oro, Plata, Bronce}`). Un documento inválido es rechazado con el
error 121 *Document failed validation*. Los campos vacíos no se guardan: no hay `null` ni cadenas vacías.

## 7. Qué cambió respecto a la Fase 1

Las correcciones de datos (participaciones individuales fundidas, banderas de equipo, comités disueltos, nombres
de NOC) están descritas en `reporte-correcciones.md`. El resultado más visible: 221 204 participaciones en lugar de
212 376, y eventos como el maratón o los 100 m ya figuran como individuales.

## 8. Limitaciones conocidas

- Los resultados de París 2024 (fuente F3) no tienen `puesto`; solo medalla.
- La base relacional de la Fase 1 **no se modificó**: las correcciones viven en MongoDB (y en `datos/corregidos/`).
- Una participación que solo llegó a la clasificatoria puede no tener la medalla del equipo (p. ej. el relevo 4×100 de
  Jamaica en 2008, que figura sin medalla).
- Alemania se reparte entre GER, FRG, GDR y SAA: la consulta por país los reúne y muestra el desglose.
