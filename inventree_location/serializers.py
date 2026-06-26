"""API serializers for the InvenTreeLocation plugin."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from rest_framework import serializers

from .models import Lieu, Reservation


def geocode_address(address):
    """Return GPS coordinates for an address using OpenStreetMap Nominatim."""

    if not address:
        return None

    query = urlencode({
        "q": address,
        "format": "json",
        "limit": 1,
    })

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


class ReservationSerializer(serializers.ModelSerializer):
    """Sérialiseur DRF pour le modèle Reservation."""

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
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


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
    """Serializer for location places with GPS coordinates.

    If auto_geocode is set to true and an address is provided without
    latitude / longitude, the serializer tries to fill GPS coordinates
    automatically using the geocoding service.
    """

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
