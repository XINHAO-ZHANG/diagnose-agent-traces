#!/usr/bin/env python3
"""Test double for an agent that answers the manual requests. Usage: fake_answer.py REQUESTS_DIR ANSWERS_DIR
For each request file it runs fake_agent.py on it and writes the JSON answer."""
import json, subprocess, sys
from pathlib import Path
req, ans = Path(sys.argv[1]), Path(sys.argv[2]); ans.mkdir(parents=True, exist_ok=True)
for f in sorted(req.glob('*.txt')):
    if '.packet.' in f.name:
        continue
    pk = req.parent.parent.parent.parent / 'packets' / (f.stem + '.json')       # PK/annotations/<pass>/requests -> PK/packets
    if not pk.exists():
        pk = req.parent.parent.parent / 'packets' / (f.stem + '.json')
    head = f.read_text().split('\n\n## UNIT PACKET\n\n')[0]
    msg = head + '\n\n## UNIT PACKET\n\n' + json.dumps(json.loads(pk.read_text()), ensure_ascii=False, separators=(',', ':'))
    out = subprocess.run([sys.executable, str(Path(__file__).with_name('fake_agent.py'))], input=msg.encode(), capture_output=True).stdout.decode()
    res = [json.loads(l) for l in out.splitlines() if l.startswith('{')][-1]
    (ans / (f.stem + '.json')).write_text(res['result'])
