# Base de Datos Unificada de Olimpiadas — Proyecto Fase 2

> Esta carpeta es la **Fase 2** y donde continúa el desarrollo. Arranca como copia de Fase 1
> (que queda congelada en [`../Proyecto Fase 1/`](../Proyecto%20Fase%201/)). Todos los comandos se
> ejecutan desde aquí. Enunciado: `775_Proyecto_2_2S2026.pdf`. Visión general en el [README raíz](../README.md).
>
> Contenido heredado de Fase 1 (modelo, carga, SPs); lo específico de Fase 2 se documentará aquí.

**Universidad de San Carlos de Guatemala** · Facultad de Ingeniería · Escuela de Ciencias y Sistemas
**Sistemas de Bases de Datos 2** — 2do. Semestre 2026

Unificación de cuatro fuentes públicas de datos olímpicos en una sola base de datos relacional
(PostgreSQL), con su modelo entidad-relación, scripts de carga y stored procedures de consulta.

---

## Fase 2 — Respaldo y restauración físicos (Postgres 17)

Estrategia: `pg_basebackup` (full) + `pg_basebackup --incremental` (cadena incremental) y
`pg_combinebackup` para restaurar. Son respaldos **físicos**, no dumps. Requiere `summarize_wal=on`
(ya está en el `docker-compose.yml`). Los datos y los respaldos viven en **volúmenes distintos**
(`olimpiadas_f2_pgdata` y `olimpiadas_f2_backups`), ambos persistentes.

Tres tipos de carga, cada uno con 4 tramos (01 = carga inicial, 02..04 = cargas siguientes):

| Tipo | Tramos |
|------|--------|
| `anio` | París 2024 → Tokio 2020 → Río 2016 → Londres 2012 (Juegos completos) |
| `deporte` | 100 m planos femenino en París 2024 → Tokio 2020 → Río 2016 → Londres 2012 |
| `deportista` | Usain Bolt en Atenas 2004 → Pekín 2008 → Londres 2012 → Río 2016 |

```bash
cp .env.example .env                              # una vez
python3 scripts/02-carga/generar_cargas.py        # genera cargas/<tipo>/<NN_...>/*.csv desde staging/

scripts/ejecutar_ciclo.sh anio                    # ciclo completo de un tipo (carga, full, 3 incr., borrar, restaurar)

# o paso a paso (para las capturas):
scripts/reset_instancia.sh                        # instancia nueva y vacía
scripts/02-carga/cargar_tramo.sh anio 01          # carga inicial
scripts/05-validacion/validar.sh anio_carga01     # SELECT COUNT(*) y SELECT * de cada tabla
scripts/03-backup/backup_full.sh anio             # full  -> /backups/anio/full
scripts/02-carga/cargar_tramo.sh anio 02
scripts/03-backup/backup_incremental.sh anio 1    # inc1  -> /backups/anio/inc1
scripts/05-validacion/fragmentacion.sh anio_carga02   # pgstattuple: tablas e índices
scripts/04-restore/restaurar.sh anio 0            # elimina la base y restaura solo el full
scripts/04-restore/restaurar.sh anio 2            # elimina la base y restaura full+inc1+inc2
```

Manual completo: [`docs/manual-usuario.md`](docs/manual-usuario.md). Para tomar las capturas del
enunciado paso a paso: `scripts/guia_capturas.sh <tipo>`.

La documentación técnica de Persona 1 está en
[`docs/documentacion-tecnica.pdf`](docs/documentacion-tecnica.pdf), con su fuente editable en
[`docs/documentacion-tecnica.md`](docs/documentacion-tecnica.md).

Los tiempos quedan en `logs/tiempos.csv` (carga, backup, restore en tres medidas: reconstrucción de
archivos, recuperación hasta aceptar conexiones y total) y la salida de cada paso en `logs/*.log`.
`restaurar.sh` siempre parte de una base eliminada. Capturas: usar una terminal que muestre la hora
(los scripts también imprimen `date`).

---

## Estado de las entregas

| Inciso | Entregable | Fecha | Estado |
|--------|-----------|-------|--------|
| **(a)** | Modelo de datos y diagrama entidad-relación | 2-SEP-2026 | ✅ Completo |
| **(b)** | Extracción de fuentes y carga a base relacional | 19-SEP-2026 | ⬜ Pendiente |
| **(c)** | Scripts SQL: tablas, llaves, índices, carga | 19-SEP-2026 | ⬜ Pendiente |
| **(d)** | Stored procedure de consulta por atleta | 19-SEP-2026 | ⬜ Pendiente |
| **(e)** | Stored procedure de consulta por país | 19-SEP-2026 | ⬜ Pendiente |

---

## Estructura de esta carpeta

```
.
├── docker-compose.yml            Postgres 16 de Fase 2 (puerto 5435)
├── .env.example                  Plantilla de variables (copiar a .env)
├── diagramas/
│   └── modelo-er-olimpiadas.drawio   Diagrama ER (draw.io, XML plano editable)
├── docs/
│   ├── modelo-de-datos.md            Diccionario de datos, cardinalidades, normalización
│   ├── HANDOFF-decisiones.md         Bitácora de decisiones de diseño (D-000..D-014)
│   └── Enunciado proyecto 1.pdf      Enunciado original del curso
├── fuentes/
│   ├── kaggle-120-years-olympic-history.zip
│   ├── kaggle-summer-olympics-medals-1896-2024.zip
│   └── datacamp-datalab-r-olympics.csv
├── scripts/
│   └── preparar-fuentes.sh           Reconstruye data/raw/ y sources/
├── data/raw/                         (no versionado — generado por el script)
└── sources/                          (no versionado — generado por el script)
```

> `data/raw/` y `sources/` no se versionan: son 180 MB derivados de los `.zip` de `fuentes/` y de un
> repositorio público. `scripts/preparar-fuentes.sh` los reconstruye de forma determinista.

---

## Preparar el entorno

```bash
git clone https://github.com/jRodas497/BD2_ProyectoFase1.git
cd BD2_ProyectoFase1/"Proyecto Fase 2"
./scripts/preparar-fuentes.sh
```

El script descomprime las fuentes de Kaggle, **normaliza los saltos de línea CR de
`noc_regions.csv`** (ver decisión D-001), clona el repositorio de Olympedia y verifica el conteo de
filas de cada archivo.

---

## Fuentes de datos

| # | Fuente | Volumen | Cobertura | Aporte único |
|---|--------|---------|-----------|--------------|
| **F1** | [Olympedia / KeithGalli](https://github.com/KeithGalli/Olympics-Dataset) | 145,500 atletas · 308,408 resultados | 1896–2022, Verano e Invierno | Fecha de nacimiento y defunción, lugar de nacimiento, **puesto además de medalla** |
| **F2** | [Kaggle — 120 years of Olympic history](https://www.kaggle.com/datasets/heesoo37/120-years-of-olympic-history-athletes-and-results) | 271,116 filas | 1896–2016, Verano e Invierno | Ciudad sede por edición, nombres de equipo, catálogo NOC→región |
| **F3** | [Kaggle — Summer Olympics Medals 1896-2024](https://www.kaggle.com/datasets/stefanydeoliveira/summer-olympics-medals-1896-2024) | 252,565 filas | 1896–2024, solo Verano | **Tokio 2020 y París 2024** |
| **F4** | [DataCamp DataLab — r-olympics](https://www.datacamp.com/datalab/datasets/r-olympics) | 99 filas | muestra | Ninguno — es un subconjunto literal de F2 |
| **F5** | [olympics.com](https://www.olympics.com/) | — | — | Referencia de verificación de calidad |

---

## El modelo en una frase

**15 entidades, 16 relaciones.** Tres decisiones lo sostienen:

1. **`PARTICIPACION` tiene grano de *entrada al evento*, no de atleta.** El oro de baloncesto de
   EE.UU. 1992 es **una** fila con medalla y **doce** en `PARTICIPACION_ATLETA`. Cargar los CSV tal
   como vienen infla el medallero por país en miles de medallas.
2. **`NOC` está separado de `PAIS`.** `URS`, `GDR`, `TCH` y `YUG` son comités disueltos con medallas
   en el histórico. Sin la separación no se puede consultar *Alemania* como `GER + FRG + GDR + SAA`.
3. **Jerarquía `DEPORTE → DISCIPLINA → EVENTO`.** Reconcilia el `Sport` de Kaggle (66 valores) con el
   `Discipline` de Olympedia (94) sin forzar una fuente a la otra.

El detalle completo está en [`docs/modelo-de-datos.md`](docs/modelo-de-datos.md); el porqué de cada
decisión, con sus alternativas descartadas, en [`docs/HANDOFF-decisiones.md`](docs/HANDOFF-decisiones.md).

---

## Ver el diagrama

`diagramas/modelo-er-olimpiadas.drawio` es XML de draw.io **sin comprimir**, editable con:

- La extensión [Draw.io Integration](https://marketplace.visualstudio.com/items?itemName=hediet.vscode-drawio) de VS Code
- [app.diagrams.net](https://app.diagrams.net/) (Archivo → Abrir desde → Dispositivo)
