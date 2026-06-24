"""API views for the InvenTreeLocation plugin.

In practice, you would define your custom views here.

Ref: https://www.django-rest-framework.org/api-guide/views/
"""

from datetime import date
import random
import string

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import ExampleSerializer


class ExampleView(APIView):
    """Example API view for the InvenTreeLocation plugin.

    This view returns some very simple example data,
    but the concept can be extended to include more complex logic.
    """

    # You can control which users can access this view using DRF permissions
    permission_classes = [permissions.IsAuthenticated]

    # Control how the response is formatted
    serializer_class = ExampleSerializer

    def get(self, request, *args, **kwargs):
        """Override the GET method to return example data."""

        from part.models import Part

        response_serializer = self.serializer_class(
            data={
                "random_text": "".join(random.choices(string.ascii_letters, k=50)),
                "part_count": Part.objects.count(),
                "today": date.today(),
            }
        )

        # Serializer must be validated before it can be returned to the client
        response_serializer.is_valid(raise_exception=True)

        return Response(response_serializer.data, status=200)
"""API views for the InvenTreeLocation plugin."""

from datetime import date
import json
import random
import string
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Lieu
from .serializers import ExampleSerializer, LieuSerializer


class ExampleView(APIView):
    """Example API view for the InvenTreeLocation plugin."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ExampleSerializer

    def get(self, request, *args, **kwargs):
        """Override the GET method to return example data."""

        from part.models import Part

        response_serializer = self.serializer_class(
            data={
                "random_text": "".join(random.choices(string.ascii_letters, k=50)),
                "part_count": Part.objects.count(),
                "today": date.today(),
            }
        )

        response_serializer.is_valid(raise_exception=True)

        return Response(response_serializer.data, status=200)


class LieuListCreateView(generics.ListCreateAPIView):
    """List and create places with GPS coordinates."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LieuSerializer

    def get_queryset(self):
        """Return places, with optional filters."""

        queryset = (
            Lieu.objects.select_related("prestation", "prestation__manifestation")
            .all()
            .order_by("nom")
        )

        prestation_id = self.request.query_params.get("prestation")
        search = self.request.query_params.get("search")

        if prestation_id:
            queryset = queryset.filter(prestation_id=prestation_id)

        if search:
            queryset = queryset.filter(nom__icontains=search)

        return queryset


class LieuDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a place.

    This endpoint allows manual update of GPS coordinates:
    - adresse
    - latitude
    - longitude
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LieuSerializer
    queryset = Lieu.objects.select_related("prestation", "prestation__manifestation")


class GeocodeAddressView(APIView):
    """Geocode an address and return latitude / longitude.

    This endpoint uses OpenStreetMap Nominatim.
    It does not save data directly in the database.
    The frontend or another backend workflow can use the response
    to fill latitude and longitude on a Lieu.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        """Return GPS coordinates for a given address."""

        address = request.query_params.get("address", "").strip()

        if not address:
            return Response(
                {"detail": "Le paramètre address est obligatoire."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = self._geocode_address(address)
        except (HTTPError, URLError, TimeoutError) as error:
            return Response(
                {
                    "detail": "Le service de géocodage est temporairement indisponible.",
                    "error": str(error),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if result is None:
            return Response(
                {"detail": "Aucune coordonnée trouvée pour cette adresse."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(result, status=status.HTTP_200_OK)

    def _geocode_address(self, address):
        """Call Nominatim and return the first result."""

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