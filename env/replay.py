#!/usr/bin/env python3
"""Replay harness: execute each conversation's gold tool calls against its
seed database using the domain's mock tools, and verify the outputs match the
recorded function_call_output payloads exactly.

Usage:
  python3 env/replay.py                 # replay all conversations
  python3 env/replay.py <conversation>  # replay one

Contract:
- conversations/<id>/state/seed_database.json holds the complete backend
  state at call start, plus an optional "external_events" list:
    [{"before_call_id": "<call_id>", "patch": {<table>: {<key>: {<field>: value}}}}]
  Each patch is applied (deep-merged) immediately before the named call is
  executed, modeling world changes no tool caused (e.g. a merchant retrying a
  charge mid-call).
- env/<domain>/tools.py exposes  TOOLS: dict[str, callable(db, args) -> output]
  Each callable may mutate db in place (write tools) and returns the output
  object that is compared, after JSON normalization, to the recorded output.
- A conversation passes when every call's output matches exactly and, if
  conversations/<id>/state/final_state.json exists, every entity field it
  asserts is present with the same value in the finished database
  (final_state is a subset check: it only states what tool results revealed).
"""
import json, sys, importlib, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'env'))


def deep_merge(dst, patch):
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_merge(dst[k], v)
        else:
            dst[k] = v


def norm(o):
    return json.dumps(o, sort_keys=True, separators=(',', ':'))


def subset_ok(expected, actual, path=''):
    """Every field in expected must exist in actual with the same value."""
    errs = []
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f'{path}: expected object, got {type(actual).__name__}']
        for k, v in expected.items():
            if k not in actual:
                errs.append(f'{path}.{k}: missing')
            else:
                errs += subset_ok(v, actual[k], f'{path}.{k}')
    elif isinstance(expected, list):
        if norm(expected) != norm(actual):
            errs.append(f'{path}: list mismatch')
    elif expected != actual:
        errs.append(f'{path}: {expected!r} != {actual!r}')
    return errs


def replay(cid, verbose=True):
    cdir = os.path.join(ROOT, 'conversations', cid)
    traj = json.load(open(os.path.join(cdir, 'transcripts', 'annotated-transcript.json')))
    seed_path = os.path.join(cdir, 'state', 'seed_database.json')
    seed = json.load(open(seed_path))
    domain = traj['domain']
    tools = importlib.import_module(f'{domain}.tools').TOOLS

    db = seed['tables']
    events = {e['before_call_id']: e['patch'] for e in seed.get('external_events', [])}
    ctx = {'scenario_time': traj.get('scenario_time'), 'conversation_id': cid}
    db['_context'] = ctx

    failures = []
    inp = traj['responses_create_params']['input']
    calls = [(it['call_id'], it['name'], json.loads(it['arguments'])) for it in inp if it.get('type') == 'function_call']
    outs = {it['call_id']: json.loads(it['output']) for it in inp if it.get('type') == 'function_call_output'}
    for call_id, name, args in calls:
        if call_id in events:
            deep_merge(db, events[call_id])
        if name not in tools:
            failures.append(f'{call_id}: tool {name} not implemented')
            continue
        try:
            got = tools[name](db, args)
        except Exception as e:
            failures.append(f'{call_id} ({name}): raised {type(e).__name__}: {e}')
            continue
        want = outs[call_id]
        if norm(got) != norm(want):
            gs, ws = norm(got), norm(want)
            i = next((j for j in range(min(len(gs), len(ws))) if gs[j] != ws[j]), min(len(gs), len(ws)))
            failures.append(f'{call_id} ({name}): output mismatch at char {i}:\n    got:  ...{gs[max(0,i-40):i+80]}\n    want: ...{ws[max(0,i-40):i+80]}')

    fs_path = os.path.join(cdir, 'state', 'final_state.json')
    if os.path.exists(fs_path):
        final = json.load(open(fs_path))
        db.pop('_context', None)
        for ent_id, ent in final.get('entities', {}).items():
            found = None
            for table in db.values():
                if isinstance(table, dict) and ent_id in table:
                    found = table[ent_id]
                    break
            if found is None:
                failures.append(f'final_state entity {ent_id}: not found in any table')
            else:
                for e in subset_ok(ent, found, ent_id):
                    failures.append(f'final_state {e}')

    status = 'PASS' if not failures else 'FAIL'
    if verbose:
        print(f'{cid}: {status} ({len(calls)} calls)')
        for f in failures:
            print(f'  {f}')
    return not failures


def main():
    targets = sys.argv[1:]
    if not targets:
        targets = sorted(os.listdir(os.path.join(ROOT, 'conversations')))
    ok = all(replay(c) for c in targets)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
