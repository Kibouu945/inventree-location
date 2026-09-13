"""Compare les tables d'exécution à la vérité, sans rien écrire.

C'est le garde-fou de la stratégie additive. Tant que les colonnes du bon font
foi, une projection qui dérive ne se voit nulle part — ni à l'écran, ni dans un
test. Cette commande recalcule et **affiche** les écarts ; `projeter_execution`
les rattrape.

    python manage.py verifier_projection
    python manage.py verifier_projection --jour 2026-09-15

Code de sortie 1 s'il existe au moins une divergence, pour qu'un enchaînement
de commandes s'arrête.
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from inventree_location.execution import bons_du_jour, divergences_du_bon
from inventree_location.models import Reservation


def _jour(valeur):
    try:
        return date.fromisoformat(valeur)
    except ValueError as erreur:
        raise CommandError(
            f"Date illisible : {valeur} (AAAA-MM-JJ attendu)"
        ) from erreur


class Command(BaseCommand):
    help = "Vérifie les tables d'exécution contre les bons, sans rien écrire."

    def add_arguments(self, parser):
        parser.add_argument(
            "--jour",
            help="Ne vérifier que les bons dont le retrait est prévu ce jour-là.",
        )

    def handle(self, *args, **options):
        bons = Reservation.objects.select_related(
            "prestation__lieu", "livreur_assigne"
        ).prefetch_related("lignes", "livraisons__lignes", "ramassages__articles")

        if options["jour"]:
            bons = bons_du_jour(_jour(options["jour"]), bons)

        divergents = 0

        for bon in bons:
            ecarts = divergences_du_bon(bon)

            if not ecarts:
                continue

            divergents += 1

            self.stdout.write(self.style.WARNING(f"{bon.numero} :"))

            for ecart in ecarts:
                self.stdout.write(f"  - {ecart}")

        if divergents:
            self.stdout.write(self.style.ERROR(f"{divergents} bon(s) en divergence."))
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS("Aucune divergence."))
