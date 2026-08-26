"""API SCRUM-112 — stock réel, retours ramassage et workflow SAV."""

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    LigneReservation,
    RentableItem,
    Reservation,
    SavTicket,
    StatutReservation,
    StatutSavTicket,
    TypeSavTicket,
)
from .permissions import ReservationPermission, RoleBasedPermission


SAV_BLOCKING_STATUSES = [
    StatutSavTicket.OUVERT,
    StatutSavTicket.EN_REPARATION,
]

SAV_AVAILABLE_STATUSES = [
    StatutSavTicket.REPARE,
    StatutSavTicket.CLOTURE,
]


def _sum_or_zero(queryset, field_name: str) -> int:
    """Retourne une somme entière, 0 si aucune ligne."""

    result = queryset.aggregate(total=Sum(field_name))

    return int(result["total"] or 0)


def get_unavailable_stock_quantity(part_id: int) -> int:
    """Calcule les quantités qui sortent du stock réellement disponible.

    Règle SCRUM-112 :
    - SAV ouvert / en réparation : indisponible temporairement.
    - Détruit : indisponible définitivement.
    - Manquant : indisponible tant que la ligne de retour le signale.
    """

    sav_quantity = _sum_or_zero(
        SavTicket.objects.filter(
            part_id=part_id,
            type_ticket=TypeSavTicket.REPARATION,
            statut__in=SAV_BLOCKING_STATUSES,
        ),
        "quantite",
    )

    destroyed_quantity = _sum_or_zero(
        SavTicket.objects.filter(
            part_id=part_id,
            type_ticket=TypeSavTicket.DESTRUCTION,
            statut=StatutSavTicket.DETRUIT,
        ),
        "quantite",
    )

    missing_quantity = _sum_or_zero(
        LigneReservation.objects.filter(
            part_id=part_id,
            quantite_manquante__gt=0,
            reservation__statut__in=[
                StatutReservation.LIVREE,
                StatutReservation.RETOURNEE,
                StatutReservation.CLOTUREE,
            ],
        ),
        "quantite_manquante",
    )

    return sav_quantity + destroyed_quantity + missing_quantity


def get_real_available_stock(part_id: int) -> int:
    """Stock réellement disponible pour les futures réservations."""

    rentable_item = RentableItem.objects.filter(part_id=part_id).first()

    if rentable_item is None:
        return 0

    theoretical_stock = int(rentable_item.stock_total or 0)
    unavailable_stock = get_unavailable_stock_quantity(part_id)

    return max(theoretical_stock - unavailable_stock, 0)


def _derive_return_state(ligne: LigneReservation) -> str:
    """Déduit un état de retour lisible depuis les quantités SCRUM-112."""

    states = []

    if ligne.quantite_ramassee:
        states.append("ok")

    if ligne.quantite_sav:
        states.append("sav")

    if ligne.quantite_detruite:
        states.append("detruit")

    if ligne.quantite_manquante:
        states.append("manquant")

    if not states:
        return ""

    if len(states) == 1:
        return states[0]

    return "mixte"


def _close_or_update_ticket(
    *,
    ligne: LigneReservation,
    type_ticket: str,
    quantite: int,
    statut_si_quantite: str,
    user,
    facturer_client: bool,
    description: str,
):
    """Crée, met à jour ou clôture un ticket lié à une ligne."""

    ticket = SavTicket.objects.filter(
        ligne_reservation=ligne,
        type_ticket=type_ticket,
    ).first()

    if quantite <= 0:
        if ticket and ticket.statut not in [
            StatutSavTicket.REPARE,
            StatutSavTicket.DETRUIT,
            StatutSavTicket.CLOTURE,
        ]:
            ticket.statut = StatutSavTicket.CLOTURE
            ticket.quantite = 0
            ticket.updated_by = user
            ticket.closed_at = timezone.now()
            ticket.resolution = (
                "Ticket clôturé automatiquement car quantité remise à 0."
            )
            ticket.save()

        return None

    if ticket is None:
        ticket = SavTicket.objects.create(
            ligne_reservation=ligne,
            reservation=ligne.reservation,
            part=ligne.part,
            type_ticket=type_ticket,
            statut=statut_si_quantite,
            quantite=quantite,
            facturer_client=facturer_client,
            description=description,
            created_by=user,
            updated_by=user,
        )

        return ticket

    ticket.quantite = quantite
    ticket.facturer_client = facturer_client
    ticket.description = description or ticket.description
    ticket.updated_by = user

    if ticket.statut in [StatutSavTicket.CLOTURE, StatutSavTicket.REPARE]:
        ticket.statut = statut_si_quantite
        ticket.closed_at = None

    ticket.save()

    return ticket


class RetourRamassageLigneSerializer(serializers.Serializer):
    """Entrée API pour saisir le retour d'une ligne de ramassage."""

    ligne = serializers.IntegerField(required=True)
    quantite_ramassee = serializers.IntegerField(required=False, min_value=0, default=0)
    quantite_sav = serializers.IntegerField(required=False, min_value=0, default=0)
    quantite_detruite = serializers.IntegerField(required=False, min_value=0, default=0)
    quantite_manquante = serializers.IntegerField(
        required=False, min_value=0, default=0
    )
    facturer_client = serializers.BooleanField(required=False, default=False)
    commentaire = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        """Contrôle que les quantités ne dépassent pas la quantité attendue."""

        ligne = (
            LigneReservation.objects.select_related("reservation")
            .filter(pk=attrs["ligne"])
            .first()
        )

        if ligne is None:
            raise serializers.ValidationError({
                "ligne": "Ligne de réservation introuvable."
            })

        expected = ligne.quantite_livree or ligne.quantite_demandee

        total = (
            attrs.get("quantite_ramassee", 0)
            + attrs.get("quantite_sav", 0)
            + attrs.get("quantite_detruite", 0)
            + attrs.get("quantite_manquante", 0)
        )

        if total > expected:
            raise serializers.ValidationError({
                "detail": (
                    "La somme ramassée + SAV + détruite + manquante "
                    "ne peut pas dépasser la quantité à ramasser."
                ),
                "ligne": ligne.pk,
                "quantite_attendue": expected,
                "quantite_saisie": total,
            })

        attrs["_ligne_instance"] = ligne

        return attrs


class RetourRamassageSerializer(serializers.Serializer):
    """Payload API du retour de ramassage."""

    lignes = RetourRamassageLigneSerializer(many=True, required=True)
    commentaire = serializers.CharField(required=False, allow_blank=True, default="")


class SavTicketSerializer(serializers.ModelSerializer):
    """Serializer lecture / édition d'un ticket SAV."""

    part_nom = serializers.CharField(source="part.name", read_only=True)
    reservation_numero = serializers.CharField(
        source="reservation.numero", read_only=True
    )
    created_by_username = serializers.CharField(
        source="created_by.username",
        read_only=True,
        allow_null=True,
    )
    updated_by_username = serializers.CharField(
        source="updated_by.username",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = SavTicket
        fields = [
            "id",
            "ligne_reservation",
            "reservation",
            "reservation_numero",
            "part",
            "part_nom",
            "type_ticket",
            "statut",
            "quantite",
            "facturer_client",
            "description",
            "diagnostic",
            "resolution",
            "created_by",
            "created_by_username",
            "updated_by",
            "updated_by_username",
            "closed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "ligne_reservation",
            "reservation",
            "reservation_numero",
            "part",
            "part_nom",
            "type_ticket",
            "created_by",
            "created_by_username",
            "updated_by",
            "updated_by_username",
            "closed_at",
            "created_at",
            "updated_at",
        ]

    def validate_statut(self, value):
        """Valide les statuts disponibles."""

        if value not in StatutSavTicket.values:
            raise serializers.ValidationError("Statut SAV invalide.")

        return value

    def update(self, instance, validated_data):
        """Met à jour le ticket et gère la clôture."""

        request = self.context.get("request")

        for field in ["statut", "diagnostic", "resolution", "facturer_client"]:
            if field in validated_data:
                setattr(instance, field, validated_data[field])

        if request and request.user and request.user.is_authenticated:
            instance.updated_by = request.user

        if instance.statut in [
            StatutSavTicket.REPARE,
            StatutSavTicket.DETRUIT,
            StatutSavTicket.CLOTURE,
        ]:
            if instance.closed_at is None:
                instance.closed_at = timezone.now()
        else:
            instance.closed_at = None

        instance.save()

        return instance


class SavTicketPagination(PageNumberPagination):
    """Pagination SAV."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class RamassageRetourView(APIView):
    """SCRUM-112 — Saisie du retour ramassage."""

    permission_classes = [ReservationPermission]
    serializer_class = RetourRamassageSerializer

    @transaction.atomic
    def patch(self, request, pk, *args, **kwargs):
        """Enregistre les quantités ramassées / SAV / détruites / manquantes."""

        reservation = (
            Reservation.objects.prefetch_related("lignes").filter(pk=pk).first()
        )

        if reservation is None:
            return Response(
                {"detail": "Réservation introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        updated_lines = []
        created_or_updated_tickets = []

        for line_data in serializer.validated_data["lignes"]:
            ligne = line_data["_ligne_instance"]

            if ligne.reservation_id != reservation.pk:
                return Response(
                    {
                        "detail": (
                            "Une ligne fournie ne correspond pas à la réservation."
                        ),
                        "ligne": ligne.pk,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            ligne.quantite_ramassee = line_data.get("quantite_ramassee", 0)
            ligne.quantite_sav = line_data.get("quantite_sav", 0)
            ligne.quantite_detruite = line_data.get("quantite_detruite", 0)
            ligne.quantite_manquante = line_data.get("quantite_manquante", 0)
            ligne.facturer_client = line_data.get("facturer_client", False)
            ligne.commentaire = line_data.get("commentaire", "")
            ligne.quantite_retournee = ligne.quantite_ramassee
            ligne.etat_retour = _derive_return_state(ligne)
            ligne.save()

            sav_ticket = _close_or_update_ticket(
                ligne=ligne,
                type_ticket=TypeSavTicket.REPARATION,
                quantite=ligne.quantite_sav,
                statut_si_quantite=StatutSavTicket.OUVERT,
                user=request.user,
                facturer_client=ligne.facturer_client,
                description=ligne.commentaire,
            )

            destruction_ticket = _close_or_update_ticket(
                ligne=ligne,
                type_ticket=TypeSavTicket.DESTRUCTION,
                quantite=ligne.quantite_detruite,
                statut_si_quantite=StatutSavTicket.DETRUIT,
                user=request.user,
                facturer_client=ligne.facturer_client,
                description=ligne.commentaire,
            )

            updated_lines.append({
                "id": ligne.pk,
                "part": ligne.part_id,
                "quantite_ramassee": ligne.quantite_ramassee,
                "quantite_sav": ligne.quantite_sav,
                "quantite_detruite": ligne.quantite_detruite,
                "quantite_manquante": ligne.quantite_manquante,
                "facturer_client": ligne.facturer_client,
                "etat_retour": ligne.etat_retour,
            })

            for ticket in [sav_ticket, destruction_ticket]:
                if ticket is not None:
                    created_or_updated_tickets.append(ticket.pk)

        reservation.commentaire = serializer.validated_data.get(
            "commentaire",
            reservation.commentaire,
        )

        if reservation.statut == StatutReservation.LIVREE:
            reservation.statut = StatutReservation.RETOURNEE
            reservation.date_retour_reelle = timezone.now()

        reservation.save()

        return Response(
            {
                "reservation": reservation.pk,
                "numero": reservation.numero,
                "statut": reservation.statut,
                "updated_lines": updated_lines,
                "sav_tickets": created_or_updated_tickets,
            },
            status=status.HTTP_200_OK,
        )


class SavTicketListView(generics.ListAPIView):
    """Liste des tickets SAV."""

    permission_classes = [RoleBasedPermission]
    serializer_class = SavTicketSerializer
    pagination_class = SavTicketPagination

    def get_queryset(self):
        """Filtre les tickets SAV."""

        queryset = (
            SavTicket.objects.select_related(
                "part",
                "reservation",
                "ligne_reservation",
                "created_by",
                "updated_by",
            )
            .all()
            .order_by("-created_at")
        )

        statut = self.request.query_params.get("statut")
        type_ticket = self.request.query_params.get("type_ticket")
        part = self.request.query_params.get("part")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")

        if statut:
            queryset = queryset.filter(statut=statut)

        if type_ticket:
            queryset = queryset.filter(type_ticket=type_ticket)

        if part and str(part).isdigit():
            queryset = queryset.filter(part_id=int(part))

        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)

        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        return queryset


class SavTicketDetailView(generics.RetrieveUpdateAPIView):
    """Détail / édition d'un ticket SAV."""

    permission_classes = [RoleBasedPermission]
    serializer_class = SavTicketSerializer

    def get_queryset(self):
        """Queryset tickets SAV."""

        return SavTicket.objects.select_related(
            "part",
            "reservation",
            "ligne_reservation",
            "created_by",
            "updated_by",
        ).all()

    def get_serializer_context(self):
        """Ajoute la requête au serializer."""

        context = super().get_serializer_context()
        context["request"] = self.request

        return context


class DestroyedItemsListView(generics.ListAPIView):
    """Liste des objets détruits, filtrable par période."""

    permission_classes = [RoleBasedPermission]
    serializer_class = SavTicketSerializer
    pagination_class = SavTicketPagination

    def get_queryset(self):
        """Retourne les tickets de destruction."""

        queryset = (
            SavTicket.objects.select_related(
                "part",
                "reservation",
                "ligne_reservation",
                "created_by",
                "updated_by",
            )
            .filter(
                type_ticket=TypeSavTicket.DESTRUCTION,
                statut=StatutSavTicket.DETRUIT,
            )
            .order_by("-created_at")
        )

        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")

        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)

        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        return queryset
