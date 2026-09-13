"""Projection de l'exécution terrain (lot L6).

Les tables `Livraison` / `Ramassage` sont alimentées par recalcul depuis les
colonnes du bon, qui restent la vérité. Ce que ces tests doivent prouver :

- la projection est **idempotente** — rejouée, elle met à jour, elle ne
  duplique pas ;
- elle ne projette **rien** quand la prestation n'a pas de lieu, condition pour
  ne casser aucune fixture existante ;
- la vérification **voit** une divergence et **n'écrit rien** ;
- la quantité restant à livrer est un **agrégat**, pas une colonne ;
- et surtout : **aucun endpoint d'écriture n'a été touché**, donc le stock réel
  ne bouge pas d'un pouce.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.utils import timezone

from inventree_location.execution import (
    divergences_du_bon,
    livraison_attendue,
    projeter_le_bon,
    quantite_restant_a_livrer,
    ramassage_attendu,
)
from inventree_location.models import (
    Livraison,
    LivraisonLigne,
    Ramassage,
    RamassageArticle,
    ReturnIncident,
    ReturnIncidentType,
    StatutReservation,
)
from inventree_location.sav import get_unavailable_stock_quantity
from inventree_location.tests.factories import creer_chaine, make_ligne, make_part


@pytest.fixture
def bon_livre(db):
    """Un bon sorti : six unités, un lieu, un livreur."""

    chaine = creer_chaine(quantite=6, stock=10)
    bon = chaine["reservation"]
    bon.statut = StatutReservation.LIVREE
    bon.date_retrait_prevue = timezone.now()
    bon.date_retrait_reelle = timezone.now()
    bon.livreur_assigne = chaine["demandeur"]
    bon.save()

    return chaine


@pytest.mark.django_db
class TestProjectionDeLaLivraison:
    def test_un_bon_sorti_projette_son_passage(self, bon_livre):
        projeter_le_bon(bon_livre["reservation"])

        livraison = Livraison.objects.get()

        assert livraison.reservation_id == bon_livre["reservation"].pk
        assert livraison.lieu_id == bon_livre["lieu"].pk
        assert livraison.sequence == 1
        assert list(livraison.livreurs.all()) == [bon_livre["demandeur"]]
        assert livraison.lignes.get().quantite_livree == 6

    def test_un_bon_non_sorti_ne_projette_rien(self, db):
        chaine = creer_chaine(quantite=2)

        assert livraison_attendue(chaine["reservation"]) is None

        projeter_le_bon(chaine["reservation"])

        assert Livraison.objects.count() == 0

    def test_une_prestation_sans_lieu_ne_projette_rien(self, db):
        """Un brouillon sans lieu est légitime : la projection s'abstient."""

        chaine = creer_chaine(quantite=2, lieu=None)
        bon = chaine["reservation"]
        bon.prestation.lieu = None
        bon.prestation.save(update_fields=["lieu"])
        bon.statut = StatutReservation.LIVREE
        bon.save(update_fields=["statut"])

        assert livraison_attendue(bon) is None
        assert ramassage_attendu(bon) is None

        projeter_le_bon(bon)

        assert Livraison.objects.count() == 0

    def test_rejouer_la_projection_ne_duplique_pas(self, bon_livre):
        projeter_le_bon(bon_livre["reservation"])
        projeter_le_bon(bon_livre["reservation"])
        projeter_le_bon(bon_livre["reservation"])

        assert Livraison.objects.count() == 1
        assert LivraisonLigne.objects.count() == 1

    def test_une_ligne_retiree_du_bon_sort_de_la_projection(self, bon_livre):
        seconde = make_ligne(
            reservation=bon_livre["reservation"],
            part=make_part(rentable=True),
            quantite_demandee=3,
        )
        projeter_le_bon(bon_livre["reservation"])

        assert LivraisonLigne.objects.count() == 2

        seconde.delete()
        projeter_le_bon(bon_livre["reservation"])

        assert LivraisonLigne.objects.count() == 1

    def test_la_quantite_restante_est_un_agregat(self, bon_livre):
        ligne = bon_livre["ligne"]

        assert quantite_restant_a_livrer(ligne) == 6

        livraison = Livraison.objects.create(
            reservation=bon_livre["reservation"], sequence=1
        )
        LivraisonLigne.objects.create(
            livraison=livraison, ligne=ligne, quantite_livree=4
        )

        assert quantite_restant_a_livrer(ligne) == 2

        second_passage = Livraison.objects.create(
            reservation=bon_livre["reservation"], sequence=2
        )
        LivraisonLigne.objects.create(
            livraison=second_passage, ligne=ligne, quantite_livree=2
        )

        # Deux passages, le bon est complet : rien ne reste, et aucune colonne
        # n'a eu à être tenue à jour.
        assert quantite_restant_a_livrer(ligne) == 0

    def test_deux_passages_sur_un_meme_bon_cohabitent(self, bon_livre):
        Livraison.objects.create(reservation=bon_livre["reservation"], sequence=1)
        Livraison.objects.create(reservation=bon_livre["reservation"], sequence=2)

        assert Livraison.objects.count() == 2

    def test_deux_fois_la_meme_sequence_est_refuse(self, bon_livre):
        from django.db.utils import IntegrityError

        Livraison.objects.create(reservation=bon_livre["reservation"], sequence=1)

        with pytest.raises(IntegrityError):
            Livraison.objects.create(reservation=bon_livre["reservation"], sequence=1)


@pytest.mark.django_db
class TestProjectionDuRamassage:
    @pytest.fixture
    def bon_retourne(self, bon_livre):
        bon = bon_livre["reservation"]
        bon.statut = StatutReservation.RETOURNEE
        bon.date_retour_reelle = timezone.now()
        bon.save()

        ligne = bon_livre["ligne"]
        ligne.quantite_retournee = 5
        ligne.save(update_fields=["quantite_retournee"])

        ReturnIncident.objects.create(
            line=ligne, type=ReturnIncidentType.BROKEN, qty=2, bill_client=True
        )
        ReturnIncident.objects.create(
            line=ligne, type=ReturnIncidentType.MISSING, qty=1
        )

        return bon_livre

    def test_les_quatre_compteurs_viennent_du_registre(self, bon_retourne):
        projeter_le_bon(bon_retourne["reservation"])

        article = RamassageArticle.objects.get()

        # Revenu 5, dont 2 cassés : 3 conformes. Le manquant vient du registre.
        assert article.quantite_recuperee == 3
        assert article.quantite_cassee == 2
        assert article.quantite_detruite == 0
        assert article.quantite_manquante == 1
        assert article.facturer_client is True

    def test_le_bon_retourne_est_un_ramassage_termine(self, bon_retourne):
        projeter_le_bon(bon_retourne["reservation"])

        assert Ramassage.objects.get().ramassage_termine is True

    def test_rejouer_la_projection_ne_duplique_pas(self, bon_retourne):
        projeter_le_bon(bon_retourne["reservation"])
        projeter_le_bon(bon_retourne["reservation"])

        assert Ramassage.objects.count() == 1
        assert RamassageArticle.objects.count() == 1

    def test_un_bon_seulement_livre_ne_projette_pas_de_ramassage(self, bon_livre):
        projeter_le_bon(bon_livre["reservation"])

        assert Ramassage.objects.count() == 0

    def test_supprimer_un_incident_se_reflete_a_la_projection_suivante(
        self, bon_retourne
    ):
        projeter_le_bon(bon_retourne["reservation"])
        ReturnIncident.objects.filter(type=ReturnIncidentType.MISSING).delete()
        projeter_le_bon(bon_retourne["reservation"])

        assert RamassageArticle.objects.get().quantite_manquante == 0


@pytest.mark.django_db
class TestVerification:
    def test_aucune_divergence_apres_projection(self, bon_livre):
        projeter_le_bon(bon_livre["reservation"])

        assert divergences_du_bon(bon_livre["reservation"]) == []

    def test_une_livraison_manquante_est_signalee(self, bon_livre):
        ecarts = divergences_du_bon(bon_livre["reservation"])

        assert ecarts == ["livraison manquante"]

    def test_une_quantite_qui_derive_est_signalee(self, bon_livre):
        projeter_le_bon(bon_livre["reservation"])

        ligne_projetee = LivraisonLigne.objects.get()
        ligne_projetee.quantite_livree = 99
        ligne_projetee.save(update_fields=["quantite_livree"])

        ecarts = divergences_du_bon(bon_livre["reservation"])

        assert len(ecarts) == 1
        assert "quantités livrées" in ecarts[0]

    def test_une_livraison_orpheline_est_signalee(self, db):
        chaine = creer_chaine(quantite=1)
        Livraison.objects.create(reservation=chaine["reservation"], sequence=1)

        ecarts = divergences_du_bon(chaine["reservation"])

        assert ecarts == [
            "une livraison est projetée alors que le bon n'est pas sorti"
        ]

    def test_la_verification_n_ecrit_rien(self, bon_livre):
        divergences_du_bon(bon_livre["reservation"])

        assert Livraison.objects.count() == 0
        assert Ramassage.objects.count() == 0


@pytest.mark.django_db
class TestCommandes:
    def test_projeter_execution_puis_verifier(self, bon_livre, capsys):
        call_command("projeter_execution")

        assert Livraison.objects.count() == 1

        call_command("verifier_projection")

        assert "Aucune divergence" in capsys.readouterr().out

    def test_le_mode_a_blanc_n_ecrit_rien(self, bon_livre, capsys):
        call_command("projeter_execution", "--dry-run")

        assert Livraison.objects.count() == 0
        assert "à blanc" in capsys.readouterr().out

    def test_verifier_projection_sort_en_erreur_sur_divergence(self, bon_livre):
        with pytest.raises(SystemExit):
            call_command("verifier_projection")

    def test_une_date_illisible_est_refusee(self, db):
        from django.core.management.base import CommandError

        with pytest.raises(CommandError):
            call_command("projeter_execution", "--jour", "hier")


@pytest.mark.django_db
class TestNonRegressionDuStock:
    """Le critère de fin du lot : aucun endpoint d'écriture n'a bougé.

    `get_unavailable_stock_quantity` est la seule source des manquants pour le
    stock réel. Projeter ne doit strictement rien y changer — c'est ce qui rend
    la stratégie additive sans risque.
    """

    def test_projeter_ne_change_pas_le_stock_indisponible(self, bon_livre):
        part = bon_livre["part"]
        ReturnIncident.objects.create(
            line=bon_livre["ligne"], type=ReturnIncidentType.MISSING, qty=2
        )

        avant = get_unavailable_stock_quantity(part.pk)

        projeter_le_bon(bon_livre["reservation"])

        assert get_unavailable_stock_quantity(part.pk) == avant
