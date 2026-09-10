"""`Groupe` devient `Client`, et les contacts apparaissent.

Écrite à la main : `RenameModel` et `RenameField` réécrivent les tables et les
colonnes **sur place**, alors qu'un `makemigrations` non interactif verrait une
suppression suivie d'une création et perdrait les données.

C'est aussi pourquoi la bascule ne demande pas la séquence en trois temps qu'on
redoutait sur `Manifestation.groupe` : la colonne étant renommée et non
recréée, sa contrainte NOT NULL n'est jamais violée.

Schéma seulement. La reprise des contacts est en `0027`, et le retrait de
`organisateur`, `Profile.groupe` et `Client.code` en `0028` — il doit venir
après que la reprise les ait lus.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventree_location", "0025_statut_des_prestations_existantes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameModel(old_name="Groupe", new_name="Client"),
        migrations.AlterModelOptions(
            name="client",
            options={
                "ordering": ["nom"],
                "verbose_name": "client",
                "verbose_name_plural": "clients",
            },
        ),
        migrations.RenameField(
            model_name="manifestation", old_name="groupe", new_name="client"
        ),
        migrations.AlterField(
            model_name="manifestation",
            name="client",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="manifestations",
                to="inventree_location.client",
                verbose_name="client",
            ),
        ),
        migrations.AlterField(
            model_name="profile",
            name="groupe",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="profiles",
                to="inventree_location.client",
                verbose_name="groupe",
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="email",
            field=models.EmailField(
                blank=True,
                max_length=254,
                null=True,
                unique=True,
                verbose_name="e-mail",
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="telephone",
            field=models.CharField(
                blank=True, default="", max_length=30, verbose_name="téléphone"
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="type_client",
            field=models.CharField(
                blank=True,
                choices=[
                    ("entreprise", "Entreprise ou association"),
                    ("particulier", "Particulier"),
                ],
                default="",
                max_length=20,
                verbose_name="type de client",
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="siret",
            field=models.CharField(
                blank=True, default="", max_length=20, verbose_name="SIRET"
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="gestionnaire",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="clients_geres",
                to=settings.AUTH_USER_MODEL,
                verbose_name="gestionnaire référent",
            ),
        ),
        migrations.AddField(
            model_name="client",
            name="actif",
            field=models.BooleanField(default=True, verbose_name="actif"),
        ),
        migrations.CreateModel(
            name="Contact",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="date de création"
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True, verbose_name="date de modification"
                    ),
                ),
                ("nom", models.CharField(max_length=120, verbose_name="nom")),
                (
                    "prenom",
                    models.CharField(
                        blank=True, default="", max_length=120, verbose_name="prénom"
                    ),
                ),
                (
                    "email",
                    models.EmailField(
                        blank=True,
                        max_length=254,
                        null=True,
                        unique=True,
                        verbose_name="e-mail",
                    ),
                ),
                (
                    "telephone",
                    models.CharField(
                        blank=True, default="", max_length=30, verbose_name="téléphone"
                    ),
                ),
                ("actif", models.BooleanField(default=True, verbose_name="actif")),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contacts",
                        to="inventree_location.client",
                        verbose_name="client",
                    ),
                ),
            ],
            options={
                "ordering": ["client", "nom", "prenom"],
                "verbose_name": "contact",
                "verbose_name_plural": "contacts",
            },
        ),
        migrations.AddField(
            model_name="manifestation",
            name="contact",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="manifestations",
                to="inventree_location.contact",
                verbose_name="contact référent",
            ),
        ),
    ]
