from django.contrib.gis.db import models as gis_models
from django.db import migrations


def replace_location_column(apps, schema_editor):
    """Replace disposable JSON location data with an empty spatial column."""
    table = schema_editor.quote_name('porchlights_porchlight')
    schema_editor.execute(f'ALTER TABLE {table} DROP COLUMN location')
    schema_editor.execute(
        f'ALTER TABLE {table} ADD COLUMN location geography(POINT,4326) NULL'
    )


class Migration(migrations.Migration):
    dependencies = [
        ('porchlights', '0004_default_invitation_and_custom_roles'),
    ]

    operations = [
        migrations.RunPython(replace_location_column, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='porchlight',
            name='location',
            field=gis_models.PointField(
                blank=True,
                geography=True,
                null=True,
                srid=4326,
                help_text='WGS84 geographic point using GeoJSON [longitude, latitude] coordinates',
            ),
        ),
    ]