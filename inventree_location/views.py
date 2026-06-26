"""API views for the InvenTreeLocation plugin."""

from datetime import date
import random
import string
from urllib.error import HTTPError, URLError

from rest_framework import generics, permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Lieu, Reservation
from .serializers import (
    ExampleSerializer,
    LieuSerializer,
    ReservationSerializer,
    geocode_address,
)


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


class LieuPagination(PageNumberPagination):
    """Pagination for location places."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class LieuListCreateView(generics.ListCreateAPIView):
    """List and create places with GPS coordinates."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LieuSerializer
    pagination_class = LieuPagination

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
    """Geocode an address and return latitude / longitude."""

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
            result = geocode_address(address)
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


class ReservationListCreateView(generics.ListCreateAPIView):
    """CRUD réservation — partie collection.

    - GET  : liste toutes les réservations.
    - POST : crée une nouvelle réservation à partir des données envoyées.
    """

    queryset = Reservation.objects.all()
    serializer_class = ReservationSerializer
    permission_classes = [permissions.IsAuthenticated]


class ReservationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """CRUD réservation — partie instance unique.

    - GET    : lit une réservation.
    - PUT    : remplace l'intégralité de ses champs.
    - PATCH  : modifie partiellement ses champs.
    - DELETE : la supprime.
    """

    queryset = Reservation.objects.all()
    serializer_class = ReservationSerializer
    permission_classes = [permissions.IsAuthenticated]