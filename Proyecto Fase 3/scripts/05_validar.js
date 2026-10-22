// Fase 3 — paso 5: validación de la carga. Ejecución: scripts/ejecutar.sh js 05_validar.js
// Compara conteos con lo esperado, revisa integridad y contrasta medalleros conocidos.
const p2 = (n) => String(n).padStart(2, "0");
const ahora = () => { const d = new Date(); return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}`; };
let fallos = 0;
const ok = (cond, msg) => { print(`  ${cond ? "[OK]   " : "[FALLA]"} ${msg}`); if (!cond) fallos++; };
print(`[${ahora()}] VALIDACIÓN de "${db.getName()}"`);

print("\n1. Conteos (esperados: Fase 1 + correcciones de docs/reporte-correcciones.md)");
const esperado = { comites: 236, paises: 205, ediciones: 63, eventos: 1761, atletas: 239678, participaciones: 221204 };
for (const [c, n] of Object.entries(esperado)) ok(db.getCollection(c).countDocuments() === n, `${c}: ${db.getCollection(c).countDocuments()} (esperado ${n})`);

print("\n2. Integridad");
ok(db.participaciones.countDocuments({ atletas: { $size: 0 } }) === 0, "toda participación tiene al menos un atleta");
const huerfanos = db.participaciones.aggregate([
  { $unwind: "$atletas" }, { $project: { id: "$atletas._id" } },
  { $lookup: { from: "atletas", localField: "id", foreignField: "_id", as: "a" } },
  { $match: { a: { $size: 0 } } }, { $count: "n" }]).toArray();
ok(huerfanos.length === 0, "todo atleta embebido en participaciones existe en la colección atletas");
const indivVarios = db.participaciones.countDocuments({ es_por_equipos: false, "atletas.1": { $exists: true } });
ok(indivVarios === 0, `ninguna participación individual tiene más de un atleta (${indivVarios})`);
const sinNoc = db.participaciones.aggregate([
  { $lookup: { from: "comites", localField: "noc.codigo", foreignField: "_id", as: "c" } },
  { $match: { c: { $size: 0 } } }, { $count: "n" }]).toArray();
ok(sinNoc.length === 0, "todo NOC de participaciones existe en comites");
const sinEdicion = db.participaciones.aggregate([
  { $lookup: { from: "ediciones", localField: "edicion._id", foreignField: "_id", as: "e" } },
  { $match: { e: { $size: 0 } } }, { $count: "n" }]).toArray();
ok(sinEdicion.length === 0, "toda edición de participaciones existe en ediciones");

print("\n3. Medalleros (una medalla de equipo cuenta UNA vez, no una por atleta)");
const medallero = (filtro) => {
  const r = {};
  db.participaciones.aggregate([{ $match: { medalla: { $exists: true }, ...filtro } },
    { $group: { _id: "$medalla", n: { $sum: 1 } } }]).forEach((x) => (r[x._id] = x.n));
  return [r.Oro || 0, r.Plata || 0, r.Bronce || 0];
};
const fr24 = medallero({ "noc.codigo": "FRA", "edicion.anio": 2024 });
ok(fr24.join("/") === "16/26/22", `Francia 2024 = ${fr24.join("/")} (oficial 16/26/22)`);
const gt = medallero({ "noc.codigo": "GUA" });
ok(gt.join("/") === "1/1/1", `Guatemala = ${gt.join("/")} (oficial 1/1/1)`);
const phelps = db.atletas.findOne({ nombre_normalizado: "michael phelps" });
ok(phelps && phelps.resumen.oro === 23 && phelps.resumen.plata === 3 && phelps.resumen.bronce === 2,
   `Michael Phelps = ${phelps.resumen.oro}/${phelps.resumen.plata}/${phelps.resumen.bronce} (23/3/2)`);
const bolt = db.atletas.findOne({ nombre_normalizado: "usain bolt" });
ok(bolt && bolt.resumen.oro === 8, `Usain Bolt = ${bolt.resumen.oro} oros (8)`);
const rugby = db.participaciones.countDocuments({ "noc.codigo": "FRA", "edicion.anio": 2024, "deporte.nombre": /Rugby/, medalla: "Oro" });
ok(rugby === 1, `Rugby Sevens Francia 2024: ${rugby} oro (el equipo cuenta 1 vez; en Fase 1 contaba 13)`);

print("\n4. Correcciones respecto a Fase 1");
const maraton = db.eventos.findOne({ nombre: "Marathon", categoria_sexo: "M" });
ok(maraton && maraton.es_por_equipos === false, "Maratón masculino es individual (en Fase 1 figuraba por equipos)");
const frg = db.comites.findOne({ _id: "FRG" });
ok(frg.es_historico === true && frg.nombre_comite === "West Germany", "FRG: histórico y nombre 'West Germany'");

print("\n5. Tamaños");
for (const c of db.getCollectionNames().sort()) {
  const s = db.getCollection(c).stats();
  print(`  ${c.padEnd(16)} ${String(s.count).padStart(8)} docs   datos ${(s.size / 1048576).toFixed(1)} MB   índices ${(s.totalIndexSize / 1048576).toFixed(1)} MB`);
}
print(`\n[${ahora()}] VALIDACIÓN ${fallos === 0 ? "COMPLETA: todo en orden" : "CON " + fallos + " FALLA(S)"}`);
