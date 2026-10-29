"""Common identifier binding for the next protocol, applied equally to P and D.

This adapter is deliberately NOT applied retrospectively to the running pilot.
It changes only the seed identifier, not features, time predicates or target
labels. The feature SQL contract puts the entity and seed_time first.
"""
import re


def bind_seed_key(sql, source_key, target_key):
    for key in (source_key,target_key):
        if not re.fullmatch(r'[a-z][a-z0-9_]*',key):
            raise ValueError('unsupported seed identifier')
    if source_key==target_key:return sql
    if '{seeds}' not in sql:raise ValueError('feature SQL needs the seed placeholder')
    seed=f'(select {target_key} as {source_key}, seed_time from {{seeds}})'
    inner=sql.strip().rstrip(';').replace('{seeds}',seed)
    return f'SELECT * FROM ({inner}) AS memory_transfer({target_key}, seed_time)'
