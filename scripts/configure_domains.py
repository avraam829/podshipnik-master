"""Configure production domain aliases, preserving secrets and other .env settings."""
import argparse
import os
from datetime import datetime, timezone
from pathlib import Path
import tempfile

ALIASES = (
    'www.gpz5.ru', 'lyhgbearing.ru', 'lyc-bearing.ru', 'hrbbrg.ru',
    'zys-bearings.ru', 'lycbearings.ru', 'skfcn.ru',
)


def configure(path):
    original = path.read_text(encoding='utf-8')
    lines = original.splitlines()
    # Include existing aliases so this update does not remove earlier domains.
    aliases = list(ALIASES)
    for line in lines:
        if line.startswith(('ADDITIONAL_DOMAINS=', 'SITE_DOMAINS=')):
            for domain in line.split('=', 1)[1].strip().strip('\"\'').split(','):
                domain = domain.strip()
                if domain and domain != 'gpz5.ru' and domain not in aliases:
                    aliases.append(domain)
    updates = {
        'PRIMARY_DOMAIN': 'gpz5.ru',
        'ADDITIONAL_DOMAINS': ','.join(aliases),
        'SITE_DOMAINS': ','.join(['gpz5.ru', *aliases]),
    }
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = path.parent / 'backups' / f'env-before-domains-{stamp}'
    backup.parent.mkdir(parents=True, exist_ok=True)
    with backup.open('xb') as stream:
        os.chmod(backup, 0o600)
        stream.write(original.encode('utf-8'))
    output = []
    seen = set()
    for line in lines:
        key = line.split('=', 1)[0]
        if key in updates:
            if key not in seen:
                output.append(f'{key}={updates[key]}')
                seen.add(key)
        else:
            output.append(line)
    output.extend(f'{key}={value}' for key, value in updates.items() if key not in seen)
    fd, temporary = tempfile.mkstemp(prefix='.env-domains-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write('\n'.join(output) + '\n')
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(f'Backup: {backup}')
    print('Primary: gpz5.ru')
    print('Aliases: ' + ', '.join(aliases))
    print('Restart web and proxy with docker compose --profile production up -d --build --wait')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env', type=Path, default=Path(__file__).resolve().parents[1] / '.env')
    args = parser.parse_args()
    configure(args.env)
