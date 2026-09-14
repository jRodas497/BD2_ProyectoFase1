#!/usr/bin/env python3
"""Genera los CSV de carga del modelo olímpico descrito en el inciso b.

Diseñado para ejecutarse sobre los archivos completos del repositorio local.
No degrada silenciosamente la regla D-003: Olympedia (bios + results) es obligatoria.

Salidas principales (15):
  fuente.csv, pais.csv, noc.csv, ciudad.csv, edicion.csv, sede.csv,
  deporte.csv, disciplina.csv, evento.csv, evento_edicion.csv, medalla.csv,
  atleta.csv, participacion.csv, participacion_atleta.csv, atleta_fuente.csv

Para fuente/medalla la especificación solo fija IDs y significados, no publica
el DDL completo; se generan catálogos mínimos de dos columnas y se documenta
la inferencia en RESUMEN_GENERACION.txt.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


HISTORICAL_NOCS = {"URS", "GDR", "TCH", "YUG", "SAA", "EUN"}
NO_COUNTRY_NOCS = {"ROT", "IOA", "EOR", "AIN", "COR"}
NOC_REGION_OVERRIDES = {"LBN": "Lebanon", "SGP": "Singapore", "ROC": "Russia"}
MEDAL_ID = {"gold": 1, "silver": 2, "bronze": 3}
PARENT_SPORT_ES = {
    "Aquatics": "Acuáticos", "Skiing": "Esquí", "Cycling": "Ciclismo",
    "Equestrian": "Ecuestre", "Gymnastics": "Gimnasia", "Canoeing": "Piragüismo",
    "Skating": "Patinaje", "Ice Hockey": "Hockey sobre hielo", "Basketball": "Baloncesto",
    "Baseball/Softball": "Béisbol y Sóftbol", "Volleyball": "Voleibol",
    "Bobsleigh": "Bobsleigh", "Roller Sports": "Deportes sobre ruedas", "Rugby": "Rugby",
    "Air Sports": "Deportes aéreos", "Football": "Fútbol",
}
STANDALONE_SPORT_ES = {
    "Australian Rules Football": "Fútbol australiano", "Bandy": "Bandy",
    "Bicycle Polo": "Ciclismo", "Canoe Marathon": "Piragüismo",
    "Equestrian Driving": "Ecuestre", "Equestrian Vaulting": "Ecuestre",
    "Glíma": "Lucha", "Hockey 5s": "Hockey", "Mixed Sports": "Deportes mixtos",
    "Roller Skating": "Deportes sobre ruedas", "Savate": "Savate",
    "Ski Mountaineering": "Esquí de montaña", "Speed Skiing": "Esquí",
    "Winter Pentathlon": "Pentatlón de invierno", "3-on-3 Ice Hockey": "Hockey sobre hielo",
    "Trampolining": "Gimnasia",
}
SEASON_ES = {"Summer": "Verano", "Winter": "Invierno", "Verano": "Verano", "Invierno": "Invierno"}
SEASON_EN = {"Summer": "Summer", "Winter": "Winter", "Verano": "Summer", "Invierno": "Winter"}

EXPECTED_HEADERS = {
    "bios": ["athlete_id", "name", "born_date", "born_city", "born_region", "born_country", "NOC", "height_cm", "weight_kg", "died_date"],
    "results": ["year", "type", "discipline", "event", "as", "athlete_id", "noc", "team", "place", "tied", "medal"],
    "f2": ["ID", "Name", "Sex", "Age", "Height", "Weight", "Team", "NOC", "Games", "Year", "Season", "City", "Sport", "Event", "Medal"],
    "noc": ["NOC", "region", "notes"],
    "f3": ["player_id", "Name", "Sex", "Team", "NOC", "Year", "Season", "City", "Sport", "Event", "Medal"],
    "f4": ["index", "id", "name", "sex", "age", "height", "weight", "team", "noc", "games", "year", "season", "city", "sport", "event", "medal"],
}

TEAM_SPORTS = {
    "3x3 Basketball", "Basketball", "Baseball", "Softball", "Baseball/Softball",
    "Football", "Handball", "Hockey", "Ice Hockey", "Lacrosse", "Polo",
    "Rugby", "Rugby Sevens", "Volleyball", "Beach Volleyball", "Water Polo",
    "Cricket", "Curling", "Tug-Of-War", "Bandy", "Hockey 5s", "Australian Rules Football",
    "3-on-3 Ice Hockey",
}
TEAM_EVENT_PATTERNS = [
    r"\bteam\b", r"\brelay\b", r"\bdoubles?\b", r"\bpairs?\b", r"\bmadison\b",
    r"\bteam pursuit\b", r"\bteam sprint\b", r"\bsynchronized\b", r"\bsynchronised\b",
    r"\bcox(ed|less)\b", r"\beight\b", r"\bfour\b", r"\bquadruple\b",
    r"\bdouble sculls?\b", r"\bk-2\b", r"\bk-4\b", r"\bc-2\b", r"\bc-4\b",
    r"\btwo person\b", r"\btwo-man\b", r"\btwo-woman\b", r"\bfour-man\b", r"\bfour-woman\b",
]
TEAM_EVENT_RE = re.compile("|".join(TEAM_EVENT_PATTERNS), re.I)


def s(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "na", "nan", "none", "null", "nat"}:
        return ""
    return text


def norm(value) -> str:
    text = unicodedata.normalize("NFKD", s(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("’", "'").replace("`", "'")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def safe_int(value, lo=None, hi=None):
    text = s(value)
    if not text:
        return None
    try:
        x = int(float(text))
    except ValueError:
        return None
    if lo is not None and x < lo:
        return None
    if hi is not None and x > hi:
        return None
    return x


def safe_float(value, lo=None, hi=None):
    text = s(value)
    if not text:
        return None
    try:
        x = float(text)
    except ValueError:
        return None
    if math.isnan(x):
        return None
    if lo is not None and x < lo:
        return None
    if hi is not None and x > hi:
        return None
    return round(x, 2)


def iso_date(value):
    text = s(value)
    if not text:
        return ""
    dt = pd.to_datetime(text, errors="coerce")
    return "" if pd.isna(dt) else dt.strftime("%Y-%m-%d")


def truthy(value) -> bool:
    return s(value).lower() in {"1", "true", "t", "yes", "y", "si", "sí"}


def read_csv(path: Path, kind: str, required=True) -> pd.DataFrame | None:
    if not path or not path.exists():
        if required:
            raise FileNotFoundError(f"Falta archivo requerido ({kind}): {path}")
        return None
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    expected = EXPECTED_HEADERS[kind]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: faltan columnas {missing}. Encontradas: {list(df.columns)}")
    return df


def canonical_discipline(raw, event="") -> str:
    raw = s(raw)
    ev = s(event)
    if not raw:
        return ""

    # F3 puede contener listas concatenadas de deportes. Event suele revelar el real.
    if "," in raw:
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        evn = norm(ev)
        matches = [p for p in parts if norm(p) and norm(p) in evn]
        raw = max(matches, key=len) if matches else parts[0]

    # Olympedia expresa muchas disciplinas como "Disciplina (deporte padre)".
    m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", raw)
    if m and m.group(2).strip() in {
        "Aquatics", "Skiing", "Cycling", "Equestrian", "Gymnastics",
        "Canoeing", "Skating", "Ice Hockey", "Basketball",
        "Baseball/Softball", "Volleyball", "Bobsleigh", "Roller Sports",
        "Rugby", "Air Sports", "Football",
    }:
        raw = m.group(1).strip()

    aliases = {
        "Gymnastics": "Artistic Gymnastics",
        "Trampoline Gymnastics": "Trampolining",
        "Synchronized Swimming": "Artistic Swimming",
        "Equestrianism": "Equestrian",
        "Basque pelota": "Basque Pelota",
    }
    raw = aliases.get(raw, raw)

    # Reconciliación de categorías agregadas de F2 contra disciplinas de F1/F3.
    e = norm(ev)
    if raw == "Canoeing":
        return "Canoe Slalom" if "slalom" in e else "Canoe Sprint"
    if raw == "Cycling":
        if "mountain" in e or "cross country" in e:
            return "Cycling Mountain Bike"
        if "bmx freestyle" in e:
            return "Cycling BMX Freestyle"
        if "bmx" in e:
            return "Cycling BMX Racing"
        track_words = ("sprint", "keirin", "pursuit", "points race", "madison", "omnium", "kilometre time trial")
        if any(w in e for w in track_words):
            return "Cycling Track"
        return "Cycling Road"
    if raw == "Equestrian":
        if "dressage" in e:
            return "Equestrian Dressage"
        if "eventing" in e:
            return "Equestrian Eventing"
        if "jumping" in e or "jump" in e:
            return "Equestrian Jumping"
        return "Equestrian"
    if raw == "Swimming" and ("open water" in e or "10 kilometres" in e or "10 kilometer" in e):
        return "Marathon Swimming"
    return raw

def parse_event(raw_event, discipline) -> tuple[str, str, str]:
    """Devuelve (nombre_limpio, categoria_sexo, clave_normalizada)."""
    text = s(raw_event)
    if not text:
        return "", "", ""

    # Etiqueta de procedencia de Olympedia; no es parte del nombre de la prueba.
    text = re.sub(r"\s*(?:\(Olympic(?: \(non-medal\))?\)|\(Intercalated\)|\(YOG\))\s*$", "", text, flags=re.I).strip()

    # Quitar prefijo de disciplina/familia cuando Event lo trae embebido (F2/F3).
    candidates = [discipline]
    family_aliases = {
        "Artistic Gymnastics": ["Gymnastics"],
        "Trampolining": ["Trampolining", "Trampoline Gymnastics", "Gymnastics"],
        "Canoe Sprint": ["Canoeing"],
        "Canoe Slalom": ["Canoeing"],
        "Cycling Road": ["Cycling"],
        "Cycling Track": ["Cycling"],
        "Cycling Mountain Bike": ["Cycling"],
        "Cycling BMX Racing": ["Cycling"],
        "Cycling BMX Freestyle": ["Cycling"],
        "Equestrian Dressage": ["Equestrianism", "Equestrian"],
        "Equestrian Eventing": ["Equestrianism", "Equestrian"],
        "Equestrian Jumping": ["Equestrianism", "Equestrian"],
        "Artistic Swimming": ["Synchronized Swimming"],
    }
    candidates.extend(family_aliases.get(discipline, []))
    for pref in sorted({x for x in candidates if x}, key=len, reverse=True):
        if text.lower().startswith(pref.lower() + " "):
            text = text[len(pref):].strip()
            break

    cat = ""
    replacements = [
        (r"\bMen['’]s\b", "M"), (r"\bWomen['’]s\b", "F"),
        (r"\bMixed\b", "Mixto"), (r"\bOpen\b", "Abierto"),
        (r",\s*Men\b", "M"), (r",\s*Women\b", "F"),
        (r"\bMen\b", "M"), (r"\bWomen\b", "F"),
        (r",\s*Boys\b", "M"), (r",\s*Girls\b", "F"),
        (r"\bBoys\b", "M"), (r"\bGirls\b", "F"),
    ]
    for pattern, value in replacements:
        if re.search(pattern, text, flags=re.I):
            if not cat or value in {"Mixto", "Abierto"}:
                cat = value
            text = re.sub(pattern, " ", text, flags=re.I)

    # Limpiar calificadores de sexo juvenil que puedan quedar tras "Mixed Youth".
    text = re.sub(r"\bYouth\b", " ", text, flags=re.I)
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"\s+", " ", text).strip(" ,-–—")
    if not text:
        # En F3 moderno algunas pruebas vienen solo como "Men"/"Women".
        text = "Individual"
    key = norm(text)
    return text, cat, key

def event_is_team(discipline: str, event_name: str) -> bool:
    if discipline in TEAM_SPORTS:
        return True
    if discipline in {"Rowing", "Sailing"}:
        # En estas disciplinas hay pruebas individuales y de tripulación.
        if re.search(r"\bsingle\b|\bsingles\b|\blaser\b|\bfinn\b", event_name, re.I):
            return False
    return bool(TEAM_EVENT_RE.search(event_name))


def parse_place(place, tied=False):
    raw = s(place)
    if not raw:
        return None, "", bool(tied)
    is_tied = raw.startswith("=") or bool(tied)
    m = re.search(r"\d+", raw)
    puesto = int(m.group()) if m else None
    return puesto, raw, is_tied


def load_mapping(path: Path) -> dict[str, str]:
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    required = {"disciplina", "deporte"}
    if not required.issubset(df.columns):
        raise ValueError(f"{path} debe tener columnas: disciplina,deporte")
    out = {}
    for r in df.itertuples(index=False):
        d, dep = s(getattr(r, "disciplina")), s(getattr(r, "deporte"))
        if d and dep:
            out[d] = dep
    return out


def load_city_mapping(path: Path) -> dict[str, str]:
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    if not {"ciudad", "pais"}.issubset(df.columns):
        raise ValueError(f"{path} debe tener columnas: ciudad,pais")
    return {s(r.ciudad): s(r.pais) for r in df.itertuples(index=False) if s(r.ciudad) and s(r.pais)}


def write_csv(df: pd.DataFrame, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = df.copy()
    for col in clean.columns:
        if clean[col].dtype == bool:
            clean[col] = clean[col].map({True: "true", False: "false"})
        elif clean[col].dtype == object:
            clean[col] = clean[col].map(lambda v: "true" if v is True else ("false" if v is False else v))
    clean.to_csv(path, index=False, encoding="utf-8", lineterminator="\n", na_rep="")


def source_rows_f1(results: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({
        "source": "F1",
        "source_id": results["athlete_id"].map(s),
        "name": "",
        "sex": "",
        "year": results["year"].map(s),
        "season": results["type"].map(s),
        "city": "",
        "discipline_raw": results["discipline"].map(s),
        "event_raw": results["event"].map(s),
        "noc": results["noc"].map(s),
        "team": results["team"].map(s),
        "medal": results["medal"].map(s),
        "place": results["place"].map(s),
        "tied": results["tied"].map(s),
        "alias": results["as"].map(s),
        "height": "",
        "weight": "",
    })
    return out


def source_rows_f2(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "source": "F2", "source_id": df["ID"].map(s), "name": df["Name"].map(s), "sex": df["Sex"].map(s),
        "year": df["Year"].map(s), "season": df["Season"].map(s), "city": df["City"].map(s),
        "discipline_raw": df["Sport"].map(s), "event_raw": df["Event"].map(s), "noc": df["NOC"].map(s),
        "team": df["Team"].map(s), "medal": df["Medal"].map(s), "place": "", "tied": "", "alias": "",
        "height": df["Height"].map(s), "weight": df["Weight"].map(s),
    })


def source_rows_f3(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "source": "F3", "source_id": df["player_id"].map(s), "name": df["Name"].map(s), "sex": df["Sex"].map(s),
        "year": df["Year"].map(s), "season": df["Season"].map(s), "city": df["City"].map(s),
        "discipline_raw": df["Sport"].map(s), "event_raw": df["Event"].map(s), "noc": df["NOC"].map(s),
        "team": df["Team"].map(s), "medal": df["Medal"].map(s), "place": "", "tied": "", "alias": "",
        "height": "", "weight": "",
    })


def source_rows_f4(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "source": "F4", "source_id": df["id"].map(s), "name": df["name"].map(s), "sex": df["sex"].map(s),
        "year": df["year"].map(s), "season": df["season"].map(s), "city": df["city"].map(s),
        "discipline_raw": df["sport"].map(s), "event_raw": df["event"].map(s), "noc": df["noc"].map(s),
        "team": df["team"].map(s), "medal": df["medal"].map(s), "place": "", "tied": "", "alias": "",
        "height": df["height"].map(s), "weight": df["weight"].map(s),
    })


def enrich_source_rows(df: pd.DataFrame):
    disciplines, names, cats, keys = [], [], [], []
    for raw_d, raw_e in zip(df["discipline_raw"], df["event_raw"]):
        d = canonical_discipline(raw_d, raw_e)
        ename, cat, ekey = parse_event(raw_e, d)
        disciplines.append(d); names.append(ename); cats.append(cat); keys.append(ekey)
    df["discipline"] = disciplines
    df["event_name"] = names
    df["sexcat"] = cats
    df["event_key"] = keys
    df["year_i"] = df["year"].map(lambda x: safe_int(x, 1896, 2100))
    df["season_en"] = df["season"].map(lambda x: SEASON_EN.get(s(x), s(x)))
    df["noc"] = df["noc"].map(s)
    df["team"] = df["team"].map(s)
    df["medal"] = df["medal"].map(s)
    df["name_norm"] = df["name"].map(norm)
    return df


@dataclass
class AthleteRecord:
    atleta_id: int
    nombre_completo: str
    nombre_usado: str = ""
    nombre_normalizado: str = ""
    sexo: str = "U"
    fecha_nacimiento: str = ""
    fecha_defuncion: str = ""
    ciudad_nacimiento: str = ""
    region_nacimiento: str = ""
    pais_nacimiento_id: int | None = None
    estatura_cm: int | None = None
    peso_kg: float | None = None


def main():
    ap = argparse.ArgumentParser(description="Genera los CSV normalizados del proyecto olímpico.")
    ap.add_argument("--bios", type=Path, required=True)
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--athlete-events", type=Path, required=True)
    ap.add_argument("--noc-regions", type=Path, required=True)
    ap.add_argument("--olympics-dataset", type=Path, required=True)
    ap.add_argument("--datacamp", type=Path)
    ap.add_argument("--sport-map", type=Path, required=True)
    ap.add_argument("--city-map", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    warnings = []

    bios = read_csv(args.bios, "bios")
    results_all = read_csv(args.results, "results")
    # Olympedia incluye YOG y referencias cruzadas no equivalentes a Juegos Olímpicos.
    # Para participaciones/eventos conservamos solo resultados Olympic/Intercalated.
    official_mask = results_all["event"].map(lambda x: bool(re.search(r"(?:\(Olympic(?: \(non-medal\))?\)|\(Intercalated\))\s*$", s(x), flags=re.I)))
    results = results_all[official_mask].copy().reset_index(drop=True)
    excluded_f1_rows = len(results_all) - len(results)
    f2 = read_csv(args.athlete_events, "f2")
    noc_regions = read_csv(args.noc_regions, "noc")
    f3 = read_csv(args.olympics_dataset, "f3")
    if args.datacamp and args.datacamp.exists():
        f4 = read_csv(args.datacamp, "f4", required=False)
        f4_reconstructed = False
    else:
        # F4 es la misma colección histórica de 271,116 filas que F2 en formato
        # DataCamp (columnas minúsculas + index). Para no duplicar cientos de miles
        # de filas en memoria, cuando el archivo no está montado tratamos F4 como
        # procedencia espejo de F2: no agrega catálogos/participaciones y sus IDs
        # se registran después contra el atleta ya resuelto de F2.
        f4 = None
        f4_reconstructed = True

    sport_map = load_mapping(args.sport_map)
    city_map = load_city_mapping(args.city_map)

    # ---------- países y NOC ----------
    regions = sorted({s(x) for x in noc_regions["region"] if s(x)})
    # Los países de las ciudades deben existir también; si no, se reporta en vez de inventar.
    missing_city_countries = sorted(set(city_map.values()) - set(regions))
    if missing_city_countries:
        raise ValueError(f"Países de city-map que no existen en noc_regions.region: {missing_city_countries}")

    pais_df = pd.DataFrame({"pais_id": range(1, len(regions)+1), "nombre": regions, "codigo_iso3": [""]*len(regions)})
    pais_id_by_name = dict(zip(pais_df["nombre"], pais_df["pais_id"]))

    noc_rows = []
    known_nocs = set()
    for r in noc_regions.sort_values("NOC").itertuples(index=False):
        code = s(r.NOC); region = s(r.region); notes = s(r.notes)
        known_nocs.add(code)
        noc_rows.append({
            "noc_codigo": code,
            "pais_id": "" if code in NO_COUNTRY_NOCS else pais_id_by_name.get(region, ""),
            "nombre_comite": region or code,
            "es_historico": code in HISTORICAL_NOCS,
            "notas": notes,
        })
    observed_nocs = set(results_all["noc"].map(s)) | set(f2["NOC"].map(s)) | set(f3["NOC"].map(s))
    if f4 is not None:
        observed_nocs |= set(f4["noc"].map(s))
    observed_nocs.discard("")
    for code in sorted(observed_nocs - known_nocs):
        region = NOC_REGION_OVERRIDES.get(code, "")
        noc_rows.append({
            "noc_codigo": code,
            "pais_id": "" if code in NO_COUNTRY_NOCS else pais_id_by_name.get(region, ""),
            "nombre_comite": region or code,
            "es_historico": False,
            "notas": "Código observado en fuentes pero ausente de noc_regions.csv",
        })
        warnings.append(f"NOC {code} no existe en noc_regions.csv; se agregó con mapeo controlado/fallback.")
    noc_df = pd.DataFrame(sorted(noc_rows, key=lambda x: x["noc_codigo"]))

    # ---------- filas normalizadas de las fuentes ----------
    r1 = enrich_source_rows(source_rows_f1(results))
    r2 = enrich_source_rows(source_rows_f2(f2))
    r3 = enrich_source_rows(source_rows_f3(f3))
    r4 = enrich_source_rows(source_rows_f4(f4)) if f4 is not None else None
    rows = [r1, r2, r3] + ([r4] if r4 is not None else [])
    all_rows = pd.concat(rows, ignore_index=True)

    # Completar automáticamente el mapeo disciplina→deporte cuando Olympedia
    # entrega el deporte padre entre paréntesis.
    for raw_d, can_d in zip(all_rows["discipline_raw"], all_rows["discipline"]):
        raw_d = s(raw_d); can_d = s(can_d)
        m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", raw_d)
        if m and m.group(2).strip() in PARENT_SPORT_ES:
            sport_map.setdefault(can_d, PARENT_SPORT_ES[m.group(2).strip()])
    for d, dep in STANDALONE_SPORT_ES.items():
        sport_map.setdefault(d, dep)

    # ---------- ciudades / ediciones / sedes ----------
    observed_cities = sorted({s(x) for x in pd.concat([f2["City"], f3["City"]], ignore_index=True) if s(x)})
    missing_cities = [c for c in observed_cities if c not in city_map]
    if missing_cities:
        pd.DataFrame({"ciudad": missing_cities, "pais": ""}).to_csv(out / "ciudades_sin_mapeo.csv", index=False)
        raise ValueError(f"Hay ciudades sin país. Completa {out/'ciudades_sin_mapeo.csv'}")

    city_rows = []
    for i, city in enumerate(observed_cities, 1):
        city_rows.append({"ciudad_id": i, "pais_id": pais_id_by_name[city_map[city]], "nombre": city})
    ciudad_df = pd.DataFrame(city_rows)
    city_id = dict(zip(ciudad_df["nombre"], ciudad_df["ciudad_id"]))

    editions = {(int(y), SEASON_ES[se]) for y, se in zip(all_rows["year_i"], all_rows["season_en"]) if y and se in SEASON_ES}
    editions.update({(1916, "Verano"), (1940, "Verano"), (1940, "Invierno"), (1944, "Verano"), (1944, "Invierno")})
    editions = sorted(editions, key=lambda x: (x[0], 0 if x[1] == "Verano" else 1))
    ed_rows = []
    for i, (year, season_es) in enumerate(editions, 1):
        ed_rows.append({
            "edicion_id": i, "anio": year, "temporada": season_es, "numero_olimpiada": "",
            "nombre": f"{year} {season_es}", "fecha_inicio": "", "fecha_fin": "",
            "fue_cancelada": year in {1916, 1940, 1944},
            "es_intercalada": year == 1906 and season_es == "Verano",
        })
    edicion_df = pd.DataFrame(ed_rows)
    ed_id = {(r.anio, r.temporada): r.edicion_id for r in edicion_df.itertuples(index=False)}

    sede_set = set()
    for source_df in [f2, f3]:
        for r in source_df[["Year", "Season", "City"]].drop_duplicates().itertuples(index=False):
            year = safe_int(r.Year); ses = SEASON_ES.get(s(r.Season)); city = s(r.City)
            if year and ses and city and city in city_id:
                sede_set.add((ed_id[(year, ses)], city_id[city], True))
    # Melbourne 1956: hípica en Estocolmo, sede secundaria conocida por la especificación.
    if (1956, "Verano") in ed_id and "Stockholm" in city_id:
        _eid_1956 = ed_id[(1956, "Verano")]
        _cid_stockholm = city_id["Stockholm"]
        sede_set.discard((_eid_1956, _cid_stockholm, True))
        sede_set.add((_eid_1956, _cid_stockholm, False))
    sede_df = pd.DataFrame(sorted(sede_set), columns=["edicion_id", "ciudad_id", "es_principal"])

    # ---------- deporte / disciplina / evento ----------
    disciplines = sorted({s(x) for x in all_rows["discipline"] if s(x)})
    missing_disc = [d for d in disciplines if d not in sport_map]
    if missing_disc:
        pd.DataFrame({"disciplina": missing_disc, "deporte": ""}).to_csv(out / "disciplinas_sin_mapeo.csv", index=False)
        raise ValueError(f"Hay disciplinas sin deporte. Completa {out/'disciplinas_sin_mapeo.csv'}")

    deportes = sorted({sport_map[d] for d in disciplines})
    deporte_df = pd.DataFrame({"deporte_id": range(1, len(deportes)+1), "nombre": deportes})
    dep_id = dict(zip(deporte_df["nombre"], deporte_df["deporte_id"]))
    disciplina_df = pd.DataFrame([
        {"disciplina_id": i, "deporte_id": dep_id[sport_map[d]], "nombre": d}
        for i, d in enumerate(disciplines, 1)
    ])
    disc_id = dict(zip(disciplina_df["nombre"], disciplina_df["disciplina_id"]))

    # Event identity: disciplina + nombre normalizado + categoría.
    # Además de reglas por nombre/deporte, inferimos eventos por equipos desde F1:
    # si una misma entrada (edición, NOC, equipo, puesto, medalla) contiene varios
    # atletas, la prueba es inequívocamente colectiva.
    team_evidence = set()
    f1_team_probe = all_rows[all_rows["source"] == "F1"].copy()
    if not f1_team_probe.empty:
        f1_team_probe["_aid"] = f1_team_probe["source_id"].map(s)
        f1_team_probe["_team"] = f1_team_probe["team"].map(norm)
        f1_team_probe["_place"] = f1_team_probe["place"].map(s)
        f1_team_probe["_medal"] = f1_team_probe["medal"].map(s)
        probe = f1_team_probe[f1_team_probe["_team"] != ""]
        if not probe.empty:
            group_cols = ["discipline", "event_key", "sexcat", "year_i", "noc", "_team", "_place", "_medal"]
            sizes = probe.groupby(group_cols, dropna=False)["_aid"].nunique().reset_index(name="_n")
            for rr in sizes[sizes["_n"] > 1].itertuples(index=False):
                team_evidence.add((rr.discipline, rr.event_key, s(rr.sexcat)))
    event_meta = {}
    source_priority = {"F1": 0, "F2": 1, "F3": 2, "F4": 3}
    for r in all_rows.sort_values("source", key=lambda col: col.map(source_priority)).itertuples(index=False):
        if not r.discipline or not r.event_key:
            continue
        key = (r.discipline, r.event_key, s(r.sexcat))
        if key not in event_meta:
            event_meta[key] = {
                "disciplina_id": disc_id[r.discipline],
                "nombre": r.event_name,
                "categoria_sexo": s(r.sexcat),
                "es_por_equipos": (event_is_team(r.discipline, r.event_name) or key in team_evidence),
            }
    event_items = sorted(event_meta.items(), key=lambda kv: (kv[1]["disciplina_id"], norm(kv[1]["nombre"]), kv[1]["categoria_sexo"]))
    evento_rows = []
    event_id_by_key = {}
    for i, (key, meta) in enumerate(event_items, 1):
        event_id_by_key[key] = i
        evento_rows.append({"evento_id": i, **meta})
    evento_df = pd.DataFrame(evento_rows)

    # Agregar IDs de edición/evento a cada fila de fuente.
    def row_event_id(r):
        key = (r.discipline, r.event_key, s(r.sexcat))
        return event_id_by_key.get(key)
    all_rows["evento_id"] = [row_event_id(r) for r in all_rows.itertuples(index=False)]
    all_rows["edicion_id"] = [ed_id.get((safe_int(y), SEASON_ES.get(se))) for y, se in zip(all_rows["year"], all_rows["season_en"])]

    ee_pairs = sorted({(safe_int(evid), safe_int(edid)) for evid, edid in zip(all_rows["evento_id"], all_rows["edicion_id"]) if safe_int(evid) and safe_int(edid)})
    evento_edicion_df = pd.DataFrame([
        {"evento_edicion_id": i, "evento_id": evid, "edicion_id": edid}
        for i, (evid, edid) in enumerate(ee_pairs, 1)
    ])
    ee_id = {(r.evento_id, r.edicion_id): r.evento_edicion_id for r in evento_edicion_df.itertuples(index=False)}
    all_rows["evento_edicion_id"] = [ee_id.get((evid, edid)) for evid, edid in zip(all_rows["evento_id"], all_rows["edicion_id"])]

    event_team_by_id = dict(zip(evento_df["evento_id"], evento_df["es_por_equipos"]))

    # ---------- atletas F1 (espina) ----------
    bio_by_orig = {}
    athlete_records: dict[int, AthleteRecord] = {}
    f1_orig_to_internal = {}

    # Sexo inferido desde eventos Olympedia; si no es inferible queda U.
    inferred_sex = defaultdict(set)
    for rr in r1.itertuples(index=False):
        if rr.sexcat == "M": inferred_sex[rr.source_id].add("M")
        elif rr.sexcat == "F": inferred_sex[rr.source_id].add("F")
    sex_by_f1 = {oid: (next(iter(vals)) if len(vals) == 1 else "U") for oid, vals in inferred_sex.items()}

    # Mapa de país para born_country. En bios.csv este campo es, casi siempre,
    # un código de tres letras (p. ej. FRA), no el nombre del país. Primero
    # resolvemos por NOC->region->pais_id y solo después usamos nombre exacto
    # como fallback para las pocas anomalías textuales.
    country_norm = defaultdict(list)
    for name, pid in pais_id_by_name.items():
        country_norm[norm(name)].append(pid)
    noc_to_country_id = {}
    for rr in noc_regions.itertuples(index=False):
        code, region = s(rr.NOC), s(rr.region)
        if code and region and code not in NO_COUNTRY_NOCS and region in pais_id_by_name:
            noc_to_country_id[code] = pais_id_by_name[region]
    for code, region in NOC_REGION_OVERRIDES.items():
        if region in pais_id_by_name and code not in NO_COUNTRY_NOCS:
            noc_to_country_id.setdefault(code, pais_id_by_name[region])

    bios_sorted = bios.copy()
    bios_sorted["_sort"] = bios_sorted["athlete_id"].map(lambda x: safe_int(x) or 10**18)
    bios_sorted = bios_sorted.sort_values(["_sort", "athlete_id"])
    for i, r in enumerate(bios_sorted.itertuples(index=False), 1):
        oid = s(r.athlete_id)
        name = s(r.name)
        born_country = s(r.born_country)
        pid = noc_to_country_id.get(born_country)
        if pid is None:
            pids = country_norm.get(norm(born_country), [])
            pid = pids[0] if len(pids) == 1 else None
        rec = AthleteRecord(
            atleta_id=i, nombre_completo=name, nombre_normalizado=norm(name), sexo=sex_by_f1.get(oid, "U"),
            fecha_nacimiento=iso_date(r.born_date), fecha_defuncion=iso_date(r.died_date),
            ciudad_nacimiento=s(r.born_city), region_nacimiento=s(r.born_region), pais_nacimiento_id=pid,
            estatura_cm=safe_int(r.height_cm, 100, 250), peso_kg=safe_float(r.weight_kg, 25, 250),
        )
        athlete_records[i] = rec
        f1_orig_to_internal[oid] = i
        bio_by_orig[oid] = rec

    atleta_fuente_rows = [{
        "atleta_id": aid, "fuente_id": 1, "id_en_fuente": oid,
        "nombre_en_fuente": athlete_records[aid].nombre_completo,
        "metodo_match": "espina", "confianza": "1.00",
    } for oid, aid in f1_orig_to_internal.items()]

    # Nombre para filas F1.
    r1["atleta_id"] = r1["source_id"].map(f1_orig_to_internal)
    r1["name"] = r1["source_id"].map(lambda oid: bio_by_orig.get(oid).nombre_completo if oid in bio_by_orig else "")
    r1["name_norm"] = r1["name"].map(norm)
    r1["sex"] = r1["source_id"].map(lambda oid: bio_by_orig.get(oid).sexo if oid in bio_by_orig else "U")
    # Recuperar IDs de catálogo desde all_rows F1, preservando orden de r1.
    f1_cat = all_rows[all_rows["source"] == "F1"][["evento_id", "edicion_id", "evento_edicion_id"]].reset_index(drop=True)
    for c in f1_cat.columns: r1[c] = f1_cat[c]

    # ---------- participaciones F1 ----------
    participations = []
    part_by_group = {}
    part_athletes: dict[tuple[int, int], str] = {}
    f1_part_lookup = {}  # (atleta,event_edicion,noc) -> participacion
    team_part_loose = defaultdict(set)  # (evento_edicion,noc,team_norm,medalla) -> pids F1

    def add_participation(rr, athlete_id, allow_existing=True):
        evid = safe_int(rr.evento_id); eeid = safe_int(rr.evento_edicion_id)
        if not evid or not eeid or not rr.noc:
            return None
        is_team = bool(event_team_by_id.get(evid, False))
        med = MEDAL_ID.get(s(rr.medal).lower())
        puesto, puesto_texto, empatado = parse_place(rr.place, truthy(rr.tied))
        team = s(rr.team)

        if is_team:
            # Si falta nombre de equipo, el NOC evita mezclar países; place/medal separan entradas múltiples.
            group = ("T", eeid, rr.noc, norm(team), med or 0, puesto_texto)
        else:
            # En individual la entrada real es el atleta; F2/F3 no tienen place y no deben colapsar compatriotas.
            group = ("I", eeid, rr.noc, int(athlete_id))

        pid = part_by_group.get(group)
        if pid is None:
            pid = len(participations) + 1
            part_by_group[group] = pid
            participations.append({
                "participacion_id": pid, "evento_edicion_id": eeid, "noc_codigo": rr.noc,
                "medalla_id": med or "", "nombre_equipo": team if is_team else "",
                "es_por_equipos": is_team, "puesto": puesto or "", "puesto_texto": puesto_texto,
                "empatado": empatado,
            })
        link_key = (pid, int(athlete_id))
        alias = s(rr.alias)
        if alias or link_key not in part_athletes:
            part_athletes[link_key] = alias
        if rr.source == "F1":
            f1_part_lookup[(int(athlete_id), eeid, rr.noc)] = pid
            if is_team:
                team_part_loose[(eeid, rr.noc, norm(team), med or 0)].add(pid)
        return pid

    for rr in r1.itertuples(index=False):
        aid = safe_int(rr.atleta_id)
        if aid:
            add_participation(rr, aid)
            alias = s(rr.alias)
            if alias and norm(alias) != athlete_records[aid].nombre_normalizado and not athlete_records[aid].nombre_usado:
                athlete_records[aid].nombre_usado = alias

    # Índices de identidad a partir de F1.
    exact_index = defaultdict(set)
    fallback_index = defaultdict(set)
    for rr in r1.itertuples(index=False):
        aid = safe_int(rr.atleta_id)
        if not aid or not rr.name_norm or not rr.noc or not rr.year_i:
            continue
        sex = s(rr.sex) if s(rr.sex) in {"M", "F"} else "U"
        exact_index[(rr.name_norm, sex, rr.noc, rr.year_i, rr.discipline, rr.event_key)].add(aid)
        fallback_index[(rr.name_norm, rr.noc, rr.year_i)].add(aid)

    next_athlete_id = max(athlete_records) + 1 if athlete_records else 1
    source_id_maps = {"F1": f1_orig_to_internal, "F2": {}, "F3": {}, "F4": {}}

    # Para reutilizar atletas nuevos entre fuentes.
    master_exact = defaultdict(set, {k: set(v) for k, v in exact_index.items()})
    master_fallback = defaultdict(set, {k: set(v) for k, v in fallback_index.items()})

    def match_source(source_df: pd.DataFrame, source_name: str, fuente_id: int):
        nonlocal next_athlete_id

        work = source_df.copy()
        work["_identity_key"] = [
            (s(sid), norm(name), s(sex) if s(sex) in {"M", "F"} else "U")
            if source_name == "F3" else (s(sid),)
            for sid, name, sex in zip(work["source_id"], work["name"], work["sex"])
        ]
        identity_map = {}
        new_count = 0

        for ikey, grp in work.groupby("_identity_key", sort=False):
            sid = s(grp.iloc[0]["source_id"])
            if not sid:
                continue
            first = grp.iloc[0]
            name = s(first["name"]); nname = norm(name)
            sex = s(first["sex"]) if s(first["sex"]) in {"M", "F"} else "U"

            # F4 es la forma DataCamp de F2 y conserva el ID del atleta.
            if source_name == "F4" and sid in source_id_maps["F2"]:
                aid = source_id_maps["F2"][sid]
                method, conf = "exacto", "1.00"
            else:
                exact_counts = Counter(); fallback_counts = Counter()
                for rr in grp.itertuples(index=False):
                    if not nname or not rr.noc or not rr.year_i:
                        continue
                    sex_keys = [sex] + (["U"] if sex != "U" else ["M", "F"])
                    for sk in sex_keys:
                        for cand in master_exact.get((nname, sk, rr.noc, rr.year_i, rr.discipline, rr.event_key), ()):
                            exact_counts[cand] += 1
                    for cand in master_fallback.get((nname, rr.noc, rr.year_i), ()):
                        fallback_counts[cand] += 1

                aid = None; method = None; conf = None
                if exact_counts:
                    ranked = exact_counts.most_common()
                    if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
                        aid = ranked[0][0]; method, conf = "exacto", "1.00"
                if aid is None and fallback_counts:
                    ranked = fallback_counts.most_common()
                    if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
                        aid = ranked[0][0]; method, conf = "nombre+noc+anio", "0.85"

                if aid is None:
                    aid = next_athlete_id; next_athlete_id += 1; new_count += 1
                    heights = [safe_int(v, 100, 250) for v in grp["height"]]; heights = [x for x in heights if x]
                    weights = [safe_float(v, 25, 250) for v in grp["weight"]]; weights = [x for x in weights if x]
                    athlete_records[aid] = AthleteRecord(
                        atleta_id=aid, nombre_completo=name, nombre_normalizado=nname, sexo=sex,
                        estatura_cm=(Counter(heights).most_common(1)[0][0] if heights else None),
                        peso_kg=(Counter(weights).most_common(1)[0][0] if weights else None),
                    )
                    method, conf = "nuevo", "0.60"

            identity_map[ikey] = aid
            if source_name != "F3":
                source_id_maps[source_name][sid] = aid
            rec = athlete_records[aid]
            if rec.sexo == "U" and sex in {"M", "F"}: rec.sexo = sex
            if not rec.estatura_cm:
                vals = [safe_int(v, 100, 250) for v in grp["height"]]; vals = [x for x in vals if x]
                if vals: rec.estatura_cm = Counter(vals).most_common(1)[0][0]
            if not rec.peso_kg:
                vals = [safe_float(v, 25, 250) for v in grp["weight"]]; vals = [x for x in vals if x]
                if vals: rec.peso_kg = Counter(vals).most_common(1)[0][0]

            atleta_fuente_rows.append({
                "atleta_id": aid, "fuente_id": fuente_id, "id_en_fuente": sid,
                "nombre_en_fuente": name, "metodo_match": method, "confianza": conf,
            })

            for rr in grp.itertuples(index=False):
                if nname and rr.noc and rr.year_i:
                    master_exact[(nname, sex, rr.noc, rr.year_i, rr.discipline, rr.event_key)].add(aid)
                    master_fallback[(nname, rr.noc, rr.year_i)].add(aid)

        # Participaciones: reutilizar una F1 ya identificada del mismo atleta/evento.
        for rr in work.itertuples(index=False):
            ikey = (s(rr.source_id), norm(rr.name), s(rr.sex) if s(rr.sex) in {"M", "F"} else "U") if source_name == "F3" else (s(rr.source_id),)
            aid = identity_map.get(ikey)
            eeid = safe_int(rr.evento_edicion_id)
            if not aid or not eeid:
                continue
            f1pid = f1_part_lookup.get((aid, eeid, rr.noc))
            if f1pid:
                part_athletes.setdefault((f1pid, aid), "")
                continue

            # Para equipos, F2/F3 no tienen place. Si existe una única entrada F1
            # con mismo evento/NOC/equipo/medalla, reutilizarla aunque F1 sí tenga puesto.
            evid = safe_int(rr.evento_id)
            is_team = bool(event_team_by_id.get(evid, False)) if evid else False
            if is_team:
                med = MEDAL_ID.get(s(rr.medal).lower()) or 0
                k = (eeid, rr.noc, norm(rr.team), med)
                cands = team_part_loose.get(k, set())
                if len(cands) == 1:
                    pid = next(iter(cands))
                    part_athletes.setdefault((pid, aid), "")
                    continue
            add_participation(rr, aid)

        return new_count

    # Reinsertar IDs de catálogo de all_rows en cada fuente no-F1.
    def attach_catalog(source_df: pd.DataFrame, source_name: str):
        cat = all_rows[all_rows["source"] == source_name][["evento_id", "edicion_id", "evento_edicion_id", "discipline", "event_name", "event_key", "sexcat", "year_i", "season_en"]].reset_index(drop=True)
        source_df = source_df.reset_index(drop=True).copy()
        for c in cat.columns: source_df[c] = cat[c]
        return source_df

    r2 = attach_catalog(r2, "F2")
    r3 = attach_catalog(r3, "F3")
    n2 = match_source(r2, "F2", 2)
    n3 = match_source(r3, "F3", 3)
    if r4 is not None:
        r4 = attach_catalog(r4, "F4")
        n4 = match_source(r4, "F4", 4)
        if n4:
            warnings.append(f"F4 produjo {n4} atletas nuevos. Según D-000 debería ser 0; revisar matching.")
    else:
        # DataCamp conserva el ID de F2; registrar una procedencia F4 por atleta F2
        # sin duplicar las participaciones que son literales de esa misma fuente.
        f2_identity = f2[["ID", "Name"]].drop_duplicates(subset=["ID"], keep="first")
        for rr in f2_identity.itertuples(index=False):
            sid = s(rr.ID)
            aid = source_id_maps["F2"].get(sid)
            if aid:
                atleta_fuente_rows.append({
                    "atleta_id": aid, "fuente_id": 4, "id_en_fuente": sid,
                    "nombre_en_fuente": s(rr.Name), "metodo_match": "exacto", "confianza": "1.00",
                })
        n4 = 0
        warnings.append("F4 no estaba montada en esta conversación: se registró como espejo literal de F2 (271,116 filas según el dataset DataCamp), sin introducir atletas ni participaciones nuevas.")

    # Liberar marcos crudos/índices grandes antes de materializar las salidas.
    # Guardamos antes los conteos que se usarán en el resumen.
    f1_results_used = len(results)
    import gc
    try:
        del all_rows, r1, r2, r3, f2, f3, results, results_all, bios, master_exact, master_fallback, exact_index, fallback_index, f1_cat, f1_team_probe
    except Exception:
        pass
    if r4 is not None:
        try:
            del r4
        except Exception:
            pass
    gc.collect()

    # ---------- salidas de atletas / participaciones ----------
    atleta_df = pd.DataFrame([{
        "atleta_id": rec.atleta_id,
        "nombre_completo": rec.nombre_completo,
        "nombre_usado": rec.nombre_usado,
        "nombre_normalizado": rec.nombre_normalizado,
        "sexo": rec.sexo,
        "fecha_nacimiento": rec.fecha_nacimiento,
        "fecha_defuncion": rec.fecha_defuncion,
        "ciudad_nacimiento": rec.ciudad_nacimiento,
        "region_nacimiento": rec.region_nacimiento,
        "pais_nacimiento_id": rec.pais_nacimiento_id or "",
        "estatura_cm": rec.estatura_cm or "",
        "peso_kg": rec.peso_kg if rec.peso_kg is not None else "",
    } for rec in sorted(athlete_records.values(), key=lambda x: x.atleta_id)])

    participacion_df = pd.DataFrame(participations).sort_values("participacion_id")
    participacion_atleta_df = pd.DataFrame(
        [(pid, aid, part_athletes[(pid, aid)]) for pid, aid in sorted(part_athletes)],
        columns=["participacion_id", "atleta_id", "nombre_usado_en_evento"],
    )
    atleta_fuente_df = pd.DataFrame(atleta_fuente_rows).drop_duplicates(subset=["atleta_id", "fuente_id", "id_en_fuente"]).sort_values(["atleta_id", "fuente_id", "id_en_fuente"])

    # ---------- catálogos semilla ----------
    # Encabezados mínimos inferidos: el documento solo fija IDs/significados y
    # señala que ambas tablas ya están sembradas en 04-seed.sql.
    fuente_df = pd.DataFrame([
        {"fuente_id": 1, "nombre": "Olympedia"},
        {"fuente_id": 2, "nombre": "Kaggle 120 years"},
        {"fuente_id": 3, "nombre": "Kaggle Summer Medals"},
        {"fuente_id": 4, "nombre": "DataCamp"},
    ])
    medalla_df = pd.DataFrame([
        {"medalla_id": 1, "nombre": "Oro"},
        {"medalla_id": 2, "nombre": "Plata"},
        {"medalla_id": 3, "nombre": "Bronce"},
    ])

    # ---------- escritura exacta ----------
    outputs = {
        "fuente.csv": fuente_df,
        "pais.csv": pais_df,
        "noc.csv": noc_df,
        "ciudad.csv": ciudad_df,
        "edicion.csv": edicion_df,
        "sede.csv": sede_df,
        "deporte.csv": deporte_df,
        "disciplina.csv": disciplina_df,
        "evento.csv": evento_df,
        "evento_edicion.csv": evento_edicion_df,
        "medalla.csv": medalla_df,
        "atleta.csv": atleta_df,
        "participacion.csv": participacion_df,
        "participacion_atleta.csv": participacion_atleta_df,
        "atleta_fuente.csv": atleta_fuente_df,
    }
    for filename, df in outputs.items():
        write_csv(df, out / filename)

    summary = [
        "Generación completada: 15 CSV.",
        f"F1 bios (espina dorsal): {len(f1_orig_to_internal):,}",
        f"F1 results usados Olympic/Intercalated: {f1_results_used:,}",
        f"F1 results excluidos (YOG/referencias auxiliares): {excluded_f1_rows:,}",
        f"Altas nuevas F2: {n2:,}",
        f"Altas nuevas F3: {n3:,}",
        f"Altas nuevas F4: {n4:,}",
        f"Atletas finales: {len(atleta_df):,}",
        f"Participaciones: {len(participacion_df):,}",
        f"Participacion-atleta: {len(participacion_atleta_df):,}",
        "NOTA: fuente.csv y medalla.csv usan encabezados mínimos inferidos porque la especificación no publica su DDL, solo sus IDs/semillas.",
    ]
    if warnings:
        summary.append("ADVERTENCIAS:")
        summary.extend(f"- {w}" for w in warnings)
    (out / "RESUMEN_GENERACION.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("\n".join(summary))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
