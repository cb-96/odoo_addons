#!/usr/bin/env bash
# Run from the patched trusted repository checkout on pve0. No container recreation.
set -euo pipefail
[[ "$(id -u)" = 0 && "$(hostname)" = pve0 ]] || { echo 'Run as root on pve0'; exit 1; }
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STATE="${1:-/root/federation-provision/state/created.json}"
read -r CI_ID REPAIR_ID < <(python3 - "$STATE" <<'PY'
import json,sys
j=json.load(open(sys.argv[1]));print(int(j['runner_id']),int(j['repair_id']))
PY
)
[[ "$CI_ID" != 110 && "$REPAIR_ID" != 110 && "$CI_ID" != "$REPAIR_ID" ]] || exit 1
[[ "$(pct config "$CI_ID" | sed -n 's/^hostname: //p')" = federation-ci ]] || exit 1
[[ "$(pct config "$REPAIR_ID" | sed -n 's/^hostname: //p')" = federation-repair ]] || exit 1
# Avoid stopping a live incident; timers are stopped after this preflight.
pct exec "$REPAIR_ID" -- python3 - <<'PY'
import json
from pathlib import Path
p=Path('/var/lib/federation-repair/private/state.json')
if p.exists() and json.loads(p.read_text()).get('active'):
    raise SystemExit('Active/interrupted incident: stop and review before deployment')
PY
pct exec "$REPAIR_ID" -- systemctl disable --now federation-repair-controller.timer federation-repair-worker.timer
pct exec "$REPAIR_ID" -- systemctl stop federation-repair-controller.service federation-repair-worker.service
# Timestamped backups, including state, private to root. Tokens never copied to host.
BACKUP="/root/federation-repair-backup-$(date +%Y%m%d-%H%M%S)"
pct exec "$REPAIR_ID" -- mkdir -m 700 "$BACKUP"
pct exec "$REPAIR_ID" -- cp -a /opt/federation-repair /etc/federation-repair "$BACKUP/"
pct exec "$REPAIR_ID" -- bash -c 'if [ -f /var/lib/federation-repair/private/state.json ]; then cp /var/lib/federation-repair/private/state.json "$1/state.json"; fi' _ "$BACKUP"
for file in controller.py worker.py; do
 pct push "$REPAIR_ID" "$ROOT/ci/local/repair/$file" "/opt/federation-repair/$file" --perms 644
 done
pct push "$REPAIR_ID" "$ROOT/ci/local/repair/controller.json" /etc/federation-repair/controller.json --perms 640
pct exec "$REPAIR_ID" -- chown root:repairctl /etc/federation-repair/controller.json
pct push "$REPAIR_ID" "$ROOT/ci/local/repair/worker.json" /etc/federation-repair/worker.json --perms 644
# Allow serial full CI to finish: six suites plus lint/report, bounded by 8h per candidate.
pct exec "$REPAIR_ID" -- mkdir -p /etc/systemd/system/federation-repair-controller.service.d
TMP="$(mktemp)"; trap 'rm -f "$TMP"' EXIT
printf '[Service]\nTimeoutStartSec=26h\n' > "$TMP"
pct push "$REPAIR_ID" "$TMP" /etc/systemd/system/federation-repair-controller.service.d/full-ci-budget.conf --perms 644
pct exec "$REPAIR_ID" -- systemctl daemon-reload
pct exec "$REPAIR_ID" -- python3 -m py_compile /opt/federation-repair/controller.py /opt/federation-repair/worker.py
# Validate installed CLI flags before starting agent jobs.
pct exec "$REPAIR_ID" -- runuser -u hermes -- env HOME=/home/hermes /home/hermes/.local/bin/hermes chat --help > "$TMP"
for flag in --base-url --api-key --model --toolsets --max-turns --query-file; do
 grep -q -- "$flag" "$TMP" || { echo "Installed Hermes missing $flag. Timers remain OFF."; exit 1; }
 done
pct exec "$REPAIR_ID" -- curl --fail --connect-timeout 5 --max-time 15 http://192.168.178.90:11434/api/tags >/dev/null
# Test isolation: successful secret read is an error.
if pct exec "$REPAIR_ID" -- runuser -u hermes -- test -r /etc/federation-repair/secrets/controller.env; then
 echo 'Worker can read publishing token: STOP'; exit 1
fi
pct exec "$CI_ID" -- runuser -u ci -- docker compose version
pct exec "$CI_ID" -- bash -c 'cd /home/ci/actions-runner; ./svc.sh status'
echo "Updated existing repair container $REPAIR_ID. Backup: $BACKUP"
echo 'Publishing OFF. Timers OFF. Push the patch, then run activate.sh review on pve0.'
