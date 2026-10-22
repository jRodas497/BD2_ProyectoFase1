// Fase 3 — paso 2: crea las colecciones de MongoDB con validación de esquema ($jsonSchema).
// Ejecución: scripts/ejecutar.sh js 02_crear_colecciones.js      (o dentro de mongosh: load("/scripts/02_crear_colecciones.js"))
//
// Modelo (ver docs/modelo-mongodb.md):
//   comites         catálogo NOC (incluye comités disueltos y los que no tienen país)
//   paises          país + sus NOC + años en que fue sede
//   ediciones       cada edición de los Juegos, con sus ciudades sede
//   eventos         catálogo deporte → disciplina → evento
//   atletas         biografía + resumen de medallas + trazabilidad de fuentes
//   participaciones UNA entrada a un evento (equipo = 1 documento con varios atletas embebidos)

const p2 = (n) => String(n).padStart(2, "0");
const ahora = () => { const d = new Date(); return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}`; };
print(`[${ahora()}] Creando colecciones en la base "${db.getName()}"`);

const entero = { bsonType: ["int", "long"] };
const texto = { bsonType: "string" };

const esquemas = {
  comites: {
    required: ["_id", "nombre_comite", "es_historico"],
    properties: { _id: texto, nombre_comite: texto, es_historico: { bsonType: "bool" }, pais_id: entero },
  },
  paises: {
    required: ["_id", "nombre", "nocs", "sedes"],
    properties: { _id: entero, nombre: texto, nocs: { bsonType: "array" }, sedes: { bsonType: "array" } },
  },
  ediciones: {
    required: ["_id", "anio", "temporada", "nombre"],
    properties: {
      _id: entero, anio: entero, temporada: { enum: ["Verano", "Invierno"] }, nombre: texto,
      sedes: { bsonType: "array" },
    },
  },
  eventos: {
    required: ["_id", "nombre", "es_por_equipos", "deporte", "disciplina"],
    properties: { _id: entero, nombre: texto, es_por_equipos: { bsonType: "bool" } },
  },
  atletas: {
    required: ["_id", "nombre_completo", "nombre_normalizado"],
    properties: {
      _id: entero, nombre_completo: texto, nombre_normalizado: texto,
      sexo: { enum: ["M", "F", "U"] }, fuentes: { bsonType: "array" },
    },
  },
  participaciones: {
    required: ["_id", "edicion", "deporte", "disciplina", "evento", "noc", "es_por_equipos", "atletas"],
    properties: {
      _id: entero,
      es_por_equipos: { bsonType: "bool" },
      medalla: { enum: ["Oro", "Plata", "Bronce", null] },
      atletas: { bsonType: "array", minItems: 1 },
    },
  },
};

for (const [nombre, esquema] of Object.entries(esquemas)) {
  db.getCollection(nombre).drop();
  db.createCollection(nombre, {
    validator: { $jsonSchema: { bsonType: "object", ...esquema } },
    validationLevel: "strict",
    validationAction: "error",
  });
  print(`  colección creada: ${nombre}`);
}
print(`[${ahora()}] Colecciones listas: ${db.getCollectionNames().sort().join(", ")}`);
