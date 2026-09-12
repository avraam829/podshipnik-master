"""Hash the review candidate, excluding generated evidence and review bookkeeping."""
import hashlib
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent.parent
paths = subprocess.check_output(
    ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=root,
).decode().split('\0')
digest = hashlib.sha256()
for name in sorted(set(paths)):
    if not name or name.startswith('docs/evidence/') or name in (
        'docs/orchestration-state.json', 'docs/FINAL_REPORT.md',
    ):
        continue
    path = root / name
    if path.is_file():
        digest.update(name.encode() + b'\0' + path.read_bytes() + b'\0')
print('worktree:' + digest.hexdigest())
