#!/usr/bin/env bash
set -euo pipefail

PATCH_FILE="${1:-registration_cutover.patch}"
SEQUENCE_FILE="sports_federation_portal/data/ir_sequence.xml"
V1_VIEW_FILE="sports_federation_portal/views/federation_tournament_registration_views.xml"

if [[ ! -f "$PATCH_FILE" ]]; then
  echo "ERROR: patch not found: $PATCH_FILE" >&2
  exit 2
fi

echo "[1/5] Validating patch against the current tree"
git apply --check --whitespace=error-all \
  --exclude="$SEQUENCE_FILE" \
  --exclude="$V1_VIEW_FILE" \
  "$PATCH_FILE"

echo "[2/5] Applying non-conflicting package changes"
git apply --whitespace=error-all \
  --exclude="$SEQUENCE_FILE" \
  --exclude="$V1_VIEW_FILE" \
  "$PATCH_FILE"

echo "[3/5] Removing V1 artifacts idempotently"
rm -f "$SEQUENCE_FILE" "$V1_VIEW_FILE"

echo "[4/5] Checking manifest references and patch whitespace"
if grep -Fq 'data/ir_sequence.xml' sports_federation_portal/__manifest__.py; then
  echo "ERROR: obsolete sequence file remains referenced by the portal manifest." >&2
  exit 4
fi
if grep -Fq 'views/federation_tournament_registration_views.xml' sports_federation_portal/__manifest__.py; then
  echo "ERROR: obsolete V1 views remain referenced by the portal manifest." >&2
  exit 5
fi
git diff --check

echo "[5/5] Running focused source contracts"
python ci/check_access_csv_integrity.py
python ci/check_registration_contract.py
python ci/check_addon_integrity.py
python ci/check_portal_competition_ownership.py
python ci/check_officiating_contract.py

echo "OK: Registration cutover package applied."
git status --short
