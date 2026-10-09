#!/usr/bin/env python3
"""Test double for an agent that answers the manual requests. Usage: fake_answer.py REQUESTS_DIR ANSWERS_DIR
For each request file it runs fake_agent.py on it and writes the JSON answer."""
import json, subprocess, sys
from pathlib import Path
req, ans = Path(sys.argv[1]), Path(sys.argv[2]); ans.mkdir(parents=True, exist_ok=True)
for f in sorted(req.glob('*.txt')):
    out = subprocess.run([sys.executable, str(Path(__file__).with_name('fake_agent.py'))], input=f.read_bytes(), capture_output=True).stdout.decode()
    res = [json.loads(l) for l in out.splitlines() if l.startswith('{')][-1]
    (ans / (f.stem + '.json')).write_text(res['result'])
