// Consulta (c): información de un atleta por nombre.
// Parámetros (variables de entorno; use scripts/consulta_atleta.sh):
//   NOMBRE (obligatorio)  nombre o parte del nombre, sin importar acentos/mayúsculas/orden de palabras
//   DEPORTE, PAIS, ANIO, TEMPORADA, MEDALLA   filtros opcionales
//   LIMITE   máximo de atletas a detallar cuando el nombre coincide con varios (por defecto 10)
//
// Dos viajes a la base: 1) candidatos por nombre (con el país, en paralelo, si hay filtro de país)
// 2) participaciones de TODOS los atletas elegidos a la vez (no una consulta por atleta).
load("/scripts/consultas/lib.js");

(async () => {
  const t0 = Date.now();
  const nombre = env("NOMBRE");
  if (!nombre) { print("Falta el parámetro NOMBRE"); return; }
  const limite = parseInt(env("LIMITE") || "10", 10);

  // 1) atletas cuyo nombre contiene TODAS las palabras buscadas (sin sus datos pesados) y, si se pide, el país
  const tokens = normalizar(nombre).split(" ").filter(Boolean);
  const buscarCandidatos = () => db.atletas.aggregate([
    { $match: { $and: tokens.map((t) => ({ nombre_normalizado: { $regex: t } })) } },
    // las fuentes viajan como textos cortos ("F1:105512"), no como documentos completos
    { $addFields: { fuentes_txt: { $map: { input: "$fuentes", as: "f", in: { $concat: ["F", { $toString: "$$f.fuente_id" }, ":", "$$f.id_en_fuente"] } } } } },
    { $project: { fuentes: 0 } }]).toArray();
  const [candidatos, comitesPais] = env("PAIS")
    ? await lote([buscarCandidatos, () => resolverComites(env("PAIS"))])
    : [await buscarCandidatos(), null];
  const exacto = normalizar(nombre);
  candidatos.sort((a, b) =>
    (b.nombre_normalizado === exacto) - (a.nombre_normalizado === exacto) ||
    ((b.resumen?.total_medallas ?? 0) - (a.resumen?.total_medallas ?? 0)) ||
    ((b.resumen?.participaciones ?? 0) - (a.resumen?.participaciones ?? 0)));

  print(`[${ahora()}] CONSULTA POR ATLETA: "${nombre}"${descFiltros() ? "  | filtros: " + descFiltros() : ""}`);
  print(`Atletas que coinciden: ${candidatos.length}`);
  if (candidatos.length === 0) { print("No se encontró ningún atleta con ese nombre."); return; }

  // 2) filtros sobre participaciones
  const filtro = filtroParticipaciones();
  if (comitesPais) {
    if (comitesPais.length === 0) { print(`No se reconoce el país "${env("PAIS")}".`); return; }
    filtro["noc.codigo"] = { $in: comitesPais.map((c) => c._id) };
  }
  const hayFiltros = !!descFiltros();

  // Con filtros solo se detallan atletas con resultados (se revisan todos los candidatos, hasta 2 000, en una sola
  // consulta); sin filtros, los primeros LIMITE.
  const consultados = candidatos.slice(0, hayFiltros ? 2000 : limite);
  const ids = consultados.map((a) => a._id);
  const partsTodas = await db.participaciones.aggregate([{ $match: { "atletas._id": { $in: ids }, ...filtro } },
    { $addFields: { ids: "$atletas._id" } },
    { $sort: { "edicion.anio": 1, "deporte.nombre": 1, _id: 1 } },
    { $project: { ...PROY_LISTA, ids: 1 } }]).toArray();
  const partsPorAtleta = new Map(ids.map((i) => [i, []]));
  for (const p of partsTodas) for (const i of p.ids) if (partsPorAtleta.has(i)) partsPorAtleta.get(i).push(p);

  let mostrados = 0;
  const omitidos = candidatos.slice(consultados.length);
  for (const a of consultados) {
    const parts = partsPorAtleta.get(a._id);
    if (parts.length === 0 && hayFiltros) { omitidos.push(a); continue; }   // con filtros solo se muestran atletas con resultados
    if (mostrados >= limite) { omitidos.push(a); continue; }
    mostrados++;

    const r = a.resumen || {};
    const nac = a.nacimiento || {};
    print("\n" + "=".repeat(100));
    print(`ATLETA: ${a.nombre_completo}${a.nombre_usado ? ` (usa: ${a.nombre_usado})` : ""}   [id ${a._id}]`);
    print("=".repeat(100));
    print(`Sexo: ${a.sexo ?? "?"}  |  Nacimiento: ${fmtFecha(a.fecha_nacimiento) ?? "s/d"}${nac.ciudad ? ", " + nac.ciudad : ""}${nac.region ? ", " + nac.region : ""}${nac.pais ? ", " + nac.pais : ""}`);
    if (a.fecha_defuncion) print(`Defunción: ${fmtFecha(a.fecha_defuncion)}`);
    print(`Estatura: ${a.estatura_cm ? a.estatura_cm + " cm" : "s/d"}  |  Peso: ${a.peso_kg ? a.peso_kg + " kg" : "s/d"}`);
    print(`Trayectoria: ${r.participaciones ?? 0} participaciones, ${r.primer_anio ?? "?"}–${r.ultimo_anio ?? "?"}, deportes: ${(r.deportes || []).join(", ")}`);
    print(`MEDALLAS (carrera): Oro ${r.oro ?? 0} | Plata ${r.plata ?? 0} | Bronce ${r.bronce ?? 0} | Total ${r.total_medallas ?? 0}`);
    if (hayFiltros) {
      const m = cuentaMedallas(parts);
      print(`MEDALLAS (con los filtros): Oro ${m.Oro} | Plata ${m.Plata} | Bronce ${m.Bronce} | Total ${m.Oro + m.Plata + m.Bronce}`);
    }
    print(`\nPARTICIPACIONES${hayFiltros ? " (filtradas)" : ""}: ${parts.length}`);
    print(`${pad("AÑO", 5)}${pad("TEMPORADA", 10)}${pad("DEPORTE", 32)}${pad("EVENTO", 36)}${pad("NOC", 5)}${pad("PUESTO", 8)}${pad("MEDALLA", 8)}EQUIPO`);
    print("-".repeat(112));
    for (const p of parts) {
      const eq = p.es_por_equipos ? `${p.nombre_equipo ? p.nombre_equipo + " " : ""}(${p.n_atl} integrantes)` : "";
      print(`${pad(p.edicion.anio, 5)}${pad(p.edicion.temporada, 10)}${pad(etiquetaDeporte(p), 32)}${pad(p.evento.nombre + (p.evento.categoria_sexo ? " " + p.evento.categoria_sexo : ""), 36)}${pad(p.noc.codigo, 5)}${pad(p.puesto_texto ?? "-", 8)}${pad(p.medalla ?? "-", 8)}${eq}`);
    }
    if (a.fuentes_txt?.length) print(`\nFuentes: ${a.fuentes_txt.join(", ")}`);
  }
  if (omitidos.length) {
    print(`\n${omitidos.length} atleta(s) más coinciden con "${nombre}"${hayFiltros ? " (sin resultados para los filtros, o fuera del límite)" : ""}: `
      + omitidos.slice(0, 15).map((a) => a.nombre_completo).join("; ") + (omitidos.length > 15 ? "; ..." : ""));
    print("Sea más específico (nombre completo) o suba LIMITE para detallarlos.");
  }
  print(`\n[${ahora()}] Consulta resuelta en ${Date.now() - t0} ms`);
})().catch((e) => { print("ERROR en la consulta: " + e.message); });
