"""API serializers for the InvenTreeLocation plugin.

In practice, you would define your custom serializers here.

Ref: https://www.django-rest-framework.org/api-guide/serializers/
"""

from rest_framework import serializers

from .models import Reservation


class ReservationSerializer(serializers.ModelSerializer):
    """Sérialiseur DRF pour le modèle `Reservation`.

    Un serializer DRF fait le pont entre les objets Python/ORM (instances de
    `Reservation`) et les représentations JSON échangées par l'API :
    - en lecture (GET), il convertit ("sérialise") une instance ou un queryset
      en dict/JSON renvoyé au client ;
    - en écriture (POST/PUT/PATCH), il valide les données JSON reçues
      (champs requis, types, clés étrangères existantes, contraintes du
      modèle...) puis les "désérialise" en instance `Reservation`, qui peut
      alors être sauvegardée via `.save()`.

    Utiliser un `ModelSerializer` plutôt qu'un `Serializer` simple permet de
    déduire les champs et leurs validateurs directement depuis le modèle.
    """

    class Meta:
        model = Reservation
        fields = [
            "id",
            "prestation",
            "demandeur",
            "validateur",
            "statut",
            "forced",
            "date_demande",
            "date_retrait_prevue",
            "date_retour_prevue",
            "date_retrait_reelle",
            "date_retour_reelle",
            "commentaire",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ExampleSerializer(serializers.Serializer):
    """Example serializer for the InvenTreeLocation plugin.

    This simply demonstrates how to create a serializer,
    with a few example fields of different types.
    """

    class Meta:
        """Meta options for this serializer."""

        fields = [
            "random_text",
            "part_count",
            "today",
        ]

    random_text = serializers.CharField(
        max_length=100,
        required=True,
        label="Random Text",
        help_text="A text field containing randomly generated data.",
    )

    part_count = serializers.IntegerField(
        label="Number of Parts",
        help_text="Total number of parts in the InvenTree database.",
    )

    today = serializers.DateField(
        required=False,
        label="Today",
        help_text="The current date.",
    )
