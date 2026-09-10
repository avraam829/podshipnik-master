from django.core.management.base import BaseCommand
from catalog.models import Category

class Command(BaseCommand):
    help = 'Creates dummy categories and subcategories'

    def handle(self, *args, **kwargs):
        self.stdout.write('Creating dummy data...')

        # Clear existing categories
        Category.objects.all().delete()

        # Create root categories
        cat1 = Category.objects.create(name='Electric Motors')
        cat2 = Category.objects.create(name='Bearings')
        cat3 = Category.objects.create(name='Other')

        # Create subcategories
        Category.objects.create(name='Electric Motors', parent=cat1)
        Category.objects.create(name='Motor Reducers', parent=cat1)

        Category.objects.create(name='Ball Bearings', parent=cat2)
        Category.objects.create(name='Roller Bearings', parent=cat2)

        self.stdout.write(self.style.SUCCESS('Successfully created dummy data.'))
