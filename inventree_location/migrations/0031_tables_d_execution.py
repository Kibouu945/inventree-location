"""Tables d'exécution terrain, en lecture seule.

`Livraison` et `Ramassage` sont les `DeliveryTask` / `PickupTask` du schéma
client, rattachés au **bon** — le lieu est un attribut du passage, pas sa clé.
Leurs enfants portent les quantités à la maille de la ligne de réservation.

Aucun écran ne les écrit à ce stade : les colonnes du bon restent la vérité, et
ces tables sont alimentées par `projeter_execution`, vérifiées par
`verifier_projection`. La stratégie est additive, le renversement de la vérité
est post-soutenance.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventree_location", "0030_unicite_des_incidents"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Livraison",
            fields=[
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
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "sequence",
                    models.PositiveSmallIntegerField(
                        default=1, verbose_name="numéro de passage"
                    ),
                ),
                (
                    "date_prevue",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="date et heure prévues"
                    ),
                ),
                (
                    "date_reelle",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="date et heure réelles"
                    ),
                ),
                (
                    "commentaire",
                    models.TextField(
                        blank=True, default="", verbose_name="commentaire"
                    ),
                ),
                (
                    "lieu",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="livraisons",
                        to="inventree_location.lieu",
                        verbose_name="lieu",
                    ),
                ),
                (
                    "livreurs",
                    models.ManyToManyField(
                        blank=True,
                        related_name="passages_de_livraison",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="livreurs assignés",
                    ),
                ),
                (
                    "reservation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="livraisons",
                        to="inventree_location.reservation",
                        verbose_name="bon de réservation",
                    ),
                ),
            ],
            options={
                "verbose_name": "livraison",
                "verbose_name_plural": "livraisons",
                "ordering": ["date_prevue", "sequence"],
            },
        ),
        migrations.CreateModel(
            name="LivraisonLigne",
            fields=[
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
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "quantite_livree",
                    models.PositiveIntegerField(
                        default=0, verbose_name="quantité livrée"
                    ),
                ),
                (
                    "ligne",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="livraisons",
                        to="inventree_location.lignereservation",
                        verbose_name="ligne de réservation",
                    ),
                ),
                (
                    "livraison",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lignes",
                        to="inventree_location.livraison",
                        verbose_name="livraison",
                    ),
                ),
            ],
            options={
                "verbose_name": "ligne de livraison",
                "verbose_name_plural": "lignes de livraison",
                "ordering": ["livraison", "ligne"],
            },
        ),
        migrations.CreateModel(
            name="Ramassage",
            fields=[
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
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "sequence",
                    models.PositiveSmallIntegerField(
                        default=1, verbose_name="numéro de passage"
                    ),
                ),
                (
                    "date_prevue",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="date et heure prévues"
                    ),
                ),
                (
                    "date_reelle",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="date et heure réelles"
                    ),
                ),
                (
                    "ramassage_termine",
                    models.BooleanField(
                        default=False, verbose_name="lieu entièrement ramassé"
                    ),
                ),
                (
                    "commentaire",
                    models.TextField(
                        blank=True, default="", verbose_name="commentaire"
                    ),
                ),
                (
                    "lieu",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ramassages",
                        to="inventree_location.lieu",
                        verbose_name="lieu",
                    ),
                ),
                (
                    "livreurs",
                    models.ManyToManyField(
                        blank=True,
                        related_name="passages_de_ramassage",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="livreurs assignés",
                    ),
                ),
                (
                    "reservation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ramassages",
                        to="inventree_location.reservation",
                        verbose_name="bon de réservation",
                    ),
                ),
            ],
            options={
                "verbose_name": "ramassage",
                "verbose_name_plural": "ramassages",
                "ordering": ["date_prevue", "sequence"],
            },
        ),
        migrations.CreateModel(
            name="RamassageArticle",
            fields=[
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
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "quantite_recuperee",
                    models.PositiveIntegerField(
                        default=0, verbose_name="quantité récupérée"
                    ),
                ),
                (
                    "quantite_cassee",
                    models.PositiveIntegerField(
                        default=0, verbose_name="quantité cassée"
                    ),
                ),
                (
                    "quantite_detruite",
                    models.PositiveIntegerField(
                        default=0, verbose_name="quantité détruite"
                    ),
                ),
                (
                    "quantite_manquante",
                    models.PositiveIntegerField(
                        default=0, verbose_name="quantité manquante"
                    ),
                ),
                (
                    "facturer_client",
                    models.BooleanField(
                        default=False, verbose_name="facturer au client"
                    ),
                ),
                (
                    "ligne",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ramassages",
                        to="inventree_location.lignereservation",
                        verbose_name="ligne de réservation",
                    ),
                ),
                (
                    "ramassage",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="articles",
                        to="inventree_location.ramassage",
                        verbose_name="ramassage",
                    ),
                ),
            ],
            options={
                "verbose_name": "article ramassé",
                "verbose_name_plural": "articles ramassés",
                "ordering": ["ramassage", "ligne"],
            },
        ),
        migrations.AddConstraint(
            model_name="livraison",
            constraint=models.UniqueConstraint(
                fields=("reservation", "sequence"),
                name="livraison_unique_par_bon_et_sequence",
            ),
        ),
        migrations.AddConstraint(
            model_name="livraisonligne",
            constraint=models.UniqueConstraint(
                fields=("livraison", "ligne"), name="livraison_ligne_unique"
            ),
        ),
        migrations.AddConstraint(
            model_name="ramassage",
            constraint=models.UniqueConstraint(
                fields=("reservation", "sequence"),
                name="ramassage_unique_par_bon_et_sequence",
            ),
        ),
        migrations.AddConstraint(
            model_name="ramassagearticle",
            constraint=models.UniqueConstraint(
                fields=("ramassage", "ligne"), name="ramassage_article_unique"
            ),
        ),
    ]
