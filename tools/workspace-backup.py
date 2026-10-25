#!/usr/bin/env python3
"""Create, verify, or restore a dated, split ZIP backup using the standard library."""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
CHUNK = 4 * 1024 * 1024
PART_SIZE = 45 * 1024 * 1024
STAGING = ROOT / 'tmp/backup-staging'


def sha256(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def safe_relative(value):
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or '..' in path.parts or ':' in value or '\\' in value:
        raise ValueError(f'Unsafe archive path: {value}')
    return path


def create(args):
    audit = json.loads(args.audit.read_text(encoding='utf-8'))
    blocked = {finding['path'] for finding in audit['findings']}
    destination = args.snapshot.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError(f'Snapshot already exists: {destination}')
    destination.mkdir(parents=True, exist_ok=True)
    STAGING.mkdir(parents=True, exist_ok=True)
    git_base = subprocess.check_output(
        ['git', '-c', f'safe.directory={ROOT.as_posix()}', 'rev-parse', 'HEAD'], cwd=ROOT,
    ).decode().strip()
    manifest = {
        'format_version': 1,
        'snapshot_date': args.date,
        'base_workspace_commit': git_base,
        'part_size_bytes': PART_SIZE,
        'exclusions': [
            {'path': path, 'reason': 'Contains a credential; retained only on the local machine.'}
            for path in sorted(blocked)
        ],
        'groups': [],
    }
    for name, prefixes in (('results', ('results/',)),
                           ('working-files', ('tmp/', 'overleaf/build/')),
                           ('source-snapshots', ('target/replay-baseline/',))):
        records = [entry for entry in audit['files']
                   if entry['path'].startswith(prefixes) and entry['path'] not in blocked]
        if not records:
            continue
        print(f'Archiving {name}: {len(records)} files', flush=True)
        with tempfile.TemporaryDirectory(prefix='mavra-backup-', dir=STAGING) as temporary:
            archive = Path(temporary) / f'{name}.zip'
            with ZipFile(archive, 'w', compression=ZIP_DEFLATED, compresslevel=6) as bundle:
                for index, record in enumerate(records):
                    relative = safe_relative(record['path'])
                    source = ROOT.joinpath(*relative.parts)
                    digest = hashlib.sha256()
                    size = 0
                    with source.open('rb') as input_file, bundle.open(relative.as_posix(), 'w', force_zip64=True) as output:
                        while data := input_file.read(CHUNK):
                            size += len(data)
                            digest.update(data)
                            output.write(data)
                    if size != record['size'] or digest.hexdigest() != record['sha256']:
                        raise ValueError(f'Source changed after audit: {source}')
                    if index % 100 == 0:
                        print(f'  {name}: {index + 1}/{len(records)}', flush=True)
            parts = []
            archive_digest = hashlib.sha256()
            with archive.open('rb') as input_file:
                index = 1
                while data := input_file.read(PART_SIZE):
                    part_name = f'{name}.zip.part{index:03d}'
                    (destination / part_name).write_bytes(data)
                    archive_digest.update(data)
                    parts.append({'path': part_name, 'size': len(data),
                                  'sha256': hashlib.sha256(data).hexdigest()})
                    index += 1
            manifest['groups'].append({
                'name': name, 'archive': archive.name,
                'archive_sha256': archive_digest.hexdigest(),
                'original_bytes': sum(record['size'] for record in records),
                'compressed_bytes': archive.stat().st_size,
                'parts': parts, 'files': records,
            })
            print(f'{name}: {archive.stat().st_size:,} bytes, {len(parts)} parts', flush=True)
    write_json(destination / 'manifest.json', manifest)
    print(f'Created {destination}', flush=True)


@contextmanager
def open_archive(snapshot, group):
    STAGING.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='mavra-restore-', dir=STAGING) as temporary:
        archive = Path(temporary) / 'archive.zip'
        digest = hashlib.sha256()
        with archive.open('wb') as output:
            for part in group['parts']:
                relative = safe_relative(part['path'])
                path = snapshot.joinpath(*relative.parts)
                if path.stat().st_size != part['size'] or sha256(path) != part['sha256']:
                    raise ValueError(f'Invalid part: {path}')
                with path.open('rb') as source:
                    while data := source.read(CHUNK):
                        digest.update(data)
                        output.write(data)
        if digest.hexdigest() != group['archive_sha256']:
            raise ValueError(f'Archive hash mismatch: {group["name"]}')
        with ZipFile(archive) as bundle:
            expected = {record['path']: record for record in group['files']}
            if len(expected) != len(group['files']) or len(bundle.infolist()) != len(expected) or set(bundle.namelist()) != set(expected):
                raise ValueError(f'Archive/manifest file mismatch: {group["name"]}')
            for name, record in expected.items():
                safe_relative(name)
                if bundle.getinfo(name).file_size != record['size']:
                    raise ValueError(f'File size mismatch: {name}')
                with bundle.open(name) as source:
                    if hashlib.file_digest(source, 'sha256').hexdigest() != record['sha256']:
                        raise ValueError(f'File hash mismatch: {name}')
            yield bundle


def verify_or_restore(args):
    snapshot = args.snapshot.resolve()
    manifest = json.loads((snapshot / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['format_version'] != 1:
        raise ValueError('Unsupported backup format')
    destination = None
    if args.command == 'restore':
        destination = args.destination.resolve()
        if destination.exists() and any(destination.iterdir()):
            raise ValueError(f'Restore destination must be empty: {destination}')
        destination.mkdir(parents=True, exist_ok=True)
    count = 0
    for group in manifest['groups']:
        print(f'Verifying {group["name"]}', flush=True)
        with open_archive(snapshot, group) as bundle:
            if destination:
                for record in group['files']:
                    relative = safe_relative(record['path'])
                    target = destination.joinpath(*relative.parts)
                    if not target.resolve().is_relative_to(destination):
                        raise ValueError(f'Restore path outside destination: {target}')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(relative.as_posix()) as source, target.open('xb') as output:
                        shutil.copyfileobj(source, output, CHUNK)
            count += len(group['files'])
    print(f'{count} files: part, archive, CRC, and SHA-256 checks passed', flush=True)
    if destination:
        print(f'Restored to {destination}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create_parser = commands.add_parser('create', help='create a snapshot from a credential-audited inventory')
    create_parser.add_argument('snapshot', type=Path)
    create_parser.add_argument('--audit', type=Path, required=True)
    create_parser.add_argument('--date', required=True)
    verify_parser = commands.add_parser('verify', help='check every part and every original file')
    verify_parser.add_argument('snapshot', type=Path)
    restore_parser = commands.add_parser('restore', help='verify and extract into an empty directory')
    restore_parser.add_argument('snapshot', type=Path)
    restore_parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    try:
        create(args) if args.command == 'create' else verify_or_restore(args)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
