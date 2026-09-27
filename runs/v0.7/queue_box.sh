#!/usr/bin/env bash
# Queue of the RTX 3060 box — relaunched on 2026-09-26 after the pause (D9):
#   1. v0.7 gemma4:12b (resumed);
#   2. v0.7 Bonsai 27B then Spark-X2.5-4B, as soon as they are installed (names read on the box);
#   3. J6 gemma4:31b on the v0.6 test set (criterion 2), outputs not read;
#   4. 031-B: the gemma4:31b judge of DeskInsight, before/after the facts, 3 passes.
# Comments and log messages translated from French on 2026-09-27; the commands are unchanged.
set -u
cd <local-path>/gbag-bench
export OLLAMA_HOST=http://<your-ollama-host>:11434 PYTHONIOENCODING=utf-8
LOG=runs/v0.7/queue.log
log() { echo "[$(date +%H:%M)] $*" >> "$LOG"; }

log "resume: v0.7 gemma4:12b"
python scripts/generate_v07.py --models gemma4:12b >> runs/v0.7/generate-local.log 2>&1
log "v0.7 gemma4:12b done (rc=$?)"

tag() {  # the exact name of an installed model whose name contains $1 (case-insensitive)
  curl -s -m 10 "$OLLAMA_HOST/api/tags" | python -c "
import json,sys
names=[m['name'] for m in json.load(sys.stdin)['models'] if '$1' in m['name'].lower()]
print(names[0] if names else '')"
}
for want in bonsai spark-x; do
  name=""
  for i in $(seq 1 360); do name=$(tag "$want"); [ -n "$name" ] && break; sleep 60; done
  if [ -z "$name" ]; then log "$want not found on the box after 6 h: skipped"; continue; fi
  log "v0.7 $name"
  python scripts/generate_v07.py --models "$name" >> "runs/v0.7/generate-local-$want.log" 2>&1
  log "v0.7 $name done (rc=$?)"
done

log "J6 on test-v06"
python scripts/campaign_v06_test.py --j6 >> runs/v0.6/test/J6-queue.log 2>&1
log "J6 done (rc=$?)"

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
log "031-B done (rc=$?)"
