#!/bin/bash
set -e
chmod 750 /data/inventree/deploy.sh
echo "=== test de la sauvegarde ==="
/data/inventree/backup.sh
echo "=== installation du cron ==="
crontab -l 2>/dev/null | grep -v 'inventree/backup.sh' >/tmp/ct || true
echo '30 3 * * * /data/inventree/backup.sh >>/data/backups/backup.log 2>&1' >>/tmp/ct
crontab /tmp/ct
rm -f /tmp/ct
crontab -l | tail -2
echo "=== contenu de /data/backups ==="
ls -lh /data/backups
echo "=== integrite du dump ==="
gzip -t /data/backups/*.sql.gz && echo "gzip valide"
zcat /data/backups/*.sql.gz | grep -c "^CREATE TABLE" | sed 's/^/tables dans le dump : /'
