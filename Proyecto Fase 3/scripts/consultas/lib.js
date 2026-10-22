// Utilidades compartidas por las consultas (se cargan con load("/scripts/consultas/lib.js")).
const p2 = (n) => String(n).padStart(2, "0");
const ahora = () => { const d = new Date(); return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}`; };
const env = (k) => { const v = process.env[k]; return v && v.trim() !== "" ? v.trim() : null; };
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
// recorta a n-1 y rellena a n: así una columna larga nunca se pega con la siguiente
const pad = (v, n) => String(v ?? "").slice(0, n - 1).padEnd(n);
const lpad = (v, n) => String(v ?? "").padStart(n);
const fmtFecha = (d) => (d ? d.toISOString().slice(0, 10) : null);

// minúsculas, sin acentos, solo letras/números/espacios (igual que atletas.nombre_normalizado)
const normalizar = (s) => s.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

// Expresión regular tolerante a acentos para buscar nombres de país/comité
const reTolerante = (t) => new RegExp(esc(t).replace(/[aáàä]/gi, "[aáàä]").replace(/[eéèë]/gi, "[eéèë]").replace(/[iíìï]/gi, "[iíìï]")
  .replace(/[oóòö]/gi, "[oóòö]").replace(/[uúùü]/gi, "[uúùü]"), "i");

// Resuelve un texto de país a comités (NOC): acepta código ("USA"), nombre del país en inglés/español o nombre del
// comité ("Soviet Union"). UN SOLO viaje: $lookup trae el documento del país (con sus NOC y sus sedes).
function resolverComites(texto) {
  const t = texto.trim(), re = reTolerante(t);
  return db.comites.aggregate([
    { $match: { $or: [{ _id: t.toUpperCase() }, { nombre_comite: re }, { pais: re }, { pais_es: re }] } },
    { $lookup: { from: "paises", localField: "pais_id", foreignField: "_id", as: "pais_doc" } },
    { $addFields: { pais_doc: { $first: "$pais_doc" } } },
  ]).toArray();
}

// Filtro común (deporte, año, temporada, medalla) sobre participaciones
function filtroParticipaciones() {
  const f = {};
  const deporte = env("DEPORTE");
  if (deporte) { const re = new RegExp(esc(deporte), "i"); f.$or = [{ "deporte.nombre": re }, { "disciplina.nombre": re }]; }
  if (env("ANIO")) f["edicion.anio"] = parseInt(env("ANIO"), 10);
  if (env("TEMPORADA")) f["edicion.temporada"] = new RegExp("^" + esc(env("TEMPORADA").slice(0, 3)), "i");
  if (env("MEDALLA")) f.medalla = new RegExp("^" + esc(env("MEDALLA")) + "$", "i");
  return f;
}
const descFiltros = () => ["DEPORTE", "PAIS", "ANIO", "TEMPORADA", "MEDALLA"].filter(env).map((k) => `${k.toLowerCase()}=${env(k)}`).join(", ");
const cuentaMedallas = (docs) => {
  const m = { Oro: 0, Plata: 0, Bronce: 0 };
  docs.forEach((d) => { if (d.medalla) m[d.medalla]++; });
  return m;
};

// "Aquatics / Swimming" cuando la disciplina difiere del deporte
const etiquetaDeporte = (p) => (p.deporte.nombre === p.disciplina.nombre ? p.deporte.nombre : `${p.deporte.nombre} / ${p.disciplina.nombre}`);

// Proyección "liviana" para listar participaciones: no trae la lista completa de atletas (en equipos puede tener
// decenas de nombres), solo cuántos son y los primeros 3. Menos datos por la red = respuesta más rápida.
const PROY_LISTA = { edicion: 1, deporte: 1, disciplina: 1, evento: 1, noc: 1, puesto_texto: 1, medalla: 1, es_por_equipos: 1, nombre_equipo: 1,
  n_atl: { $size: "$atletas" }, nombres: { $slice: [{ $map: { input: "$atletas", as: "a", in: "$$a.nombre" } }, 3] } };
const ordenMedalla = { $ifNull: ["$medalla_orden", 9] };   // sin medalla ordena al final (en MongoDB los faltantes ordenan primero)

// Ejecuta varias consultas independientes: en paralelo (otra conexión por cada una) o una tras otra.
// PARALELO=0 las serializa. Cada proceso de mongosh arranca con UNA conexión; abrir más (handshake TLS) cuesta
// varios viajes en un servidor remoto, así que el paralelismo solo conviene si cada consulta es larga.
const lote = async (fns) => (env("PARALELO") === "0" ? (async () => { const r = []; for (const f of fns) r.push(await f()); return r; })() : Promise.all(fns.map((f) => f())));
