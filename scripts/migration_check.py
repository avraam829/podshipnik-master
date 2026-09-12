"""Validate upgrade on an online backup; never write to the source database."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

source=Path(sys.argv[1])
target=Path('docs/evidence/migration-copy.sqlite3').resolve()
if target.exists():
    raise SystemExit('Existing migration copy preserved. Choose a fresh target before rerunning.')
connection=sqlite3.connect('file:'+source.as_posix()+'?mode=ro',uri=True)
columns=[row[1] for row in connection.execute('PRAGMA table_info(catalog_product)')]
def digest(db):
    rows=db.execute('SELECT '+','.join('"'+c+'"' for c in columns)+' FROM catalog_product ORDER BY id').fetchall()
    return len(rows),hashlib.sha256(json.dumps(rows,default=str,ensure_ascii=False).encode()).hexdigest()
before=digest(connection)
copy=sqlite3.connect(target)
connection.backup(copy)
copy.close()
connection.close()
env={**os.environ,'DATABASE_PATH':str(target),'DJANGO_DEBUG':'True'}
if '--roundtrip' in sys.argv:
    subprocess.run([sys.executable,'manage.py','migrate','catalog','0004','--noinput'],env=env,check=True)
subprocess.run([sys.executable,'manage.py','migrate','--noinput'],env=env,check=True)
copy=sqlite3.connect(target)
after=digest(copy)
assert before==after,(before,after)
count,unique,empty=copy.execute("SELECT count(*),count(DISTINCT slug),sum(slug IS NULL OR slug='') FROM catalog_product").fetchone()
assert count==unique and empty==0
result={'products':count,'original_columns_unchanged':True,'unique_slugs':unique,'empty_slugs':empty,'roundtrip':'--roundtrip' in sys.argv,'source':source.name}
Path('docs/evidence/migration-results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
copy.close()
print(json.dumps(result))
