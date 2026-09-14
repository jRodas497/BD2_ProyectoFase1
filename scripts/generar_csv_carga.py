#!/usr/bin/env python3
"""
Genera los 15 CSV de carga (inciso b) a partir de las 4 fuentes crudas,
siguiendo docs/especificacion-etl-csv.md.

Fuentes:
  F1 Olympedia    -> sources/keithgalli/clean-data/{bios,results,noc_regions}.csv  (espina dorsal de atleta/puesto)
  F2 Kaggle 120y  -> data/raw/{athlete_events,noc_regions}.csv                     (ciudad sede, catalogo NOC)
  F3 Kaggle 1896-2024 -> data/raw/olympics_dataset.csv                            (relleno Tokio 2020 / Paris 2024)
  F4 DataCamp     -> fuentes/datacamp-datalab-r-olympics.csv                       (subconjunto de F2, solo verificacion)

Salida: staging/*.csv (15 archivos + catalogos ya sembrados en 04-seed.sql se omiten)
"""
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "staging"
OUT.mkdir(exist_ok=True)

WARNINGS = []


def warn(msg):
    WARNINGS.append(msg)
    print(f"[WARN] {msg}")


def normalizar_nombre(s):
    if pd.isna(s):
        return None
    s = str(s).strip().lower()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def to_bool_str(v):
    if pd.isna(v):
        return "false"
    return "true" if bool(v) else "false"


# Columnas que el esquema define como enteras (SERIAL/INT/SMALLINT); se fuerzan a Int64
# nullable para evitar que pandas las escriba como floats ("6.0") cuando hay NULLs de por medio.
COLUMNAS_ENTERAS = {
    "pais_id", "ciudad_id", "edicion_id", "numero_olimpiada", "deporte_id", "disciplina_id",
    "evento_id", "evento_edicion_id", "atleta_id", "pais_nacimiento_id", "estatura_cm",
    "participacion_id", "medalla_id", "puesto", "fuente_id",
}


def write_csv(df, name, cols):
    df = df.reindex(columns=cols)
    for col in df.columns:
        if col in COLUMNAS_ENTERAS:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    path = OUT / name
    df.to_csv(path, index=False, na_rep="")
    print(f"  -> {name}: {len(df)} filas")


print("=" * 70)
print("1. CARGANDO FUENTES CRUDAS")
print("=" * 70)

bios = pd.read_csv(BASE / "sources/keithgalli/clean-data/bios.csv")
results = pd.read_csv(BASE / "sources/keithgalli/clean-data/results.csv")
noc_reg1 = pd.read_csv(BASE / "sources/keithgalli/clean-data/noc_regions.csv")

f2 = pd.read_csv(BASE / "data/raw/athlete_events.csv")
noc_reg2 = pd.read_csv(BASE / "data/raw/noc_regions.csv")

f3 = pd.read_csv(BASE / "data/raw/olympics_dataset.csv")

f4 = pd.read_csv(BASE / "fuentes/datacamp-datalab-r-olympics.csv", encoding="utf-8-sig")

# Filtrar Youth Olympic Games y entradas vacias del F1 (no son parte del alcance del modelo)
antes = len(results)
results = results[~results["event"].astype(str).str.endswith("(YOG)", na=False)].copy()
print(f"F1 results: descartadas {antes - len(results)} filas de Youth Olympic Games")

antes = len(results)
results = results.dropna(subset=["discipline"]).copy()
if len(results) < antes:
    warn(f"F1 results: {antes - len(results)} filas sin discipline, descartadas")

print(f"F1 bios={len(bios)} results={len(results)} | F2={len(f2)} | F3={len(f3)} | F4={len(f4)}")

# ---------------------------------------------------------------------------
print("=" * 70)
print("2. PAIS / NOC")
print("=" * 70)

noc_reg = pd.concat([noc_reg1, noc_reg2], ignore_index=True).drop_duplicates(subset=["NOC"], keep="first")
noc_reg = noc_reg.set_index("NOC")

# Codigos NOC especiales sin pais asociado (equipos no nacionales)
SIN_PAIS = {"ROT", "IOA", "EOR", "AIN"}
# Overrides de pais para codigos faltantes en noc_regions o que representan un pais concreto
OVERRIDE_REGION = {"SGP": "Singapore", "LBN": "Lebanon", "ROC": "Russia"}
# NOCs historicos (comites disueltos)
HISTORICOS = {"URS", "GDR", "TCH", "YUG", "SAA", "EUN"}

# Todos los codigos NOC que aparecen en cualquier fuente
codigos_noc = set(noc_reg.index)
codigos_noc |= set(results["noc"].dropna().unique())
codigos_noc |= set(f2["NOC"].dropna().unique())
codigos_noc |= set(f3["NOC"].dropna().unique())
codigos_noc |= set(f4["noc"].dropna().unique())
codigos_noc |= set(bios["born_country"].dropna().unique()) & set(noc_reg.index)  # solo los que sean codigos validos
codigos_noc = sorted(codigos_noc)

pais_nombre_de_noc = {}
notas_de_noc = {}
for code in codigos_noc:
    if code in OVERRIDE_REGION:
        pais_nombre_de_noc[code] = OVERRIDE_REGION[code]
    elif code in SIN_PAIS:
        pais_nombre_de_noc[code] = None
    elif code in noc_reg.index:
        region = noc_reg.loc[code, "region"]
        pais_nombre_de_noc[code] = region if pd.notna(region) else None
        notes = noc_reg.loc[code, "notes"] if "notes" in noc_reg.columns else None
        notas_de_noc[code] = notes if pd.notna(notes) else None
    else:
        warn(f"NOC '{code}' sin region conocida; se deja sin pais")
        pais_nombre_de_noc[code] = None

nombres_pais = sorted({v for v in pais_nombre_de_noc.values() if v})

pais_df = pd.DataFrame({
    "pais_id": range(1, len(nombres_pais) + 1),
    "nombre": nombres_pais,
    "codigo_iso3": [None] * len(nombres_pais),
})
pais_id_de_nombre = dict(zip(pais_df["nombre"], pais_df["pais_id"]))

noc_rows = []
for code in codigos_noc:
    nombre_pais = pais_nombre_de_noc.get(code)
    pais_id = pais_id_de_nombre.get(nombre_pais) if nombre_pais else None
    nombre_comite = nombre_pais if nombre_pais else code
    noc_rows.append({
        "noc_codigo": code,
        "pais_id": pais_id,
        "nombre_comite": nombre_comite,
        "es_historico": to_bool_str(code in HISTORICOS),
        "notas": notas_de_noc.get(code),
    })
noc_df = pd.DataFrame(noc_rows)

print(f"pais: {len(pais_df)} filas | noc: {len(noc_df)} filas")

# ---------------------------------------------------------------------------
print("=" * 70)
print("3. CIUDAD / EDICION / SEDE")
print("=" * 70)

CIUDAD_PAIS = {
    "Athina": "Greece", "Paris": "France", "St. Louis": "USA", "London": "UK",
    "Stockholm": "Sweden", "Antwerpen": "Belgium", "Amsterdam": "Netherlands",
    "Los Angeles": "USA", "Berlin": "Germany", "Helsinki": "Finland",
    "Melbourne": "Australia", "Roma": "Italy", "Tokyo": "Japan",
    "Mexico City": "Mexico", "Munich": "Germany", "Montreal": "Canada",
    "Moskva": "Russia", "Seoul": "South Korea", "Barcelona": "Spain",
    "Atlanta": "USA", "Sydney": "Australia", "Beijing": "China",
    "Rio de Janeiro": "Brazil",
    "Chamonix": "France", "Sankt Moritz": "Switzerland",
    "Garmisch-Partenkirchen": "Germany", "Oslo": "Norway",
    "Squaw Valley": "USA", "Innsbruck": "Austria", "Sapporo": "Japan",
    "Lake Placid": "USA", "Sarajevo": "Bosnia and Herzegovina",
    "Calgary": "Canada", "Albertville": "France", "Lillehammer": "Norway",
    "Nagano": "Japan", "Salt Lake City": "USA", "Torino": "Italy",
    "Vancouver": "Canada", "Sochi": "Russia", "Grenoble": "France",
    "Cortina d'Ampezzo": "Italy",
}

ciudades_crudas = sorted(set(f2["City"].dropna().unique()) | set(f3["City"].dropna().unique()))
faltantes = [c for c in ciudades_crudas if c not in CIUDAD_PAIS]
if faltantes:
    warn(f"Ciudades sin pais mapeado (se omiten de ciudad.csv): {faltantes}")
ciudades_crudas = [c for c in ciudades_crudas if c in CIUDAD_PAIS]

for pais_nombre in set(CIUDAD_PAIS.values()):
    if pais_nombre not in pais_id_de_nombre:
        warn(f"Pais de ciudad host '{pais_nombre}' no estaba en catalogo de pais; se agrega")
        new_id = pais_df["pais_id"].max() + 1
        pais_df = pd.concat([pais_df, pd.DataFrame([{"pais_id": new_id, "nombre": pais_nombre, "codigo_iso3": None}])], ignore_index=True)
        pais_id_de_nombre[pais_nombre] = new_id

ciudad_df = pd.DataFrame({
    "ciudad_id": range(1, len(ciudades_crudas) + 1),
    "pais_id": [pais_id_de_nombre[CIUDAD_PAIS[c]] for c in ciudades_crudas],
    "nombre": ciudades_crudas,
})
ciudad_id_de_nombre = dict(zip(ciudad_df["nombre"], ciudad_df["ciudad_id"]))

# Ediciones: union de (anio, temporada) presentes en F1/F2/F3
season_map = {"Summer": "Verano", "Winter": "Invierno"}

ed_f1 = results[["year", "type"]].dropna().rename(columns={"year": "anio", "type": "temporada"})
ed_f1["anio"] = ed_f1["anio"].astype(int)
ed_f1["temporada"] = ed_f1["temporada"].map(season_map)

ed_f2 = f2[["Year", "Season"]].rename(columns={"Year": "anio", "Season": "temporada"})
ed_f2["temporada"] = ed_f2["temporada"].map(season_map)

ed_f3 = f3[["Year", "Season"]].rename(columns={"Year": "anio", "Season": "temporada"})
ed_f3["temporada"] = ed_f3["temporada"].map(season_map)

ediciones = pd.concat([ed_f1, ed_f2, ed_f3], ignore_index=True).dropna().drop_duplicates()
ediciones = ediciones.sort_values(["anio", "temporada"]).reset_index(drop=True)

CANCELADAS = [(1916, "Verano"), (1940, "Verano"), (1940, "Invierno"), (1944, "Verano"), (1944, "Invierno")]
for anio, temp in CANCELADAS:
    if not ((ediciones["anio"] == anio) & (ediciones["temporada"] == temp)).any():
        ediciones = pd.concat([ediciones, pd.DataFrame([{"anio": anio, "temporada": temp}])], ignore_index=True)

ediciones = ediciones.sort_values(["anio", "temporada"]).reset_index(drop=True)
ediciones["edicion_id"] = range(1, len(ediciones) + 1)
ediciones["nombre"] = ediciones["anio"].astype(str) + " " + ediciones["temporada"]
ediciones["fue_cancelada"] = ediciones.apply(lambda r: (r["anio"], r["temporada"]) in CANCELADAS, axis=1)
ediciones["es_intercalada"] = (ediciones["anio"] == 1906) & (ediciones["temporada"] == "Verano")
ediciones["numero_olimpiada"] = None
ediciones["fecha_inicio"] = None
ediciones["fecha_fin"] = None

edicion_id_de = {(r.anio, r.temporada): r.edicion_id for r in ediciones.itertuples()}

edicion_df = ediciones[["edicion_id", "anio", "temporada", "numero_olimpiada", "nombre",
                        "fecha_inicio", "fecha_fin", "fue_cancelada", "es_intercalada"]].copy()
edicion_df["fue_cancelada"] = edicion_df["fue_cancelada"].map(to_bool_str)
edicion_df["es_intercalada"] = edicion_df["es_intercalada"].map(to_bool_str)

# Sede: ciudades por edicion (F2 + F3), es_principal = ciudad mas frecuente de esa edicion
sede_src = pd.concat([
    f2[["Year", "Season", "City"]].rename(columns={"Year": "anio", "Season": "temporada", "City": "ciudad"}),
    f3[["Year", "Season", "City"]].rename(columns={"Year": "anio", "Season": "temporada", "City": "ciudad"}),
], ignore_index=True)
sede_src["temporada"] = sede_src["temporada"].map(season_map)
sede_src = sede_src.dropna(subset=["ciudad"])
sede_src = sede_src[sede_src["ciudad"].isin(ciudad_id_de_nombre)]

conteo = sede_src.groupby(["anio", "temporada", "ciudad"]).size().reset_index(name="n")
sede_rows = []
for (anio, temp), grupo in conteo.groupby(["anio", "temporada"]):
    ed_id = edicion_id_de.get((anio, temp))
    if ed_id is None:
        continue
    grupo = grupo.sort_values("n", ascending=False)
    principal_marcada = False
    for _, r in grupo.iterrows():
        sede_rows.append({
            "edicion_id": ed_id,
            "ciudad_id": ciudad_id_de_nombre[r["ciudad"]],
            "es_principal": to_bool_str(not principal_marcada),
        })
        principal_marcada = True
sede_df = pd.DataFrame(sede_rows)

print(f"ciudad: {len(ciudad_df)} | edicion: {len(edicion_df)} | sede: {len(sede_df)}")

# ---------------------------------------------------------------------------
print("=" * 70)
print("4. DEPORTE / DISCIPLINA / EVENTO / EVENTO_EDICION")
print("=" * 70)


def parse_disciplina(d):
    m = re.match(r"^(.*)\s\(([^)]+)\)$", str(d))
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return str(d).strip(), str(d).strip()


disc_pairs = sorted(set(parse_disciplina(d) for d in results["discipline"].dropna().unique()))
# Alias / correcciones manuales para eventos que solo aparecen en F3-2024
disc_pairs.append(("Trampolining", "Gymnastics"))  # F3 dice "Trampoline Gymnastics"
disc_pairs.append(("Breaking", "Breaking"))         # deporte nuevo en Paris 2024
disc_pairs = sorted(set(disc_pairs))

deportes = sorted({d for _, d in disc_pairs})
deporte_df = pd.DataFrame({"deporte_id": range(1, len(deportes) + 1), "nombre": deportes})
deporte_id_de = dict(zip(deporte_df["nombre"], deporte_df["deporte_id"]))

disciplina_df = pd.DataFrame({
    "disciplina_id": range(1, len(disc_pairs) + 1),
    "deporte_id": [deporte_id_de[dep] for _, dep in disc_pairs],
    "nombre": [disc for disc, _ in disc_pairs],
})
disciplina_id_de = dict(zip(disciplina_df["nombre"], disciplina_df["disciplina_id"]))
deporte_de_disciplina = dict(disc_pairs)

SEXO_TOKEN_MAP = {"Men": "M", "Women": "F", "Mixed": "Mixto", "Open": "Abierto"}


def parse_evento_f1(evento_txt):
    e2 = re.sub(r"\s*\([^)]*\)\s*$", "", str(evento_txt)).strip()
    if "," in e2:
        nombre, token = e2.rsplit(",", 1)
        token = token.strip()
        categoria = SEXO_TOKEN_MAP.get(token)
        if categoria is None:
            nombre = e2
        else:
            nombre = nombre.strip()
    else:
        nombre, categoria = e2, None
    return nombre, categoria


def parse_evento_generico(evento_txt):
    """Parser best-effort para el 'Event' de F3 (formato inconsistente, sin prefijo de deporte)."""
    e = str(evento_txt).strip()
    m = re.search(r"\b(Men's|Women's|Mixed)\b", e)
    categoria = None
    if m:
        token = m.group(1)
        categoria = {"Men's": "M", "Women's": "F", "Mixed": "Mixto"}[token]
        e2 = (e[:m.start()] + e[m.end():]).strip()
    else:
        m2 = re.search(r"\b(Men|Women)\b", e)
        if m2:
            categoria = "M" if m2.group(1) == "Men" else "F"
            e2 = (e[:m2.start()] + e[m2.end():]).strip()
        else:
            e2 = e
    e2 = re.sub(r"\s+", " ", e2).strip(" ,-")
    if not e2:
        e2 = e
    return e2, categoria


# --- eventos desde F1 ---
results["disciplina_nombre"], results["deporte_nombre"] = zip(*results["discipline"].map(parse_disciplina))
results["evento_nombre"], results["evento_sexo"] = zip(*results["event"].map(parse_evento_f1))
results["disciplina_id"] = results["disciplina_nombre"].map(disciplina_id_de)

TEAM_KEYWORDS = re.compile(
    r"\b(Team|Relay|Group|Duet|Eights|Four|Pair|Coxed|Doubles|Fours|Squad)\b", re.IGNORECASE
)

# es_por_equipos por evento: dato-dirigido, se calcula tras agrupar participaciones (mas abajo)
evento_keys_f1 = results[["disciplina_id", "evento_nombre", "evento_sexo"]].drop_duplicates()

# --- eventos nuevos desde F3 (solo year==2024, la unica franja que aporta participaciones nuevas) ---
f3_2024 = f3[f3["Year"] == 2024].copy()


def resolver_disciplina_f3(sport, event):
    sport_first = str(sport).split(",")[0].strip()
    if sport_first == "Equestrian":
        for kw, disc in (("Jumping", "Equestrian Jumping"), ("Dressage", "Equestrian Dressage"), ("Eventing", "Equestrian Eventing")):
            if str(event).startswith(kw):
                return disc
        return "Equestrian Eventing"
    if sport_first == "Trampoline Gymnastics":
        return "Trampolining"
    if sport_first == "Breaking":
        return "Breaking"
    if sport_first in disciplina_id_de:
        return sport_first
    warn(f"F3 2024: deporte '{sport_first}' sin disciplina reconocida; se descarta")
    return None


f3_2024["disciplina_nombre"] = [resolver_disciplina_f3(s, e) for s, e in zip(f3_2024["Sport"], f3_2024["Event"])]
antes = len(f3_2024)
f3_2024 = f3_2024[f3_2024["disciplina_nombre"].notna()]
if len(f3_2024) < antes:
    warn(f"F3 2024: {antes - len(f3_2024)} filas descartadas por deporte no reconocido")
f3_2024["disciplina_id"] = f3_2024["disciplina_nombre"].map(disciplina_id_de)


def parse_evento_f3(disciplina, event):
    if disciplina.startswith("Equestrian"):
        kw = disciplina.replace("Equestrian ", "")
        nombre = str(event)[len(kw):].strip() if str(event).startswith(kw) else str(event)
        return nombre, "Abierto"
    return parse_evento_generico(event)


f3_2024["evento_nombre"], f3_2024["evento_sexo"] = zip(
    *[parse_evento_f3(d, e) for d, e in zip(f3_2024["disciplina_nombre"], f3_2024["Event"])]
)
f3_2024["es_por_equipos_kw"] = f3_2024["Event"].astype(str).str.contains(TEAM_KEYWORDS)

evento_keys_f3 = f3_2024[["disciplina_id", "evento_nombre", "evento_sexo"]].drop_duplicates()

evento_keys = pd.concat([evento_keys_f1, evento_keys_f3], ignore_index=True).drop_duplicates()
evento_keys = evento_keys.reset_index(drop=True)
evento_keys["evento_id"] = range(1, len(evento_keys) + 1)

evento_id_de = {}
for r in evento_keys.itertuples():
    evento_id_de[(r.disciplina_id, r.evento_nombre, r.evento_sexo)] = r.evento_id

results["evento_id"] = [evento_id_de[(d, n, s)] for d, n, s in zip(results["disciplina_id"], results["evento_nombre"], results["evento_sexo"])]
f3_2024["evento_id"] = [evento_id_de[(d, n, s)] for d, n, s in zip(f3_2024["disciplina_id"], f3_2024["evento_nombre"], f3_2024["evento_sexo"])]

# evento_edicion
results["edicion_id"] = [
    edicion_id_de.get((int(y), season_map.get(t))) if pd.notna(y) and pd.notna(t) else None
    for y, t in zip(results["year"], results["type"])
]
faltan_edicion = results["edicion_id"].isnull().sum()
if faltan_edicion:
    warn(f"F1 results: {faltan_edicion} filas sin edicion resuelta, se descartan de participacion")
f3_2024["edicion_id"] = edicion_id_de[(2024, "Verano")]

ee_keys_f1 = results.dropna(subset=["edicion_id"])[["evento_id", "edicion_id"]].drop_duplicates()
ee_keys_f3 = f3_2024[["evento_id", "edicion_id"]].drop_duplicates()
ee_keys = pd.concat([ee_keys_f1, ee_keys_f3], ignore_index=True).drop_duplicates().reset_index(drop=True)
ee_keys["evento_edicion_id"] = range(1, len(ee_keys) + 1)
ee_id_de = {(r.evento_id, r.edicion_id): r.evento_edicion_id for r in ee_keys.itertuples()}

results["evento_edicion_id"] = [ee_id_de.get((e, ed)) for e, ed in zip(results["evento_id"], results["edicion_id"])]
f3_2024["evento_edicion_id"] = [ee_id_de.get((e, ed)) for e, ed in zip(f3_2024["evento_id"], f3_2024["edicion_id"])]

print(f"deporte: {len(deporte_df)} | disciplina: {len(disciplina_df)} | evento: {len(evento_keys)} | evento_edicion: {len(ee_keys)}")

# ---------------------------------------------------------------------------
print("=" * 70)
print("5. PARTICIPACION / PARTICIPACION_ATLETA (grano = entrada, no atleta)")
print("=" * 70)

# --- F1: agrupar por (evento_edicion, noc, place, medal, tied) --- (vectorizado, sin loops fila a fila)
MEDALLA_ID = {"Gold": 1, "Silver": 2, "Bronze": 3}
results["medalla_id"] = results["medal"].map(MEDALLA_ID)
results_validos = results.dropna(subset=["evento_edicion_id"]).copy()
results_validos["evento_edicion_id"] = results_validos["evento_edicion_id"].astype(int)

# clave de agrupacion segura frente a NaN
results_validos["grp_place"] = results_validos["place"].fillna(-1)
results_validos["grp_medal"] = results_validos["medalla_id"].fillna(-1)

grp_cols = ["evento_edicion_id", "noc", "grp_place", "grp_medal", "tied"]
results_validos["participacion_id"] = results_validos.groupby(grp_cols, sort=False).ngroup() + 1

g = results_validos.groupby("participacion_id", sort=True)
part_base = g.agg(
    evento_edicion_id=("evento_edicion_id", "first"),
    noc_codigo=("noc", "first"),
    medalla_id=("medalla_id", "first"),
    place=("place", "first"),
    tied=("tied", "first"),
    n=("athlete_id", "size"),
).reset_index()
team_nunique = g["team"].nunique(dropna=True)
team_first = g["team"].first()
part_base["team_nunique"] = part_base["participacion_id"].map(team_nunique)
part_base["team_first"] = part_base["participacion_id"].map(team_first)

part_base["es_por_equipos"] = part_base["n"] > 1
cond_equipo = part_base["es_por_equipos"] & (part_base["team_nunique"] == 1)
part_base["nombre_equipo"] = np.where(cond_equipo, part_base["team_first"], None)
part_base["medalla_id"] = part_base["medalla_id"].astype("Int64")

puesto_int = part_base["place"].astype("Int64")
puesto_texto = puesto_int.astype(str).where(puesto_int.notna(), None)
tied_mask = part_base["tied"].fillna(False) & puesto_int.notna()
puesto_texto = puesto_texto.where(~tied_mask, "=" + puesto_texto)
part_base["puesto"] = puesto_int
part_base["puesto_texto"] = puesto_texto
part_base["empatado"] = part_base["tied"].fillna(False)

participaciones = part_base[[
    "participacion_id", "evento_edicion_id", "noc_codigo", "medalla_id", "nombre_equipo",
    "es_por_equipos", "puesto", "puesto_texto", "empatado",
]].to_dict("records")

pid_counter = int(part_base["participacion_id"].max()) + 1
print(f"  F1 -> {pid_counter - 1} participaciones")

pa = results_validos[["participacion_id", "athlete_id", "as"]].merge(
    bios[["athlete_id", "name"]], on="athlete_id", how="left"
)
pa["nombre_usado_en_evento"] = np.where(pa["as"].notna() & (pa["as"] != pa["name"]), pa["as"], None)
part_atleta_rows = pa.rename(columns={"athlete_id": "atleta_id"})[
    ["participacion_id", "atleta_id", "nombre_usado_en_evento"]
].to_dict("records")

# --- F3 2024: grano por (evento_edicion, noc, medal) si es equipo (segun keyword), si no 1 fila = 1 participacion ---
f3_2024_validos = f3_2024.dropna(subset=["evento_edicion_id"]).copy()
f3_2024_validos["evento_edicion_id"] = f3_2024_validos["evento_edicion_id"].astype(int)
f3_2024_validos["medalla_id"] = f3_2024_validos["Medal"].map(MEDALLA_ID)

es_equipo_por_evento_edicion = f3_2024_validos.groupby("evento_edicion_id")["es_por_equipos_kw"].any().to_dict()

f3_new_athletes_needed = []  # se resuelve en la seccion de atletas; aqui solo dejamos marcado el player_id

nuevas_participaciones_f3 = []
nuevas_part_atleta_f3 = []

for evento_edicion_id, sub in f3_2024_validos.groupby("evento_edicion_id"):
    if es_equipo_por_evento_edicion.get(evento_edicion_id, False):
        for (noc, medalla_id), grupo in sub.groupby(["NOC", "medalla_id"], dropna=False):
            n = len(grupo)
            team_vals = grupo["Team"].dropna().unique()
            nombre_equipo = team_vals[0] if len(team_vals) >= 1 else None
            nuevas_participaciones_f3.append({
                "evento_edicion_id": evento_edicion_id,
                "noc_codigo": noc,
                "medalla_id": int(medalla_id) if pd.notna(medalla_id) else None,
                "nombre_equipo": nombre_equipo,
                "es_por_equipos": True,
                "puesto": None, "puesto_texto": None, "empatado": False,
                "_miembros": grupo["player_id"].tolist(),
                "_nombres": grupo["Name"].tolist(),
            })
    else:
        for _, row in sub.iterrows():
            nuevas_participaciones_f3.append({
                "evento_edicion_id": evento_edicion_id,
                "noc_codigo": row["NOC"],
                "medalla_id": int(row["medalla_id"]) if pd.notna(row["medalla_id"]) else None,
                "nombre_equipo": None,
                "es_por_equipos": False,
                "puesto": None, "puesto_texto": None, "empatado": False,
                "_miembros": [row["player_id"]],
                "_nombres": [row["Name"]],
            })

print(f"  F3 2024 -> {len(nuevas_participaciones_f3)} participaciones nuevas (Paris 2024)")

# es_por_equipos final por evento_id = OR de todas sus evento_edicion
part_es_equipo_por_ee = {p["evento_edicion_id"]: p["es_por_equipos"] for p in participaciones}
for p in nuevas_participaciones_f3:
    part_es_equipo_por_ee[p["evento_edicion_id"]] = part_es_equipo_por_ee.get(p["evento_edicion_id"], False) or p["es_por_equipos"]

ee_to_evento = {r.evento_edicion_id: r.evento_id for r in ee_keys.itertuples()}
evento_es_equipo = {}
for ee_id, flag in part_es_equipo_por_ee.items():
    ev_id = ee_to_evento.get(ee_id)
    if ev_id is not None:
        evento_es_equipo[ev_id] = evento_es_equipo.get(ev_id, False) or flag

evento_df = evento_keys.rename(columns={"evento_nombre": "nombre", "evento_sexo": "categoria_sexo"})
evento_df["categoria_sexo"] = evento_df["categoria_sexo"].fillna("Abierto")
evento_df["es_por_equipos"] = evento_df["evento_id"].map(lambda e: to_bool_str(evento_es_equipo.get(e, False)))
evento_df = evento_df[["evento_id", "disciplina_id", "nombre", "categoria_sexo", "es_por_equipos"]]

evento_edicion_df = ee_keys[["evento_edicion_id", "evento_id", "edicion_id"]]

print("=" * 70)
print("6. ATLETA / ATLETA_FUENTE")
print("=" * 70)

# --- sexo inferido desde eventos en los que participo (F1) --- (vectorizado)
tmp = results_validos[["athlete_id", "evento_sexo"]].dropna(subset=["evento_sexo"])
sx = tmp.groupby("athlete_id")["evento_sexo"]
sexo_nun = sx.nunique()
sexo_first = sx.first()
sexo_valido = sexo_first.where(sexo_first.isin(["M", "F"]), "U")
sexo_por_atleta = sexo_valido.where(sexo_nun == 1, "U").to_dict()

bios["nombre_normalizado"] = bios["name"].map(normalizar_nombre)
bios["sexo"] = bios["athlete_id"].map(sexo_por_atleta).fillna("U")
bios["pais_nacimiento_id"] = bios["born_country"].map(lambda c: pais_id_de_nombre.get(pais_nombre_de_noc.get(c)) if c in pais_nombre_de_noc else None)

atleta_rows = bios.rename(columns={
    "athlete_id": "atleta_id", "name": "nombre_completo", "born_date": "fecha_nacimiento",
    "born_city": "ciudad_nacimiento", "born_region": "region_nacimiento",
    "died_date": "fecha_defuncion", "height_cm": "estatura_cm", "weight_kg": "peso_kg",
})
atleta_rows["nombre_usado"] = None
atleta_df = atleta_rows[[
    "atleta_id", "nombre_completo", "nombre_usado", "nombre_normalizado", "sexo",
    "fecha_nacimiento", "fecha_defuncion", "ciudad_nacimiento", "region_nacimiento",
    "pais_nacimiento_id", "estatura_cm", "peso_kg",
]].copy()

siguiente_atleta_id = int(atleta_df["atleta_id"].max()) + 1

# atleta_fuente: F1 (espina)
FUENTE_ID = {"F1": 1, "F2": 2, "F3": 3, "F4": 4}
af_rows = []
for r in bios.itertuples():
    af_rows.append({
        "atleta_id": r.athlete_id, "fuente_id": FUENTE_ID["F1"], "id_en_fuente": str(r.athlete_id),
        "nombre_en_fuente": r.name, "metodo_match": "espina", "confianza": 1.0,
    })

# --- indices de matching contra la espina (F1) ---
res_join = results[["athlete_id", "noc", "year"]].dropna(subset=["year"]).copy()
res_join["year"] = res_join["year"].astype(int)
res_join = res_join.merge(bios[["athlete_id", "nombre_normalizado"]], on="athlete_id", how="left")

# --- vectorizado: nunique()/first() por grupo en vez de iterar grupo por grupo ---
g1 = res_join.groupby(["nombre_normalizado", "noc", "year"])["athlete_id"]
u1, f1v = g1.nunique(), g1.first()
idx_nombre_noc_anio = f1v[u1 == 1].to_dict()

g2 = res_join.groupby(["nombre_normalizado", "noc"])["athlete_id"]
u2, f2v = g2.nunique(), g2.first()
idx_nombre_noc = f2v[u2 == 1].to_dict()

cnt_nombre = bios["nombre_normalizado"].value_counts()
bios_unicos = bios[bios["nombre_normalizado"].map(cnt_nombre) == 1]
idx_nombre_solo = dict(zip(bios_unicos["nombre_normalizado"], bios_unicos["athlete_id"]))


def nombre_nucleo(nombre_normalizado):
    """Primer + ultimo token del nombre: recupera casos de nombres compuestos, apellidos
    de casada o alias que rompen la igualdad exacta de nombre_normalizado (ej. 'usain st
    leo bolt' vs 'usain bolt')."""
    if not nombre_normalizado:
        return nombre_normalizado
    partes = nombre_normalizado.split(" ")
    if len(partes) <= 2:
        return nombre_normalizado
    return partes[0] + " " + partes[-1]


res_join["nucleo"] = res_join["nombre_normalizado"].map(nombre_nucleo)
g3 = res_join.groupby(["nucleo", "noc"])["athlete_id"]
u3, f3v = g3.nunique(), g3.first()
idx_nucleo_noc = f3v[u3 == 1].to_dict()

bios["nucleo"] = bios["nombre_normalizado"].map(nombre_nucleo)
cnt_nucleo = bios["nucleo"].value_counts()
bios_nucleo_unicos = bios[bios["nucleo"].map(cnt_nucleo) == 1]
idx_nucleo_solo = dict(zip(bios_nucleo_unicos["nucleo"], bios_nucleo_unicos["athlete_id"]))

# registro de atletas nuevos creados por F2/F3 (para que F3/F4 puedan reusarlos, y F4 no cree ninguno)
nuevos_por_nombre_noc = {}


def resolver_atleta(nombre_normalizado, noc, anio, permitir_nuevo, fuente_tag):
    global siguiente_atleta_id
    if (nombre_normalizado, noc, anio) in idx_nombre_noc_anio:
        return idx_nombre_noc_anio[(nombre_normalizado, noc, anio)], "exacto", 0.90
    if (nombre_normalizado, noc) in idx_nombre_noc:
        return idx_nombre_noc[(nombre_normalizado, noc)], "nombre+noc+anio", 0.75
    nucleo = nombre_nucleo(nombre_normalizado)
    if (nucleo, noc) in idx_nucleo_noc:
        return idx_nucleo_noc[(nucleo, noc)], "nombre+noc+anio", 0.65
    if nombre_normalizado in idx_nombre_solo:
        return idx_nombre_solo[nombre_normalizado], "nombre+noc+anio", 0.55
    if nucleo in idx_nucleo_solo:
        return idx_nucleo_solo[nucleo], "nombre+noc+anio", 0.45
    key = (nombre_normalizado, noc)
    if key in nuevos_por_nombre_noc:
        return nuevos_por_nombre_noc[key], "nuevo", 0.50
    if not permitir_nuevo:
        return None, None, None
    aid = siguiente_atleta_id
    siguiente_atleta_id += 1
    nuevos_por_nombre_noc[key] = aid
    return aid, "nuevo", 0.50


nuevos_atleta_rows = []
ids_ya_agregados = set()  # evita reconstruir un set() completo en cada iteracion (O(n^2))

# --- F2: solo trazabilidad (atleta_fuente) + posibles altas nuevas ---
f2_u = f2.drop_duplicates(subset=["ID"]).copy()
f2_u["nombre_normalizado"] = f2_u["Name"].map(normalizar_nombre)
for r in f2_u.itertuples():
    aid, metodo, conf = resolver_atleta(r.nombre_normalizado, r.NOC, int(r.Year), True, "F2")
    if metodo == "nuevo" and aid not in ids_ya_agregados:
        ids_ya_agregados.add(aid)
        nuevos_atleta_rows.append({
            "atleta_id": aid, "nombre_completo": r.Name, "nombre_usado": None,
            "nombre_normalizado": r.nombre_normalizado,
            "sexo": r.Sex if r.Sex in ("M", "F") else "U",
            "fecha_nacimiento": None, "fecha_defuncion": None,
            "ciudad_nacimiento": None, "region_nacimiento": None, "pais_nacimiento_id": None,
            "estatura_cm": r.Height if pd.notna(r.Height) else None,
            "peso_kg": r.Weight if pd.notna(r.Weight) else None,
        })
    af_rows.append({
        "atleta_id": aid, "fuente_id": FUENTE_ID["F2"], "id_en_fuente": str(r.ID),
        "nombre_en_fuente": r.Name, "metodo_match": metodo, "confianza": conf,
    })

# --- F3: trazabilidad + altas nuevas (incluye a los atletas nuevos de Paris 2024) ---
f3_u = f3.drop_duplicates(subset=["player_id"]).copy()
f3_u["nombre_normalizado"] = f3_u["Name"].map(normalizar_nombre)
for r in f3_u.itertuples():
    aid, metodo, conf = resolver_atleta(r.nombre_normalizado, r.NOC, int(r.Year), True, "F3")
    if metodo == "nuevo" and aid not in ids_ya_agregados:
        ids_ya_agregados.add(aid)
        nuevos_atleta_rows.append({
            "atleta_id": aid, "nombre_completo": r.Name, "nombre_usado": None,
            "nombre_normalizado": r.nombre_normalizado,
            "sexo": r.Sex if r.Sex in ("M", "F") else "U",
            "fecha_nacimiento": None, "fecha_defuncion": None,
            "ciudad_nacimiento": None, "region_nacimiento": None, "pais_nacimiento_id": None,
            "estatura_cm": None, "peso_kg": None,
        })
    af_rows.append({
        "atleta_id": aid, "fuente_id": FUENTE_ID["F3"], "id_en_fuente": str(r.player_id),
        "nombre_en_fuente": r.Name, "metodo_match": metodo, "confianza": conf,
    })

atleta_id_de_player_id_f3 = {}
for r in f3_u.itertuples():
    aid, _, _ = resolver_atleta(r.nombre_normalizado, r.NOC, int(r.Year), False, "F3")
    if aid is None:
        aid, _, _ = resolver_atleta(r.nombre_normalizado, r.NOC, int(r.Year), True, "F3")
    atleta_id_de_player_id_f3[r.player_id] = aid

# --- F4: NO debe crear altas nuevas (D-000); si no matchea, se descarta con advertencia ---
f4_u = f4.drop_duplicates(subset=["id"]).copy()
f4_u["nombre_normalizado"] = f4_u["name"].map(normalizar_nombre)
f4_sin_match = 0
for r in f4_u.itertuples():
    aid, metodo, conf = resolver_atleta(r.nombre_normalizado, r.noc, int(r.year), False, "F4")
    if aid is None:
        f4_sin_match += 1
        continue
    af_rows.append({
        "atleta_id": aid, "fuente_id": FUENTE_ID["F4"], "id_en_fuente": str(r.id),
        "nombre_en_fuente": r.name, "metodo_match": metodo, "confianza": conf,
    })
if f4_sin_match:
    warn(f"F4: {f4_sin_match} filas sin match contra F1/F2/F3 (D-000: no deberian existir); se omiten de atleta_fuente")

nuevos_atleta_df = pd.DataFrame(nuevos_atleta_rows)
atleta_df_final = pd.concat([atleta_df, nuevos_atleta_df], ignore_index=True) if len(nuevos_atleta_df) else atleta_df
atleta_fuente_df = pd.DataFrame(af_rows).drop_duplicates(subset=["atleta_id", "fuente_id", "id_en_fuente"])

print(f"atleta: {len(atleta_df_final)} ({len(nuevos_atleta_rows)} altas nuevas de F2/F3) | atleta_fuente: {len(atleta_fuente_df)}")

# --- completar participacion_atleta de F3 2024 con los atleta_id ya resueltos ---
for p in nuevas_participaciones_f3:
    p["participacion_id"] = None  # se asigna abajo

pid_counter_f3 = pid_counter
participaciones_f3_final = []
for p in nuevas_participaciones_f3:
    p["participacion_id"] = pid_counter_f3
    miembros = p.pop("_miembros")
    nombres = p.pop("_nombres")
    for player_id, nombre in zip(miembros, nombres):
        aid = atleta_id_de_player_id_f3.get(player_id)
        nuevas_part_atleta_f3.append({
            "participacion_id": pid_counter_f3, "atleta_id": aid, "nombre_usado_en_evento": None,
        })
    participaciones_f3_final.append(p)
    pid_counter_f3 += 1

todas_participaciones = participaciones + [
    {k: v for k, v in p.items() if k != "es_por_equipos" or True} for p in participaciones_f3_final
]
# normalizar es_por_equipos a bool str al final
participacion_df = pd.DataFrame(todas_participaciones)
participacion_df["es_por_equipos"] = participacion_df["es_por_equipos"].map(to_bool_str)
participacion_df["empatado"] = participacion_df["empatado"].map(to_bool_str)

participacion_atleta_df = pd.DataFrame(part_atleta_rows + nuevas_part_atleta_f3)
antes_pa = len(participacion_atleta_df)
participacion_atleta_df = participacion_atleta_df.dropna(subset=["atleta_id"])
if len(participacion_atleta_df) < antes_pa:
    warn(f"participacion_atleta: {antes_pa - len(participacion_atleta_df)} filas sin atleta_id resuelto, descartadas")
participacion_atleta_df["atleta_id"] = participacion_atleta_df["atleta_id"].astype(int)

antes_dedup = len(participacion_atleta_df)
participacion_atleta_df = participacion_atleta_df.drop_duplicates(subset=["participacion_id", "atleta_id"])
if len(participacion_atleta_df) < antes_dedup:
    warn(
        f"participacion_atleta: {antes_dedup - len(participacion_atleta_df)} filas duplicadas "
        "(mismo atleta repetido en la misma entrada, artefacto de la fuente) colapsadas a una sola"
    )

print(f"participacion: {len(participacion_df)} | participacion_atleta: {len(participacion_atleta_df)}")

# ---------------------------------------------------------------------------
print("=" * 70)
print("7. ESCRITURA DE CSV")
print("=" * 70)

write_csv(pais_df, "pais.csv", ["pais_id", "nombre", "codigo_iso3"])
write_csv(noc_df, "noc.csv", ["noc_codigo", "pais_id", "nombre_comite", "es_historico", "notas"])
write_csv(ciudad_df, "ciudad.csv", ["ciudad_id", "pais_id", "nombre"])
write_csv(edicion_df, "edicion.csv", ["edicion_id", "anio", "temporada", "numero_olimpiada", "nombre",
                                      "fecha_inicio", "fecha_fin", "fue_cancelada", "es_intercalada"])
write_csv(sede_df, "sede.csv", ["edicion_id", "ciudad_id", "es_principal"])
write_csv(deporte_df, "deporte.csv", ["deporte_id", "nombre"])
write_csv(disciplina_df, "disciplina.csv", ["disciplina_id", "deporte_id", "nombre"])
write_csv(evento_df, "evento.csv", ["evento_id", "disciplina_id", "nombre", "categoria_sexo", "es_por_equipos"])
write_csv(evento_edicion_df, "evento_edicion.csv", ["evento_edicion_id", "evento_id", "edicion_id"])
write_csv(atleta_df_final, "atleta.csv", [
    "atleta_id", "nombre_completo", "nombre_usado", "nombre_normalizado", "sexo",
    "fecha_nacimiento", "fecha_defuncion", "ciudad_nacimiento", "region_nacimiento",
    "pais_nacimiento_id", "estatura_cm", "peso_kg",
])
write_csv(participacion_df, "participacion.csv", [
    "participacion_id", "evento_edicion_id", "noc_codigo", "medalla_id", "nombre_equipo",
    "es_por_equipos", "puesto", "puesto_texto", "empatado",
])
write_csv(participacion_atleta_df, "participacion_atleta.csv", [
    "participacion_id", "atleta_id", "nombre_usado_en_evento",
])
write_csv(atleta_fuente_df, "atleta_fuente.csv", [
    "atleta_id", "fuente_id", "id_en_fuente", "nombre_en_fuente", "metodo_match", "confianza",
])

print("=" * 70)
print(f"LISTO. {len(WARNINGS)} advertencias.")
print("=" * 70)
with open(OUT / "_warnings.log", "w") as f:
    f.write("\n".join(WARNINGS))
