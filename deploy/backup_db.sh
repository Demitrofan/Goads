#!/bin/sh
# Ночная копия базы. Запускает goads-backup.timer (deploy/goads-backup.*).
# .backup делает целостную копию даже пока сборщик пишет в базу (cp живого файла может дать битую).
set -eu
umask 077
DIR=/srv/goads/backups
KEEP=7
mkdir -p "$DIR"
NAME="db_rielt-$(date +%Y-%m-%d).db"
TMP="$DIR/.$NAME.tmp"
rm -f "$TMP"
sqlite3 /srv/goads/db_rielt.db ".timeout 60000" ".backup '$TMP'"
# Копия должна открываться и быть целой — иначе не подменяем прошлую
[ "$(sqlite3 "$TMP" 'PRAGMA integrity_check;')" = "ok" ]
gzip -f "$TMP"
mv "$TMP.gz" "$DIR/$NAME.gz"
ln -sf "$NAME.gz" "$DIR/latest.db.gz"
# Оставляем 7 последних
ls -1t "$DIR"/db_rielt-*.db.gz | tail -n +$((KEEP + 1)) | xargs -r rm -f
echo "backup ok: $NAME.gz $(du -h "$DIR/$NAME.gz" | cut -f1)"
