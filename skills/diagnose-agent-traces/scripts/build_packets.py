"""Stage 2a: build annotation packets from raw transcripts. No model call.
Usage: python3 build_packets.py --run RUN_DIR --out OUT_DIR [--label RUN] [--harness unk_harness]
                                [--max-input-tokens 200000] [--games a,b]
One unit = one level segment of one game. A packet has the FULL text of every section (no cut).
The SYSTEM PROMPT section is the fixed harness prompt; it is not repeated in the packets.
Writes OUT_DIR/{packets/,inputs/,units.json,chunk_plan.json,build_audit.json}. Exit 1 if an audit check fails."""
import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

from lib import find_transcript, load_benchmark, parse_records, stamp_s

FROZEN = Path(__file__).resolve().parents[1] / 'references' / 'frozen-inputs'
FORMATS = {'v1.1': ('annotator-prompt-v1.1.md', 'output-contract-v1.1.json'),   # shares and one quote per turn
           'v1.2': ('annotator-prompt-v1.2.md', 'output-contract-v1.2.json')}   # summary, shares, reason, quote per turn
COMMON = ['addendum-full-traces.md', 'protocol.md', 'codebook-fm-v0.1.md']
FORMAT = ('TXT tool-agent transcript, FULL (untruncated); a record = one agent turn; '
          'Step k = k-th environment action of this level')  # frozen text: a change gives a new prompt, so keep it
# input tokens ~= TOK_A + TOK_B * message_chars (fit on 142 calls of gpt-5.6-luna-high)
TOK_A, TOK_B, CONTEXT = 20577, 0.3095, 272000
CUT = re.compile(r'…\[truncated \d+ chars\]…')


def est_tokens(chars):
    return int(TOK_A + TOK_B * chars)


def jlen(v):
    return len(json.dumps(v, ensure_ascii=False, separators=(',', ':')))


def level_of(apl, completed, idx):
    c = 0
    for i, a in enumerate(apl):
        c += a
        if idx <= c and a > 0:
            return i + 1
    return completed + 1


def packet_records(recs, boundary):
    start = recs[0]['header_action']
    out = []
    for i, rec in enumerate(recs):
        nxt = recs[i + 1] if i + 1 < len(recs) else boundary
        first = rec['header_action'] - start + 1
        last = (nxt['header_action'] - start) if nxt else None
        secs = [{'section_index': si, 'kind': s['kind'], 'source_line': s['source_line'], 'text': s['text']}
                for si, s in enumerate(rec['sections']) if s['kind'] != 'SYSTEM PROMPT']  # the fixed harness prompt is not repeated
        msg = next((ln.split(':', 1)[1].strip() for x in rec['sections'] if x['kind'] == 'ANALYZER STATUS'
                    for ln in x['text'].splitlines() if ln.startswith(('request_error:', 'message:'))), None)
        wall = stamp_s(nxt['timestamp']) - stamp_s(rec['timestamp']) if nxt else None
        if wall is not None and wall < 0:
            wall += 86400
        out.append({'record_id': rec['record_id'], 'source_line': rec['source_line'], 'timestamp': rec['timestamp'],
                    'turn_stats': {'reasoning_chars_full': sum(len(x['text']) for x in rec['sections'] if x['kind'] == 'THINKING'),
                                   'tool_code_chars_full': sum(len(x['text']) for x in rec['sections'] if x['kind'].startswith('TOOL CALL')),
                                   'model_calls': sum(1 for x in rec['sections'] if x['kind'] == 'THINKING'),
                                   'wall_seconds_to_next_record': wall,
                                   'actions_in_turn': (last - first + 1) if last is not None else None, 'turn_end_status': msg},
                    'level_steps_executed_in_this_record': [first, last] if last is None or last >= first else [],
                    'completed_actions_at_record_start': first - 1, 'sections': secs})
    tail = None
    if boundary:
        up = next((s for s in boundary['sections'] if s['kind'] == 'USER PROMPT'), None)
        tail = {'record_id': boundary['record_id'], 'note': 'first record of the next level (completion boundary)',
                'user_prompt': up['text'] if up else None}
    return {'format': FORMAT, 'truncation': 'none', 'records': out, 'completion_boundary': tail}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--run', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--label', default='RUN', help='prefix of the unit ids (default RUN)')
    ap.add_argument('--harness', default='unk_harness'); ap.add_argument('--games')
    ap.add_argument('--max-input-tokens', type=int, default=200000)
    ap.add_argument('--format', choices=sorted(FORMATS), default='v1.1',
                    help='annotation format. v1.1: shares and a quote per turn (the 2026-10-08 format). v1.2: also a summary and a reason per turn')
    a = ap.parse_args(argv)
    out = Path(a.out)
    if (out / 'units.json').exists():
        print(f'FAIL: {out}/units.json exists. Use a new output directory.'); return 1
    (out / 'packets').mkdir(parents=True, exist_ok=True); (out / 'inputs').mkdir(exist_ok=True)
    pf, cf = FORMATS[a.format]
    names = {pf: 'annotator-prompt.md', cf: 'output-contract.json'}
    for f in [pf, cf] + COMMON:
        shutil.copy2(FROZEN / f, out / 'inputs' / names.get(f, f))
    INPUT_FILES = ['annotator-prompt.md', 'output-contract.json'] + COMMON
    in_sha = {f: hashlib.sha256((out / 'inputs' / f).read_bytes()).hexdigest() for f in INPUT_FILES}
    prompt_chars = sum(len((out / 'inputs' / f).read_text()) for f in INPUT_FILES) + 200
    bench = load_benchmark(a.run)
    games = a.games.split(',') if a.games else sorted(bench)
    units, plan, fails, warns = [], [], [], []
    for g in games:
        B = bench[g]; apl = B['actions_per_level']
        path, _ = find_transcript(a.run, g)
        if path is None:
            fails.append(f'{g}: transcript not found'); continue
        recs = parse_records(path)
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        model = next((ln.split(':', 1)[1].strip() for r in recs for s in r['sections'] if s['kind'] == 'ANALYZER STATUS'
                      for ln in s['text'].splitlines() if ln.startswith('model:')), 'Unknown')
        sysp = {s['text'] for r in recs for s in r['sections'] if s['kind'] == 'SYSTEM PROMPT'}
        if len(sysp) > 1:
            warns.append(f'{g}: {len(sysp)} different system prompts in one run; packets omit them all')
        if any(r['other_tool_sections'] for r in recs):
            warns.append(f'{g}: sections of another tool than python exist; they are inside the previous section text')
        groups = []
        for r in recs:
            lv = level_of(apl, B['levels_completed'], r['header_action'])
            if groups and groups[-1][0] == lv:
                groups[-1][1].append(r)
            else:
                groups.append((lv, [r]))
        for gi, (lv, rs) in enumerate(groups):
            boundary = groups[gi + 1][1][0] if gi + 1 < len(groups) else None
            ex = packet_records(rs, boundary)
            uid = f'{a.label}__{g}__L{lv}__a1'
            cleared = lv <= B['levels_completed']
            ident = {'uid': uid, 'run_id': path.stem, 'harness': a.harness, 'model': model, 'game_id': g, 'level': lv,
                     'attempt': 1, 'source_sha256': sha,
                     'outcome_known_from_logs': {'cleared': True, 'actions': apl[lv - 1], 'terminal_status': 'cleared'} if cleared
                     else {'cleared': None, 'actions': None, 'terminal_status': 'timeout' if B['state'] == 'gave_up' else B['state']}}
            pk = {'unit': ident, 'raw_excerpt': ex}
            # audit: no cut marker made by us; the characters in the packet equal the characters in the source records
            src = sum(len(s['text']) for r in rs for s in r['sections'] if s['kind'] != 'SYSTEM PROMPT')
            got = sum(len(s['text']) for r in ex['records'] for s in r['sections'])
            if src != got or any(CUT.search(s['text']) for r in ex['records'] for s in r['sections']):
                fails.append(f'{uid}: packet text differs from source ({got} vs {src} chars) or has a cut marker')
            n = jlen(pk); est = est_tokens(prompt_chars + n)
            entry = {'uid': uid, 'packet_chars': n, 'est_input_tokens': est, 'chunks': 1, 'chunk_files': [f'{uid}.json']}
            if est > a.max_input_tokens:
                cap = int((a.max_input_tokens - TOK_A - 3000) / TOK_B) - prompt_chars - jlen(dict(pk, raw_excerpt={k: v for k, v in ex.items() if k != 'records'}))
                parts, cur, cl = [], [], 0
                for it in ex['records']:
                    L = jlen(it) + 1
                    if cur and cl + L > cap:
                        parts.append(cur); cur, cl = [], 0
                    cur.append(it); cl += L
                parts.append(cur)
                files = []
                for i, part in enumerate(parts, 1):
                    ce = dict(ex); ce['records'] = part
                    if i < len(parts):
                        ce['completion_boundary'] = None
                    cp = {'unit': ident, 'chunk': {'index': i, 'total': len(parts), 'first': part[0]['record_id'],
                                                   'last': part[-1]['record_id'], 'n_items': len(part)}, 'raw_excerpt': ce}
                    fn = f'{uid}__c{i}of{len(parts)}.json'
                    (out / 'packets' / fn).write_text(json.dumps(cp, ensure_ascii=False, indent=2) + '\n'); files.append(fn)
                entry.update(chunks=len(parts), chunk_files=files)
            else:
                (out / 'packets' / f'{uid}.json').write_text(json.dumps(pk, ensure_ascii=False, indent=2) + '\n')
            plan.append(entry)
            units.append(dict(ident, side=a.label, outcome=ident['outcome_known_from_logs']))
    (out / 'units.json').write_text(json.dumps({'label': a.label, 'format': a.format, 'prompt_sha256': in_sha['annotator-prompt.md'],
                                                'inputs_sha256': hashlib.sha256(json.dumps(in_sha, sort_keys=True).encode()).hexdigest(),
                                                'input_sha256': in_sha, 'units': units}, indent=1))
    (out / 'chunk_plan.json').write_text(json.dumps({'context_tokens': CONTEXT, 'max_input_tokens': a.max_input_tokens,
                                                      'prompt_chars': prompt_chars, 'units': plan}, indent=1))
    big = max(plan, key=lambda p: p['est_input_tokens']) if plan else None
    audit = {'units': len(units), 'chunked_units': sum(p['chunks'] > 1 for p in plan), 'fail': fails, 'warn': warns,
             'est_input_tokens_total': sum(p['est_input_tokens'] for p in plan),
             'largest': big and {'uid': big['uid'], 'est_input_tokens': big['est_input_tokens']}}
    (out / 'build_audit.json').write_text(json.dumps(audit, indent=1))
    print(json.dumps(audit, indent=1))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
