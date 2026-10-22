#!/usr/bin/env bash
# Consulta (d): información de un país.
# Uso: scripts/consulta_pais.sh "<pais>" [anio] [temporada] [deporte] [medalla]
#   scripts/consulta_pais.sh Guatemala
#   scripts/consulta_pais.sh "Francia" 2024
#   scripts/consulta_pais.sh USA "" Verano Swimming Oro
#   DETALLE=1 scripts/consulta_pais.sh Guatemala        lista todas las participaciones
# Acepta nombre (inglés/español), código NOC (USA, GUA, URS) o nombre de comité ("Soviet Union").
cd "$(dirname "$0")/.."
exec scripts/ejecutar.sh js consultas/consulta_pais.js \
  -e "PAIS=${1:?uso: consulta_pais.sh \"<pais>\" [anio] [temporada] [deporte] [medalla]}" \
  -e "ANIO=${2:-}" -e "TEMPORADA=${3:-}" -e "DEPORTE=${4:-}" -e "MEDALLA=${5:-}" -e "DETALLE=${DETALLE:-}" -e "TOPE=${TOPE:-150}"
