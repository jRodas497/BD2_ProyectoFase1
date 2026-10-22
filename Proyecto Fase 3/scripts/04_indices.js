// Fase 3 — paso 4: índices. Ejecución: scripts/ejecutar.sh js 04_indices.js
// Cada índice responde a un patrón de las consultas del proyecto (ver docs/modelo-mongodb.md §4).
const p2 = (n) => String(n).padStart(2, "0");
const ahora = () => { const d = new Date(); return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}`; };
print(`[${ahora()}] Creando índices en "${db.getName()}"`);

const indices = [
  // consulta por atleta: buscar por nombre y luego sus participaciones (multikey sobre el arreglo embebido)
  ["atletas", { nombre_normalizado: 1 }, {}],
  ["atletas", { "resumen.total_medallas": -1 }, {}],
  ["participaciones", { "atletas._id": 1, "edicion.anio": 1 }, {}],
  // consulta por país: participaciones y medallero por comité (NOC) y año
  // cubriente: contiene todos los campos que usa el resumen (año, temporada, deporte, medalla), así que la consulta
  // se resuelve leyendo solo el índice, sin tocar los documentos
  ["participaciones", { "noc.codigo": 1, "edicion.anio": 1, "edicion.temporada": 1, "deporte.nombre": 1, medalla: 1 }, { name: "cubre_resumen_pais" }],
  ["participaciones", { "pais._id": 1, medalla_orden: 1 }, {}],
  // filtros opcionales de ambas consultas
  ["participaciones", { "deporte.nombre": 1, "edicion.anio": 1 }, {}],
  ["participaciones", { "edicion._id": 1 }, {}],
  ["participaciones", { evento_edicion_id: 1 }, {}],
  // solo las participaciones con medalla (parcial: ocupa mucho menos espacio)
  ["participaciones", { medalla_orden: 1, "noc.codigo": 1 }, { partialFilterExpression: { medalla_orden: { $exists: true } } }],
  ["comites", { nombre_comite: 1 }, {}],
  ["comites", { pais_id: 1 }, {}],
  ["comites", { pais: 1 }, {}],
  ["paises", { nombre: 1 }, { unique: true }],
  ["paises", { nombre_es: 1 }, {}],
  ["paises", { "nocs.codigo": 1 }, {}],
  ["ediciones", { anio: 1, temporada: 1 }, { unique: true }],
  ["eventos", { nombre: 1 }, {}],
  ["eventos", { "deporte.nombre": 1, "disciplina.nombre": 1 }, {}],
];

// versión anterior de este índice (solo noc + año): el cubriente lo reemplaza
try { db.participaciones.dropIndex("noc.codigo_1_edicion.anio_1"); print("  (índice anterior noc.codigo_1_edicion.anio_1 eliminado: lo reemplaza cubre_resumen_pais)"); } catch (e) { /* no existía */ }

for (const [col, clave, opts] of indices) {
  const t0 = Date.now();
  const nombre = db.getCollection(col).createIndex(clave, opts);
  print(`  ${col}.${nombre}  (${Date.now() - t0} ms)`);
}
print(`[${ahora()}] Índices listos`);
for (const c of db.getCollectionNames().sort()) {
  print(`  ${c}: ${db.getCollection(c).getIndexes().length} índices (incluye _id)`);
}
