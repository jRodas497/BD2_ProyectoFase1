# Fase 3 — Olimpiadas en MongoDB

**Universidad de San Carlos de Guatemala** · Facultad de Ingeniería · Escuela de Ciencias y Sistemas
**Sistemas de Bases de Datos 2** — 2do. Semestre 2026 · Enunciado: `Enunciado proyecto 3.pdf`

Los datos de la Fase 1 migrados a **MongoDB 7**, con lo que falló en la carga relacional corregido, más dos
consultas: por **atleta** y por **país**.

## Inicio rápido

```bash
cd "Proyecto Fase 3"
cp .env.example .env                 # ajustar la clave
scripts/cargar_todo.sh               # MongoDB + correcciones + colecciones + carga + índices + validación (~65 s)

scripts/consulta_atleta.sh "Usain Bolt"
scripts/consulta_atleta.sh "Michael Phelps" Swimming "" 2012     # nombre [deporte] [pais] [anio]
scripts/consulta_pais.sh Guatemala
scripts/consulta_pais.sh Francia 2024                            # pais [anio] [temporada] [deporte] [medalla]
```
Solo requiere Docker. MongoDB queda en el puerto **27018** con volumen persistente.
También funciona contra un cluster de **MongoDB Atlas** definiendo `MONGO_URI` en `.env` (guía, sección 10).

## Qué contiene

| Entrega del enunciado | Dónde |
|---|---|
| a) datos de la Fase 1 en MongoDB, completos y corregidos | `scripts/01_corregir_datos.py`, `scripts/03_cargar_mongo.py`, [`docs/reporte-correcciones.md`](docs/reporte-correcciones.md) |
| b) scripts de colecciones, índices y carga + archivos fuente + bitácora con fecha y hora | `scripts/02_*.js`, `04_*.js`, `datos/fase1/`, `logs/` |
| c) método por atleta (con filtros deporte, país, año) | `scripts/consulta_atleta.sh` |
| d) método por país (participaciones, medallas, resultados, años, sede) | `scripts/consulta_pais.sh` |

## Documentación

- [`docs/guia-mongodb.md`](docs/guia-mongodb.md): guía paso a paso con los comandos de MongoDB, las salidas reales y la solución de problemas.
- [`docs/modelo-mongodb.md`](docs/modelo-mongodb.md): por qué 6 colecciones, qué se embebe y qué se referencia, índices.
- [`docs/reporte-correcciones.md`](docs/reporte-correcciones.md): defectos de la Fase 1 corregidos, con cifras.

## Colecciones

| Colección | Documentos | Contenido |
|---|---|---|
| `participaciones` | 221 204 | una entrada a un evento; atletas, edición, deporte, evento y NOC embebidos |
| `atletas` | 239 678 | biografía, resumen de medallas, fuentes |
| `eventos` | 1 761 | catálogo deporte → disciplina → evento |
| `paises` | 205 | país, sus NOC y los años en que fue sede |
| `comites` | 236 | catálogo NOC (incluye comités disueltos) |
| `ediciones` | 63 | Juegos y sus ciudades sede |
