from django.db import migrations, models


def create_default_invitations(apps, schema_editor):
    Porchlight = apps.get_model('porchlights', 'Porchlight')
    Invitation = apps.get_model('porchlights', 'Invitation')
    for porchlight in Porchlight.objects.all():
        Invitation.objects.get_or_create(
            porchlight=porchlight,
            is_guest=False,
            defaults={
                'invited_by_id': porchlight.owner_id,
                'role': 'GUEST',
                'max_uses': 0,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ('porchlights', '0003_alter_porchlight_location'),
    ]

    operations = [
        migrations.AlterField(
            model_name='invitation',
            name='role',
            field=models.CharField(default='GUEST', max_length=50),
        ),
        migrations.RunPython(create_default_invitations, migrations.RunPython.noop),
    ]