#!/usr/bin/env bash
# Ejecutar con una cuenta de respaldo y ~/.my.cnf privado, nunca con claves en argumentos.
set -euo pipefail
umask 077
DESTINO=${DESTINO:-/var/backups/laboratorios}
BASE=${BASE:-laboratorios}
if command -v mariadb-dump >/dev/null 2>&1; then
    DUMP=mariadb-dump
else
    DUMP=mysqldump
fi
mkdir -p "$DESTINO"
OPCIONES=()
if [[ -n ${MYSQL_CNF:-} ]]; then
    [[ -r "$MYSQL_CNF" ]] || { printf 'No se puede leer MYSQL_CNF\n' >&2; exit 1; }
    OPCIONES+=("--defaults-extra-file=$MYSQL_CNF")
fi
TEMPORAL=$(mktemp "$DESTINO/.laboratorios-XXXXXX.sql.gz.part")
trap 'rm -f -- "$TEMPORAL"' EXIT
"$DUMP" "${OPCIONES[@]}" --single-transaction --quick --skip-lock-tables --no-tablespaces \
    --triggers --default-character-set=utf8mb4 "$BASE" | gzip > "$TEMPORAL"
gzip -t "$TEMPORAL"
FINAL="$DESTINO/laboratorios-$(date +%Y%m%d-%H%M%S)-$$.sql.gz"
mv -- "$TEMPORAL" "$FINAL"
printf 'Respaldo completado: %s\n' "$FINAL"
# Retencion optativa: activarla solo despues de verificar copia externa y restauracion.
if [[ ${DEPURAR_RESPALDOS:-0} == 1 ]]; then
    find "$DESTINO" -maxdepth 1 -type f -name 'laboratorios-*.sql.gz' -mtime +30 -delete
fi
