// Consulta (d): información de un país.
// Parámetros (variables de entorno; use scripts/consulta_pais.sh):
//   PAIS (obligatorio)   nombre (inglés o español), código NOC o nombre de comité ("Soviet Union")
//   ANIO, TEMPORADA, DEPORTE, MEDALLA   filtros opcionales
//   DETALLE=1            lista TODAS las participaciones (por defecto: solo medallas; con filtros: todas)
//
// Optimizada para pocos viajes a la base (en un cluster remoto cada viaje cuesta ~100 ms o más):
//   1 viaje   resolver el texto del país + traer sus NOC y sedes ($lookup)
//   1 viaje   (en paralelo) ─ participaciones por año/NOC            [índice cubriente: no lee documentos]
//                           ─ medallas por año/NOC/deporte/medalla   [índice cubriente]
//                           ─ atletas distintos (total y por año)
//                           ─ filas del detalle, ya recortadas (3 nombres + cuántos son)
load("/scripts/consultas/lib.js");

(async () => {
  const t0 = Date.now();
  const texto = env("PAIS");
  if (!texto) { print("Falta el parámetro PAIS"); return; }

  const comites = await resolverComites(texto);
  const filtrosTxt = descFiltros().replace(/pais=[^,]*,? ?/, "");
  print(`[${ahora()}] CONSULTA POR PAÍS: "${texto}"${filtrosTxt ? "  | filtros: " + filtrosTxt : ""}`);
  if (comites.length === 0) { print("No se reconoce ese país o comité."); return; }

  // Agrupar por país (los comités sin país —AIN, EOR, IOA...— quedan como grupos propios).
  // Del país se toman TODOS sus comités (p. ej. "Germany" → GER, FRG, GDR, SAA) aunque el texto solo coincida con uno.
  const grupos = new Map();
  for (const c of comites) {
    const k = c.pais_id ?? `NOC:${c._id}`;
    if (!grupos.has(k)) grupos.set(k, { pais_id: c.pais_id, nombre: c.pais ?? c.nombre_comite, nombre_es: c.pais_es, doc: c.pais_doc, comites: [] });
    grupos.get(k).comites.push(c);
  }
  for (const g of grupos.values()) {
    if (g.doc) g.comites = [...g.doc.nocs].sort((a, b) => (a.codigo < b.codigo ? -1 : 1)).map((n) => ({ _id: n.codigo, nombre_comite: n.nombre_comite, es_historico: n.es_historico }));
  }

  const filtroBase = filtroParticipaciones();
  const hayFiltros = Object.keys(filtroBase).length > 0;
  const detalle = env("DETALLE") === "1" || hayFiltros;
  const tope = parseInt(env("TOPE") || "150", 10);
  const MEDALLAS = ["Oro", "Plata", "Bronce"];

  for (const g of grupos.values()) {
    const codigos = g.comites.map((c) => c._id);
    const filtro = { "noc.codigo": { $in: codigos }, ...filtroBase };
    const conMedalla = { $and: [filtro, { medalla: { $in: MEDALLAS } }] };

    // --- los 4 cálculos independientes salen a la vez
    const [porAnioNoc, medallas, atl, filas] = await lote([
      // participaciones por año/temporada/NOC (solo usa campos del índice cubriente)
      () => db.participaciones.aggregate([{ $match: filtro },
        { $group: { _id: { a: "$edicion.anio", t: "$edicion.temporada", n: "$noc.codigo" }, p: { $sum: 1 } } }]).toArray(),
      // medallas por año/temporada/NOC/deporte/medalla
      () => db.participaciones.aggregate([{ $match: conMedalla },
        { $group: { _id: { a: "$edicion.anio", t: "$edicion.temporada", n: "$noc.codigo", d: "$deporte.nombre", m: "$medalla" }, c: { $sum: 1 } } }]).toArray(),
      // atletas distintos: por edición y en total
      () => db.participaciones.aggregate([{ $match: filtro },
        { $project: { a: "$edicion.anio", t: "$edicion.temporada", atl: "$atletas._id" } }, { $unwind: "$atl" },
        { $group: { _id: { a: "$a", t: "$t", x: "$atl" } } },
        { $facet: { porAnio: [{ $group: { _id: { a: "$_id.a", t: "$_id.t" }, n: { $sum: 1 } } }],
                    total: [{ $group: { _id: "$_id.x" } }, { $count: "n" }] } }]).toArray(),
      // filas del detalle (solo medallas, o todas con DETALLE/filtros), ya recortadas
      () => db.participaciones.aggregate([{ $match: detalle ? filtro : conMedalla },
        { $addFields: { o: ordenMedalla } }, { $sort: { "edicion.anio": 1, o: 1, "deporte.nombre": 1 } }, { $limit: tope + 1 },
        { $project: PROY_LISTA }]).toArray(),
    ]);

    print("\n" + "=".repeat(100));
    print(`PAÍS: ${g.nombre}${g.nombre_es && g.nombre_es !== g.nombre ? ` (${g.nombre_es})` : ""}`);
    print("=".repeat(100));
    print(`Comités (NOC): ${g.comites.map((c) => `${c._id} ${c.nombre_comite}${c.es_historico ? " [disuelto]" : ""}`).join("  |  ")}`);

    // ---- sede (el documento del país ya vino con el $lookup)
    const sedes = (g.doc?.sedes || []).filter((s) => !s.cancelada);
    print(sedes.length
      ? `Sede de los Juegos: SÍ — ${sedes.map((s) => `${s.anio} ${s.temporada} (${s.ciudad})`).join(", ")}`
      : "Sede de los Juegos: no ha sido sede");

    const total = porAnioNoc.reduce((s, x) => s + x.p, 0);
    if (total === 0) { print("\nSin participaciones para los filtros indicados."); continue; }

    // ---- acumular en memoria (son pocas filas: años × comités × deportes)
    const porAnio = new Map(), porComite = new Map(), porDep = new Map();
    const anio = (a, t) => { const k = `${a}|${t}`; if (!porAnio.has(k)) porAnio.set(k, { a, t, partic: 0, Oro: 0, Plata: 0, Bronce: 0, atletas: 0 }); return porAnio.get(k); };
    const comite = (n) => { if (!porComite.has(n)) porComite.set(n, { n, partic: 0, Oro: 0, Plata: 0, Bronce: 0 }); return porComite.get(n); };
    for (const x of porAnioNoc) { anio(x._id.a, x._id.t).partic += x.p; comite(x._id.n).partic += x.p; }
    let oro = 0, plata = 0, bronce = 0;
    for (const x of medallas) {
      const { a, t, n, d, m } = x._id;
      anio(a, t)[m] += x.c; comite(n)[m] += x.c;
      if (!porDep.has(d)) porDep.set(d, { d, Oro: 0, Plata: 0, Bronce: 0, n: 0 });
      const pd = porDep.get(d); pd[m] += x.c; pd.n += x.c;
      if (m === "Oro") oro += x.c; else if (m === "Plata") plata += x.c; else bronce += x.c;
    }
    const f0 = atl[0] || { porAnio: [], total: [] };
    for (const x of f0.porAnio) anio(x._id.a, x._id.t).atletas = x.n;
    const atletas = f0.total[0]?.n ?? 0;

    print(`\nRESUMEN${hayFiltros ? " (con filtros)" : ""}: ${total.toLocaleString()} participaciones (entradas a un evento) | ${atletas.toLocaleString()} atletas distintos | ${porAnio.size} ediciones`);
    print(`MEDALLERO: Oro ${oro} | Plata ${plata} | Bronce ${bronce} | Total ${oro + plata + bronce}   (un equipo cuenta una sola medalla)`);

    // ---- por comité (si hay más de uno)
    if (g.comites.length > 1) {
      print("\nPOR COMITÉ:");
      [...porComite.values()].sort((x, y) => y.partic - x.partic)
        .forEach((x) => print(`  ${pad(x.n, 5)} participaciones ${lpad(x.partic, 6)}   Oro ${lpad(x.Oro, 4)}  Plata ${lpad(x.Plata, 4)}  Bronce ${lpad(x.Bronce, 4)}`));
    }

    // ---- por año de participación
    print("\nPARTICIPACIÓN POR EDICIÓN:");
    print(`${pad("AÑO", 6)}${pad("TEMPORADA", 11)}${lpad("PARTIC.", 8)}${lpad("ATLETAS", 9)}${lpad("ORO", 6)}${lpad("PLATA", 7)}${lpad("BRONCE", 8)}  SEDE`);
    const esSede = new Set(sedes.map((s) => `${s.anio}${s.temporada}`));
    for (const x of [...porAnio.values()].sort((p, q) => p.a - q.a || (p.t < q.t ? -1 : 1)))
      print(`${pad(x.a, 6)}${pad(x.t, 11)}${lpad(x.partic, 8)}${lpad(x.atletas, 9)}${lpad(x.Oro, 6)}${lpad(x.Plata, 7)}${lpad(x.Bronce, 8)}  ${esSede.has(`${x.a}${x.t}`) ? "◄ sede" : ""}`);

    // ---- medallas por deporte
    const top = [...porDep.values()].sort((x, y) => y.n - x.n || (x.d < y.d ? -1 : 1)).slice(0, 10);   // empate: orden alfabético
    if (top.length) {
      print("\nMEDALLAS POR DEPORTE (top 10):");
      top.forEach((x) => print(`  ${pad(x.d, 26)} Oro ${lpad(x.Oro, 4)}  Plata ${lpad(x.Plata, 4)}  Bronce ${lpad(x.Bronce, 4)}  Total ${lpad(x.n, 4)}`));
    }

    // ---- resultados (detalle)
    print(`\n${detalle ? "RESULTADOS" : "RESULTADOS CON MEDALLA"}${filas.length > tope ? ` (primeros ${tope}; suba TOPE para ver más)` : ""}:`);
    print(`${pad("AÑO", 5)}${pad("DEPORTE", 32)}${pad("EVENTO", 34)}${pad("NOC", 5)}${pad("PUESTO", 8)}${pad("MEDALLA", 8)}ATLETAS`);
    print("-".repeat(110));
    for (const p of filas.slice(0, tope)) {
      const nombres = p.n_atl > 3 ? p.nombres.join(", ") + ` +${p.n_atl - 3}` : p.nombres.join(", ");
      print(`${pad(p.edicion.anio, 5)}${pad(etiquetaDeporte(p), 32)}${pad(p.evento.nombre + (p.evento.categoria_sexo ? " " + p.evento.categoria_sexo : ""), 34)}${pad(p.noc.codigo, 5)}${pad(p.puesto_texto ?? "-", 8)}${pad(p.medalla ?? "-", 8)}${p.es_por_equipos ? `[${p.nombre_equipo ?? "equipo"}] ` : ""}${nombres}`);
    }
  }
  print(`\n[${ahora()}] Consulta resuelta en ${Date.now() - t0} ms`);
})().catch((e) => { print("ERROR en la consulta: " + e.message); });
