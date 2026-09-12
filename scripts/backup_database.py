"""Consistent SQLite backup. Refuses to overwrite an existing destination."""
import argparse
import sqlite3
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path)
parser.add_argument('destination', type=Path)
args = parser.parse_args()
source = args.source.resolve(strict=True)
destination = args.destination.resolve()
if source == destination:
    parser.error('Source and destination must differ')
destination.parent.mkdir(parents=True, exist_ok=True)
# Exclusive creation also protects against accidental repeated backups.
with destination.open('xb'):
    pass
with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as original:
    with sqlite3.connect(destination) as backup:
        original.backup(backup)
        assert backup.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
print(f'Backup verified: {destination}')
