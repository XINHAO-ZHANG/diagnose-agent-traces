"""Shared helpers for stage 0 and stage 1 (stdlib only, python >= 3.8).
A run directory has `benchmark.json` and `transcripts/<game>-*_p0.txt` (DUCK format)."""
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

HDR = re.compile(r'^--- analysis_step=(\d+) \| action=(\d+) \| (\d\d:\d\d:\d\d) \| (.+?) ---$', re.M)
SECTION = re.compile(r'^\[(THINKING|MODEL RESPONSE META|USER PROMPT|SYSTEM PROMPT|ANALYZER STATUS|TOOL CALL[^\]\n]*|TOOL RESULT[^\]\n]*)\]$', re.M)
# Two different markers. The annotation builder writes '…[truncated N chars]…' (a cut of the text we give the
# annotator: always a FAIL). The harness writes '... [truncated N chars]' at the end of a tool output that the
# model itself saw cut (information only).
TRUNC_PACKET = re.compile(r'…\[truncated \d+ chars\]…')
TRUNC_HARNESS = re.compile(r'^\.\.\. \[truncated \d+ chars\]', re.M)


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def load_benchmark(run_dir):
    """Return {short_game_id: game_run dict}. Short id = game_id before the first '-'."""
    b = load_json(Path(run_dir) / 'benchmark.json')
    return {g['game_id'].split('-')[0]: g for g in b['game_runs']}


def find_transcript(run_dir, game):
    hits = sorted((Path(run_dir) / 'transcripts').glob(f'{game}-*_p0.txt'))
    return hits[0] if len(hits) == 1 else None, len(hits)


def parse_turns(path):
    """One dict per transcript record. Counts only; the text itself is not kept."""
    t = Path(path).read_text(encoding='utf-8', errors='replace')
    hs = list(HDR.finditer(t))
    turns = []
    for i, h in enumerate(hs):
        body = t[h.end(): hs[i + 1].start() if i + 1 < len(hs) else len(t)]
        st = body.split('[ANALYZER STATUS]')[-1] if '[ANALYZER STATUS]' in body else ''
        msg = re.search(r'^message:\s*(.*)$', st, re.M)
        err = re.search(r'^request_error:\s*(.*)$', st, re.M)
        rto = re.search(r'read timeout=([\d.]+)', err.group(1)) if err else None
        secs = list(SECTION.finditer(body))
        think = 0
        for j, s in enumerate(secs):
            if s.group(1) == 'THINKING':
                end = secs[j + 1].start() if j + 1 < len(secs) else len(body)
                think += len(body[s.end():end].strip())
        turns.append({
            'analysis_step': int(h.group(1)), 'action_hdr': int(h.group(2)), 'clock': h.group(3),
            'model_responses': body.count('[MODEL RESPONSE META]'),
            'tool_calls': len(re.findall(r'^\[TOOL CALL', body, re.M)),
            'reasoning_chars_reported': sum(int(x) for x in re.findall(r'^reasoning_chars:\s*(\d+)', body, re.M)),
            'thinking_chars_in_text': think,
            'truncation_markers': len(TRUNC_PACKET.findall(body)),
            'harness_tool_output_cuts': len(TRUNC_HARNESS.findall(body)),
            'message': msg.group(1).strip() if msg else None,
            'request_error': bool(err), 'read_timeout_s': float(rto.group(1)) if rto else None,
        })
    return turns


def clock_to_seconds(clock, start):
    """Seconds from `start` (datetime) to the next occurrence of HH:MM:SS (handles midnight)."""
    c = datetime.combine(start.date(), datetime.strptime(clock, '%H:%M:%S').time())
    if c < start - timedelta(seconds=5):
        c += timedelta(days=1)
    return (c - start).total_seconds()


# ---- full record parser (stage 2). Same rules as skills/annotate-agent-trajectories/scripts/intake.py ----
RECORD_HEADER = re.compile(r'^--- analysis_step=(\d+) \| action=(\d+) \| (\d+:\d+:\d+) \| tool-agent ---$', re.M)
RECORD_SECTION = re.compile(r'^\[(SYSTEM PROMPT|USER PROMPT|MODEL RESPONSE META|THINKING|TOOL CALL: python|TOOL RESULT: python|ANALYZER STATUS)\][ \t]*\r?$', re.M)
OTHER_TOOL_SECTION = re.compile(r'^\[(TOOL CALL|TOOL RESULT)(?!: python\])[^\]\n]*\]\s*$', re.M)


def parse_records(path):
    """List of records with full section text. record_id = 'record-<n>', n = position of the header in the file."""
    text = Path(path).read_text(encoding='utf-8', errors='replace')
    headers = list(RECORD_HEADER.finditer(text))
    records = []
    for i, header in enumerate(headers):
        start = header.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        markers = list(RECORD_SECTION.finditer(text, start, end))
        sections = []
        for j, m in enumerate(markers):
            finish = markers[j + 1].start() if j + 1 < len(markers) else end
            sections.append({'kind': m[1], 'source_line': text.count('\n', 0, m.start()) + 1,
                             'text': text[m.end():finish].strip('\r\n')})
        records.append({'record_id': f'record-{i + 1}', 'source_line': text.count('\n', 0, header.start()) + 1,
                        'analysis_step': int(header[1]), 'header_action': int(header[2]), 'timestamp': header[3],
                        'sections': sections,
                        'other_tool_sections': len(OTHER_TOOL_SECTION.findall(text, start, end))})
    return records


def stamp_s(t):
    h, m, s = (int(x) for x in t.split(':'))
    return h * 3600 + m * 60 + s
