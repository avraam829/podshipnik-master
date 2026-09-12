from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Устаревший JSON-импорт отключён: используйте проверяемый XLSX-импорт.'

    def add_arguments(self, parser):
        parser.add_argument('--file', type=str, help='Устаревший параметр; JSON больше не импортируется.')

    def handle(self, *args, **options):
        raise CommandError(
            'JSON-импорт отключён: он не имел стабильных кодов и мог создать дубликаты. '
            'Используйте: python manage.py import_xlsx <файл.xlsx> для проверки, затем добавьте --apply. '
            'В админке: «Товары» → «Импорт из Excel». Ничего не изменено.'
        )
