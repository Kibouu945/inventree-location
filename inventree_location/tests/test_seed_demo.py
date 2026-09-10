"""Commande `seed_demo` : jeu de données de démonstration."""

from __future__ import annotations

import pytest

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from inventree_location import roles
from inventree_location.models import (
    Client,
    Contact,
    Manifestation,
    Prestation,
    RentableItem,
    Reservation,
    ReturnIncident,
)


@pytest.mark.django_db
class TestSeedDemo:
    def test_cree_un_jeu_complet(self, capsys):
        call_command("seed_demo")

        assert Client.objects.count() == 3
        assert Contact.objects.count() == 3
        assert get_user_model().objects.count() == len(roles.ALL_ROLES)
        assert Manifestation.objects.count() == 5
        assert Prestation.objects.count() == 10
        assert Reservation.objects.count() == 10
        # Les deux zones de la manifestation terminée portent chacune un
        # cassé et un manquant : de quoi alimenter le SAV et le rapport de
        # pertes.
        assert ReturnIncident.objects.count() == 4

    def test_les_comptes_sont_utilisables(self):
        """`POST /api/user/` ignore le mot de passe ; la commande, non."""

        from django.contrib.auth import authenticate

        call_command("seed_demo")

        assert authenticate(username="demo_livreur", password="Demo!2026") is not None

    def test_chaque_role_a_son_compte(self):
        call_command("seed_demo")

        for role in roles.ALL_ROLES:
            compte = get_user_model().objects.get(username=f"demo_{role}")

            assert list(compte.groups.values_list("name", flat=True)) == [role]

    def test_le_poids_est_renseigne_sauf_sur_le_virtuel(self):
        call_command("seed_demo")

        physiques = RentableItem.objects.filter(is_virtual=False)

        assert physiques.exists()
        assert not physiques.filter(poids__isnull=True).exists()
        assert RentableItem.objects.get(is_virtual=True).poids is None

    def test_est_idempotente(self):
        call_command("seed_demo")
        call_command("seed_demo")

        assert Client.objects.count() == 3
        assert Prestation.objects.count() == 10
        assert Reservation.objects.count() == 10

    def test_refuse_une_base_qui_porte_autre_chose(self):
        Client.objects.create(nom="Vrai client")

        with pytest.raises(CommandError, match="hors démonstration"):
            call_command("seed_demo")

    def test_force_passe_outre(self):
        Client.objects.create(nom="Vrai client")

        call_command("seed_demo", "--force")

        assert Client.objects.count() == 4

    def test_reset_ne_supprime_que_la_demonstration(self):
        vrai = Client.objects.create(nom="Vrai client")

        call_command("seed_demo", "--force")
        call_command("seed_demo", "--reset", "--force")

        assert Client.objects.filter(pk=vrai.pk).exists()
        assert Client.objects.count() == 4

    def test_date_pivot_invalide_est_refusee(self):
        with pytest.raises(CommandError, match="AAAA-MM-JJ"):
            call_command("seed_demo", "--date-pivot", "hier")

    def test_la_date_pivot_deplace_les_manifestations(self):
        call_command("seed_demo", "--date-pivot", "2027-03-01")

        annees = {m.date_debut.year for m in Manifestation.objects.all()}

        assert annees == {2027}
