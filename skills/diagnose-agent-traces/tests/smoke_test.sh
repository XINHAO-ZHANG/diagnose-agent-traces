#!/bin/sh
# Smoke test: every stage on a made-up run, with a test double instead of a model. No account, no cost.
# Usage: sh tests/smoke_test.sh
set -e
HERE=$(cd "$(dirname "$0")/.." && pwd)
T=$(mktemp -d)
cd "$HERE"
python3 tests/make_sample_run.py "$T/run" >/dev/null
echo "== stages 0 and 1";            python3 scripts/stage01.py --run "$T/run" --out "$T/s01" | tail -3
echo "== free check";                python3 scripts/pipeline.py --run "$T/run" --base "$T/run" --work "$T/w1" --name NEW --base-name BASE | tail -3
echo "== annotate with a command";   FAKE_PLAIN=1 python3 scripts/pipeline.py --run "$T/run" --base "$T/run" --work "$T/w2" --name NEW --base-name BASE \
    --annotate --backend command --command "FAKE_PLAIN=1 python3 $HERE/tests/fake_agent.py" --model fake | tail -2
test -s "$T/w2/REPORT.md"
echo "== annotate with the current agent (manual)"
python3 scripts/pipeline.py --run "$T/run" --work "$T/w3" --name NEW --annotate --backend manual --model fake >/dev/null || [ $? -eq 4 ]
for d in "$T"/w3/packets/*/annotations/*; do python3 tests/fake_answer.py "$d/requests" "$d/answers"; done
python3 scripts/pipeline.py --run "$T/run" --work "$T/w3" --name NEW --annotate --backend manual --model fake | tail -1
test -s "$T/w3/REPORT.md"
echo "== a broken run must stop at stage 0"
mkdir -p "$T/bad"; cp "$T/run/benchmark.json" "$T/bad/"
if python3 scripts/stage01.py --run "$T/bad" --out "$T/sbad" >/dev/null; then echo "FAIL: stage 0 passed on a broken run"; exit 1; fi
echo "SMOKE TEST OK"
