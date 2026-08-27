from django.db import migrations, models
from django.db.models.functions import Lower


def deduplicate_names(apps, schema_editor):
    """Rename pre-existing duplicates so the new constraint can be applied.

    The oldest bot keeps the name; every later namesake becomes "name (2)",
    "name (3)", ... — the same scheme the app now suggests when a student
    picks a name that is already taken.
    """
    SavedStrategy = apps.get_model("game", "SavedStrategy")
    seen = set()
    for strategy in SavedStrategy.objects.order_by("id"):
        name = (strategy.name or "").strip() or "ربات"
        candidate, index = name, 1
        while candidate.casefold() in seen:
            index += 1
            suffix = f" ({index})"
            candidate = name[: 120 - len(suffix)] + suffix
        seen.add(candidate.casefold())
        if candidate != strategy.name:
            strategy.name = candidate
            strategy.save(update_fields=["name"])


class Migration(migrations.Migration):

    dependencies = [
        ("game", "0003_playerkit"),
    ]

    operations = [
        migrations.RunPython(deduplicate_names, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="savedstrategy",
            name="name",
            field=models.CharField(
                help_text="نام نمایشی ربات (حداکثر ۱۲۰ کاراکتر) — باید در کل سامانه یکتا باشد.",
                max_length=120,
                verbose_name="نام استراتژی",
            ),
        ),
        migrations.AddConstraint(
            model_name="savedstrategy",
            constraint=models.UniqueConstraint(
                Lower("name"),
                name="uniq_saved_strategy_name_ci",
                violation_error_message="رباتی با این نام از قبل وجود دارد. یک نام دیگر انتخاب کن.",
            ),
        ),
    ]
