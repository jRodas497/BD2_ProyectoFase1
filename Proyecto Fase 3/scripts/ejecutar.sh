#!/usr/bin/env bash
# Ejecuta un script de mongosh o de Python contra MongoDB.
# Uso: scripts/ejecutar.sh js <archivo.js> [-e VAR=valor ...]   ej.: scripts/ejecutar.sh js 04_indices.js
#      scripts/ejecutar.sh shell                                 abre mongosh interactivo en la base
#      scripts/ejecutar.sh eval '<expresión>'                    ejecuta UNA consulta suelta y muestra el resultado
#      scripts/ejecutar.sh py <archivo.py>                       script Python con pymongo (contenedor "loader")
#
# Dos modos, según .env:
#   LOCAL (por defecto): MongoDB en el contenedor de docker-compose (usuario/clave de .env).
#   NUBE  (si MONGO_URI está definida en .env): MongoDB Atlas u otro servidor remoto; no se usa el contenedor local.
#   MONGO_MODO=local en la línea de comandos obliga al modo local aunque .env tenga MONGO_URI.
cd "$(dirname "$0")/.."
set -a; source .env; set +a
export HOST_UID=$(id -u) HOST_GID=$(id -g)
# MONGO_MODO=local fuerza el MongoDB de Docker aunque .env tenga MONGO_URI (útil para alternar sin editar .env):
#   MONGO_MODO=local scripts/consulta_pais.sh Guatemala
[ "${MONGO_MODO:-}" = local ] && unset MONGO_URI
IMAGEN_MONGO="mongo:7.0"
if [ -n "${MONGO_URI:-}" ]; then
  MODO=nube; URI="$MONGO_URI"
else
  MODO=local; URI="mongodb://$MONGO_USER:$MONGO_PASSWORD@localhost:27017/$MONGO_DB?authSource=admin"
fi

# mongosh: en modo local dentro del contenedor "mongo"; en modo nube, con un contenedor de un solo uso
mongosh_run() {   # mongosh_run <interactivo:0|1> <args de mongosh...>
  local inter="$1"; shift
  local tty=0; [ "$inter" = 1 ] && [ -t 0 ] && tty=1      # solo pide terminal si hay una (si no, acepta texto por tubería)
  if [ "$MODO" = local ]; then
    local t=(-T); [ "$tty" = 1 ] && t=()
    docker compose exec "${t[@]}" "${ENV_ARGS[@]}" mongo mongosh "$URI" "$@"
  else
    local i=(-i); [ "$tty" = 1 ] && i=(-it)
    docker run --rm "${i[@]}" -e TZ=America/Guatemala "${ENV_ARGS[@]}" -v "$PWD/scripts:/scripts:ro" "$IMAGEN_MONGO" mongosh "$URI" "$@"
  fi
}

case "${1:?js|shell|eval|py}" in
  js)    shift; archivo="${1:?archivo .js}"; shift; ENV_ARGS=("$@")
         mongosh_run 0 --quiet --file "/scripts/$archivo" ;;
  shell) ENV_ARGS=(); mongosh_run 1 ;;
  eval)  shift; ENV_ARGS=(); mongosh_run 0 --quiet --eval "${1:?expresión de mongosh entre comillas}" ;;
  py)    shift; archivo="${1:?archivo .py}"
         # --no-deps: no exige el MongoDB local (en modo nube no existe)
         docker compose run --rm --no-deps -T -e MONGO_URI="${MONGO_URI:-mongodb://$MONGO_USER:$MONGO_PASSWORD@mongo:27017/?authSource=admin}" loader python "scripts/$archivo" ;;
esac
