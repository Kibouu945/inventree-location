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
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .conflicts import (
    CONFLICT_STATUSES,
    detect_reservation_conflicts,
    list_current_conflicts,
)
from . import roles
from .models import (
    Groupe,
    Lieu,
    LigneReservation,
    Manifestation,
    Prestation,
    RentableItem,
    Reservation,
    StatutReservation,
)
from .permissions import (
    CatalogPermission,
    LieuPermission,
    ManifestationPermission,
    PrestationPermission,
    ReservationPermission,
    ReturnCheckinPermission,
    RoleBasedPermission,
)
from .serializers import (
    CatalogPartSerializer,
    ExampleSerializer,
    GroupeSerializer,
    LieuSerializer,
    ManifestationSerializer,
    PrestationSerializer,
    RentableItemSerializer,
    ReservationCheckinSerializer,
    ReservationSerializer,
    ReservationTransitionSerializer,
    UserSerializer,
    geocode_candidates,
)
from .stock import _as_date, compute_prestation_stock, compute_stock_availability
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
        """Return places, with optional search filter."""

        queryset = Lieu.objects.all().order_by("nom")

        search = self.request.query_params.get("search")

        if search:
            queryset = queryset.filter(
                Q(nom__icontains=search) | Q(adresse__icontains=search)
            )

        return queryset


class LieuDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a place."""

    permission_classes = [LieuPermission]
    serializer_class = LieuSerializer
    queryset = Lieu.objects.all()


class GeocodeAddressView(APIView):
    """Geocode an address and return latitude / longitude."""

    permission_classes = [LieuPermission]

    def get(self, request, *args, **kwargs):
        """Return a list of geocoding candidates for a given address."""

        address = request.query_params.get("address", "").strip()

        if not address:
            return Response(
                {"detail": "Le paramètre address est obligatoire."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            results = geocode_candidates(address)
        except (HTTPError, URLError, TimeoutError) as error:
            return Response(
                {
                    "detail": "Le service de géocodage est temporairement indisponible.",
                    "error": str(error),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if not results:
            return Response(
                {"detail": "Aucune coordonnée trouvée pour cette adresse."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({"results": results}, status=status.HTTP_200_OK)


class ReservationListCreateView(generics.ListCreateAPIView):
    """CRUD réservation — partie collection.

    - GET  : liste les réservations, filtrables par statut et période.
    - POST : crée une nouvelle réservation (lignes imbriquées supportées).

    Paramètres de filtre :
    - statut    : filtre exact sur le statut (répétable)
    - date_from : réservations dont le retour prévu est >= à cette date
    - date_to   : réservations dont le retrait prévu est <= à cette date
    - search    : recherche sur le numéro, l'événement ou le demandeur

    Tri par date de demande décroissante par défaut.
    """

    serializer_class = ReservationSerializer
    permission_classes = [ReservationPermission]

    @staticmethod
    def _parse_csv_int_values(values):
        """Parse les valeurs CSV / répétables en une liste d'entiers uniques."""

        parsed = []
        seen = set()

        for value in values:
            for chunk in value.split(","):
                chunk = chunk.strip()
                if not chunk:
                    continue

                try:
                    candidate = int(chunk)
                except ValueError:
                    continue

                if candidate in seen:
                    continue

                seen.add(candidate)
                parsed.append(candidate)

        return parsed

    def get_queryset(self):
        """Retourne les réservations, filtrées par statut, période et recherche."""

        queryset = (
            Reservation.objects.select_related("prestation", "demandeur")
            .prefetch_related("lignes")
            .all()
            .order_by("-date_demande")
        )

        # Un livreur pur ne voit que les réservations validées.
        if roles.sees_only_deliverable_reservations(self.request.user):
            queryset = queryset.filter(statut=StatutReservation.VALIDEE)

        statuts = self.request.query_params.getlist("statut")

        if statuts:
            queryset = queryset.filter(statut__in=statuts)

        categories = self._parse_csv_int_values(
            self.request.query_params.getlist("categories")
        )

        if categories:
            queryset = queryset.filter(
                lignes__part__category_id__in=categories
            ).distinct()

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
    """CRUD réservation — partie instance unique."""

    queryset = Reservation.objects.prefetch_related(
        "lignes",
        "status_logs",
    ).all()
    serializer_class = ReservationSerializer
    permission_classes = [ReservationPermission]

    #: Une réservation n'est modifiable qu'avant validation.
    STATUTS_EDITABLES = (StatutReservation.BROUILLON, StatutReservation.SOUMISE)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.statut not in self.STATUTS_EDITABLES:
            raise ValidationError({
                "detail": (
                    f"Une réservation « {instance.get_statut_display().lower()} » "
                    "n'est plus modifiable."
                )
            })
        return super().update(request, *args, **kwargs)

    def perform_destroy(self, instance):
        # Seul un brouillon se supprime ; au-delà on annule via une transition.
        if instance.statut != StatutReservation.BROUILLON:
            raise ValidationError({
                "detail": "Seule une réservation en brouillon peut être supprimée."
            })
        instance.delete()


class ReservationConflictCheckView(APIView):
    """Détection des conflits de stock d'une réservation (US-03 / SCRUM-76).

    GET renvoie le détail des conflits de stock de la réservation :
    - 200 s'il n'y a aucun conflit ;
    - 409 si au moins un conflit est détecté.
    """

    permission_classes = [ReservationPermission]

    def get(self, request, pk, *args, **kwargs):
        """Retourne les conflits de stock de la réservation."""

        reservation = (
            Reservation.objects.prefetch_related("lignes").filter(pk=pk).first()
        )

        if reservation is None:
            return Response(
                {"detail": "Réservation introuvable."},
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
    """Endpoint permettant de faire évoluer le statut d'une réservation."""

    permission_classes = [ReservationPermission]
    serializer_class = ReservationTransitionSerializer

    def get(self, request, pk, *args, **kwargs):
        """Retourne les transitions disponibles pour la réservation."""

        reservation = Reservation.objects.filter(pk=pk).first()

        if reservation is None:
            return Response(
                {"detail": "Réservation introuvable."},
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
        """Applique une transition de statut à une réservation."""

        reservation = Reservation.objects.filter(pk=pk).first()

        if reservation is None:
            return Response(
                {"detail": "Réservation introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data["statut"]

        # L'arbitrage (valider / refuser) est réservé au gestionnaire et à l'admin.
        arbitrage = {StatutReservation.VALIDEE, StatutReservation.REFUSEE}
        if new_status in arbitrage and not roles.can_arbitrate_reservations(
            request.user
        ):
            return Response(
                {"detail": "Seul un gestionnaire peut valider ou refuser."},
                status=status.HTTP_403_FORBIDDEN,
            )

        result = transition_reservation_status(
            reservation=reservation,
            new_status=new_status,
            user=request.user,
            comment=serializer.validated_data.get("comment", ""),
        )

        return Response(result, status=status.HTTP_200_OK)


class ReservationCheckinView(APIView):
    """Check-in retour ligne par ligne (SCRUM-94) : OK / manquant / casse.

    - GET  : accessible uniquement quand la reservation est au statut
      livree ; renvoie les lignes a pointer.
    - POST : valide que somme(ok + manquant + casse) == quantite demandee
      pour chaque ligne, journalise les incidents, puis cloture la
      reservation (livree -> retournee -> cloturee).
    """

    permission_classes = [ReturnCheckinPermission]
    serializer_class = ReservationCheckinSerializer

    def _get_reservation(self, pk):
        return (
            Reservation.objects.prefetch_related("lignes", "lignes__part")
            .filter(pk=pk)
            .first()
        )

    def get(self, request, pk, *args, **kwargs):
        """Retourne la reservation et ses lignes si elle est livree."""

        reservation = self._get_reservation(pk)

        if reservation is None:
            return Response(
                {"detail": "Reservation introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if reservation.statut != StatutReservation.LIVREE:
            return Response(
                {
                    "detail": (
                        "Le check-in retour n'est accessible que pour une "
                        "reservation livree."
                    ),
                    "current_status": reservation.statut,
                },
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            {
                "reservation": reservation.pk,
                "numero": reservation.numero,
                "statut": reservation.statut,
                "lignes": [
                    {
                        "id": ligne.pk,
                        "part": ligne.part_id,
                        "part_name": getattr(ligne.part, "name", str(ligne.part)),
                        "quantite_demandee": ligne.quantite_demandee,
                        "quantite_retour_ok": ligne.quantite_retour_ok,
                        "quantite_retour_manquant": ligne.quantite_retour_manquant,
                        "quantite_retour_casse": ligne.quantite_retour_casse,
                        "commentaire": ligne.commentaire,
                    }
                    for ligne in reservation.lignes.all()
                ],
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request, pk, *args, **kwargs):
        """Enregistre le check-in retour et cloture la reservation."""

        reservation = self._get_reservation(pk)

        if reservation is None:
            return Response(
                {"detail": "Reservation introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if reservation.statut != StatutReservation.LIVREE:
            return Response(
                {
                    "detail": (
                        "Le check-in retour n'est accessible que pour une "
                        "reservation livree."
                    ),
                    "current_status": reservation.statut,
                },
                status=status.HTTP_409_CONFLICT,
            )

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        lignes_by_id = {ligne.pk: ligne for ligne in reservation.lignes.all()}
        payload_lignes = serializer.validated_data["lignes"]
        errors = {}

        for entry in payload_lignes:
            ligne = lignes_by_id.get(entry["id"])

            if ligne is None:
                errors[str(entry["id"])] = (
                    "Cette ligne n'appartient pas a la reservation."
                )
                continue

            total = entry["ok"] + entry["manquant"] + entry["casse"]

            if total != ligne.quantite_demandee:
                errors[str(entry["id"])] = (
                    "La somme OK + manquant + casse (" + str(total) + ") doit "
                    "egaler la quantite demandee ("
                    + str(ligne.quantite_demandee)
                    + ")."
                )

        if errors:
            return Response({"lignes": errors}, status=status.HTTP_400_BAD_REQUEST)

        incidents = []

        for entry in payload_lignes:
            ligne = lignes_by_id[entry["id"]]
            ligne.quantite_retour_ok = entry["ok"]
            ligne.quantite_retour_manquant = entry["manquant"]
            ligne.quantite_retour_casse = entry["casse"]
            ligne.quantite_retournee = entry["ok"] + entry["casse"]
            ligne.commentaire = entry.get("commentaire", "")

            if entry["casse"] > 0:
                ligne.etat_retour = "casse"
            elif entry["manquant"] > 0:
                ligne.etat_retour = "manquant"
            else:
                ligne.etat_retour = "ok"

            ligne.save(
                update_fields=[
                    "quantite_retour_ok",
                    "quantite_retour_manquant",
                    "quantite_retour_casse",
                    "quantite_retournee",
                    "commentaire",
                    "etat_retour",
                    "updated_at",
                ]
            )

            if entry["manquant"] > 0 or entry["casse"] > 0:
                incidents.append(
                    str(getattr(ligne.part, "name", ligne.part_id))
                    + ": "
                    + str(entry["manquant"])
                    + " manquant(s), "
                    + str(entry["casse"])
                    + " casse(s)"
                )

        incident_comment = (
            "Incidents check-in : " + "; ".join(incidents)
            if incidents
            else "Check-in retour sans incident."
        )

        transition_reservation_status(
            reservation=reservation,
            new_status=StatutReservation.RETOURNEE,
            user=request.user,
            comment=incident_comment,
        )
        transition_reservation_status(
            reservation=reservation,
            new_status=StatutReservation.CLOTUREE,
            user=request.user,
            comment="Cloturee automatiquement apres check-in retour.",
        )

        reservation.refresh_from_db()

        return Response(
            {
                "reservation": reservation.pk,
                "statut": reservation.statut,
                "incidents": incidents,
            },
            status=status.HTTP_200_OK,
        )


class ConflictsListView(APIView):
    """Liste les réservations actuellement en conflit."""

    permission_classes = [ReservationPermission]

    def get(self, request, *args, **kwargs):
        """Retourne les réservations en conflit triées par date de retrait prévue."""

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
                    reservation__prestation__lieu_id=lieu_id
                )

            scope_ids = set(scoped_lines.values_list("part_id", flat=True))

        # Les articles virtuels (services, ex. « nettoyage ») n'ont pas de stock
        # physique : ni seuil, ni tension n'ont de sens pour eux. Sans ce filtre
        # ils remontaient en alerte à 200 % de « 0 louable(s) ».
        rentable_items = (
            RentableItem.objects.select_related("part").filter(is_virtual=False).all()
        )

        if scope_ids is not None:
            rentable_items = rentable_items.filter(part_id__in=scope_ids)

        from .conflicts import get_part_total_stock
        from .stock import compute_parts_availability

        rentable_items = list(rentable_items)
        alerts = []
        now = timezone.now()

        # Une seule passe pour la disponibilité du jour de tous les articles.
        availability = compute_parts_availability([
            rentable.part_id for rentable in rentable_items
        ])

        for rentable in rentable_items:
            part = rentable.part
            # Deux grandeurs distinctes, une seule source : ce qu'on possède de
            # louable (InvenTree) et ce qu'il en reste de libre aujourd'hui.
            stock_total = get_part_total_stock(part, rentable_item=rentable)
            stock_available = availability.get(part.pk, stock_total)
            low = rentable.seuil_alerte_bas
            high = rentable.seuil_alerte_haut

            part_reasons = []

            # Les seuils portent sur ce qu'on possède, pas sur ce qui est libre
            # à l'instant : réapprovisionner se décide sur le parc, pas sur le
            # calendrier des réservations.
            if rentable.consommable and low is not None and stock_total <= low:
                part_reasons.append({
                    "type": "low_threshold",
                    "message": (
                        f"Stock trop bas : {stock_total} en stock, "
                        f"seuil bas fixé à {low}"
                    ),
                })

            if high is not None and stock_total >= high:
                part_reasons.append({
                    "type": "high_threshold",
                    "message": (
                        f"Stock au-dessus du seuil haut : "
                        f"{stock_total} en stock, seuil haut fixé à {high}"
                    ),
                })

            projected = self._projected_tension(
                part_id=part.pk,
                total_stock=max(stock_total, 1),
                now=now,
                manifestation_id=manifestation_id,
                lieu_id=lieu_id,
            )

            if projected["occupation_rate"] >= 90:
                part_reasons.append({
                    "type": "projected_tension",
                    "message": (
                        f"Tension projetée {projected['occupation_rate']:.1f} % : "
                        f"{projected['reserved_quantity']} réservé(s) sur "
                        f"{stock_total} louable(s), "
                        f"alerte au-delà de 90 %"
                    ),
                })

            if not part_reasons:
                continue

            alerts.append({
                "part_id": part.pk,
                "part_name": getattr(part, "name", str(part)),
                "consommable": rentable.consommable,
                "stock_available": stock_available,
                "stock_total": stock_total,
                "seuil_alerte_bas": low,
                "seuil_alerte_haut": high,
                "projected_reserved_quantity": projected["reserved_quantity"],
                "projected_occupation_rate": round(projected["occupation_rate"], 2),
                "reasons": part_reasons,
            })

        alerts.sort(key=lambda item: item["part_name"].lower())

        return alerts

    def _projected_tension(
        self, part_id, total_stock, now, manifestation_id=None, lieu_id=None
    ):
        end = now + timedelta(days=30)
        lines = LigneReservation.objects.filter(
            part_id=part_id,
            reservation__statut__in=CONFLICT_STATUSES,
            reservation__date_retrait_prevue__lte=end,
            reservation__date_retour_prevue__gte=now,
        )

        if manifestation_id is not None:
            lines = lines.filter(
                reservation__prestation__manifestation_id=manifestation_id
            )

        if lieu_id is not None:
            lines = lines.filter(reservation__prestation__lieu_id=lieu_id)

        reserved = lines.aggregate(total=Sum("quantite_demandee"))["total"] or 0
        occupation = (reserved / max(total_stock, 1)) * 100

        return {
            "reserved_quantity": int(reserved),
            "occupation_rate": float(occupation),
        }

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
            from_email=getattr(
                settings, "DEFAULT_FROM_EMAIL", "noreply@inventree.local"
            ),
            recipient_list=recipients,
            fail_silently=True,
        )
        cache.set(cache_key, timezone.now().isoformat(), timeout=3600)
        return True


def parse_optional_date_param(request, name):
    """Lit un paramètre de date optionnel de la query string.

    Absent ou vide vaut « non fourni » (l'appelant retombe alors sur la
    journée courante). Une valeur malformée est une erreur du client : on
    renvoie 400 plutôt que de laisser remonter la `ValueError` de `_as_date`
    en 500 depuis un endpoint de liste public.
    """

    raw = request.query_params.get(name)

    if raw is None or not raw.strip():
        return None

    try:
        return _as_date(raw)
    except ValueError:
        raise ValidationError({
            name: "Date invalide : format attendu AAAA-MM-JJ (ou ISO 8601)."
        }) from None


def parse_optional_int_param(request, name):
    """Lit un paramètre entier optionnel de la query string (None si absent)."""

    raw = request.query_params.get(name)

    if raw is None or not str(raw).strip():
        return None

    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValidationError({
            name: "Identifiant invalide : entier attendu."
        }) from None


def annotate_stock_available(
    parts, date_debut=None, date_fin=None, exclude_reservation_id=None
):
    """Attache `.stock_available` à chaque Part pour la sérialisation catalogue.

    Sans `date_debut`/`date_fin`, la disponibilité est calculée pour la
    journée courante (CAT-04). Les articles virtuels (services) restent à
    `None`, exposés en 0 par le sérialiseur.

    `exclude_reservation_id` sert à l'édition d'une réservation : ses propres
    quantités ne doivent pas être décomptées de ce qu'elle peut demander.
    """

    from .stock import compute_parts_availability

    parts = list(parts)
    availability = compute_parts_availability(
        [part.pk for part in parts],
        date_debut,
        date_fin,
        exclude_reservation_id=exclude_reservation_id,
    )

    for part in parts:
        part.stock_available = availability.get(part.pk)


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

        annotate_stock_available(
            page,
            parse_optional_date_param(request, "date_debut"),
            parse_optional_date_param(request, "date_fin"),
            parse_optional_int_param(request, "exclude_reservation"),
        )

        serializer = self.serializer_class(page, many=True)

        return paginator.get_paginated_response(serializer.data)

    def _parse_ids(self, ids):
        """Parse une liste d'identifiants de Part séparés par des virgules."""

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

        - virtual absent : pas de filtre (matériel réel + virtuel).
        - virtual=true    : articles virtuels uniquement (ex: prestations).
        - virtual=false   : matériel réel uniquement.
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
    """Fiche détail d'un Part du catalogue."""

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

        annotate_stock_available(
            [part],
            parse_optional_date_param(request, "date_debut"),
            parse_optional_date_param(request, "date_fin"),
            parse_optional_int_param(request, "exclude_reservation"),
        )

        serializer = self.serializer_class(part)
        return Response(serializer.data, status=status.HTTP_200_OK)


class RentableFlagBulkUpdateView(APIView):
    """Met à jour en masse le drapeau louable / consommable de Part."""

    permission_classes = [CatalogPermission]

    def patch(self, request, *args, **kwargs):
        """Applique les drapeaux fournis à la liste de parts."""

        from part.models import Part

        part_ids = request.data.get("part_ids")

        if not isinstance(part_ids, list) or not part_ids:
            return Response(
                {"detail": "part_ids doit être une liste non vide."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        defaults = {}

        if "is_rentable" in request.data:
            defaults["is_rentable"] = bool(request.data.get("is_rentable"))

        if "consommable" in request.data:
            defaults["consommable"] = bool(request.data.get("consommable"))

        if "is_virtual" in request.data:
            defaults["is_virtual"] = bool(request.data.get("is_virtual"))

        # Le stock ne se règle pas ici : il appartient à InvenTree et se met à
        # jour par les StockItem (cf. conflicts.get_part_total_stock).
        if "stock_total" in request.data:
            return Response(
                {
                    "stock_total": (
                        "Le stock est celui d'InvenTree : mettez l'article en "
                        "stock (StockItem) plutôt que de saisir une quantité ici."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not defaults:
            return Response(
                {
                    "detail": (
                        "Fournir au moins is_rentable, consommable ou is_virtual."
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
        """Crée ou met à jour les drapeaux location du Part."""

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


class ManifestationListCreateView(generics.ListCreateAPIView):
    """CRUD manifestation — collection (ORG-01)."""

    permission_classes = [ManifestationPermission]
    serializer_class = ManifestationSerializer
    pagination_class = LieuPagination

    def get_queryset(self):
        """Retourne les manifestations, filtrées par statut et recherche."""

        queryset = (
            Manifestation.objects.select_related("organisateur", "groupe")
            .all()
            .order_by("-date_debut")
        )

        statuts = self.request.query_params.getlist("statut")

        if statuts:
            queryset = queryset.filter(statut__in=statuts)

        search = self.request.query_params.get("search")

        if search:
            queryset = queryset.filter(nom__icontains=search)

        return queryset


class ManifestationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """CRUD manifestation — instance unique (ORG-01)."""

    permission_classes = [ManifestationPermission]
    serializer_class = ManifestationSerializer
    queryset = Manifestation.objects.select_related("organisateur", "groupe")


def _prestation_queryset():
    """Queryset commun aux vues prestation, avec relations préchargées."""

    return (
        Prestation.objects.select_related("manifestation", "lieu")
        .prefetch_related("lignes_prestation__part")
        .all()
    )


class PrestationListCreateView(generics.ListCreateAPIView):
    """CRUD prestation — collection (ORG-01 / RES-09).

    Paramètres de filtre :
    - manifestation : filtre exact sur la manifestation parente.
    - search        : recherche sur le nom de la prestation ou de sa manifestation.
    """

    permission_classes = [PrestationPermission]
    serializer_class = PrestationSerializer
    pagination_class = LieuPagination

    def get_queryset(self):
        """Retourne les prestations, filtrées par manifestation et recherche."""

        queryset = _prestation_queryset().order_by("-date_debut")

        manifestation_id = self.request.query_params.get("manifestation")

        if manifestation_id:
            queryset = queryset.filter(manifestation_id=manifestation_id)

        search = self.request.query_params.get("search")

        if search:
            queryset = queryset.filter(
                Q(nom__icontains=search) | Q(manifestation__nom__icontains=search)
            )

        return queryset


class PrestationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """CRUD prestation — instance unique (ORG-01 / RES-09)."""

    permission_classes = [PrestationPermission]
    serializer_class = PrestationSerializer
    queryset = _prestation_queryset()


class PrestationStockView(APIView):
    """Disponibilité au jour des articles d'une prestation enregistrée (STK-01).

    - 200 s'il n'y a aucune pénurie ;
    - 409 si au moins un article est en pénurie.
    """

    permission_classes = [PrestationPermission]

    def get(self, request, pk, *args, **kwargs):
        """Retourne la disponibilité de stock de la prestation."""

        prestation = (
            Prestation.objects.prefetch_related("lignes_prestation")
            .filter(pk=pk)
            .first()
        )

        if prestation is None:
            return Response(
                {"detail": "Prestation introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        result = compute_prestation_stock(prestation)

        response_status = (
            status.HTTP_409_CONFLICT if result["has_shortage"] else status.HTTP_200_OK
        )

        return Response(result, status=response_status)


class PrestationStockPreviewView(APIView):
    """Disponibilité au jour AVANT sauvegarde (temps réel côté front, STK-01).

    Corps attendu : ``{"date_debut", "date_fin", "lignes": [{"part", "quantite"}],
    "exclude_prestation": <pk optionnel>}``.
    """

    permission_classes = [PrestationPermission]

    def post(self, request, *args, **kwargs):
        """Calcule la disponibilité pour une saisie non encore enregistrée."""

        date_debut = request.data.get("date_debut")
        date_fin = request.data.get("date_fin")
        lignes = request.data.get("lignes") or []

        if not date_debut or not date_fin:
            return Response(
                {"detail": "date_debut et date_fin sont obligatoires."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        requested_lines = [
            {"part_id": ligne.get("part"), "quantite": ligne.get("quantite", 0)}
            for ligne in lignes
            if ligne.get("part") is not None
        ]

        result = compute_stock_availability(
            date_debut,
            date_fin,
            requested_lines,
            exclude_prestation_id=request.data.get("exclude_prestation"),
        )

        response_status = (
            status.HTTP_409_CONFLICT if result["has_shortage"] else status.HTTP_200_OK
        )

        return Response(result, status=response_status)


class GroupeListView(generics.ListAPIView):
    """Liste des groupes scouts (lecture seule), pour le sélecteur manifestation."""

    permission_classes = [RoleBasedPermission]
    serializer_class = GroupeSerializer
    pagination_class = CatalogPagination

    def get_queryset(self):
        """Retourne les groupes, filtrés par recherche texte."""

        queryset = Groupe.objects.all().order_by("nom")

        search = self.request.query_params.get("search")

        if search:
            queryset = queryset.filter(
                Q(nom__icontains=search) | Q(code__icontains=search)
            )

        return queryset


class UserListView(generics.ListAPIView):
    """Liste des utilisateurs actifs (lecture seule), pour le sélecteur demandeur.

    Paramètre de filtre :
    - search : recherche sur username, prénom, nom ou email.
    """

    permission_classes = [RoleBasedPermission]
    serializer_class = UserSerializer
    pagination_class = CatalogPagination

    def get_queryset(self):
        """Retourne les utilisateurs actifs, filtrés par recherche texte."""

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
