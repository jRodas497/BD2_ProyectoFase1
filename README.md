# Base de Datos Unificada de Olimpiadas — Proyecto Fase 1

**Universidad de San Carlos de Guatemala** · Facultad de Ingeniería · Escuela de Ciencias y Sistemas
**Sistemas de Bases de Datos 2** — 2do. Semestre 2026

Unificación de cuatro fuentes públicas de datos olímpicos en una sola base de datos relacional
(PostgreSQL), con su modelo entidad-relación, scripts de carga y stored procedures de consulta.

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

## Estructura del repositorio

```
.
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
cd BD2_ProyectoFase1
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
