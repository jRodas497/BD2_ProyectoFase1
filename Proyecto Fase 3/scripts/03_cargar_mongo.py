#!/usr/bin/env python3
"""
Fase 3 — paso 3: carga a MongoDB los CSV corregidos (datos/corregidos/) como documentos.

Se ejecuta dentro del contenedor "loader":  scripts/ejecutar.sh py 03_cargar_mongo.py
Variables: MONGO_URI, MONGO_DB (las pone docker-compose).

Decisiones de modelado (justificación completa en docs/modelo-mongodb.md):
  * participaciones es la colección central y respeta el grano de la Fase 1: UNA entrada a un evento.
    Un equipo es UN documento con sus atletas embebidos -> el medallero cuenta documentos y no se infla.
  * Se desnormalizan edición, deporte, disciplina, evento y NOC dentro de cada participación para
    resolver las dos consultas del proyecto sin $lookup.
  * atletas guarda un resumen de medallas precalculado y la trazabilidad de fuentes embebida.
  * Los valores vacíos de los CSV se omiten del documento (no se guardan nulls ni cadenas vacías).
"""
import csv
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from pymongo import MongoClient

BASE = Path(__file__).resolve().parents[1]
DATOS = BASE / "datos" / "corregidos"
LOTE = 5000
MEDALLA = {"1": ("Oro", 1), "2": ("Plata", 2), "3": ("Bronce", 3)}


def ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg):
    print(f"[{ahora()}] {msg}", flush=True)


def leer(nombre):
    with open(DATOS / f"{nombre}.csv", newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def entero(v):
    return int(v) if v not in ("", None) else None


def numero(v):
    return float(v) if v not in ("", None) else None


def booleano(v):
    return v == "true"


def fecha(v):
    if not v:
        return None
    try:
        return datetime.strptime(v, "%Y-%m-%d")
    except ValueError:
        return None


def limpio(d):
    """Quita claves con valor None o cadena vacía (recursivo en dicts)."""
    return {k: (limpio(v) if isinstance(v, dict) else v) for k, v in d.items() if v not in (None, "")}


def insertar(col, docs, etiqueta):
    n, lote = 0, []
    for d in docs:
        lote.append(d)
        if len(lote) >= LOTE:
            col.insert_many(lote, ordered=False)
            n += len(lote)
            lote = []
    if lote:
        col.insert_many(lote, ordered=False)
        n += len(lote)
    log(f"  {etiqueta}: {n:,} documentos")
    return n


def main():
    # la base sale de la URI (…/olimpiadas); si la URI no la trae, de MONGO_DB
    db = MongoClient(os.environ["MONGO_URI"]).get_default_database(default=os.environ["MONGO_DB"])
    log(f"Carga a MongoDB, base '{db.name}', origen {DATOS}")

    # ------------------------------------------------------------------ catálogos en memoria
    pais_nombre = {}
    paises_base = {}
    for r in leer("pais"):
        pid = int(r["pais_id"])
        pais_nombre[pid] = r["nombre"]
        paises_base[pid] = r
    ciudades = {int(r["ciudad_id"]): (r["nombre"], int(r["pais_id"])) for r in leer("ciudad")}
    ediciones = {int(r["edicion_id"]): r for r in leer("edicion")}
    deportes = {int(r["deporte_id"]): r["nombre"] for r in leer("deporte")}
    disciplinas = {int(r["disciplina_id"]): (r["nombre"], int(r["deporte_id"])) for r in leer("disciplina")}
    eventos = {int(r["evento_id"]): r for r in leer("evento")}
    ev_ed = {int(r["evento_edicion_id"]): (int(r["evento_id"]), int(r["edicion_id"])) for r in leer("evento_edicion")}
    nocs = {r["noc_codigo"]: r for r in leer("noc")}

    # ------------------------------------------------------------------ comites
    log("Colección comites")
    docs = []
    for cod, r in nocs.items():
        pid = entero(r["pais_id"])
        docs.append(limpio({
            "_id": cod, "nombre_comite": r["nombre_comite"], "nombre_comite_fase1": r["nombre_comite_fase1"],
            "es_historico": booleano(r["es_historico"]), "notas": r["notas"],
            "pais_id": pid, "pais": pais_nombre.get(pid), "pais_es": paises_base[pid]["nombre_es"] if pid else None,
        }))
    db.comites.delete_many({})
    insertar(db.comites, docs, "comites")

    # ------------------------------------------------------------------ ediciones y sedes
    log("Colección ediciones")
    sedes_de = defaultdict(list)
    for r in leer("sede"):
        nom, pid = ciudades[int(r["ciudad_id"])]
        sedes_de[int(r["edicion_id"])].append(
            {"ciudad": nom, "pais_id": pid, "pais": pais_nombre[pid], "es_principal": booleano(r["es_principal"])})
    docs = []
    for eid, r in ediciones.items():
        docs.append(limpio({
            "_id": eid, "anio": int(r["anio"]), "temporada": r["temporada"],
            "numero_olimpiada": entero(r["numero_olimpiada"]), "nombre": r["nombre"],
            "fecha_inicio": fecha(r["fecha_inicio"]), "fecha_fin": fecha(r["fecha_fin"]),
            "fue_cancelada": booleano(r["fue_cancelada"]), "es_intercalada": booleano(r["es_intercalada"]),
            "sedes": sedes_de.get(eid, []),
        }))
    db.ediciones.delete_many({})
    insertar(db.ediciones, docs, "ediciones")

    # ------------------------------------------------------------------ paises (con NOC y años como sede)
    log("Colección paises")
    nocs_de = defaultdict(list)
    for cod, r in nocs.items():
        if r["pais_id"]:
            nocs_de[int(r["pais_id"])].append(limpio({
                "codigo": cod, "nombre_comite": r["nombre_comite"], "es_historico": booleano(r["es_historico"]),
                "notas": r["notas"]}))
    sedes_pais = defaultdict(list)
    for eid, lista in sedes_de.items():
        e = ediciones[eid]
        for s in lista:
            sedes_pais[s["pais_id"]].append({
                "edicion_id": eid, "anio": int(e["anio"]), "temporada": e["temporada"], "ciudad": s["ciudad"],
                "es_principal": s["es_principal"], "cancelada": booleano(e["fue_cancelada"])})
    docs = []
    for pid, r in paises_base.items():
        docs.append(limpio({
            "_id": pid, "nombre": r["nombre"], "nombre_es": r["nombre_es"], "codigo_iso3": r["codigo_iso3"],
            "nocs": nocs_de.get(pid, []),
            "sedes": sorted(sedes_pais.get(pid, []), key=lambda s: (s["anio"], s["temporada"])),
        }))
    db.paises.delete_many({})
    insertar(db.paises, docs, "paises")

    # ------------------------------------------------------------------ eventos (catálogo)
    log("Colección eventos")
    ediciones_de = defaultdict(list)
    for _, (evid, eid) in ev_ed.items():
        ediciones_de[evid].append(eid)
    docs = []
    for evid, r in eventos.items():
        dn, dep_id = disciplinas[int(r["disciplina_id"])]
        docs.append(limpio({
            "_id": evid, "nombre": r["nombre"], "categoria_sexo": r["categoria_sexo"],
            "es_por_equipos": booleano(r["es_por_equipos"]),
            "deporte": {"_id": dep_id, "nombre": deportes[dep_id]},
            "disciplina": {"_id": int(r["disciplina_id"]), "nombre": dn},
        }) | {"ediciones": sorted(ediciones_de.get(evid, []))})
    db.eventos.delete_many({})
    insertar(db.eventos, docs, "eventos")

    # ------------------------------------------------------------------ participaciones
    log("Colección participaciones (leyendo atletas para embeber sus nombres)")
    nombre_atleta = {}
    for r in leer("atleta"):
        nombre_atleta[int(r["atleta_id"])] = r["nombre_completo"]
    miembros = defaultdict(list)
    for r in leer("participacion_atleta"):
        aid = int(r["atleta_id"])
        miembros[int(r["participacion_id"])].append(
            limpio({"_id": aid, "nombre": nombre_atleta[aid], "nombre_usado_en_evento": r["nombre_usado_en_evento"]}))

    resumen = defaultdict(lambda: {"participaciones": 0, "oro": 0, "plata": 0, "bronce": 0,
                                   "anios": set(), "deportes": set()})

    def docs_participacion():
        for r in leer("participacion"):
            pid = int(r["participacion_id"])
            evid, edid = ev_ed[int(r["evento_edicion_id"])]
            ev, ed = eventos[evid], ediciones[edid]
            dn, dep_id = disciplinas[int(ev["disciplina_id"])]
            n = nocs[r["noc_codigo"]]
            pais_id = entero(n["pais_id"])
            med, med_ord = MEDALLA.get(r["medalla_id"], (None, None))
            atl = sorted(miembros[pid], key=lambda a: a["_id"])
            for a in atl:
                s = resumen[a["_id"]]
                s["participaciones"] += 1
                s["anios"].add(int(ed["anio"]))
                s["deportes"].add(deportes[dep_id])
                if med:
                    s[{"Oro": "oro", "Plata": "plata", "Bronce": "bronce"}[med]] += 1
            yield limpio({
                "_id": pid, "participacion_origen_id": entero(r["participacion_origen_id"]),
                "evento_edicion_id": int(r["evento_edicion_id"]),
                "edicion": {"_id": edid, "anio": int(ed["anio"]), "temporada": ed["temporada"], "nombre": ed["nombre"]},
                "deporte": {"_id": dep_id, "nombre": deportes[dep_id]},
                "disciplina": {"_id": int(ev["disciplina_id"]), "nombre": dn},
                "evento": {"_id": evid, "nombre": ev["nombre"], "categoria_sexo": ev["categoria_sexo"]},
                "noc": {"codigo": r["noc_codigo"], "nombre_comite": n["nombre_comite"], "es_historico": booleano(n["es_historico"])},
                "pais": {"_id": pais_id, "nombre": pais_nombre.get(pais_id)} if pais_id else None,
                "medalla": med, "medalla_orden": med_ord,
                "puesto": entero(r["puesto"]), "puesto_texto": r["puesto_texto"], "empatado": booleano(r["empatado"]),
                "nombre_equipo": r["nombre_equipo"], "es_por_equipos": booleano(r["es_por_equipos"]),
                "atletas": atl,
            })

    db.participaciones.delete_many({})
    insertar(db.participaciones, docs_participacion(), "participaciones")

    # ------------------------------------------------------------------ atletas (+ resumen + fuentes)
    log("Colección atletas (con resumen de medallas y trazabilidad de fuentes)")
    fuentes = {r["fuente_id"]: r["nombre"] for r in leer("fuente")}
    fuentes_de = defaultdict(list)
    for r in leer("atleta_fuente"):
        fuentes_de[int(r["atleta_id"])].append(limpio({
            "fuente_id": int(r["fuente_id"]), "fuente": fuentes[r["fuente_id"]], "id_en_fuente": r["id_en_fuente"],
            "nombre_en_fuente": r["nombre_en_fuente"], "metodo_match": r["metodo_match"],
            "confianza": numero(r["confianza"])}))

    def docs_atleta():
        for r in leer("atleta"):
            aid = int(r["atleta_id"])
            s = resumen.get(aid)
            res = None
            if s:
                res = {"participaciones": s["participaciones"], "oro": s["oro"], "plata": s["plata"], "bronce": s["bronce"],
                       "total_medallas": s["oro"] + s["plata"] + s["bronce"],
                       "primer_anio": min(s["anios"]), "ultimo_anio": max(s["anios"]), "deportes": sorted(s["deportes"])}
            ppid = entero(r["pais_nacimiento_id"])
            yield limpio({
                "_id": aid, "nombre_completo": r["nombre_completo"], "nombre_usado": r["nombre_usado"],
                "nombre_normalizado": r["nombre_normalizado"], "sexo": r["sexo"],
                "fecha_nacimiento": fecha(r["fecha_nacimiento"]), "fecha_defuncion": fecha(r["fecha_defuncion"]),
                "nacimiento": {"ciudad": r["ciudad_nacimiento"], "region": r["region_nacimiento"],
                               "pais_id": ppid, "pais": pais_nombre.get(ppid)},
                "estatura_cm": entero(r["estatura_cm"]), "peso_kg": numero(r["peso_kg"]),
                "resumen": res, "fuentes": fuentes_de.get(aid, []),
            })

    db.atletas.delete_many({})
    insertar(db.atletas, docs_atleta(), "atletas")
    log("Carga terminada")


if __name__ == "__main__":
    sys.exit(main())
