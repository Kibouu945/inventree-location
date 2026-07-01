"""API serializers for the InvenTreeLocation plugin."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from rest_framework import serializers

from .models import (
    LigneReservation,
    Lieu,
    RentableItem,
    Reservation,
    ReservationStatusLog,
    StatutReservation,
)


def geocode_address(address):
    """Return GPS coordinates for an address using OpenStreetMap Nominatim."""

    if not address:
        return None

    query = urlencode(
        {
            "q": address,
            "format": "json",
            "limit": 1,
        }
    )

    url = f"https://nominatim.openstreetmap.org/search?{query}"

    request = Request(
        url,
        headers={
            "User-Agent": "inventree-location-plugin/0.1",
        },
    )

    with urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not payload:
        return None

    first_result = payload[0]

    return {
        "address": address,
        "display_name": first_result.get("display_name"),
        "latitude": first_result.get("lat"),
        "longitude": first_result.get("lon"),
        "source": "OpenStreetMap Nominatim",
    }


class LigneReservationSerializer(serializers.ModelSerializer):
    """Sérialiseur d'une ligne de réservation."""

    class Meta:
        """Configuration du serializer LigneReservation."""

        model = LigneReservation
        fields = [
            "id",
            "part",
            "quantite_demandee",
            "quantite_livree",
            "quantite_retournee",
            "etat_retour",
            "commentaire",
        ]
        read_only_fields = ["id"]


class ReservationStatusLogSerializer(serializers.ModelSerializer):
    """Sérialiseur du journal de transition de statut."""

    changed_by_username = serializers.CharField(
        source="changed_by.username",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        """Configuration du serializer ReservationStatusLog."""

        model = ReservationStatusLog
        fields = [
            "id",
            "reservation",
            "changed_by",
            "changed_by_username",
            "from_status",
            "to_status",
            "comment",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "reservation",
            "changed_by",
            "changed_by_username",
            "from_status",
            "to_status",
            "comment",
            "created_at",
        ]


class ReservationTransitionSerializer(serializers.Serializer):
    """Serializer utilisé pour demander une transition de statut."""

    statut = serializers.ChoiceField(
        choices=StatutReservation.choices,
        required=True,
        help_text="Nouveau statut demandé pour la réservation.",
    )
    comment = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Commentaire facultatif lié à la transition.",
    )


class ReservationSerializer(serializers.ModelSerializer):
    """Sérialiseur DRF pour le modèle Reservation, avec lignes imbriquées."""

    lignes = LigneReservationSerializer(many=True, required=False)
    status_logs = ReservationStatusLogSerializer(many=True, read_only=True)

    class Meta:
        """Configuration du serializer Reservation."""

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
            "lignes",
            "status_logs",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "status_logs"]

    def create(self, validated_data):
        """Crée une réservation et ses lignes imbriquées."""

        lignes_data = validated_data.pop("lignes", None)
        reservation = super().create(validated_data)

        if lignes_data:
            self._replace_lignes(reservation, lignes_data)

        return reservation

    def update(self, instance, validated_data):
        """Met à jour une réservation et, si fournies, remplace ses lignes."""

        lignes_data = validated_data.pop("lignes", None)
        reservation = super().update(instance, validated_data)

        if lignes_data is not None:
            self._replace_lignes(reservation, lignes_data)

        return reservation

    def _replace_lignes(self, reservation, lignes_data):
        """Remplace l'intégralité des lignes de la réservation."""

        reservation.lignes.all().delete()

        LigneReservation.objects.bulk_create(
            [
                LigneReservation(reservation=reservation, **ligne_data)
                for ligne_data in lignes_data
            ]
        )


class RentableItemSerializer(serializers.ModelSerializer):
    """Drapeaux location d'un Part."""

    class Meta:
        """Configuration du serializer RentableItem."""

        model = RentableItem
        fields = [
            "part",
            "is_rentable",
            "consommable",
            "caution",
            "valeur_remplacement",
            "seuil_alerte_bas",
        ]
        read_only_fields = ["part"]


class ExampleSerializer(serializers.Serializer):
    """Example serializer for the InvenTreeLocation plugin."""

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


class LieuSerializer(serializers.ModelSerializer):
    """Serializer for location places with GPS coordinates."""

    auto_geocode = serializers.BooleanField(
        write_only=True,
        required=False,
        default=False,
        help_text="Active le géocodage automatique à partir de l'adresse.",
    )

    class Meta:
        """Meta options for LieuSerializer."""

        model = Lieu
        fields = [
            "id",
            "prestation",
            "nom",
            "adresse",
            "latitude",
            "longitude",
            "capacite",
            "auto_geocode",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]

    def validate_latitude(self, value):
        """Validate latitude range."""

        if value is not None and (value < -90 or value > 90):
            raise serializers.ValidationError(
                "La latitude doit être comprise entre -90 et 90."
            )

        return value

    def validate_longitude(self, value):
        """Validate longitude range."""

        if value is not None and (value < -180 or value > 180):
            raise serializers.ValidationError(
                "La longitude doit être comprise entre -180 et 180."
            )

        return value

    def create(self, validated_data):
        """Create a place and optionally geocode its address."""

        auto_geocode = validated_data.pop("auto_geocode", False)
        self._apply_auto_geocode(validated_data, auto_geocode)

        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Update a place and optionally geocode its address."""

        auto_geocode = validated_data.pop("auto_geocode", False)
        self._apply_auto_geocode(validated_data, auto_geocode)

        return super().update(instance, validated_data)

    def _apply_auto_geocode(self, validated_data, auto_geocode):
        """Fill latitude and longitude from address when requested."""

        if not auto_geocode:
            return

        address = validated_data.get("adresse")

        if not address:
            return

        if validated_data.get("latitude") is not None:
            return

        if validated_data.get("longitude") is not None:
            return

        try:
            result = geocode_address(address)
        except (HTTPError, URLError, TimeoutError):
            return

        if not result:
            return

        validated_data["latitude"] = result.get("latitude")
        validated_data["longitude"] = result.get("longitude")


class CatalogPartSerializer(serializers.Serializer):
    """Serializer used to expose InvenTree parts in the rental catalog."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True, allow_blank=True)
    IPN = serializers.CharField(read_only=True, allow_blank=True, allow_null=True)
    active = serializers.BooleanField(read_only=True)
    category = serializers.IntegerField(source="category_id", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    rentable = serializers.SerializerMethodField()
    consommable = serializers.SerializerMethodField()

    def get_rentable(self, obj):
        """Drapeau louable issu de RentableItem."""

        rentable_info = getattr(obj, "rentable_info", None)

        if rentable_info is None:
            return True

        return bool(rentable_info.is_rentable)

    def get_consommable(self, obj):
        """Drapeau consommable issu de RentableItem."""

        rentable_info = getattr(obj, "rentable_info", None)

        if rentable_info is None:
            return False

        return bool(rentable_info.consommable)