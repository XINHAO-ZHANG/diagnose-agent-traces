"""Stage 2b helpers: message assembly, model answer parsing, row building, chunk merge, cost.
Ported from the 2026-10-08 runner (run_cursor.py, run_g1.py) with the same rules."""
import json

CODES = ["FM1_REPEATED_EXPLORATION", "FM2_FEEDBACK_NOT_USED", "FM3_NO_REVISION_AFTER_CONTRADICTION",
         "FM4_POST_K_DELAY", "FM5_EXECUTION_DEVIATION", "FM6_TOOL_OR_STATE_ERROR"]
RW = ["RW_PRODUCTIVE", "RW_REDERIVE", "RW_BOARD_REDESCRIBE", "RW_OVERDELIBERATION", "RW_LOCKIN_BATCH",
      "RW_DISCARDED", "RW_TOOL_DEBUG", "RW_UNCLEAR"]
# $ per 1M tokens: input, cache write, cache read, output (cursor.com/docs/models-and-pricing, fetched 2026-10-08)
PRICES = {'composer-2.5': (0.5, 0.5, 0.2, 2.5), 'gpt-5.6-luna-high': (0.2, 0.25, 0.02, 1.2),
          'gemini-3.8-flash-high': (0.75, 0.75, 0.075, 3.5), 'gemini-3.8-flash-medium': (0.75, 0.75, 0.075, 3.5),
          'gemini-3.1-pro': (2.0, 2.0, 0.2, 12.0), 'claude-sonnet-5-high': (2.0, 2.5, 0.2, 10.0)}
AVG_OUTPUT_TOKENS = 4872   # measured: mean output tokens per unit over 142 calls (2026-10-08)


def cost(prices, usage):
    if not prices or not usage:
        return None
    return (usage.get('inputTokens', 0) * prices[0] + usage.get('cacheWriteTokens', 0) * prices[1] +
            usage.get('cacheReadTokens', 0) * prices[2] + usage.get('outputTokens', 0) * prices[3]) / 1e6


def message(inputs, packet):
    """Prompt + addendum + protocol + codebook + output contract + packet. Byte-equal to the 2026-10-08 G1/G2 message."""
    def r(f):
        old = {'annotator-prompt.md': 'annotator-prompt-v1.1.md', 'output-contract.json': 'output-contract-v1.1.json'}   # packets built before v1.2
        return (inputs / f).read_text() if (inputs / f).exists() else (inputs / old[f]).read_text()
    msg = ''.join([r('annotator-prompt.md'), '\n\n## PROTOCOL\n\n' + r('protocol.md'),
                   '\n\n## CODEBOOK\n\n' + r('codebook-fm-v0.1.md'), '\n\n## OUTPUT CONTRACT\n\n' + r('output-contract.json'),
                   '\n\n## UNIT PACKET\n\n' + json.dumps(packet, ensure_ascii=False, separators=(',', ':'))])
    return msg.replace('\n\n## PROTOCOL\n\n', r('addendum-full-traces.md') + '\n\n## PROTOCOL\n\n', 1)


def parse_json(body):
    body = (body or '').strip()
    if body.startswith('```'):
        body = body.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    dec = json.JSONDecoder()
    for i, ch in enumerate(body):
        if ch == '{':
            try:
                v, _ = dec.raw_decode(body[i:])
                if isinstance(v, dict) and ('failure_modes' in v or 'milestones' in v):
                    return v
            except json.JSONDecodeError:
                pass
    raise ValueError('no JSON object in model result')


def texts(packet):
    out = []
    for r in packet['raw_excerpt'].get('records', []):
        out += [s.get('text') or '' for s in r['sections']]
    return out


def tri(v):
    if v in (True, False, None):
        return v
    if isinstance(v, str):
        return {'true': True, 'false': False}.get(v.strip().lower())
    return None


def enum(v, allowed, default=None):
    return v if v in allowed else default


def intn(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v if v >= 0 else None
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return None


def build_row(unit, packet, draft, pass_name, model_id, prompt_sha, fmt='v1.1', inputs_sha=None):
    """Normalise the model answer. A quote is 'verified' when it is a substring of the packet text.
    'present: true' without evidence becomes null."""
    fixes = []
    lines = {r['record_id']: r['source_line'] for r in packet['raw_excerpt'].get('records', [])}
    corpus = texts(packet)
    ms = draft.get('milestones') or {}
    mil = {'K_status': enum(ms.get('K_status'), ('observed', 'candidate', 'unknown', 'not_reached'), 'unknown'),
           'K_completed_actions': intn(ms.get('K_completed_actions')),
           'K_confidence': enum(ms.get('K_confidence'), ('high', 'medium', 'low'), None),
           'S_status': enum(ms.get('S_status'), ('observed', 'candidate', 'unknown', 'not_reached'), 'unknown'),
           'S_completed_actions': intn(ms.get('S_completed_actions')), 'n_C': intn(ms.get('n_C')), 'n_R': intn(ms.get('n_R'))}
    mt = draft.get('metrics') or {}
    sint = lambda v: v if isinstance(v, int) and not isinstance(v, bool) else None
    met = {'A_K': sint(mt.get('A_K')), 'P_C': sint(mt.get('P_C')), 'D_K': sint(mt.get('D_K')), 'A_KS': sint(mt.get('A_KS')),
           'status': enum(mt.get('status'), ('exact', 'conditional', 'unknown'), 'unknown')}
    fm_in = draft.get('failure_modes') or {}
    fm, nq, nqv = {}, 0, 0
    for c in CODES:
        v = fm_in.get(c)
        if not isinstance(v, dict):
            fixes.append(f'{c}: missing -> null'); fm[c] = {'present': None, 'rationale': 'runner: code missing in model output'}
            continue
        pres = tri(v.get('present')); evs = []
        for e in v.get('evidence') or []:
            if not isinstance(e, dict):
                continue
            item = {}; rid = e.get('record_id'); st = intn(e.get('step'))
            if rid in lines:
                item['record_id'] = rid; item['source_line'] = lines[rid]
            else:
                item['source_line'] = None
            if st is not None:
                item['action_index'] = st
            if isinstance(e.get('quote'), str) and e['quote'].strip():
                q = e['quote']; item['quote'] = q; nq += 1
                ok = any(q in t for t in corpus); item['quote_verified'] = ok; nqv += ok
            if isinstance(e.get('observation'), str) and e['observation'].strip():
                item['observation'] = e['observation']
            if 'quote' in item or 'observation' in item:
                evs.append(item)
        o = {'present': pres, 'confidence': enum(v.get('confidence'), ('high', 'medium', 'low'), None),
             'steps': v.get('steps') if isinstance(v.get('steps'), str) else (str(v['steps']) if v.get('steps') is not None else None),
             'cost_actions': intn(v.get('cost_actions')), 'evidence': evs,
             'rationale': v.get('rationale') if isinstance(v.get('rationale'), str) else ''}
        if pres is True and not evs:
            fixes.append(f'{c}: present=true without evidence -> null'); o['present'] = None
            o['rationale'] = ('runner: true without evidence downgraded to null. ' + o['rationale']).strip()
        if o['present'] is True and o['confidence'] is None:
            o['confidence'] = 'low'; fixes.append(f'{c}: missing confidence -> low')
        fm[c] = o
    ol = [{'label': str(x.get('label')), 'episode_ids': x.get('episode_ids') if isinstance(x.get('episode_ids'), list) else []}
          for x in (draft.get('other_labels') or []) if isinstance(x, dict) and x.get('label')]
    row = {'record_type': 'failure_mode_unit', 'schema_version': 'trajectory-v1+fm-v0.1', 'codebook_version': 'fm-v0.1',
           'inputs_sha256': inputs_sha, 'prompt_version': ('annot-prompt-v1.1-cursor' if fmt == 'v1.1' else f'annot-prompt-{fmt}') + ' + addendum-full-traces', 'prompt_sha256': prompt_sha,
           'annotator_id': pass_name, 'annotator_model': model_id, 'batch': pass_name, 'blind': True,
           'retrospective_exposure': True, 'run_id': unit['run_id'], 'harness': unit['harness'], 'model': unit['model'],
           'game_id': unit['game_id'], 'level': unit['level'], 'attempt': unit['attempt'],
           'source_ids': [unit['source_sha256']], 'annotation_path': f"packets/{unit['uid']}.json",
           'outcome': unit['outcome'], 'milestones': mil, 'metrics': met, 'failure_modes': fm,
           'other_labels': ol, 'notes': draft.get('notes') if isinstance(draft.get('notes'), str) else ''}
    rw = []
    for x in draft.get('reasoning_waste') or []:
        if not isinstance(x, dict) or not isinstance(x.get('allocation'), dict):
            continue
        al = {k: float(v) for k, v in x['allocation'].items() if k in RW and isinstance(v, (int, float)) and v >= 0}
        s = sum(al.values())
        if s <= 0:
            continue
        q = x.get('quote') if isinstance(x.get('quote'), str) else None
        item = {'record_id': x.get('record_id'), 'steps': x.get('steps'), 'allocation': {k: v / s for k, v in al.items()},
                'quote': q, 'quote_verified': (any(q in t for t in corpus) if q else None)}
        for f in ('summary', 'reason'):      # v1.2 fields
            if isinstance(x.get(f), str) and x[f].strip():
                item[f] = x[f].strip()
        rw.append(item)
    return row, rw, fixes, nq, nqv


CONF = {'low': 1, 'medium': 2, 'high': 3}


def merge(drafts):
    """Deterministic merge of the answers for the chunks of one unit, in order.
    present = true if any chunk true, else false if any false, else null. cost_actions = sum of known costs."""
    out = {'failure_modes': {}, 'other_labels': [], 'reasoning_waste': [], 'notes': ''}
    for c in CODES:
        vs = [(i, d.get('failure_modes', {}).get(c)) for i, d in enumerate(drafts, 1)]
        vs = [(i, v) for i, v in vs if isinstance(v, dict)]
        pres = [tri(v.get('present')) for _, v in vs]
        tr = [(i, v) for i, v in vs if tri(v.get('present')) is True]
        costs = [intn(v.get('cost_actions')) for _, v in tr]
        out['failure_modes'][c] = {
            'present': True if tr else (False if False in pres else None),
            'confidence': max((v.get('confidence') for _, v in tr if v.get('confidence') in CONF), key=lambda x: CONF[x], default=None),
            'steps': '; '.join(f"c{i}:{v.get('steps')}" for i, v in tr if v.get('steps')) or None,
            'cost_actions': sum(x for x in costs if x is not None) if any(x is not None for x in costs) else None,
            'evidence': [e for _, v in (tr or vs) for e in (v.get('evidence') or [])],
            'rationale': ' | '.join(f"[c{i}] {v.get('rationale', '')}" for i, v in vs)}
    kd = next((d for d in drafts if (d.get('milestones') or {}).get('K_status') in ('observed', 'candidate')), drafts[-1])
    sd = next((d for d in drafts if (d.get('milestones') or {}).get('S_status') in ('observed', 'candidate')), drafts[-1])
    km, sm = kd.get('milestones') or {}, sd.get('milestones') or {}

    def ssum(k):
        xs = [intn((d.get('milestones') or {}).get(k)) for d in drafts]
        return sum(x for x in xs if x is not None) if any(x is not None for x in xs) else None
    out['milestones'] = {'K_status': km.get('K_status'), 'K_completed_actions': km.get('K_completed_actions'),
                         'K_confidence': km.get('K_confidence'), 'S_status': sm.get('S_status'),
                         'S_completed_actions': sm.get('S_completed_actions'), 'n_C': ssum('n_C'), 'n_R': ssum('n_R')}
    out['metrics'] = kd.get('metrics') or {}
    for i, d in enumerate(drafts, 1):
        out['other_labels'] += [x for x in d.get('other_labels') or [] if isinstance(x, dict)]
        out['reasoning_waste'] += [x for x in d.get('reasoning_waste') or [] if isinstance(x, dict)]
        out['notes'] += f"[chunk {i}/{len(drafts)}] {d.get('notes') or ''} "
    return out
