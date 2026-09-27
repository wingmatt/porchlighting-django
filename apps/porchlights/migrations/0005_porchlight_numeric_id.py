from django.db import migrations, models


def populate_numeric_ids(apps, schema_editor):
    Porchlight = apps.get_model('porchlights', 'Porchlight')
    for numeric_id, porchlight in enumerate(Porchlight.objects.order_by('created_at', 'id'), start=1):
        Porchlight.objects.filter(pk=porchlight.pk).update(numeric_id=numeric_id)


class Migration(migrations.Migration):
    dependencies = [
        ('porchlights', '0004_default_invitation_and_custom_roles'),
    ]

    operations = [
        migrations.AddField(
            model_name='porchlight',
            name='numeric_id',
            field=models.PositiveIntegerField(blank=True, db_index=True, null=True, unique=True),
        ),
        migrations.RunPython(populate_numeric_ids, migrations.RunPython.noop),
    ]