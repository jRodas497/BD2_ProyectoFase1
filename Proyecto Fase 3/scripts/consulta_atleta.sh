#!/usr/bin/env bash
# Consulta (c): información de un atleta.
# Uso: scripts/consulta_atleta.sh "<nombre>" [deporte] [pais] [anio] [temporada] [medalla]
#   scripts/consulta_atleta.sh "Usain Bolt"
#   scripts/consulta_atleta.sh "Michael Phelps" Swimming "" 2012
#   scripts/consulta_atleta.sh "Bolt" Athletics JAM
# Use "" para omitir un parámetro intermedio. LIMITE=3 scripts/consulta_atleta.sh "Bolt" limita atletas detallados.
cd "$(dirname "$0")/.."
exec scripts/ejecutar.sh js consultas/consulta_atleta.js \
  -e "NOMBRE=${1:?uso: consulta_atleta.sh \"<nombre>\" [deporte] [pais] [anio] [temporada] [medalla]}" \
  -e "DEPORTE=${2:-}" -e "PAIS=${3:-}" -e "ANIO=${4:-}" -e "TEMPORADA=${5:-}" -e "MEDALLA=${6:-}" -e "LIMITE=${LIMITE:-10}"
