"""Migration initiale de l'app `part` factice (tests uniquement)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies: list = []

    operations = [
        migrations.CreateModel(
            name="Part",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("IPN", models.CharField(blank=True, default="", max_length=100)),
                ("active", models.BooleanField(default=True)),
            ],
            options={},
        ),
    ]
