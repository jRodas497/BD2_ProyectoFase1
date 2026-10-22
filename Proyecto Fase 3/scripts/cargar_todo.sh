#!/usr/bin/env bash
# Ejecuta TODO el proceso de la Fase 3 de punta a punta y deja la bitácora con fecha y hora en logs/.
#   1 levantar MongoDB  2 corregir datos de Fase 1  3 crear colecciones  4 cargar documentos
#   5 crear índices     6 validar
# Uso: scripts/cargar_todo.sh        (repetible: recrea las colecciones desde cero)
cd "$(dirname "$0")/.."
mkdir -p logs
LOG="logs/carga_$(date +%Y%m%d_%H%M%S).log"
S=scripts
set -a; source .env; set +a; export HOST_UID=$(id -u) HOST_GID=$(id -g)
paso() { echo; echo "######## PASO $1 — $(date '+%F %T') ########"; }
{
  echo "Fase 3 — carga completa a MongoDB. Inicio: $(date '+%F %T %Z')   Equipo: $(uname -n)"
  T0=$(date +%s)
  if [ -n "${MONGO_URI:-}" ]; then
    paso "1/6: modo NUBE (MONGO_URI definida en .env): no se levanta MongoDB local"; docker compose build loader
    CHEQUEO=(docker run --rm mongo:7.0 mongosh "$MONGO_URI" --quiet --eval "db.runCommand({ping:1}).ok")
  else
    paso "1/6: levantar MongoDB";            docker compose up -d --wait mongo && docker compose build loader
    CHEQUEO=(docker compose exec -T mongo mongosh "mongodb://$MONGO_USER:$MONGO_PASSWORD@localhost:27017/admin?authSource=admin" --quiet --eval "db.runCommand({ping:1}).ok")
  fi
  # La clave de .env se fija al crear el volumen por primera vez: si se cambió después, MongoDB la rechaza
  if ! "${CHEQUEO[@]}" >/dev/null 2>&1; then
    echo
    echo "ERROR: MongoDB rechazó la conexión (Authentication failed o servidor inalcanzable)."
    echo "  Modo local: causa habitual, se cambió MONGO_PASSWORD en .env DESPUÉS de crear el volumen."
    echo "    Opción 1: devolver en .env la clave con la que se creó el volumen."
    echo "    Opción 2: usar la clave nueva y recrear el volumen: docker compose down -v && scripts/cargar_todo.sh"
    echo "  Modo nube: revisar MONGO_URI (usuario, clave, nombre del cluster) y que su IP esté permitida en Atlas."
    exit 1
  fi
  paso "2/6: corregir datos de Fase 1";    $S/ejecutar.sh py 01_corregir_datos.py
  paso "3/6: crear colecciones";           $S/ejecutar.sh js 02_crear_colecciones.js
  paso "4/6: cargar documentos";           $S/ejecutar.sh py 03_cargar_mongo.py
  paso "5/6: crear índices";               $S/ejecutar.sh js 04_indices.js
  paso "6/6: validar";                     $S/ejecutar.sh js 05_validar.js
  echo; echo "Fin: $(date '+%F %T %Z')   Duración total: $(( $(date +%s) - T0 )) s"
} 2>&1 | tee "$LOG"
status=${PIPESTATUS[0]}
echo "Bitácora guardada en $LOG"
exit "$status"
