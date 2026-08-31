#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# preparar-fuentes.sh
#
# Reconstruye los datos crudos que el repositorio NO versiona por tamano:
#   - data/raw/    descomprimiendo los .zip originales de fuentes/
#   - sources/     clonando el repositorio publico de Olympedia (KeithGalli)
#
# Uso:  ./scripts/preparar-fuentes.sh
#
# Proyecto Fase 1 - Sistemas de Bases de Datos 2 - USAC
# ---------------------------------------------------------------------------
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RAIZ"

echo "==> Raiz del proyecto: $RAIZ"

# --- 1. Descomprimir las fuentes de Kaggle -------------------------------
echo "==> Descomprimiendo fuentes de Kaggle en data/raw/"
mkdir -p data/raw
unzip -o -q "fuentes/kaggle-120-years-olympic-history.zip"        -d data/raw
unzip -o -q "fuentes/kaggle-summer-olympics-medals-1896-2024.zip" -d data/raw

# --- 2. Normalizar noc_regions.csv (hallazgo de calidad D-001) ------------
# El archivo viene con saltos de linea CR (Mac clasico): `wc -l` reporta 0 y
# un COPY directo cargaria todo el archivo como una sola fila.
NOC="data/raw/noc_regions.csv"
if [ -f "$NOC" ] && [ "$(wc -l < "$NOC")" -eq 0 ]; then
  echo "==> Normalizando saltos de linea CR -> LF en noc_regions.csv"
  tr '\r' '\n' < "$NOC" > "$NOC.tmp" && mv "$NOC.tmp" "$NOC"
fi

# --- 3. Clonar el repositorio de Olympedia --------------------------------
if [ -d "sources/keithgalli/.git" ]; then
  echo "==> sources/keithgalli ya existe, omitiendo clon"
else
  echo "==> Clonando KeithGalli/Olympics-Dataset en sources/keithgalli"
  mkdir -p sources
  git clone --depth 1 https://github.com/KeithGalli/Olympics-Dataset.git sources/keithgalli
fi

# --- 4. Verificacion ------------------------------------------------------
echo
echo "==> Verificacion de las fuentes"
verificar() {
  if [ -f "$1" ]; then
    printf '    OK   %-46s %8s filas\n' "$1" "$(($(wc -l < "$1") - 1))"
  else
    printf '    FALTA %-45s\n' "$1"; return 1
  fi
}
verificar "data/raw/athlete_events.csv"
verificar "data/raw/olympics_dataset.csv"
verificar "data/raw/noc_regions.csv"
verificar "sources/keithgalli/clean-data/bios.csv"
verificar "sources/keithgalli/clean-data/results.csv"
verificar "fuentes/datacamp-datalab-r-olympics.csv"

echo
echo "==> Fuentes listas."
