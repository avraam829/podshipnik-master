from django.db import migrations, models
import unicodedata
from django.utils.text import slugify


def populate(apps, schema_editor):
    Product = apps.get_model('catalog', 'Product')
    seen = set()
    for product in Product.objects.all().iterator(chunk_size=1000):
        label = slugify(f'{product.designation} {product.manufacturer}', allow_unicode=True)[:180].strip('-') or 'podshipnik'
        slug = f'{label}-{product.code.encode("utf-8").hex()}'
        if slug in seen:
            raise ValueError(f'URL collision for product {product.pk}')
        seen.add(slug)
        text = unicodedata.normalize('NFKC', product.designation).casefold()
        key = ''.join(c for c in text if not c.isspace() and unicodedata.category(c) != 'Pd' and c != '-')
        Product.objects.filter(pk=product.pk).update(slug=slug, search_key=key,
            has_spaces=any(c.isspace() for c in product.designation.strip()))


class Migration(migrations.Migration):
    dependencies = [('catalog', '0004_telegramorder_telegramorderitem')]
    operations = [
        migrations.AddField('product', 'slug', models.SlugField(max_length=400, null=True, allow_unicode=True, editable=False)),
        migrations.AddField('product', 'search_key', models.CharField(max_length=255, default='', db_index=True, editable=False), preserve_default=False),
        migrations.AddField('product', 'has_spaces', models.BooleanField(default=False, editable=False)),
        migrations.RunPython(populate, migrations.RunPython.noop),
        migrations.AlterField('product', 'slug', models.SlugField(max_length=400, unique=True, allow_unicode=True, editable=False)),
    ]
