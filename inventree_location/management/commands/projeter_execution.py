"""Remplit les tables d'exécution depuis la vérité actuelle des bons."""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from inventree_location.execution import bons_du_jour, projeter_le_bon
from inventree_location.models import Reservation


def _jour(valeur):
    try:
        return date.fromisoformat(valeur)
    except ValueError as erreur:
        raise CommandError(
            f"Date illisible : {valeur} (AAAA-MM-JJ attendu)"
        ) from erreur


class Command(BaseCommand):
    help = "Projette livraisons et ramassages depuis les bons de réservation."

    def add_arguments(self, parser):
        parser.add_argument(
            "--jour",
            help="Ne projeter que les bons dont le retrait est prévu ce jour-là.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Compte ce qui serait projeté sans rien écrire.",
        )

    def handle(self, *args, **options):
        bons = Reservation.objects.select_related(
            "prestation__lieu", "livreur_assigne"
        ).prefetch_related("lignes")

        if options["jour"]:
            bons = bons_du_jour(_jour(options["jour"]), bons)

        livraisons = ramassages = 0

        # Une seule transaction : une projection à moitié écrite serait pire
        # que pas de projection, `verifier_projection` la lirait comme une
        with transaction.atomic():
            for bon in bons:
                resultat = projeter_le_bon(bon)

                livraisons += resultat["livraison"] is not None
                ramassages += resultat["ramassage"] is not None

            if options["dry_run"]:
                transaction.set_rollback(True)

        prefixe = "(à blanc) " if options["dry_run"] else ""

        self.stdout.write(
            self.style.SUCCESS(
                f"{prefixe}{livraisons} livraison(s) et {ramassages} ramassage(s) "
                "projeté(s)."
            )
        )
