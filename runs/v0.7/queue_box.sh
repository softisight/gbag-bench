#!/usr/bin/env bash
# File d'attente de la box 3060 — relancée le 2026-09-26 après la pause (D9) :
#   1. v0.7 gemma4:12b (reprise) ;
#   2. v0.7 Bonsai 27B puis Spark-X2.5-4B, dès qu'ils sont installés (noms lus sur la box) ;
#   3. J6 gemma4:31b sur le jeu de test v0.6 (critère 2), sorties non lues ;
#   4. 031-B : le juge gemma4:31b, avant/après les faits, 3 passes.
set -u
cd <local-path>/gbag-bench
export OLLAMA_HOST=http://<your-ollama-host>:11434 PYTHONIOENCODING=utf-8
LOG=runs/v0.7/queue.log
log() { echo "[$(date +%H:%M)] $*" >> "$LOG"; }

log "reprise : v0.7 gemma4:12b"
python scripts/generate_v07.py --models gemma4:12b >> runs/v0.7/generate-local.log 2>&1
log "v0.7 gemma4:12b fini (rc=$?)"

tag() {  # le nom exact d'un modèle installé dont le nom contient $1 (insensible à la casse)
  curl -s -m 10 "$OLLAMA_HOST/api/tags" | python -c "
import json,sys
names=[m['name'] for m in json.load(sys.stdin)['models'] if '$1' in m['name'].lower()]
print(names[0] if names else '')"
}
for want in bonsai spark-x; do
  name=""
  for i in $(seq 1 360); do name=$(tag "$want"); [ -n "$name" ] && break; sleep 60; done
  if [ -z "$name" ]; then log "$want introuvable sur la box après 6 h : sauté"; continue; fi
  log "v0.7 $name"
  python scripts/generate_v07.py --models "$name" >> "runs/v0.7/generate-local-$want.log" 2>&1
  log "v0.7 $name fini (rc=$?)"
done

log "J6 sur test-v06"
python scripts/campaign_v06_test.py --j6 >> runs/v0.6/test/J6-queue.log 2>&1
log "J6 fini (rc=$?)"

log "031-B gemma4:31b, 3 passes"
cd <local-path>/DeskInsightCS-031B
DESKINSIGHT_031B_CASES="<local-path>/gbag-bench/runs/031b/cases.jsonl" \
DESKINSIGHT_031B_DB_DIR="<local-path>/gbag-bench/databases" \
DESKINSIGHT_031B_OUT="<local-path>/gbag-bench/runs/031b/measure.jsonl" \
DESKINSIGHT_031B_MODEL="gemma4:31b" \
DESKINSIGHT_031B_PASSES=3 \
"/c/Program Files/dotnet/dotnet.exe" test tests/DeskInsight.Tests --filter "FullyQualifiedName~Mesure031B" \
  -m:1 -nodeReuse:false >> <local-path>/gbag-bench/runs/031b/measure-console.log 2>&1
cd <local-path>/gbag-bench
log "031-B fini (rc=$?)"
