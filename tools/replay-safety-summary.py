#!/usr/bin/env python3
"""Reproduce service/refusal counts from the four archived benchmark replays.

Uses the same common question keys and condition/snapshot arm as the paper's
existing replay statistics. Structural scenarios are the five targeted change
types, not a claim that every predicate used by a definition is covered.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPES = {
    'Benign': {'append', 'backfill', 'correct', 'addcol'},
    'Structural': {'status', 'revision', 'dupload', 'dimhist', 'latekey'},
    'Outside': {'unit', 'mirror'},
}
CLASSES = ('correct', 'served_wrong', 'unavailable_needed', 'unavailable_unneeded')
BASE = ROOT / 'exp/2026-10-02-cache-baseline-tpcds'
GENERAL = ROOT / 'exp/2026-10-11-generality'


def key(row):
    return tuple(row[field] for field in ('lib', 'change', 'entry', 'task'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tex-out', type=Path, default=ROOT / 'overleaf/gen/replay-safety.tex')
    parser.add_argument('--json-out', type=Path, default=GENERAL / 'replay-safety-summary.json')
    args = parser.parse_args()
    general_stats = json.loads((GENERAL / 'generality-stats.json').read_text())
    sources = [('tpcds', BASE / 'tpcds-replay-outcomes.json.gz',
                json.loads((BASE / 'tpcds-replay-stats.json').read_text()))]
    sources += [(name, GENERAL / f'{name}-replay-report.json.gz', general_stats[name])
                for name in ('tpch', 'ssb', 'financial')]
    pooled = {scope: Counter() for scope in SCOPES}
    audit = {'unit': 'common (library, change, entry, task) question instance',
             'arm': 'condition/snapshot', 'sources': [], 'datasets': {},
             'structural_failures': []}
    for name, path, expected in sources:
        report = json.loads(gzip.decompress(path.read_bytes()))
        outcomes = report['outcomes']
        groups = {(row['policy'], row['oracle']) for row in outcomes}
        common = set.intersection(*[
            {key(row) for row in outcomes if (row['policy'], row['oracle']) == group}
            for group in groups])
        rows = [row for row in outcomes if (row['policy'], row['oracle']) == ('condition', 'snapshot')
                and key(row) in common]
        counts = Counter(row['class'] for row in rows)
        recorded = expected['task_level_common']['condition/snapshot']
        assert len(rows) == recorded['n'], name
        assert all(counts[cls] == recorded[cls] for cls in CLASSES), name
        assert all(row['change'] in set.union(*SCOPES.values()) for row in rows), name
        audit['sources'].append({'path': str(path.relative_to(ROOT)),
                                 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        audit['datasets'][name] = {}
        for scope, changes in SCOPES.items():
            subset = [row for row in rows if row['change'] in changes]
            count = Counter(row['class'] for row in subset)
            pooled[scope].update(count)
            audit['datasets'][name][scope] = {'n': len(subset), **{cls: count[cls] for cls in CLASSES}}
        audit['structural_failures'] += [dict(dataset=name, **row) for row in rows
                                        if row['change'] in SCOPES['Structural']
                                        and row['class'] == 'served_wrong']
    definition_path = GENERAL / 'libs/tpch-kept.json'
    entries = json.loads(definition_path.read_text())['metric_report']['entries']
    entry = next(row for row in entries if row['metric']['name'] == 'q12_b0_lineitem')
    audit['predicate_failure_definition'] = {
        'path': str(definition_path.relative_to(ROOT)),
        'sha256': hashlib.sha256(definition_path.read_bytes()).hexdigest(),
        'time': entry['metric']['time'], 'filters': entry['metric']['filters'],
        'holdout': entry['holdout'],
    }
    macros = {}
    audit['pooled'] = {}
    for scope, count in pooled.items():
        refused = count['unavailable_needed'] + count['unavailable_unneeded']
        audit['pooled'][scope] = {'n': sum(count.values()), **{cls: count[cls] for cls in CLASSES}}
        macros.update({f'Rs{scope}N': sum(count.values()), f'Rs{scope}Correct': count['correct'],
                       f'Rs{scope}Wrong': count['served_wrong'], f'Rs{scope}Refused': refused,
                       f'Rs{scope}Unneeded': count['unavailable_unneeded']})
    macros['RsTotal'] = sum(sum(count.values()) for count in pooled.values())
    for suffix, task in (('Single', 'P1'), ('Diff', 'T1'), ('Rank', 'T2')):
        matches = [row for row in audit['structural_failures']
                   if row['entry'] == 'q12_b0_lineitem' and row['task'] == f'q12_b0_lineitem-{task}']
        assert len(matches) == 1, matches
        macros[f'RsQ{suffix}Observed'] = int(matches[0]['value'])
        macros[f'RsQ{suffix}Gold'] = int(matches[0]['gold'])
    assert all(name.isascii() and name.isalpha() for name in macros)
    lines = ['% generated by tools/replay-safety-summary.py; do not edit']
    lines += ['\\newcommand{\\' + name + '}{' + f'{value:,}'.replace(',', '{,}') + '}'
              for name, value in sorted(macros.items())]
    args.tex_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.tex_out.write_text('\n'.join(lines) + '\n')
    args.json_out.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(audit['pooled'], ensure_ascii=False))


if __name__ == '__main__':
    main()
