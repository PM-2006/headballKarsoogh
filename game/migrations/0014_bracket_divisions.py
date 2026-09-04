"""Split the single knockout bracket into one per division (boys / girls).

The existing row becomes the boys' bracket; the girls' one is created on first
use by ``KnockoutBracket.load``. ``singleton_id`` goes: ``division`` is now the
field that keeps each draw unique.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0013_knockoutbracket'),
    ]

    operations = [
        migrations.AddField(
            model_name='knockoutbracket',
            name='division',
            field=models.CharField(
                choices=[('boys', 'پسران'), ('girls', 'دختران')],
                default='boys',
                max_length=8,
                verbose_name='بخش',
            ),
        ),
        migrations.AlterField(
            model_name='knockoutbracket',
            name='division',
            field=models.CharField(
                choices=[('boys', 'پسران'), ('girls', 'دختران')],
                default='boys',
                max_length=8,
                unique=True,
                verbose_name='بخش',
            ),
        ),
        migrations.RemoveField(
            model_name='knockoutbracket',
            name='singleton_id',
        ),
        migrations.AlterModelOptions(
            name='knockoutbracket',
            options={
                'ordering': ('division',),
                'verbose_name': 'جدول حذفی',
                'verbose_name_plural': 'جدول\u200cهای حذفی',
            },
        ),
    ]
