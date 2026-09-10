import json
from django.core.management.base import BaseCommand, CommandError
from catalog.importing import import_xlsx, ImportValidationError


class Command(BaseCommand):
    help = 'Validate XLSX; write only with --apply. No destructive reconciliation.'
    def add_arguments(self, parser):
        parser.add_argument('file')
        parser.add_argument('--apply', action='store_true')
    def handle(self, *args, **options):
        try:
            result = import_xlsx(options['file'], dry_run=not options['apply'])
        except (ImportValidationError, OSError) as error:
            raise CommandError(str(error))
        self.stdout.write(json.dumps(result, ensure_ascii=False))
