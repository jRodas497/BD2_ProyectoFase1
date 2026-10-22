// Plantillas para preguntas nuevas el día de la calificación. Cada bloque responde un TIPO de pregunta; basta cambiar
// los valores marcados. Para correr todos:  scripts/ejecutar.sh js consultas/plantillas.js
// O copiar un bloque dentro de mongosh:      scripts/ejecutar.sh shell
const t = (s) => print("\n### " + s);

t("A. ¿Quién ganó el oro/plata/bronce en [evento] de [año]?   (100 metres masculino, Verano 2012)");
db.participaciones.find({ "edicion.anio": 2012, "edicion.temporada": "Verano", "evento.nombre": "100 metres", "evento.categoria_sexo": "M", medalla: { $exists: true } })
  .sort({ medalla_orden: 1 }).forEach((p) => print(`  ${p.medalla}: ${p.atletas.map((a) => a.nombre).join(", ")} (${p.noc.codigo})`));

t("B. ¿Cuántas participaciones tuvo [país] en [deporte]?   (GUA, Athletics)");
print("  " + db.participaciones.countDocuments({ "noc.codigo": "GUA", "deporte.nombre": "Athletics" }));

t("C. ¿Qué atletas de [país] ganaron medalla?   (GUA; nombre, medalla, año)");
db.participaciones.aggregate([{ $match: { "noc.codigo": "GUA", medalla: { $exists: true } } }, { $unwind: "$atletas" },
  { $sort: { "edicion.anio": 1 } }, { $project: { _id: 0, n: "$atletas.nombre", m: "$medalla", a: "$edicion.anio", e: "$evento.nombre" } }])
  .forEach((x) => print(`  ${x.n} — ${x.m} ${x.a} (${x.e})`));

t("D. Los [N] países con más medallas de oro en la historia   (top 5 por comité)");
db.participaciones.aggregate([{ $match: { medalla: "Oro" } }, { $group: { _id: "$noc.codigo", oros: { $sum: 1 } } }, { $sort: { oros: -1 } }, { $limit: 5 }])
  .forEach((x) => print(`  ${x._id}: ${x.oros}`));

t("E. ¿Dónde y cuándo se hicieron los Juegos de [año]?   (2016 Verano)");
printjson(db.ediciones.findOne({ anio: 2016, temporada: "Verano" }, { _id: 0, nombre: 1, sedes: 1 }));

t("F. Atletas con una característica física   (los 3 más altos; nacidos en Guatemala)");
db.atletas.find({ estatura_cm: { $exists: true } }, { nombre_completo: 1, estatura_cm: 1, _id: 0 }).sort({ estatura_cm: -1 }).limit(3).forEach((a) => print(`  ${a.nombre_completo}: ${a.estatura_cm} cm`));
print("  nacidos en Guatemala: " + db.atletas.countDocuments({ "nacimiento.pais": "Guatemala" }));

t("G. ¿Cuántos atletas distintos tiene [país]?   (GUA)");
printjson(db.participaciones.aggregate([{ $match: { "noc.codigo": "GUA" } }, { $unwind: "$atletas" }, { $group: { _id: "$atletas._id" } }, { $count: "atletas" }]).toArray());

t("H. Medallas de [país] en un año, desglosadas por deporte   (FRA 2024)");
db.participaciones.aggregate([{ $match: { "noc.codigo": "FRA", "edicion.anio": 2024, medalla: { $exists: true } } },
  { $group: { _id: "$deporte.nombre", total: { $sum: 1 } } }, { $sort: { total: -1 } }, { $limit: 5 }]).forEach((x) => print(`  ${x._id}: ${x.total}`));

t("I. Un evento concreto a lo largo de los años   (oros del maratón masculino)");
db.participaciones.aggregate([{ $match: { "evento.nombre": "Marathon", "evento.categoria_sexo": "M", medalla: "Oro" } }, { $sort: { "edicion.anio": 1 } },
  { $project: { _id: 0, a: "$edicion.anio", n: { $arrayElemAt: ["$atletas.nombre", 0] }, c: "$noc.codigo" } }, { $limit: 5 }]).forEach((x) => print(`  ${x.a}: ${x.n} (${x.c})`));

t("J. Equipos: integrantes de un equipo medallista   (Rugby Sevens Francia 2024)");
const eq = db.participaciones.findOne({ "noc.codigo": "FRA", "edicion.anio": 2024, "disciplina.nombre": "Rugby Sevens", medalla: "Oro" });
print(`  ${eq.nombre_equipo}, ${eq.atletas.length} integrantes: ${eq.atletas.slice(0, 5).map((a) => a.nombre).join(", ")}...`);
