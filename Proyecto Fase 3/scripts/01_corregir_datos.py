#!/usr/bin/env python3
"""
Fase 3 — paso 1: corrige los defectos de carga de la Fase 1 ANTES de cargar a MongoDB.

Entrada : datos/fase1/*.csv      (los CSV tal como quedaron cargados en PostgreSQL en la Fase 1)
Salida  : datos/corregidos/*.csv (mismas tablas, corregidas) + docs/reporte-correcciones.md

Correcciones (el enunciado pide que lo que falló en la carga relacional quede corregido):

  C1  Participaciones individuales fundidas.  El ETL de Fase 1 agrupaba las filas del resultado por
      (evento_edicion, NOC, puesto, medalla, empate). En un evento individual, dos atletas del mismo
      país con el mismo puesto -o sin puesto (DNS/DNF)- quedaban en UNA sola "participación" con
      varios atletas. Se separan: una participación por atleta.
  C2  es_por_equipos del evento.  Como consecuencia de C1, eventos individuales (maratón, 100 m,
      disco, florete individual...) quedaron marcados "por equipos". Se recalcula con evidencia de
      los datos: un evento es de equipo si la mayoría de sus participaciones con medalla (o, si no
      tiene medallas, la mayoría de todas) tienen más de un atleta.
  C3  participacion.es_por_equipos pasa a ser coherente con el evento corregido (decisión D-012).
  C4  NOC: comités disueltos marcados como vigentes (FRG, SCG, AHO, BOH, ANZ, WIF, YAR, YMD, UAR, RHO,
      NBO, NFL, CRT) y nombres de comité tomados de la región ("Russia" para URS/EUN, "Germany" para
      GDR/FRG/SAA, "Czech Republic" para TCH, "Serbia" para YUG...). Se conserva el original en
      nombre_comite_fase1.
  C5  País: errores de escritura ("Boliva") y nombre alterno en español para búsquedas.

Uso: python3 scripts/01_corregir_datos.py
"""
import csv
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
ENTRADA, SALIDA = BASE / "datos" / "fase1", BASE / "datos" / "corregidos"
REPORTE = BASE / "docs" / "reporte-correcciones.md"

NOC_HISTORICOS = {"FRG", "SCG", "AHO", "BOH", "ANZ", "WIF", "YAR", "YMD", "UAR", "RHO", "NBO", "NFL", "CRT"}
NOC_NOMBRES = {
    "URS": "Soviet Union", "EUN": "Unified Team", "GDR": "East Germany", "FRG": "West Germany",
    "SAA": "Saar", "TCH": "Czechoslovakia", "YUG": "Yugoslavia", "SCG": "Serbia and Montenegro",
    "BOH": "Bohemia", "ANZ": "Australasia", "AHO": "Netherlands Antilles", "RHO": "Rhodesia",
    "WIF": "West Indies Federation", "UAR": "United Arab Republic", "YAR": "North Yemen",
    "YMD": "South Yemen", "NBO": "North Borneo", "NFL": "Newfoundland", "CRT": "Crete",
    "ROC": "Russian Olympic Committee", "AIN": "Individual Neutral Athletes",
    "EOR": "Refugee Olympic Team", "ROT": "Refugee Olympic Team", "IOA": "Individual Olympic Athletes",
    "TUV": "Tuvalu", "BOL": "Bolivia", "USA": "United States", "GBR": "Great Britain",
}
PAIS_NOMBRES = {"Boliva": "Bolivia"}
# nombre alterno en español para que la consulta por país funcione también en español
PAIS_ALIAS_ES = {
    "Germany": "Alemania", "USA": "Estados Unidos", "Spain": "España", "France": "Francia",
    "UK": "Reino Unido", "Japan": "Japón", "China": "China", "Brazil": "Brasil", "Mexico": "México",
    "Italy": "Italia", "Russia": "Rusia", "Canada": "Canadá", "Switzerland": "Suiza",
    "Netherlands": "Países Bajos", "Sweden": "Suecia", "Greece": "Grecia", "Belgium": "Bélgica",
    "Austria": "Austria", "Denmark": "Dinamarca", "Norway": "Noruega", "Finland": "Finlandia",
    "Poland": "Polonia", "Hungary": "Hungría", "Czech Republic": "República Checa",
    "Serbia": "Serbia", "Croatia": "Croacia", "Ireland": "Irlanda", "Cuba": "Cuba",
    "Jamaica": "Jamaica", "Australia": "Australia", "New Zealand": "Nueva Zelanda",
    "South Korea": "Corea del Sur", "North Korea": "Corea del Norte", "Turkey": "Turquía",
    "Egypt": "Egipto", "South Africa": "Sudáfrica", "Argentina": "Argentina", "Chile": "Chile",
    "Colombia": "Colombia", "Peru": "Perú", "Venezuela": "Venezuela", "Ecuador": "Ecuador",
    "Costa Rica": "Costa Rica", "Honduras": "Honduras", "El Salvador": "El Salvador",
    "Nicaragua": "Nicaragua", "Panama": "Panamá", "Guatemala": "Guatemala", "Haiti": "Haití",
    "Dominican Republic": "República Dominicana", "Puerto Rico": "Puerto Rico", "Uruguay": "Uruguay",
    "Paraguay": "Paraguay", "Bolivia": "Bolivia", "Morocco": "Marruecos", "Kenya": "Kenia",
    "Ethiopia": "Etiopía", "India": "India", "Iran": "Irán", "Israel": "Israel",
    "Ukraine": "Ucrania", "Romania": "Rumanía", "Bulgaria": "Bulgaria", "Portugal": "Portugal",
}


def leer(nombre):
    with open(ENTRADA / f"{nombre}.csv", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        return r.fieldnames, list(r)


def escribir(nombre, campos, filas):
    with open(SALIDA / f"{nombre}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)


def main():
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ahora}] Corrección de datos de Fase 1 -> {SALIDA}")
    if SALIDA.exists():
        shutil.rmtree(SALIDA)
    SALIDA.mkdir(parents=True)

    # Tablas que pasan sin cambios
    for t in ["ciudad", "edicion", "sede", "deporte", "disciplina", "evento_edicion",
              "atleta", "atleta_fuente", "medalla", "fuente"]:
        shutil.copy(ENTRADA / f"{t}.csv", SALIDA / f"{t}.csv")

    # ---------------- datos de entrada ----------------
    c_ev, evento = leer("evento")
    c_ee, ev_ed = leer("evento_edicion")
    c_pa, part = leer("participacion")
    c_pat, pa = leer("participacion_atleta")
    c_noc, noc = leer("noc")
    c_pais, pais = leer("pais")

    ee_evento = {r["evento_edicion_id"]: r["evento_id"] for r in ev_ed}
    atletas_de = defaultdict(list)
    for r in pa:
        atletas_de[r["participacion_id"]].append(r)
    n_orig = len(part)

    # ---------------- C2: es_por_equipos del evento por evidencia ----------------
    est = defaultdict(lambda: Counter())
    for p in part:
        e = ee_evento[p["evento_edicion_id"]]
        multi = len(atletas_de[p["participacion_id"]]) > 1
        est[e]["n"] += 1
        est[e]["multi"] += multi
        if p["medalla_id"]:
            est[e]["med"] += 1
            est[e]["medmulti"] += multi
    equipo = {}
    for e, s in est.items():
        equipo[e] = (s["medmulti"] / s["med"] >= 0.5) if s["med"] >= 1 else (s["multi"] / s["n"] >= 0.5)
    ev_cambiados = []
    for r in evento:
        antes = r["es_por_equipos"] == "true"
        ahora_ = equipo.get(r["evento_id"], antes)
        if antes != ahora_:
            ev_cambiados.append((r["nombre"], r["categoria_sexo"], antes, ahora_, est[r["evento_id"]]["n"]))
        r["es_por_equipos"] = "true" if ahora_ else "false"
    escribir("evento", c_ev, evento)
    ev_flag = {r["evento_id"]: r["es_por_equipos"] for r in evento}

    # ---------------- C1 + C3: separar individuales fundidos ----------------
    max_id = max(int(p["participacion_id"]) for p in part)
    sig = max_id + 1
    nuevas_part, nuevos_pa = [], []
    separadas = 0
    ejemplos = []
    for p in sorted(part, key=lambda x: int(x["participacion_id"])):
        pid = p["participacion_id"]
        evid = ee_evento[p["evento_edicion_id"]]
        es_eq = ev_flag[evid] == "true"
        miembros = sorted(atletas_de[pid], key=lambda r: int(r["atleta_id"]))
        base = dict(p, participacion_origen_id=pid)
        if not es_eq and len(miembros) > 1:
            separadas += 1
            if len(ejemplos) < 5:
                ejemplos.append((pid, p["noc_codigo"], p["evento_edicion_id"], len(miembros)))
            for i, m in enumerate(miembros):
                nid = pid if i == 0 else str(sig)
                if i > 0:
                    sig += 1
                nuevas_part.append(dict(base, participacion_id=nid, es_por_equipos="false", nombre_equipo=""))
                nuevos_pa.append(dict(m, participacion_id=nid))
        else:
            nuevas_part.append(dict(base, es_por_equipos="true" if es_eq else "false"))
            nuevos_pa.extend(dict(m) for m in miembros)
    escribir("participacion", c_pa + ["participacion_origen_id"], nuevas_part)
    escribir("participacion_atleta", c_pat, nuevos_pa)

    # ---------------- C4: NOC ----------------
    noc_hist, noc_nom = [], []
    for r in noc:
        r["nombre_comite_fase1"] = r["nombre_comite"]
        if r["noc_codigo"] in NOC_HISTORICOS and r["es_historico"] != "true":
            noc_hist.append(r["noc_codigo"])
            r["es_historico"] = "true"
        nuevo = NOC_NOMBRES.get(r["noc_codigo"])
        if nuevo and nuevo != r["nombre_comite"]:
            noc_nom.append((r["noc_codigo"], r["nombre_comite"], nuevo))
            r["nombre_comite"] = nuevo
    escribir("noc", c_noc + ["nombre_comite_fase1"], noc)

    # ---------------- C5: país ----------------
    pais_corr = []
    for r in pais:
        if r["nombre"] in PAIS_NOMBRES:
            pais_corr.append((r["nombre"], PAIS_NOMBRES[r["nombre"]]))
            r["nombre"] = PAIS_NOMBRES[r["nombre"]]
        r["nombre_es"] = PAIS_ALIAS_ES.get(r["nombre"], "")
    escribir("pais", c_pais + ["nombre_es"], pais)

    # ---------------- verificaciones ----------------
    est2 = Counter()
    pa_por = Counter(r["participacion_id"] for r in nuevos_pa)
    for p in nuevas_part:
        if p["es_por_equipos"] == "false" and pa_por[p["participacion_id"]] > 1:
            est2["individual_con_varios"] += 1
    assert est2["individual_con_varios"] == 0, "quedaron individuales con varios atletas"
    assert len(pa_por) == len(nuevas_part) and all(pa_por[p["participacion_id"]] >= 1 for p in nuevas_part)
    assert len(nuevos_pa) == len(pa), "no debe perderse ninguna fila participacion_atleta"

    # ---------------- reporte ----------------
    L = [f"# Reporte de correcciones de datos (Fase 1 → Fase 3)\n",
         f"Generado por `scripts/01_corregir_datos.py` el {ahora}.\n",
         "| Tabla | Fase 1 | Corregida |", "|---|---|---|",
         f"| participacion | {n_orig:,} | {len(nuevas_part):,} |",
         f"| participacion_atleta | {len(pa):,} | {len(nuevos_pa):,} |",
         f"| evento (flag es_por_equipos cambiado) | — | {len(ev_cambiados)} eventos |",
         f"| noc (marcados como históricos) | — | {len(noc_hist)} |",
         f"| noc (nombre de comité corregido) | — | {len(noc_nom)} |\n",
         "## C1 · Participaciones individuales fundidas",
         f"- Participaciones individuales con más de un atleta separadas: **{separadas:,}**.",
         f"- Participaciones nuevas creadas: **{len(nuevas_part) - n_orig:,}** (ids desde {max_id + 1}).",
         "- Cada participación nueva guarda `participacion_origen_id` con el id de Fase 1.",
         "- Ejemplos (participacion_id, NOC, evento_edicion_id, atletas fundidos): "
         + "; ".join(str(e) for e in ejemplos) + "\n",
         "## C2 · Eventos con es_por_equipos corregido",
         f"Total: {len(ev_cambiados)} (de {len(evento)}). Pasaron a **individual**: "
         f"{sum(1 for e in ev_cambiados if e[2])}; pasaron a **equipo**: {sum(1 for e in ev_cambiados if not e[2])}.\n",
         "Los 25 con más participaciones:\n", "| Evento | Sexo | Antes | Ahora | Participaciones |", "|---|---|---|---|---|"]
    for n_, s_, a_, d_, c_ in sorted(ev_cambiados, key=lambda x: -x[4])[:25]:
        L.append(f"| {n_} | {s_} | {'equipo' if a_ else 'individual'} | {'equipo' if d_ else 'individual'} | {c_:,} |")
    L += ["", "## C4 · NOC", f"- Marcados como históricos: {', '.join(noc_hist)}.",
          "- Nombres corregidos: " + ", ".join(f"{c} ({a} → {b})" for c, a, b in noc_nom), "",
          "## C5 · País", f"- Correcciones: {pais_corr}.",
          f"- Nombre en español agregado a {sum(1 for r in pais if r['nombre_es'])} países.", ""]
    REPORTE.write_text("\n".join(L), encoding="utf-8")
    print(f"  participaciones: {n_orig:,} -> {len(nuevas_part):,} (separadas {separadas:,})")
    print(f"  eventos con flag cambiado: {len(ev_cambiados)} | NOC históricos: {len(noc_hist)} | nombres NOC: {len(noc_nom)}")
    print(f"  reporte: {REPORTE}")
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Corrección terminada")


if __name__ == "__main__":
    main()
