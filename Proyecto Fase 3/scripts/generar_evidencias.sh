#!/usr/bin/env bash
# Corre consultas de ejemplo y guarda cada salida (con fecha y hora) en logs/consulta_*.log.
# Sirve como evidencia de los incisos (c) y (d) y de que las consultas responden en milisegundos.
cd "$(dirname "$0")/.."
mkdir -p logs
ej() { local f="logs/consulta_$1.log"; shift; { echo "\$ $*"; "$@"; } 2>&1 | tee "$f" | tail -1; }
ej atleta_usain_bolt        scripts/consulta_atleta.sh "Usain Bolt"
ej atleta_phelps_2012       scripts/consulta_atleta.sh "Michael Phelps" Swimming "" 2012
ej atleta_nadia_comaneci    scripts/consulta_atleta.sh "Nadia Comaneci"
ej atleta_bolt_ambiguo      scripts/consulta_atleta.sh "Bolt"
ej atleta_barrondo          scripts/consulta_atleta.sh "Erick Barrondo"
ej pais_guatemala           scripts/consulta_pais.sh Guatemala
ej pais_francia_2024        scripts/consulta_pais.sh Francia 2024
ej pais_usa_natacion_oro    scripts/consulta_pais.sh USA "" Verano Swimming Oro
ej pais_alemania            scripts/consulta_pais.sh Alemania
ej pais_urss                scripts/consulta_pais.sh "Soviet Union"
