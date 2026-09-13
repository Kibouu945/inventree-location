"""API serializers for the InvenTreeLocation plugin."""

import json
import logging
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .conflicts import (
    detect_location_reservation_conflicts,
    detect_reservation_conflicts,
    register_location_conflict_history,
    register_stock_conflict_history,
)
from .models import (
    EtatLivraison,
    Client,
    Contact,
    LignePrestation,
    LivraisonStatusLog,
    LigneReservation,
    Lieu,
    Manifestation,
    Reservation,
    ReservationStatusLog,
    Prestation,
    RentableItem,
    ReturnIncident,
    ReturnIncidentType,
    SavTicket,
    StatutManifestation,
    StatutReservation,
    StatutPrestation,
)
from .services.workflow_service import transition_reservation_status
from .stock import compute_prestation_stock
from .ramassage import lignes_a_ramasser
from .retours import (
    appliquer_etat_retour,
    facturer_le_client,
    quantite_attendue_au_retour,
    quantites_du_retour,
)
from .sav import get_real_available_stock


logger = logging.getLogger(__name__)


# Produit français : on restreint le géocodage à la France pour éviter les
# faux positifs à l'étranger (ex. « Champ de Mars » → un pic au Québec).
GEOCODE_COUNTRY_CODES = "fr"


def _nominatim_search(address, limit):
    """Query OpenStreetMap Nominatim (restricted to France) and return the raw list."""

    query = urlencode({
        "q": address,
        "format": "json",
        "limit": limit,
        "countrycodes": GEOCODE_COUNTRY_CODES,
    })

    url = f"https://nominatim.openstreetmap.org/search?{query}"

    request = Request(
        url,
        headers={
            "User-Agent": "inventree-location-plugin/0.1",
        },
    )

    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def geocode_candidates(address, limit=5):
    """Return up to ``limit`` geocoding candidates for an address.

    Une recherche texte libre est souvent ambiguë (« Champs de Mars » matche
    plusieurs lieux en France) : on renvoie donc plusieurs candidats pour que
    l'utilisateur choisisse le bon plutôt que de deviner à sa place.
    """

    if not address:
        return []

    payload = _nominatim_search(address, limit)

    return [
        {
            "display_name": item.get("display_name"),
            "latitude": _round_coord(item.get("lat")),
            "longitude": _round_coord(item.get("lon")),
        }
        for item in payload
    ]


def geocode_address(address):
    """Return the single best GPS match for an address (auto-geocode serveur)."""

    if not address:
        return None

    payload = _nominatim_search(address, 1)

    if not payload:
        return None

    first_result = payload[0]

    return {
        "address": address,
        "display_name": first_result.get("display_name"),
        "latitude": _round_coord(first_result.get("lat")),
        "longitude": _round_coord(first_result.get("lon")),
        "source": "OpenStreetMap Nominatim",
    }


def _round_coord(value):
    """Round a coordinate to 6 decimal places (the DB column precision).

    Nominatim renvoie souvent 7+ décimales, ce qui dépasse le
    ``decimal_places=6`` du modèle ``Lieu`` et fait échouer la validation.
    """

    if value is None:
        return None

    try:
        rounded = Decimal(str(value)).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )
    except (InvalidOperation, ValueError):
        return value

    # Fixed-point (jamais de notation scientifique), sans zéros de fin.
    text = format(rounded, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")

    return text


def _user_label(user):
    """Nom lisible d'un utilisateur : « Prénom Nom (username) », sinon username."""

    if user is None:
        return ""

    full_name = f"{user.first_name} {user.last_name}".strip()

    return f"{full_name} ({user.username})" if full_name else user.username


class LigneReservationSerializer(serializers.ModelSerializer):
    """Sérialiseur d'une ligne de réservation.

    Les quantités de retour ne sont plus stockées sur la ligne — sept colonnes
    y disaient ce que le registre d'incidents dit déjà (cf. `retours.py` et la
    migration `0021`). Elles restent exposées **sous les mêmes noms**, calculées
    en une passe, pour que les écrans n'aient pas à changer.
    """

    quantite_ramassee = serializers.SerializerMethodField()
    quantite_sav = serializers.SerializerMethodField()
    quantite_detruite = serializers.SerializerMethodField()
    quantite_manquante = serializers.SerializerMethodField()
    facturer_client = serializers.SerializerMethodField()
    quantite_retour_ok = serializers.SerializerMethodField()
    quantite_retour_manquant = serializers.SerializerMethodField()
    quantite_retour_casse = serializers.SerializerMethodField()

    # Pour l'arborescence, qui affiche « Sono YAMAHA / Réf. 1516 ». Suppose la
    # Part préchargée (`prefetch_related("lignes__part")`), sinon une requête
    # par ligne.
    part_name = serializers.CharField(source="part.name", read_only=True)
    part_noi = serializers.CharField(source="part.IPN", read_only=True)

    def _quantites(self, obj):
        """Une seule reconstitution par ligne, mémorisée sur l'instance."""

        cache = getattr(obj, "_quantites_retour", None)

        if cache is None:
            cache = quantites_du_retour(obj)
            obj._quantites_retour = cache

        return cache

    def get_quantite_ramassee(self, obj):
        return self._quantites(obj)["ok"]

    def get_quantite_sav(self, obj):
        return self._quantites(obj)["casse"]

    def get_quantite_detruite(self, obj):
        return self._quantites(obj)["detruit"]

    def get_quantite_manquante(self, obj):
        return self._quantites(obj)["manquant"]

    def get_quantite_retour_ok(self, obj):
        return self._quantites(obj)["ok"]

    def get_quantite_retour_manquant(self, obj):
        return self._quantites(obj)["manquant"]

    def get_quantite_retour_casse(self, obj):
        return self._quantites(obj)["casse"]

    def get_facturer_client(self, obj):
        return facturer_le_client(obj)

    class Meta:
        """Configuration du serializer LigneReservation."""

        model = LigneReservation
        fields = [
            "id",
            "part",
            "part_name",
            "part_noi",
            "quantite_demandee",
            "quantite_livree",
            "quantite_retournee",
            "quantite_ramassee",
            "quantite_sav",
            "quantite_detruite",
            "quantite_manquante",
            "facturer_client",
            "etat_retour",
            "quantite_retour_ok",
            "quantite_retour_manquant",
            "quantite_retour_casse",
            "commentaire",
        ]
        # Le détail du retour n'appartient qu'aux écrans de retour (check-in
        # magasinier et saisie de ramassage) : il est calculé, donc en lecture
        # seule par construction, et ne peut plus être remis à zéro par une
        # réécriture des lignes de la réservation.
        read_only_fields = ["id"]


def sync_ligne_etat_retour(ligne):
    """Recalcule `etat_retour` d'une ligne (cf. `retours.py`).

    Conservée comme point d'entrée des vues d'incidents ; la règle elle-même
    vit dans `retours.appliquer_etat_retour`, partagée avec le check-in et la
    saisie de ramassage.
    """

    appliquer_etat_retour(ligne)


class ReturnIncidentSerializer(serializers.ModelSerializer):
    """Sérialiseur d'un incident de retour."""

    # Déclaré explicitement : le `ChoiceField` implicite du ModelSerializer
    # rejette la valeur avant tout `validate_type`, dont le message français
    # n'atteignait donc jamais le client.
    type = serializers.ChoiceField(
        choices=ReturnIncidentType.choices,
        error_messages={
            "invalid_choice": "Type d'incident invalide : manquant ou cassé attendu."
        },
    )
    qty = serializers.IntegerField(
        min_value=1,
        error_messages={"min_value": "La quantité signalée doit être d'au moins 1."},
    )
    line_part_name = serializers.CharField(source="line.part.name", read_only=True)
    line_reservation_numero = serializers.CharField(
        source="line.reservation.numero", read_only=True
    )
    reported_by_username = serializers.CharField(
        source="reported_by.username", read_only=True, allow_null=True
    )

    class Meta:
        """Configuration du serializer ReturnIncident."""

        model = ReturnIncident
        fields = [
            "id",
            "line",
            "line_part_name",
            "line_reservation_numero",
            "type",
            "qty",
            "comment",
            "bill_client",
            "reported_at",
            "reported_by",
            "reported_by_username",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "line_part_name",
            "line_reservation_numero",
            "reported_at",
            "reported_by",
            "reported_by_username",
            "created_at",
            "updated_at",
        ]
        # Le validateur d'unicité déduit de `incident_unique_par_ligne_et_type`
        # est écarté au profit de `_refuser_le_doublon` : il passe avant
        # `validate()` et son message anglais ne nomme pas l'enregistrement
        # fautif. La contrainte reste le filet en base.
        validators = []

    def validate(self, attrs):
        """Seul le manquant est plafonné par la quantité sortie.

        Le cassé et le détruit ne le sont pas : du matériel circule entre
        lieux, et douze objets rendus cassés pour dix sortis est un constat
        possible qu'il faut pouvoir enregistrer (R36). Le manquant, lui, ne
        peut pas dépasser ce qui est parti — on ne perd pas ce qu'on n'a pas
        livré. Règle arrêtée en recette le 11/09.
        """

        line = attrs.get("line") or getattr(self.instance, "line", None)

        if line is not None:
            type_incident = attrs.get("type") or getattr(self.instance, "type", None)
            qty = attrs.get("qty", getattr(self.instance, "qty", 0))

            if type_incident == ReturnIncidentType.MISSING:
                max_qty = quantite_attendue_au_retour(line)

                if qty > max_qty:
                    raise serializers.ValidationError({
                        "qty": (
                            f"La quantité manquante ({qty}) dépasse la "
                            f"quantité sortie ({max_qty}) : on ne peut pas "
                            "perdre plus que ce qui est parti."
                        )
                    })

            self._refuser_le_doublon(line, attrs)

        return attrs

    def _refuser_le_doublon(self, line, attrs):
        """Un seul incident par ligne et par nature.

        Le registre porte un total par nature : le geste correct est d'ajuster
        l'enregistrement existant, pas d'en créer un second. Le message le
        nomme, là où le validateur automatique de DRF sort un
        « must make a unique set » en anglais qui ne dit pas lequel.
        """

        type_incident = attrs.get("type") or getattr(self.instance, "type", None)
        autres = line.incidents.filter(type=type_incident)

        if self.instance is not None:
            autres = autres.exclude(pk=self.instance.pk)

        existant = autres.first()

        if existant is None:
            return

        raise serializers.ValidationError({
            "type": (
                f"Un incident « {existant.get_type_display()} » existe déjà sur "
                f"cette ligne (#{existant.pk}, {existant.qty} unité(s)) : "
                "modifiez-le au lieu d'en créer un second."
            )
        })

    def create(self, validated_data):
        """Crée l'incident et met à jour l'état de retour de la ligne."""

        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            validated_data["reported_by"] = request.user

        incident = super().create(validated_data)
        self._reporter_sur_la_ligne(incident)

        return incident

    def update(self, instance, validated_data):
        """Met à jour l'incident, puis réaligne l'état de retour de la ligne."""

        incident = super().update(instance, validated_data)
        self._reporter_sur_la_ligne(incident)

        return incident

    @staticmethod
    def _reporter_sur_la_ligne(incident):
        """Réaligne la ligne : état recalculé, commentaire jamais effacé."""

        ligne = incident.line

        # Le commentaire de la ligne appartient au magasinier : il n'est repris
        # que si l'incident en fournit un, jamais remis à blanc.
        if incident.comment:
            ligne.commentaire = incident.comment
            ligne.save(update_fields=["commentaire", "updated_at"])

        sync_ligne_etat_retour(ligne)


class ReturnIncidentHistorySerializer(ReturnIncidentSerializer):
    """Incident enrichi du contexte réservation / manifestation (SCRUM-100).

    Ces champs vivaient sur le sérialiseur partagé, ce qui coûtait cher :
    `event_name` traverse `line.reservation.prestation.manifestation`, et seule
    la vue historique avait le `select_related` correspondant. La liste et le
    détail des incidents payaient deux requêtes de plus par incident pour des
    champs qu'ils n'exposent pas.
    """

    part_name = serializers.CharField(source="line.part.name", read_only=True)
    reservation_id = serializers.IntegerField(
        source="line.reservation_id", read_only=True
    )
    reservation_number = serializers.CharField(
        source="line.reservation.numero", read_only=True
    )
    event_name = serializers.CharField(
        source="line.reservation.prestation.manifestation.nom", read_only=True
    )

    class Meta(ReturnIncidentSerializer.Meta):
        """Ajoute le contexte d'affichage aux champs de base."""

        fields = ReturnIncidentSerializer.Meta.fields + [
            "part_name",
            "reservation_id",
            "reservation_number",
            "event_name",
        ]
        read_only_fields = ReturnIncidentSerializer.Meta.read_only_fields + [
            "part_name",
            "reservation_id",
            "reservation_number",
            "event_name",
        ]


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


class CheckinLigneSerializer(serializers.Serializer):
    """Une ligne de check-in retour (SCRUM-94) : OK / manquant / cassé + commentaire.

    La validation de la somme (== quantité demandée) se fait au niveau de la
    vue, une fois la ligne de réservation résolue par `id`.

    `commentaire` n'a volontairement pas de valeur par défaut : absent du
    payload, il reste absent de `validated_data`, et la vue laisse alors
    intact le commentaire déjà saisi sur la ligne de réservation.
    """

    id = serializers.IntegerField(required=True)
    ok = serializers.IntegerField(required=True, min_value=0)
    manquant = serializers.IntegerField(required=True, min_value=0)
    casse = serializers.IntegerField(required=True, min_value=0)
    commentaire = serializers.CharField(required=False, allow_blank=True)


class ReservationCheckinSerializer(serializers.Serializer):
    """Payload du check-in retour d'une réservation (POST checkin)."""

    lignes = CheckinLigneSerializer(many=True, required=True)


class RetourLigneSerializer(serializers.Serializer):
    """Une ligne du bon de réservation avec sa quantité rendue (SCRUM-95)."""

    id = serializers.IntegerField(required=True)
    quantite_rendue = serializers.IntegerField(required=True, min_value=0)


class PrestationRetourSerializer(serializers.Serializer):
    """Payload de déclaration du retour d'une prestation (POST retour)."""

    lignes = RetourLigneSerializer(many=True, required=True)


class ReservationSerializer(serializers.ModelSerializer):
    """Sérialiseur DRF pour le modèle Reservation, avec lignes imbriquées."""

    lignes = LigneReservationSerializer(many=True, required=False)
    status_logs = ReservationStatusLogSerializer(many=True, read_only=True)
    prestation_nom = serializers.CharField(source="prestation.nom", read_only=True)
    demandeur_nom = serializers.SerializerMethodField()
    validateur_nom = serializers.SerializerMethodField()

    class Meta:
        """Configuration du serializer Reservation."""

        model = Reservation
        fields = [
            "id",
            "numero",
            "prestation",
            "prestation_nom",
            "demandeur",
            "demandeur_nom",
            "validateur",
            "validateur_nom",
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
        read_only_fields = ["id", "numero", "created_at", "updated_at", "status_logs"]

    @staticmethod
    def _user_label(user):
        """Nom lisible d'un utilisateur : « Prénom Nom (username) », sinon username."""

        return _user_label(user)

    def get_demandeur_nom(self, obj):
        """Nom lisible du demandeur."""

        return self._user_label(obj.demandeur)

    def get_validateur_nom(self, obj):
        """Nom lisible du validateur."""

        return self._user_label(obj.validateur)

    def validate(self, attrs):
        """Règles métier : permissives en brouillon, strictes au-delà.

        Une réservation en statut `brouillon` peut être sauvegardée
        incomplète. Dès qu'elle est soumise (ou plus), le demandeur, la
        prestation, la période, au moins une ligne et au moins un article
        virtuel (ex: prestation de nettoyage) deviennent obligatoires, la
        période doit couvrir au minimum les dates de la prestation, et les
        objets référencés doivent être actifs et louables.
        """

        statut = attrs.get(
            "statut", getattr(self.instance, "statut", StatutReservation.BROUILLON)
        )

        if statut == StatutReservation.BROUILLON:
            return attrs

        def effective(field):
            if field in attrs:
                return attrs[field]
            return getattr(self.instance, field, None) if self.instance else None

        prestation = effective("prestation")
        date_retrait = effective("date_retrait_prevue")
        date_retour = effective("date_retour_prevue")

        errors = {}

        if not date_retrait:
            errors["date_retrait_prevue"] = (
                "La date de retrait est obligatoire pour soumettre la réservation."
            )

        if not date_retour:
            errors["date_retour_prevue"] = (
                "La date de retour est obligatoire pour soumettre la réservation."
            )

        if date_retrait and date_retour:
            if date_retrait > date_retour:
                errors["date_retour_prevue"] = (
                    "La date de retour doit être postérieure ou égale à la date de retrait."
                )
            elif prestation:
                if date_retrait > prestation.date_debut:
                    errors["date_retrait_prevue"] = (
                        "La période doit couvrir au moins les dates de la prestation."
                    )

                if date_retour < prestation.date_fin:
                    errors["date_retour_prevue"] = (
                        "La période doit couvrir au moins les dates de la prestation."
                    )

        lignes = attrs.get("lignes")

        if lignes is None and self.instance is not None:
            lignes = list(self.instance.lignes.all())

        lignes = lignes or []

        if not lignes:
            errors["lignes"] = (
                "Au moins une ligne de matériel est obligatoire pour soumettre la réservation."
            )
        else:
            part_ids = [
                ligne.part_id if hasattr(ligne, "part_id") else ligne["part"].pk
                for ligne in lignes
            ]

            # Les trois règles portent sur la même clé : on les cumule au lieu
            # de les écraser, sinon un objet inactif remontait « il manque un
            # article virtuel » — un message qui ne désigne pas le problème.
            lignes_errors = []

            if self._has_inactive_part(part_ids):
                lignes_errors.append(
                    "Un objet non actif ne peut pas être ajouté à une réservation."
                )

            if RentableItem.objects.filter(
                part_id__in=part_ids,
                is_rentable=False,
            ).exists():
                lignes_errors.append(
                    "Un objet non louable ne peut pas être ajouté à une réservation."
                )

            if not RentableItem.objects.filter(
                part_id__in=part_ids,
                is_virtual=True,
            ).exists():
                lignes_errors.append(
                    "Au moins un article virtuel (ex: prestation de nettoyage) "
                    "est obligatoire pour soumettre la réservation."
                )

            if lignes_errors:
                errors["lignes"] = lignes_errors

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    @staticmethod
    def _has_inactive_part(part_ids) -> bool:
        """Vrai si au moins une des Parts est désactivée côté InvenTree.

        Le contrôle porte sur `Part.active` et non sur `RentableItem` : une
        Part sans extension louable l'est par défaut, mais elle peut très bien
        être désactivée — passer par `RentableItem` laissait filtrer ces Parts.
        """

        from part.models import Part

        return Part.objects.filter(pk__in=part_ids, active=False).exists()

    @transaction.atomic
    def create(self, validated_data):
        """Crée une réservation, ses lignes, et refuse la validation en conflit."""

        lignes_data = validated_data.pop("lignes", None)
        reservation = super().create(validated_data)

        if lignes_data:
            self._replace_lignes(reservation, lignes_data)

        self._register_conflict_history(reservation)
        self._validate_stock_conflicts_if_needed(reservation)

        return reservation

    @transaction.atomic
    def update(self, instance, validated_data):
        """Met à jour une réservation et refuse la validation en conflit."""

        lignes_data = validated_data.pop("lignes", None)
        reservation = super().update(instance, validated_data)

        if lignes_data is not None:
            self._replace_lignes(reservation, lignes_data)

        self._register_conflict_history(reservation)
        self._validate_stock_conflicts_if_needed(reservation)

        return reservation

    def _replace_lignes(self, reservation, lignes_data):
        """Remplace l'intégralité des lignes de la réservation.

        La suppression **cascade** sur le registre d'incidents et sur les
        tickets SAV, y compris les tickets ouverts que le stock réel lit
        encore. La vue refuse déjà l'édition au-delà de « soumise », mais
        l'endpoint des incidents accepte n'importe quelle ligne quel que soit
        le statut du bon : un brouillon peut donc porter un constat, et le
        perdait sans un mot. D'où le refus explicite.
        """

        self._refuser_si_le_retour_est_constate(reservation)

        reservation.lignes.all().delete()

        LigneReservation.objects.bulk_create([
            LigneReservation(reservation=reservation, **ligne_data)
            for ligne_data in lignes_data
        ])

    @staticmethod
    def _refuser_si_le_retour_est_constate(reservation):
        """Refuse le remplacement des lignes quand un retour a été constaté."""

        incidents = ReturnIncident.objects.filter(line__reservation=reservation).count()
        tickets = SavTicket.objects.filter(
            ligne_reservation__reservation=reservation
        ).count()

        if not incidents and not tickets:
            return

        constats = []

        if incidents:
            constats.append(f"{incidents} incident(s) de retour")

        if tickets:
            constats.append(f"{tickets} ticket(s) SAV")

        raise serializers.ValidationError({
            "lignes": (
                f"Ce bon porte {' et '.join(constats)} : remplacer ses lignes "
                "les supprimerait. Modifiez la quantité de la ligne concernée, "
                "ou traitez le retour avant de rouvrir le bon."
            )
        })

    def _register_conflict_history(self, reservation):
        """Journalise les conflits détectés, qu'ils bloquent ou non (SCRUM-110).

        L'historique et le blocage sont deux choses distinctes : une demande
        peut être enregistrée en conflit et arbitrée plus tard, mais le conflit
        doit rester tracé. Les fonctions d'enregistrement existaient sans
        qu'aucun appel ne les atteigne : l'historique restait vide.
        """

        if not reservation.date_retrait_prevue or not reservation.date_retour_prevue:
            return

        register_stock_conflict_history(
            reservation, detect_reservation_conflicts(reservation)
        )
        register_location_conflict_history(
            reservation, detect_location_reservation_conflicts(reservation)
        )

    def _validate_stock_conflicts_if_needed(self, reservation):
        """Refuse la validation d'une réservation en conflit de stock non forcé."""

        if reservation.statut != StatutReservation.VALIDEE or reservation.forced:
            return

        conflict_result = detect_reservation_conflicts(reservation)

        if conflict_result["has_conflict"]:
            raise serializers.ValidationError({
                "detail": (
                    "Validation refusée : conflit de stock détecté. "
                    "Résolvez le conflit ou passez forced=true."
                ),
                "conflicts": conflict_result["conflicts"],
            })


class RamassageSerializer(serializers.ModelSerializer):
    prestation_nom = serializers.CharField(source="prestation.nom", read_only=True)
    manifestation_nom = serializers.CharField(
        source="prestation.manifestation.nom",
        read_only=True,
    )
    client_nom = serializers.CharField(
        source="prestation.manifestation.client.nom",
        read_only=True,
        default="",
    )
    demandeur_nom = serializers.SerializerMethodField()
    date_ramassage = serializers.DateTimeField(
        source="date_retour_prevue",
        read_only=True,
    )
    lieu = serializers.SerializerMethodField()
    nb_objets = serializers.SerializerMethodField()
    quantite_totale = serializers.SerializerMethodField()
    recap_par_vehicule = serializers.SerializerMethodField()
    lignes = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = [
            "id",
            "numero",
            "prestation",
            "prestation_nom",
            "manifestation_nom",
            "client_nom",
            "demandeur",
            "demandeur_nom",
            "statut",
            "date_ramassage",
            "date_retrait_prevue",
            "date_retour_prevue",
            "lieu",
            "nb_objets",
            "quantite_totale",
            "recap_par_vehicule",
            "lignes",
        ]

    def get_demandeur_nom(self, obj):
        return ReservationSerializer._user_label(obj.demandeur)

    def get_lieu(self, obj):
        lieu = obj.prestation.lieu
        if lieu is None:
            return None

        return {
            "id": lieu.id,
            "nom": lieu.nom,
            "adresse": lieu.adresse,
            "latitude": str(lieu.latitude) if lieu.latitude is not None else None,
            "longitude": str(lieu.longitude) if lieu.longitude is not None else None,
        }

    def get_nb_objets(self, obj):
        return len(lignes_a_ramasser(obj))

    def get_quantite_totale(self, obj):
        total = 0
        for ligne in lignes_a_ramasser(obj):
            total += quantite_attendue_au_retour(ligne)
        return total

    def get_recap_par_vehicule(self, obj):
        return [
            {
                "vehicule": "Non attribué",
                "quantite_totale": self.get_quantite_totale(obj),
            }
        ]

    def get_lignes(self, obj):
        lignes = []
        for ligne in lignes_a_ramasser(obj):
            quantites = quantites_du_retour(ligne)
            lignes.append({
                "id": ligne.id,
                "part": ligne.part_id,
                "part_nom": ligne.part.name,
                "quantite_demandee": ligne.quantite_demandee,
                "quantite_livree": ligne.quantite_livree,
                "quantite_a_ramasser": quantite_attendue_au_retour(ligne),
                "quantite_retournee": quantites["revenue"],
                "quantite_ramassee": quantites["ok"],
                "quantite_sav": quantites["casse"],
                "quantite_detruite": quantites["detruit"],
                "quantite_manquante": quantites["manquant"],
                "facturer_client": facturer_le_client(ligne),
                "etat_retour": ligne.etat_retour,
                "commentaire": ligne.commentaire,
            })
        return lignes


class BonRamassageSerializer(RamassageSerializer):
    """Sérialiseur détaillé pour le bon de ramassage imprimable."""

    lignes = serializers.SerializerMethodField()

    class Meta(RamassageSerializer.Meta):
        """Configuration du serializer BonRamassage."""

        fields = RamassageSerializer.Meta.fields + [
            "lignes",
            "commentaire",
        ]

    def get_lignes(self, obj):
        """Détail des articles à ramasser."""

        lignes = []

        # Pas de `select_related` ici : la vue a déjà préchargé `lignes__part`,
        # et le rajouter annulerait ce prefetch au profit d'une requête neuve.
        for ligne in lignes_a_ramasser(obj):
            quantites = quantites_du_retour(ligne)

            lignes.append({
                "id": ligne.id,
                "part": ligne.part_id,
                "part_nom": ligne.part.name,
                "quantite_demandee": ligne.quantite_demandee,
                "quantite_livree": ligne.quantite_livree,
                "quantite_a_ramasser": quantite_attendue_au_retour(ligne),
                "quantite_retournee": quantites["revenue"],
                "quantite_ramassee": quantites["ok"],
                "quantite_sav": quantites["casse"],
                "quantite_detruite": quantites["detruit"],
                "quantite_manquante": quantites["manquant"],
                "facturer_client": facturer_le_client(ligne),
                "etat_retour": ligne.etat_retour,
                "commentaire": ligne.commentaire,
            })

        return lignes


class RentableItemSerializer(serializers.ModelSerializer):
    """Drapeaux location d'un Part.

    Le stock physique n'y figure pas : il appartient à InvenTree et se met à
    jour par les `StockItem`, pas par ce formulaire. `stock_total` reste
    exposé en lecture par `CatalogPartSerializer`, calculé depuis InvenTree.
    """

    class Meta:
        """Configuration du serializer RentableItem."""

        model = RentableItem
        fields = [
            "part",
            "is_rentable",
            "consommable",
            "is_virtual",
            "caution",
            "valeur_remplacement",
            "poids",
            "seuil_alerte_bas",
            "seuil_alerte_haut",
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
        help_text="Total number of Parts in the InvenTree database.",
    )

    today = serializers.DateField(
        required=False,
        label="Today",
        help_text="The current date.",
    )


class RoundedDecimalField(serializers.DecimalField):
    """DecimalField qui arrondit l'entrée au lieu de rejeter l'excès de décimales.

    Les coordonnées GPS collées depuis une carte comportent souvent plus de
    décimales que le ``decimal_places`` autorisé ; on quantifie plutôt que
    de renvoyer une 400.
    """

    def validate_precision(self, value):
        """Round to the allowed decimal places before precision validation."""

        if self.decimal_places is not None:
            value = value.quantize(
                Decimal(1).scaleb(-self.decimal_places),
                rounding=ROUND_HALF_UP,
            )

        return super().validate_precision(value)


class LieuSerializer(serializers.ModelSerializer):
    """Serializer for location places with GPS coordinates."""

    latitude = RoundedDecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
    )

    longitude = RoundedDecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
    )

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
            "nom",
            "description",
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


class DeliveryLigneSerializer(serializers.ModelSerializer):
    part_name = serializers.CharField(source="part.name", read_only=True)
    is_virtual = serializers.SerializerMethodField()

    class Meta:
        model = LigneReservation
        fields = [
            "id",
            "part",
            "part_name",
            "quantite_demandee",
            "quantite_livree",
            "quantite_retournee",
            "is_virtual",
        ]
        read_only_fields = fields

    def get_is_virtual(self, obj) -> bool:
        rentable = getattr(obj.part, "rentable_info", None)
        return bool(rentable and rentable.is_virtual)


class LivraisonStatusLogSerializer(serializers.ModelSerializer):
    """Une ligne du journal d'état d'une livraison (US-19)."""

    to_etat_display = serializers.SerializerMethodField()
    changed_by_nom = serializers.SerializerMethodField()

    class Meta:
        """Configuration du serializer de journal de livraison."""

        model = LivraisonStatusLog
        fields = [
            "id",
            "from_etat",
            "to_etat",
            "to_etat_display",
            "changed_by_nom",
            "commentaire",
            "photo",
            "created_at",
        ]
        read_only_fields = fields

    def get_to_etat_display(self, obj):
        """Libellé lisible du nouvel état ; vide = remise dans le pool."""

        if not obj.to_etat:
            return "Non assignée"

        return EtatLivraison(obj.to_etat).label

    def get_changed_by_nom(self, obj):
        """Nom lisible de l'auteur du changement."""

        return _user_label(obj.changed_by)


class DeliverySerializer(serializers.ModelSerializer):
    prestation_nom = serializers.CharField(source="prestation.nom", read_only=True)
    manifestation_nom = serializers.CharField(
        source="prestation.manifestation.nom", read_only=True, default=""
    )
    client_nom = serializers.CharField(
        source="prestation.manifestation.client.nom", read_only=True, default=""
    )
    demandeur_nom = serializers.SerializerMethodField()
    lieu_detail = LieuSerializer(source="prestation.lieu", read_only=True)
    organisateur_nom = serializers.SerializerMethodField()
    organisateur_telephone = serializers.SerializerMethodField()
    lignes = DeliveryLigneSerializer(many=True, read_only=True)
    quantite_totale = serializers.SerializerMethodField()
    livreur_assigne_nom = serializers.SerializerMethodField()
    etat_livraison_display = serializers.SerializerMethodField()
    livraison_status_logs = LivraisonStatusLogSerializer(many=True, read_only=True)

    class Meta:
        model = Reservation
        fields = [
            "id",
            "numero",
            "statut",
            "prestation_nom",
            "manifestation_nom",
            "client_nom",
            "demandeur_nom",
            "lieu_detail",
            "organisateur_nom",
            "organisateur_telephone",
            "date_retrait_prevue",
            "date_retour_prevue",
            "commentaire",
            "lignes",
            "quantite_totale",
            "livreur_assigne",
            "livreur_assigne_nom",
            "date_assignation",
            "etat_livraison",
            "etat_livraison_display",
            "livraison_status_logs",
        ]
        read_only_fields = fields

    def get_demandeur_nom(self, obj):
        """Nom lisible du demandeur (gérant interne)."""

        return _user_label(obj.demandeur)

    def get_livreur_assigne_nom(self, obj):
        """Nom lisible du livreur qui a pris la livraison, vide sinon."""

        return _user_label(obj.livreur_assigne) if obj.livreur_assigne_id else ""

    def get_etat_livraison_display(self, obj):
        """Libellé de l'état ; vide tant que personne n'a pris la livraison."""

        if not obj.etat_livraison:
            return ""

        return EtatLivraison(obj.etat_livraison).label

    def get_organisateur_nom(self, obj):
        """Nom de l'interlocuteur à joindre sur place.

        Les clés `organisateur_*` sont conservées : quatre écrans de livraison
        les consomment. Seule la source change — le contact référent de la
        manifestation, à défaut le client lui-même.
        """

        return _libelle_interlocuteur(obj.prestation.manifestation)

    def get_organisateur_telephone(self, obj):
        """Téléphone de l'interlocuteur, vide si non renseigné."""

        manifestation = obj.prestation.manifestation
        contact = manifestation.contact

        if contact is not None and contact.telephone:
            return contact.telephone

        return manifestation.client.telephone

    def get_quantite_totale(self, obj):
        """Somme des quantités demandées sur les seules lignes physiques.

        Un article virtuel — nettoyage, montage — ne se charge pas dans le
        camion : le compter donnait au livreur un total supérieur au nombre
        d'objets à embarquer, et différent de celui du bon de ramassage.
        """

        return sum(ligne.quantite_demandee for ligne in lignes_a_ramasser(obj))


class CatalogPartSerializer(serializers.Serializer):
    """Serializer used to expose InvenTree Parts in the rental catalog."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True, allow_blank=True)
    IPN = serializers.CharField(read_only=True, allow_blank=True, allow_null=True)
    active = serializers.BooleanField(read_only=True)
    category = serializers.IntegerField(source="category_id", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    stock_available = serializers.SerializerMethodField()
    stock_reel_disponible = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    rentable = serializers.SerializerMethodField()
    consommable = serializers.SerializerMethodField()
    is_virtual = serializers.SerializerMethodField()
    stock_total = serializers.SerializerMethodField()
    poids = serializers.SerializerMethodField()
    seuil_alerte_bas = serializers.SerializerMethodField()
    seuil_alerte_haut = serializers.SerializerMethodField()

    def _rentable_info(self, obj):
        """Récupère l'extension RentableItem attachée par la vue catalogue."""

        attached = getattr(obj, "_location_rentable_info", None)

        if attached is not None:
            return attached

        try:
            return getattr(obj, "rentable_info", None)
        except Exception:
            return None

    def get_stock_available(self, obj):
        """Disponibilité **sur la période demandée**, annotée par la vue.

        À ne pas confondre avec `stock_reel_disponible` (SCRUM-112) : ici on
        répond « combien puis-je réserver du 12 au 14 mars », là-bas « combien
        reste-t-il en état de servir, hors SAV et casse ». Les deux chiffres
        diffèrent légitimement et portaient le même nom.
        """

        for attr in ["stock_available", "available_stock"]:
            value = getattr(obj, attr, None)

            if value is not None:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return 0

        return 0

    def get_stock_reel_disponible(self, obj):
        """Stock en état de servir : total InvenTree moins SAV et détruits."""

        return get_real_available_stock(obj.id)

    def get_image_url(self, obj):
        """URL de l'image principale si le modèle en expose une.

        `Part.image` est un champ fichier : son `str()` donne le **nom**
        (« part_images/tente.png »), pas une URL. Le front le posait tel quel
        dans un `<img src>`, résolu relativement à `/web/…`, donc en 404 : la
        photo d'un objet n'était jamais visible. On passe par `.url`, qui
        préfixe avec MEDIA_URL, et on ne retombe sur `str()` que pour les
        attributs déjà textuels (`thumbnail` d'InvenTree, par exemple).
        """

        for attr in ["image", "image_url", "thumbnail", "thumbnail_url"]:
            value = getattr(obj, attr, None)

            if not value:
                continue

            url = getattr(value, "url", None)

            return str(url) if url else str(value)

        return None

    def get_rentable(self, obj):
        """Drapeau louable issu de RentableItem.

        Une Part désactivée côté InvenTree n'est jamais louable, quels que
        soient ses drapeaux plugin (SCRUM-111 : « Désactiver » dans le
        back-office doit sortir l'objet du catalogue louable).
        """

        if not bool(getattr(obj, "active", True)):
            return False

        if not bool(getattr(obj, "active", True)):
            return False

        rentable_info = self._rentable_info(obj)

        if rentable_info is None:
            return True

        return bool(rentable_info.is_rentable)

    def get_consommable(self, obj):
        """Drapeau consommable issu de RentableItem."""

        rentable_info = self._rentable_info(obj)

        if rentable_info is None:
            return False

        return bool(rentable_info.consommable)

    def get_is_virtual(self, obj):
        """Drapeau article virtuel issu de RentableItem (False par défaut)."""

        rentable_info = getattr(obj, "rentable_info", None)

        if rentable_info is None:
            return False

        return bool(rentable_info.is_virtual)

    def get_stock_total(self, obj):
        """Stock physique louable, tel qu'InvenTree le connaît."""

        from .conflicts import get_part_total_stock

        return get_part_total_stock(obj)

    def get_poids(self, obj):
        """Poids unitaire, ou `None` s'il n'est pas renseigné."""

        rentable_info = getattr(obj, "rentable_info", None)

        return None if rentable_info is None else rentable_info.poids

    def get_seuil_alerte_bas(self, obj):
        """Seuil bas configurable du part (null par défaut)."""

        rentable_info = getattr(obj, "rentable_info", None)

        if rentable_info is None:
            return None

        return rentable_info.seuil_alerte_bas

    def get_seuil_alerte_haut(self, obj):
        """Seuil haut configurable du part (null par défaut)."""

        rentable_info = getattr(obj, "rentable_info", None)

        if rentable_info is None:
            return None

        return rentable_info.seuil_alerte_haut


#: Un bon annulé ou refusé n'engage plus rien : ni volume, ni livraison.
STATUTS_SANS_ENGAGEMENT = (
    StatutReservation.ANNULEE,
    StatutReservation.REFUSEE,
    StatutReservation.BROUILLON,
)

#: Bons dont le matériel est physiquement sorti.
STATUTS_DEJA_SORTIS = (
    StatutReservation.LIVREE,
    StatutReservation.RETOURNEE,
    StatutReservation.CLOTUREE,
)


def _volume_des_bons(reservations):
    """Volume engagé d'un lot de bons, annulés exclus.

    Repli du sérialiseur quand la vue n'a pas annoté : il sert au détail d'une
    prestation ou d'une manifestation, jamais à une liste, où il ferait une
    requête par ligne.
    """

    return sum(
        ligne.quantite_demandee
        for bon in reservations
        if bon.statut not in STATUTS_SANS_ENGAGEMENT
        for ligne in bon.lignes.all()
    )


def _etat_des_bons(reservations):
    """Avancement des livraisons d'un lot de bons : sortis sur engagés.

    Trois nombres plutôt qu'un pourcentage : le planning affiche « 2/5 », et un
    pourcentage se recalcule côté écran si besoin, l'inverse non.
    """

    engages = [bon for bon in reservations if bon.statut not in STATUTS_SANS_ENGAGEMENT]
    livres = sum(1 for bon in engages if bon.statut in STATUTS_DEJA_SORTIS)

    return {
        "bons": len(engages),
        "livres": livres,
        "a_livrer": max(len(engages) - livres, 0),
    }


def _bons_de_la_manifestation(manifestation):
    """Tous les bons d'une manifestation, quel que soit leur statut."""

    return [
        bon
        for prestation in manifestation.prestations.all()
        for bon in prestation.reservations.all()
    ]


def _etat_annote(obj):
    """Avancement lu depuis les annotations de la vue, ou `None` si absentes."""

    total = getattr(obj, "bons_engages", None)
    livres = getattr(obj, "bons_livres", None)

    if total is None or livres is None:
        return None

    return {"bons": total, "livres": livres, "a_livrer": max(total - livres, 0)}


def _libelle_interlocuteur(manifestation):
    """Contact référent d'une manifestation, à défaut le nom du client."""

    contact = manifestation.contact

    if contact is None:
        return manifestation.client.nom

    complet = f"{contact.prenom} {contact.nom}".strip()

    return complet or manifestation.client.nom


class ClientSerializer(serializers.ModelSerializer):
    """Client en lecture, pour le sélecteur de manifestation et « mes clients »."""

    gestionnaire_nom = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            "id",
            "nom",
            "adresse",
            "email",
            "telephone",
            "type_client",
            "siret",
            "gestionnaire",
            "gestionnaire_nom",
            "actif",
        ]
        # DRF interdit de reprendre un champ déclaré dans `read_only_fields`.
        read_only_fields = [nom for nom in fields if nom != "gestionnaire_nom"]

    def get_gestionnaire_nom(self, obj) -> str:
        return _user_label(obj.gestionnaire)


class ContactSerializer(serializers.ModelSerializer):
    """Contact d'un client, en lecture."""

    nom_complet = serializers.SerializerMethodField()

    class Meta:
        model = Contact
        fields = [
            "id",
            "client",
            "nom",
            "prenom",
            "nom_complet",
            "email",
            "telephone",
            "actif",
        ]
        read_only_fields = fields

    def get_nom_complet(self, obj):
        return f"{obj.prenom} {obj.nom}".strip()


class UserSerializer(serializers.ModelSerializer):
    """Sérialiseur léger d'un utilisateur InvenTree."""

    class Meta:
        """Configuration du serializer User."""

        model = get_user_model()
        fields = ["id", "username", "first_name", "last_name", "email"]
        read_only_fields = fields


class LignePrestationSerializer(serializers.ModelSerializer):
    """Article + quantité rattaché à une prestation (RES-09)."""

    part_name = serializers.CharField(source="part.name", read_only=True)

    class Meta:
        """Configuration du serializer LignePrestation."""

        model = LignePrestation
        fields = [
            "id",
            "part",
            "part_name",
            "quantite",
            "commentaire",
        ]
        read_only_fields = ["id", "part_name"]


class PrestationSerializer(serializers.ModelSerializer):
    """CRUD d'une prestation : manifestation, lieu unique et liste d'articles.

    Une prestation se déroule sur un seul lieu (ORG-02) et porte sa propre liste
    de matériel + quantités (RES-09). Les lignes sont imbriquées et remplacées
    intégralement à chaque écriture, comme pour les réservations.
    """

    manifestation_nom = serializers.CharField(
        source="manifestation.nom",
        read_only=True,
    )
    lieu_detail = LieuSerializer(source="lieu", read_only=True)
    lignes = LignePrestationSerializer(
        source="lignes_prestation", many=True, required=False
    )
    quantite_totale = serializers.SerializerMethodField()
    etat_livraison = serializers.SerializerMethodField()

    class Meta:
        """Configuration du serializer Prestation."""

        model = Prestation
        fields = [
            "id",
            "nom",
            "date_debut",
            "date_fin",
            "description",
            "statut",
            "modifie_apres_devis",
            "manifestation",
            "manifestation_nom",
            "lieu",
            "lieu_detail",
            "lignes",
            "quantite_totale",
            "etat_livraison",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "manifestation_nom",
            "lieu_detail",
            "quantite_totale",
            "etat_livraison",
            "created_at",
            "updated_at",
        ]

    def get_quantite_totale(self, obj):
        """Volume d'objets engagés sur cette prestation, annulés exclus.

        Même mesure que `ManifestationSerializer.quantite_totale`, un cran plus
        bas : les prestations d'une manifestation totalisent donc exactement sa
        barre de planning. Prendre ici les lignes de prestation — le
        prévisionnel — donnerait un autre nombre, et deux mailles qui ne
        s'additionnent pas.
        """

        annotee = getattr(obj, "volume_engage", None)

        if annotee is not None:
            return annotee

        return _volume_des_bons(obj.reservations.all())

    def get_etat_livraison(self, obj):
        """Avancement des livraisons de la prestation : sortis sur engagés."""

        return _etat_annote(obj) or _etat_des_bons(obj.reservations.all())

    def validate(self, attrs):
        """Dates de prestation incluses dans celles de la manifestation."""

        def effective(field):
            if field in attrs:
                return attrs[field]
            return getattr(self.instance, field, None) if self.instance else None

        date_debut = effective("date_debut")
        date_fin = effective("date_fin")
        manifestation = effective("manifestation")

        errors = {}

        # Nouvelle prestation seulement sur une manif pas encore démarrée.
        if (
            self.instance is None
            and manifestation
            and not manifestation.accepte_nouvelles_prestations
        ):
            errors["manifestation"] = (
                "Impossible d'ajouter une prestation : la manifestation est "
                f"« {manifestation.get_statut_display().lower()} » "
                f"(statut effectif : {manifestation.statut_effectif})."
            )

        if date_debut and date_fin and date_debut > date_fin:
            errors["date_fin"] = (
                "La date de fin doit être postérieure ou égale à la date de début."
            )

        # Bornage au jour, dans le fuseau courant (localdate sur les deux dates
        # sinon le jour décale à minuit entre l'entrée DRF et l'UTC en base).
        if (
            manifestation
            and date_debut
            and timezone.localdate(date_debut)
            < timezone.localdate(manifestation.date_debut)
        ):
            errors["date_debut"] = (
                "La prestation doit se dérouler pendant la manifestation "
                f"(à partir du {timezone.localdate(manifestation.date_debut):%d/%m/%Y})."
            )

        if (
            manifestation
            and date_fin
            and timezone.localdate(date_fin)
            > timezone.localdate(manifestation.date_fin)
        ):
            errors["date_fin"] = (
                "La prestation doit se dérouler pendant la manifestation "
                f"(jusqu'au {timezone.localdate(manifestation.date_fin):%d/%m/%Y})."
            )

        # Le lieu reste nullable en base pour autoriser les brouillons, mais une
        # prestation sans lieu est invisible des tournées : on ne la laisse pas
        # quitter le brouillon. Avant, un POST sans lieu passait en silence.
        statut = effective("statut")

        if statut and statut != StatutPrestation.BROUILLON and not effective("lieu"):
            errors["lieu"] = (
                "Le lieu est obligatoire dès que la prestation quitte le brouillon."
            )

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """Crée une prestation et ses lignes, puis signale une pénurie (STK-01)."""

        lignes_data = validated_data.pop("lignes_prestation", None)
        prestation = super().create(validated_data)

        if lignes_data:
            self._replace_lignes(prestation, lignes_data)

        self._signaler_penurie(prestation)

        return prestation

    @transaction.atomic
    def update(self, instance, validated_data):
        """Met à jour une prestation et ses lignes, puis signale une pénurie."""

        lignes_data = validated_data.pop("lignes_prestation", None)
        prestation = super().update(instance, validated_data)

        if lignes_data is not None:
            self._replace_lignes(prestation, lignes_data)

        self._signaler_penurie(prestation)

        return prestation

    def _replace_lignes(self, prestation, lignes_data):
        """Remplace l'intégralité des lignes d'articles de la prestation."""

        prestation.lignes_prestation.all().delete()

        LignePrestation.objects.bulk_create([
            LignePrestation(prestation=prestation, **ligne_data)
            for ligne_data in lignes_data
        ])

    def _signaler_penurie(self, prestation):
        """Journalise une pénurie de stock sans refuser l'enregistrement.

        Ce contrôle levait une `ValidationError` dans la transaction de
        `create` / `update`, ce qui annulait la sauvegarde. En recette
        (07/09/2026, remarque 6), le client s'est retrouvé dans une impasse :
        « un article dépasse le stock disponible, le système bloque alors la
        réservation et seul annuler est possible. Il ne faut pas bloquer mais
        alerter. (Voir les Epic E & F) ». Sa prestation était perdue, donc
        aucune réservation, donc aucune livraison ni ramassage — le cycle
        complet n'a jamais pu être déroulé.

        Il a raison sur le fond, et le CDC V06 va dans son sens : l'US 3
        demande « une alerte immédiate dans une table avec tag de couleur », un
        « message expliquant : disponibles / réservés / manquants » et une
        « proposition d'alternative », et l'épic F attend des alertes de seuil
        sur le tableau de bord. Nulle part un refus d'écriture. C'est notre
        backlog (STK-01, CON-04) qui avait durci la règle en blocage sec.

        Une prestation porte le *prévisionnel* : dire « il me faudra 6 tables »
        avant de savoir comment les trouver est un usage normal, et le
        prévisionnel est précisément ce qui permet d'anticiper la tension. Le
        garde-fou reste là où il protège quelque chose de réel : le passage
        d'une réservation en statut « validée » refuse toujours une pénurie non
        forcée (`ReservationSerializer._validate_stock_conflicts_if_needed`).

        La pénurie n'est pas inscrite au registre des conflits ici :
        `ConflictHistory.reservation` n'est pas nullable, une pénurie purement
        prévisionnelle n'a donc pas d'entrée à porter. Elle remonte par
        `PrestationStockPreviewView` (que le formulaire interroge en direct) et
        entrera au registre dès qu'une réservation la matérialisera.
        """

        result = compute_prestation_stock(prestation)

        if not result["has_shortage"]:
            return

        shortages = [line for line in result["lines"] if line["shortage"]]

        logger.warning(
            "Prestation %s enregistrée avec %s article(s) en pénurie : %s",
            prestation.pk,
            len(shortages),
            ", ".join(
                f"part {line['part_id']} (manque {line['missing']})"
                for line in shortages
            ),
        )


class ManifestationSerializer(serializers.ModelSerializer):
    """CRUD d'une manifestation (événement).

    Le planning (maquette du CDC) affiche au survol d'une barre le nom du
    client, son interlocuteur, le volume d'objets engagés et l'avancement des
    livraisons. Ces quatre informations sont lues, jamais écrites, et calculées
    par la vue : les agréger ici, manifestation par manifestation, ferait une
    requête par ligne de planning.
    """

    organisateur_nom = serializers.SerializerMethodField()
    client_nom = serializers.CharField(source="client.nom", read_only=True)
    contact_telephone = serializers.SerializerMethodField()
    quantite_totale = serializers.SerializerMethodField()
    etat_livraison = serializers.SerializerMethodField()
    prestations_count = serializers.SerializerMethodField()
    statut_effectif = serializers.CharField(read_only=True)

    #: en_cours / terminée sont dérivés des dates, pas posables à la main.
    STATUTS_MANUELS = (
        StatutManifestation.BROUILLON,
        StatutManifestation.PLANIFIEE,
        StatutManifestation.ANNULEE,
    )

    class Meta:
        """Configuration du serializer Manifestation."""

        model = Manifestation
        fields = [
            "id",
            "nom",
            "description",
            "date_debut",
            "date_fin",
            "statut",
            "statut_effectif",
            "couleur",
            "pourcent_remise_globale",
            "client",
            "client_nom",
            "contact",
            "organisateur_nom",
            "contact_telephone",
            "quantite_totale",
            "etat_livraison",
            "prestations_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "statut_effectif",
            "organisateur_nom",
            "prestations_count",
            "created_at",
            "updated_at",
        ]

    def get_organisateur_nom(self, obj):
        """Interlocuteur de la manifestation.

        Clé conservée pour ne pas casser les écrans qui la lisent ; la source
        est le contact référent, à défaut le client.
        """

        return _libelle_interlocuteur(obj)

    def get_prestations_count(self, obj):
        """Nombre de prestations.

        Lu depuis l'annotation de la vue : `source="prestations.count"`
        déclenchait un `SELECT COUNT` par manifestation, soit dix requêtes pour
        dix barres de planning.
        """

        annotee = getattr(obj, "prestations_total", None)

        return annotee if annotee is not None else obj.prestations.count()

    def get_contact_telephone(self, obj):
        """Téléphone du contact référent — celui qu'on compose depuis le planning."""

        contact = obj.contact

        return contact.telephone if contact is not None else ""

    def get_quantite_totale(self, obj):
        """Volume d'objets engagés, annulés exclus.

        Lue depuis l'annotation posée par la vue quand elle existe. Le repli
        calcule ligne à ligne : il sert au détail d'une manifestation, pas à la
        liste, où il ferait une requête par ligne.
        """

        annotee = getattr(obj, "volume_engage", None)

        if annotee is not None:
            return annotee

        return _volume_des_bons(_bons_de_la_manifestation(obj))

    def get_etat_livraison(self, obj):
        """Avancement des livraisons : combien de bons sont sortis, sur combien."""

        return _etat_annote(obj) or _etat_des_bons(_bons_de_la_manifestation(obj))

    def validate_statut(self, value):
        """Refuse un statut dérivé posé à la main."""

        if value not in self.STATUTS_MANUELS:
            raise serializers.ValidationError(
                "Ce statut est calculé automatiquement d'après les dates et ne "
                "peut pas être défini manuellement (statuts posables : "
                "brouillon, planifiée, annulée)."
            )
        return value

    def validate(self, attrs):
        """La date de fin doit être postérieure ou égale à la date de début."""

        def effective(field):
            if field in attrs:
                return attrs[field]
            return getattr(self.instance, field, None) if self.instance else None

        date_debut = effective("date_debut")
        date_fin = effective("date_fin")

        if date_debut and date_fin and date_debut > date_fin:
            raise serializers.ValidationError({
                "date_fin": (
                    "La date de fin doit être postérieure ou égale à la date de début."
                )
            })

        return attrs

    @transaction.atomic
    def update(self, instance, validated_data):
        """Annulation en cascade : les réservations liées sont annulées aussi."""

        becoming_annulee = (
            validated_data.get("statut") == StatutManifestation.ANNULEE
            and instance.statut != StatutManifestation.ANNULEE
        )

        manifestation = super().update(instance, validated_data)

        if becoming_annulee:
            self._cancel_related_reservations(manifestation)

        return manifestation

    @staticmethod
    def _cancel_related_reservations(manifestation):
        """Annule les réservations pré-livraison ; les livrées/retournées
        (matériel sorti) sont laissées au circuit retour."""

        cancellables = Reservation.objects.filter(
            prestation__manifestation=manifestation,
            statut__in=[
                StatutReservation.BROUILLON,
                StatutReservation.SOUMISE,
                StatutReservation.VALIDEE,
            ],
        )

        for reservation in cancellables:
            transition_reservation_status(
                reservation,
                StatutReservation.ANNULEE,
                comment="Manifestation annulée",
            )
