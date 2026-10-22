// Consultas libres de ejemplo para la calificación. Cada bloque funciona solo y se puede copiar y pegar en mongosh
// (scripts/ejecutar.sh shell). Para correr todos:  scripts/ejecutar.sh js consultas/ejemplos.js
const titulo = (t) => print("\n### " + t);

titulo("1. Top 5 atletas con más medallas (resumen precalculado)");
db.atletas.find({}, { nombre_completo: 1, "resumen.oro": 1, "resumen.plata": 1, "resumen.bronce": 1, "resumen.total_medallas": 1, _id: 0 })
  .sort({ "resumen.total_medallas": -1 }).limit(5).forEach((a) => print(`  ${a.nombre_completo}: ${a.resumen.oro}/${a.resumen.plata}/${a.resumen.bronce} (total ${a.resumen.total_medallas})`));

titulo("2. Medallero de una edición: 5 primeros comités en 2024 (una medalla de equipo cuenta una vez)");
db.participaciones.aggregate([
  { $match: { "edicion.anio": 2024, medalla: { $exists: true } } },
  { $group: { _id: "$noc.codigo", oro: { $sum: { $cond: [{ $eq: ["$medalla", "Oro"] }, 1, 0] } },
      plata: { $sum: { $cond: [{ $eq: ["$medalla", "Plata"] }, 1, 0] } }, bronce: { $sum: { $cond: [{ $eq: ["$medalla", "Bronce"] }, 1, 0] } } } },
  { $sort: { oro: -1, plata: -1, bronce: -1 } }, { $limit: 5 }]).forEach((x) => print(`  ${x._id}: ${x.oro}/${x.plata}/${x.bronce}`));

titulo("3. Países que han sido sede más de una vez de los Juegos de Verano");
db.paises.find({ "sedes.1": { $exists: true } }, { nombre: 1, sedes: 1 }).forEach((p) => {
  const v = p.sedes.filter((s) => s.temporada === "Verano" && !s.cancelada);
  if (v.length > 1) print(`  ${p.nombre}: ${v.map((s) => s.anio + " " + s.ciudad).join(", ")}`);
});

titulo("4. Medallistas de oro de Guatemala (nombre, año, evento)");
db.participaciones.aggregate([{ $match: { "noc.codigo": "GUA", medalla: "Oro" } }, { $unwind: "$atletas" },
  { $project: { _id: 0, atleta: "$atletas.nombre", anio: "$edicion.anio", evento: "$evento.nombre", deporte: "$deporte.nombre" } }]).forEach((x) => print(`  ${x.atleta} — ${x.anio} ${x.deporte} ${x.evento}`));

titulo("5. Cuántos atletas distintos participaron en Tokio 2020 (Verano)");
printjson(db.participaciones.aggregate([{ $match: { "edicion.anio": 2020, "edicion.temporada": "Verano" } }, { $unwind: "$atletas" },
  { $group: { _id: "$atletas._id" } }, { $count: "atletas_distintos" }]).toArray());

titulo("6. Medallas de un atleta por deporte (Michael Phelps, id 93860)");
db.participaciones.aggregate([{ $match: { "atletas._id": 93860, medalla: { $exists: true } } },
  { $group: { _id: { deporte: "$disciplina.nombre", medalla: "$medalla" }, n: { $sum: 1 } } }, { $sort: { n: -1 } }]).forEach((x) => print(`  ${x._id.deporte} ${x._id.medalla}: ${x.n}`));

titulo("7. Oros por edición de un atleta (Usain Bolt, id 105512)");
db.participaciones.aggregate([{ $match: { "atletas._id": 105512, medalla: "Oro" } },
  { $group: { _id: "$edicion.anio", oros: { $sum: 1 } } }, { $sort: { _id: 1 } }]).forEach((x) => print(`  ${x._id}: ${x.oros} oros`));

titulo("8. Eventos individuales vs por equipos (corrección de la Fase 3)");
db.eventos.aggregate([{ $group: { _id: "$es_por_equipos", eventos: { $sum: 1 } } }]).forEach((x) => print(`  ${x._id ? "por equipos" : "individuales"}: ${x.eventos}`));
