"""API views for the InvenTreeLocation plugin."""

from datetime import date, timedelta
import random
import string
from urllib.error import HTTPError, URLError

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.mail import send_mail
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .conflicts import (
    build_part_availability_histogram,
    compute_part_availability,
    detect_reservation_conflicts,
    list_current_conflicts,
)
from .models import (
    Lieu,
    LigneReservation,
    Manifestation,
    Prestation,
    RentableItem,
    Reservation,
)
from .permissions import (
    CatalogPermission,
    LieuPermission,
    ReservationPermission,
    RoleBasedPermission,
)
from .serializers import (
    CatalogPartSerializer,
    ExampleSerializer,
    LieuSerializer,
    PrestationSerializer,
    RentableItemSerializer,
    ReservationSerializer,
    ReservationTransitionSerializer,
    UserSerializer,
    geocode_address,
)
from .services.workflow_service import (
    get_available_transitions,
    transition_reservation_status,
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


class CatalogPagination(PageNumberPagination):
    """Pagination for catalog results."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 100


class LieuListCreateView(generics.ListCreateAPIView):
    """List and create places with GPS coordinates."""

    permission_classes = [LieuPermission]
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
    """Retrieve, update or delete a place."""

    permission_classes = [LieuPermission]
    serializer_class = LieuSerializer
    queryset = Lieu.objects.select_related("prestation", "prestation__manifestation")


class GeocodeAddressView(APIView):
    """Geocode an address and return latitude / longitude."""

    permission_classes = [LieuPermission]

    def get(self, request, *args, **kwargs):
        """Return GPS coordinates for a given address."""

        address = request.query_params.get("address", "").strip()

        if not address:
            return Response(
                {"detail": "Le paramÃ¨tre address est obligatoire."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = geocode_address(address)
        except (HTTPError, URLError, TimeoutError) as error:
            return Response(
                {
                    "detail": "Le service de gÃ©ocodage est temporairement indisponible.",
                    "error": str(error),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if result is None:
            return Response(
                {"detail": "Aucune coordonnÃ©e trouvÃ©e pour cette adresse."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(result, status=status.HTTP_200_OK)


class ReservationListCreateView(generics.ListCreateAPIView):
    """CRUD rÃ©servation â€” partie collection.

    - GET  : liste les rÃ©servations, filtrables par statut et pÃ©riode.
    - POST : crÃ©e une nouvelle rÃ©servation (lignes imbriquÃ©es supportÃ©es).

    ParamÃ¨tres de filtre :
    - statut    : filtre exact sur le statut (rÃ©pÃ©table)
    - date_from : rÃ©servations dont le retour prÃ©vu est >= Ã  cette date
    - date_to   : rÃ©servations dont le retrait prÃ©vu est <= Ã  cette date
    - search    : recherche sur le numÃ©ro, l'Ã©vÃ©nement ou le demandeur

    Tri par date de demande dÃ©croissante par dÃ©faut.
    """

    serializer_class = ReservationSerializer
    permission_classes = [ReservationPermission]

    def get_queryset(self):
        """Retourne les rÃ©servations, filtrÃ©es par statut, pÃ©riode et recherche."""

        queryset = (
            Reservation.objects.select_related("prestation", "demandeur")
            .prefetch_related("lignes")
            .all()
            .order_by("-date_demande")
        )

        statuts = self.request.query_params.getlist("statut")

        if statuts:
            queryset = queryset.filter(statut__in=statuts)

        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")

        if date_from:
            queryset = queryset.filter(date_retour_prevue__gte=date_from)

        if date_to:
            queryset = queryset.filter(date_retrait_prevue__lte=date_to)

        search = self.request.query_params.get("search")

        if search:
            queryset = queryset.filter(
                Q(numero__icontains=search)
                | Q(prestation__nom__icontains=search)
                | Q(demandeur__username__icontains=search)
                | Q(demandeur__first_name__icontains=search)
                | Q(demandeur__last_name__icontains=search)
            )

        return queryset


class ReservationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """CRUD rÃ©servation â€” partie instance unique."""

    queryset = Reservation.objects.prefetch_related(
        "lignes",
        "status_logs",
    ).all()
    serializer_class = ReservationSerializer
    permission_classes = [ReservationPermission]


class ReservationConflictCheckView(APIView):
    """DÃ©tection des conflits de stock d'une rÃ©servation (US-03 / SCRUM-76).

    GET renvoie le dÃ©tail des conflits de stock de la rÃ©servation :
    - 200 s'il n'y a aucun conflit ;
    - 409 si au moins un conflit est dÃ©tectÃ©.
    """

    permission_classes = [ReservationPermission]

    def get(self, request, pk, *args, **kwargs):
        """Retourne les conflits de stock de la rÃ©servation."""

        reservation = (
            Reservation.objects.prefetch_related("lignes").filter(pk=pk).first()
        )

        if reservation is None:
            return Response(
                {"detail": "RÃ©servation introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        conflict_result = detect_reservation_conflicts(reservation)

        response_status = (
            status.HTTP_409_CONFLICT
            if conflict_result["has_conflict"]
            else status.HTTP_200_OK
        )

        return Response(conflict_result, status=response_status)


class ReservationTransitionView(APIView):
    """Endpoint permettant de faire Ã©voluer le statut d'une rÃ©servation."""

    permission_classes = [ReservationPermission]
    serializer_class = ReservationTransitionSerializer

    def get(self, request, pk, *args, **kwargs):
        """Retourne les transitions disponibles pour la rÃ©servation."""

        reservation = Reservation.objects.filter(pk=pk).first()

        if reservation is None:
            return Response(
                {"detail": "RÃ©servation introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "reservation": reservation.pk,
                "current_status": reservation.statut,
                "available_transitions": get_available_transitions(reservation.statut),
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk, *args, **kwargs):
        """Applique une transition de statut Ã  une rÃ©servation."""

        reservation = Reservation.objects.filter(pk=pk).first()

        if reservation is None:
            return Response(
                {"detail": "RÃ©servation introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = transition_reservation_status(
            reservation=reservation,
            new_status=serializer.validated_data["statut"],
            user=request.user,
            comment=serializer.validated_data.get("comment", ""),
        )

        return Response(result, status=status.HTTP_200_OK)


class ConflictsListView(APIView):
    """Liste les rÃ©servations actuellement en conflit."""

    permission_classes = [ReservationPermission]

    def get(self, request, *args, **kwargs):
        """Retourne les rÃ©servations en conflit triÃ©es par date de retrait prÃ©vue."""

        return Response(list_current_conflicts(), status=status.HTTP_200_OK)

class StockAlertListView(APIView):
    """Liste les objets en alerte de seuil / tension, avec option email."""

    permission_classes = [RoleBasedPermission]

    def get(self, request, *args, **kwargs):
        manifestation_id = request.query_params.get("manifestation")
        lieu_id = request.query_params.get("lieu")
        notify = str(request.query_params.get("notify", "")).lower() in {
            "1",
            "true",
            "yes",
        }

        alerts = self._build_alerts(
            manifestation_id=int(manifestation_id)
            if str(manifestation_id).isdigit()
            else None,
            lieu_id=int(lieu_id) if str(lieu_id).isdigit() else None,
        )

        email_sent = False
        if notify and alerts:
            email_sent = self._send_alert_email(alerts)

        return Response(
            {
                "count": len(alerts),
                "email_sent": email_sent,
                "alerts": alerts,
            },
            status=status.HTTP_200_OK,
        )

    def _build_alerts(self, manifestation_id=None, lieu_id=None):
        scope_ids = None

        if manifestation_id is not None or lieu_id is not None:
            scoped_lines = LigneReservation.objects.select_related(
                "reservation__prestation"
            )

            if manifestation_id is not None:
                scoped_lines = scoped_lines.filter(
                    reservation__prestation__manifestation_id=manifestation_id
                )

            if lieu_id is not None:
                scoped_lines = scoped_lines.filter(
                    reservation__prestation__lieux__id=lieu_id
                )

            scope_ids = set(scoped_lines.values_list("part_id", flat=True))

        rentable_items = RentableItem.objects.select_related("part").all()

        if scope_ids is not None:
            rentable_items = rentable_items.filter(part_id__in=scope_ids)

        alerts = []
        now = timezone.now()

        for rentable in rentable_items:
            part = rentable.part
            stock_available = self._safe_stock_available(part)
            low = rentable.seuil_alerte_bas
            high = rentable.seuil_alerte_haut

            part_reasons = []

            if rentable.consommable and low is not None and stock_available <= low:
                part_reasons.append(
                    {
                        "type": "low_threshold",
                        "message": f"Stock bas atteint ({stock_available} <= {low})",
                    }
                )

            if high is not None and stock_available >= high:
                part_reasons.append(
                    {
                        "type": "high_threshold",
                        "message": f"Seuil haut atteint ({stock_available} >= {high})",
                    }
                )

            projected = self._projected_tension(
                part_id=part.pk,
                total_stock=max(int(rentable.stock_total or 0), 1),
                now=now,
                manifestation_id=manifestation_id,
                lieu_id=lieu_id,
            )

            if projected["occupation_rate"] >= 90:
                part_reasons.append(
                    {
                        "type": "projected_tension",
                        "message": (
                            f"Tension projetée élevée "
                            f"({projected['occupation_rate']:.1f}% >= 90%)"
                        ),
                    }
                )

            if not part_reasons:
                continue

            alerts.append(
                {
                    "part_id": part.pk,
                    "part_name": getattr(part, "name", str(part)),
                    "consommable": rentable.consommable,
                    "stock_available": stock_available,
                    "stock_total": int(rentable.stock_total or 0),
                    "seuil_alerte_bas": low,
                    "seuil_alerte_haut": high,
                    "projected_reserved_quantity": projected["reserved_quantity"],
                    "projected_occupation_rate": round(projected["occupation_rate"], 2),
                    "reasons": part_reasons,
                }
            )

        alerts.sort(key=lambda item: item["part_name"].lower())

        return alerts

    def _projected_tension(self, part_id, total_stock, now, manifestation_id=None, lieu_id=None):
        end = now + timedelta(days=30)
        lines = LigneReservation.objects.filter(
            part_id=part_id,
            reservation__statut__in={
                "confirmée",
                "livrée",
                "retournée",
                "validee",
                "livree",
                "retournee",
            },
            reservation__date_retrait_prevue__lte=end,
            reservation__date_retour_prevue__gte=now,
        )

        if manifestation_id is not None:
            lines = lines.filter(reservation__prestation__manifestation_id=manifestation_id)

        if lieu_id is not None:
            lines = lines.filter(reservation__prestation__lieux__id=lieu_id)

        reserved = lines.aggregate(total=Sum("quantite_demandee"))["total"] or 0
        occupation = (reserved / max(total_stock, 1)) * 100

        return {
            "reserved_quantity": int(reserved),
            "occupation_rate": float(occupation),
        }

    def _safe_stock_available(self, part):
        for attr in ("stock_available", "available_stock", "in_stock", "total_stock"):
            value = getattr(part, attr, None)
            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    continue

        return 0

    def _send_alert_email(self, alerts):
        cache_key = "inventree_location_stock_alert_email_last_sent"
        last_sent = cache.get(cache_key)

        if last_sent:
            return False

        recipients = list(
            get_user_model()
            .objects.filter(groups__name__in=["admin", "gestionnaire"], is_active=True)
            .exclude(email="")
            .values_list("email", flat=True)
            .distinct()
        )

        if not recipients:
            return False

        lines = [
            f"- {item['part_name']} (stock {item['stock_available']}/{item['stock_total']})"
            for item in alerts
        ]

        subject = "[InvenTree Location] Alerte seuil stock"
        body = "Objets en alerte:\n\n" + "\n".join(lines)

        send_mail(
            subject=subject,
            message=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@inventree.local"),
            recipient_list=recipients,
            fail_silently=True,
        )
        cache.set(cache_key, timezone.now().isoformat(), timeout=3600)
        return True

class CatalogPartListView(APIView):
    """List InvenTree parts with catalog filters."""

    permission_classes = [CatalogPermission]
    serializer_class = CatalogPartSerializer
    pagination_class = CatalogPagination

    def get(self, request, *args, **kwargs):
        """Return a filtered and paginated catalog of InvenTree parts."""

        from part.models import Part

        queryset = (
            Part.objects.select_related("category", "rentable_info")
            .all()
            .order_by("name")
        )

        search = request.query_params.get("search")
        category = request.query_params.get("category")
        categories = request.query_params.get("categories")
        active = request.query_params.get("active")
        rentable = request.query_params.get("rentable")
        virtual = request.query_params.get("virtual")
        ids = request.query_params.get("ids")

        if ids:
            queryset = queryset.filter(pk__in=self._parse_ids(ids))

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
                | Q(IPN__icontains=search)
            )

        category_ids = self._parse_category_ids(category, categories)

        if category_ids:
            queryset = queryset.filter(category_id__in=category_ids)

        active_value = self._parse_boolean(active)

        if active_value is not None:
            queryset = queryset.filter(active=active_value)

        queryset = self._filter_rentable(queryset, rentable)
        queryset = self._filter_virtual(queryset, virtual)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)

        serializer = self.serializer_class(page, many=True)

        return paginator.get_paginated_response(serializer.data)

    def _parse_ids(self, ids):
        """Parse une liste d'identifiants de Part sÃ©parÃ©s par des virgules."""

        return [int(value) for value in str(ids).split(",") if value.strip().isdigit()]

    def _parse_category_ids(self, category, categories):
        """Parse category filters from query parameters."""

        values = []

        if category:
            values.append(category)

        if categories:
            values.extend(categories.split(","))

        category_ids = []

        for value in values:
            value = str(value).strip()

            if value.isdigit():
                category_ids.append(int(value))

        return category_ids

    def _parse_boolean(self, value):
        """Parse boolean query parameter."""

        if value is None:
            return None

        value = str(value).lower().strip()

        if value in ["true", "1", "yes", "y"]:
            return True

        if value in ["false", "0", "no", "n"]:
            return False

        return None

    def _filter_rentable(self, queryset, rentable):
        """Filtre le catalogue selon le drapeau louable de RentableItem."""

        if rentable is not None and str(rentable).lower().strip() == "all":
            return queryset

        rentable_value = self._parse_boolean(rentable)

        if rentable_value is None:
            rentable_value = True

        if rentable_value:
            return queryset.filter(
                Q(rentable_info__is_rentable=True) | Q(rentable_info__isnull=True)
            )

        return queryset.filter(rentable_info__is_rentable=False)

    def _filter_virtual(self, queryset, virtual):
        """Filtre optionnel sur le drapeau article virtuel de RentableItem.

        - virtual absent : pas de filtre (matÃ©riel rÃ©el + virtuel).
        - virtual=true    : articles virtuels uniquement (ex: prestations).
        - virtual=false   : matÃ©riel rÃ©el uniquement.
        """

        virtual_value = self._parse_boolean(virtual)

        if virtual_value is None:
            return queryset

        if virtual_value:
            return queryset.filter(rentable_info__is_virtual=True)

        return queryset.filter(
            Q(rentable_info__is_virtual=False) | Q(rentable_info__isnull=True)
        )


class CatalogPartDetailView(APIView):
    """Fiche dÃ©tail d'un Part du catalogue."""

    permission_classes = [CatalogPermission]
    serializer_class = CatalogPartSerializer

    def get(self, request, pk, *args, **kwargs):
        from part.models import Part

        part = (
            Part.objects.select_related("category", "rentable_info")
            .filter(pk=pk)
            .first()
        )

        if part is None:
            return Response(
                {"detail": "Part introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(part)
        return Response(serializer.data, status=status.HTTP_200_OK)


class RentableFlagBulkUpdateView(APIView):
    """Met Ã  jour en masse le drapeau louable / consommable de Part."""

    permission_classes = [CatalogPermission]

    def patch(self, request, *args, **kwargs):
        """Applique les drapeaux fournis Ã  la liste de parts."""

        from part.models import Part

        part_ids = request.data.get("part_ids")

        if not isinstance(part_ids, list) or not part_ids:
            return Response(
                {"detail": "part_ids doit Ãªtre une liste non vide."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        defaults = {}

        if "is_rentable" in request.data:
            defaults["is_rentable"] = bool(request.data.get("is_rentable"))

        if "consommable" in request.data:
            defaults["consommable"] = bool(request.data.get("consommable"))

        if "is_virtual" in request.data:
            defaults["is_virtual"] = bool(request.data.get("is_virtual"))

        if "stock_total" in request.data:
            defaults["stock_total"] = int(request.data.get("stock_total"))

        if not defaults:
            return Response(
                {
                    "detail": (
                        "Fournir au moins is_rentable, consommable, "
                        "is_virtual ou stock_total."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_ids = list(
            Part.objects.filter(pk__in=part_ids).values_list("pk", flat=True)
        )

        for part_id in valid_ids:
            RentableItem.objects.update_or_create(
                part_id=part_id,
                defaults=defaults,
            )

        return Response(
            {"updated": valid_ids, "applied": defaults},
            status=status.HTTP_200_OK,
        )


class RentablePartDetailView(APIView):
    """Drapeaux location d'un Part unique."""

    permission_classes = [CatalogPermission]
    serializer_class = RentableItemSerializer

    def get(self, request, pk, *args, **kwargs):
        """Retourne les drapeaux location du Part."""

        from part.models import Part

        if not Part.objects.filter(pk=pk).exists():
            return Response(
                {"detail": "Part introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        rentable_item = RentableItem.objects.filter(part_id=pk).first()

        if rentable_item is None:
            return Response(
                {
                    "part": pk,
                    "is_rentable": True,
                    "consommable": False,
                    "is_virtual": False,
                    "stock_total": 0,
                    "caution": None,
                    "valeur_remplacement": None,
                    "seuil_alerte_bas": None,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            self.serializer_class(rentable_item).data,
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk, *args, **kwargs):
        """CrÃ©e ou met Ã  jour les drapeaux location du Part."""

        from part.models import Part

        if not Part.objects.filter(pk=pk).exists():
            return Response(
                {"detail": "Part introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        rentable_item, _created = RentableItem.objects.get_or_create(part_id=pk)
        serializer = self.serializer_class(
            rentable_item,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data, status=status.HTTP_200_OK)


class PrestationListView(generics.ListAPIView):
    """Liste des prestations (lecture seule), pour le sÃ©lecteur Ã©vÃ©nement.

    ParamÃ¨tre de filtre :
    - search : recherche sur le nom de la prestation ou de sa manifestation.
    """

    permission_classes = [RoleBasedPermission]
    serializer_class = PrestationSerializer
    pagination_class = LieuPagination

    def get_queryset(self):
        """Retourne les prestations, filtrÃ©es par recherche texte."""

        queryset = (
            Prestation.objects.select_related("manifestation")
            .prefetch_related("lieux")
            .all()
            .order_by("-date_debut")
        )

        search = self.request.query_params.get("search")

        if search:
            queryset = queryset.filter(
                Q(nom__icontains=search) | Q(manifestation__nom__icontains=search)
            )

        return queryset


class UserListView(generics.ListAPIView):
    """Liste des utilisateurs actifs (lecture seule), pour le sÃ©lecteur demandeur.

    ParamÃ¨tre de filtre :
    - search : recherche sur username, prÃ©nom, nom ou email.
    """

    permission_classes = [RoleBasedPermission]
    serializer_class = UserSerializer
    pagination_class = CatalogPagination

    def get_queryset(self):
        """Retourne les utilisateurs actifs, filtrÃ©s par recherche texte."""

        queryset = get_user_model().objects.filter(is_active=True).order_by("username")

        search = self.request.query_params.get("search")

        if search:
            queryset = queryset.filter(
                Q(username__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
            )

        return queryset

