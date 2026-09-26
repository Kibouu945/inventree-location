"""Projection de l'exécution terrain (lot L6), puis sa greffe (lot L7)."""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location import roles

from inventree_location.execution import (
    divergences_du_bon,
    livraison_attendue,
    projeter_le_bon,
    quantite_deposee,
    quantite_restant_a_livrer,
    ramassage_attendu,
)
from inventree_location.livraison import (
    LivraisonRefusee,
    accepter_livraison,
    changer_etat_livraison,
    relacher_livraison,
)
from inventree_location.models import (
    EtatLivraison,
    LigneReservation,
    Livraison,
    LivraisonLigne,
    Ramassage,
    RamassageArticle,
    Reservation,
    ReturnIncident,
    ReturnIncidentType,
    StatutReservation,
)
from inventree_location.sav import RamassageRetourView, get_unavailable_stock_quantity
from inventree_location.services.workflow_service import (
    transition_reservation_status,
)
from inventree_location.tests.factories import (
    creer_chaine,
    make_ligne,
    make_part,
    make_user,
)


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

        assert ecarts == ["une livraison est projetée alors que le bon n'est pas sorti"]

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
    """Le critère de fin du lot : aucun endpoint d'écriture n'a bougé."""

    def test_projeter_ne_change_pas_le_stock_indisponible(self, bon_livre):
        part = bon_livre["part"]
        ReturnIncident.objects.create(
            line=bon_livre["ligne"], type=ReturnIncidentType.MISSING, qty=2
        )

        avant = get_unavailable_stock_quantity(part.pk)

        projeter_le_bon(bon_livre["reservation"])

        assert get_unavailable_stock_quantity(part.pk) == avant


@pytest.fixture
def bon_a_livrer(db):
    """Un bon validé, avec un lieu et un créneau : prêt à entrer en tournée."""

    chaine = creer_chaine(quantite=4, stock=10)
    bon = chaine["reservation"]
    bon.statut = StatutReservation.VALIDEE
    bon.date_retrait_prevue = timezone.now()
    bon.save(update_fields=["statut", "date_retrait_prevue"])

    return chaine


@pytest.mark.django_db
class TestGreffeDuJournalDeLivraison:
    """Le journal de livraison écrit les tables d'exécution (lot L7, greffe 1)."""

    def test_accepter_ne_projette_aucun_passage(self, bon_a_livrer):
        """Prendre une livraison n'est pas la faire : rien n'est encore sorti."""

        bon = bon_a_livrer["reservation"]

        accepter_livraison(bon.pk, bon_a_livrer["demandeur"])

        assert Livraison.objects.count() == 0

        bon.refresh_from_db()

        assert divergences_du_bon(bon) == []

    def test_livrer_ecrit_le_passage_sans_commande(self, bon_a_livrer):
        bon = bon_a_livrer["reservation"]
        livreur = bon_a_livrer["demandeur"]

        accepter_livraison(bon.pk, livreur)
        changer_etat_livraison(bon.pk, EtatLivraison.EN_COURS, livreur)
        changer_etat_livraison(bon.pk, EtatLivraison.LIVREE, livreur)

        livraison = Livraison.objects.get()

        assert livraison.reservation_id == bon.pk
        assert livraison.lieu_id == bon_a_livrer["lieu"].pk
        assert livraison.sequence == 1
        assert list(livraison.livreurs.all()) == [livreur]
        assert livraison.lignes.get().quantite_livree == 4

    def test_le_depot_ecrit_l_heure_reelle_et_le_passage_la_porte(self, bon_a_livrer):
        """La colonne n'avait aucun écrivain avant cette greffe."""

        bon = bon_a_livrer["reservation"]
        livreur = bon_a_livrer["demandeur"]

        accepter_livraison(bon.pk, livreur)
        changer_etat_livraison(bon.pk, EtatLivraison.EN_COURS, livreur)

        bon.refresh_from_db()

        assert bon.date_retrait_reelle is None

        changer_etat_livraison(bon.pk, EtatLivraison.LIVREE, livreur)
        bon.refresh_from_db()

        assert bon.date_retrait_reelle is not None
        assert Livraison.objects.get().date_reelle == bon.date_retrait_reelle

    def test_l_heure_du_depot_ne_s_ecrit_qu_une_fois(self, bon_a_livrer):
        """Ce qui garantit l'unicité, c'est la machine à états, pas un garde."""

        bon = bon_a_livrer["reservation"]
        livreur = bon_a_livrer["demandeur"]

        accepter_livraison(bon.pk, livreur)
        changer_etat_livraison(bon.pk, EtatLivraison.EN_COURS, livreur)
        changer_etat_livraison(bon.pk, EtatLivraison.PROBLEME, livreur)
        bon.refresh_from_db()

        assert bon.date_retrait_reelle is None

        changer_etat_livraison(bon.pk, EtatLivraison.LIVREE, livreur)
        bon.refresh_from_db()
        depot = bon.date_retrait_reelle

        assert depot is not None

        with pytest.raises(LivraisonRefusee):
            changer_etat_livraison(bon.pk, EtatLivraison.LIVREE, livreur)

        bon.refresh_from_db()

        assert bon.date_retrait_reelle == depot

    def test_relacher_ne_laisse_aucun_passage(self, bon_a_livrer):
        bon = bon_a_livrer["reservation"]
        livreur = bon_a_livrer["demandeur"]

        accepter_livraison(bon.pk, livreur)
        relacher_livraison(bon.pk, livreur)

        assert Livraison.objects.count() == 0

        bon.refresh_from_db()

        assert divergences_du_bon(bon) == []

    def test_la_greffe_ne_laisse_aucune_divergence(self, bon_a_livrer, capsys):
        """La preuve du lot : la commande de vérification ne trouve rien."""

        bon = bon_a_livrer["reservation"]
        livreur = bon_a_livrer["demandeur"]

        accepter_livraison(bon.pk, livreur)
        changer_etat_livraison(bon.pk, EtatLivraison.EN_COURS, livreur)
        changer_etat_livraison(bon.pk, EtatLivraison.LIVREE, livreur)

        call_command("verifier_projection")

        assert "Aucune divergence" in capsys.readouterr().out

    def test_un_bon_annule_apres_livraison_perd_son_passage(self, bon_a_livrer):
        """La rétractation : aligner, c'est aussi retirer."""

        bon = bon_a_livrer["reservation"]
        livreur = bon_a_livrer["demandeur"]

        accepter_livraison(bon.pk, livreur)
        changer_etat_livraison(bon.pk, EtatLivraison.EN_COURS, livreur)
        changer_etat_livraison(bon.pk, EtatLivraison.LIVREE, livreur)

        assert Livraison.objects.count() == 1

        bon.refresh_from_db()
        bon.statut = StatutReservation.ANNULEE
        bon.save(update_fields=["statut"])

        projeter_le_bon(bon)

        assert Livraison.objects.count() == 0
        assert divergences_du_bon(bon) == []


@pytest.mark.django_db
class TestGreffeDuPassageDeStatut:
    """Le service de statut écrit les tables d'exécution (lot L7, greffe 2)."""

    def test_livrer_sans_passer_par_le_livreur_ecrit_le_passage(self, bon_a_livrer):
        """Le gestionnaire livre au clavier : la table suit quand même."""

        bon = bon_a_livrer["reservation"]

        transition_reservation_status(
            bon, StatutReservation.LIVREE, user=bon_a_livrer["demandeur"]
        )

        livraison = Livraison.objects.get()

        assert livraison.reservation_id == bon.pk
        assert livraison.lieu_id == bon_a_livrer["lieu"].pk
        assert livraison.lignes.get().quantite_livree == 4
        assert divergences_du_bon(bon) == []

    def test_le_retour_ecrit_le_ramassage_depuis_le_registre(self, bon_a_livrer):
        """Les quatre compteurs viennent du registre, jamais d'un payload."""

        bon = bon_a_livrer["reservation"]
        ligne = bon_a_livrer["ligne"]

        transition_reservation_status(bon, StatutReservation.LIVREE)

        ligne.quantite_retournee = 3
        ligne.save(update_fields=["quantite_retournee"])
        ReturnIncident.objects.create(line=ligne, type=ReturnIncidentType.BROKEN, qty=1)
        ReturnIncident.objects.create(
            line=ligne, type=ReturnIncidentType.MISSING, qty=1
        )

        transition_reservation_status(bon, StatutReservation.RETOURNEE)

        article = RamassageArticle.objects.get()

        assert article.quantite_recuperee == 2
        assert article.quantite_cassee == 1
        assert article.quantite_manquante == 1
        assert Ramassage.objects.get().ramassage_termine is True
        assert divergences_du_bon(bon) == []

    def test_annuler_un_bon_livre_retire_son_passage(self, bon_a_livrer):
        """Arbitrage à confirmer côté métier, voir le rapport du lot."""

        bon = bon_a_livrer["reservation"]

        transition_reservation_status(bon, StatutReservation.LIVREE)

        assert Livraison.objects.count() == 1

        transition_reservation_status(bon, StatutReservation.ANNULEE)

        assert Livraison.objects.count() == 0
        assert divergences_du_bon(bon) == []

    def test_une_transition_refusee_n_ecrit_rien(self, bon_a_livrer):
        """Le refus arrive avant la transaction : ni statut, ni passage."""

        bon = bon_a_livrer["reservation"]

        with pytest.raises(ValidationError):
            transition_reservation_status(bon, StatutReservation.CLOTUREE)

        assert Livraison.objects.count() == 0


@pytest.mark.django_db
class TestGreffeDeLaSaisieDeRamassage:
    """La saisie de ramassage écrit les tables d'exécution (lot L7, greffe 3)."""

    def test_la_saisie_ecrit_le_passage_de_ramassage(self, bon_a_livrer):
        bon = bon_a_livrer["reservation"]
        bon.statut = StatutReservation.LIVREE
        bon.save(update_fields=["statut"])
        magasinier = make_user(role=roles.MAGASINIER)

        requete = APIRequestFactory().patch(
            f"/plugin/inventree-location/ramassages/{bon.pk}/retour/",
            {
                "lignes": [
                    {
                        "ligne": bon_a_livrer["ligne"].pk,
                        "quantite_ramassee": 2,
                        "quantite_sav": 1,
                        "quantite_detruite": 1,
                        "quantite_manquante": 1,
                        "facturer_client": True,
                    }
                ]
            },
            format="json",
        )
        force_authenticate(requete, user=magasinier)
        reponse = RamassageRetourView.as_view()(requete, pk=bon.pk)

        assert reponse.status_code == 200

        bon.refresh_from_db()
        ramassage = Ramassage.objects.get()
        article = RamassageArticle.objects.get()

        assert ramassage.lieu_id == bon_a_livrer["lieu"].pk
        assert ramassage.date_reelle == bon.date_retour_reelle
        assert ramassage.ramassage_termine is True
        assert article.quantite_recuperee == 2
        assert article.quantite_cassee == 1
        assert article.quantite_detruite == 1
        # Déclarée par la saisie, pas déduite : R31 (« le manquant se déduit »)
        # est une règle d'écran, que F7 portera.
        assert article.quantite_manquante == 1
        assert article.facturer_client is True

    def test_la_saisie_ne_laisse_aucune_divergence(self, bon_a_livrer, capsys):
        bon = bon_a_livrer["reservation"]
        bon.statut = StatutReservation.LIVREE
        bon.save(update_fields=["statut"])
        magasinier = make_user(role=roles.MAGASINIER)

        requete = APIRequestFactory().patch(
            f"/plugin/inventree-location/ramassages/{bon.pk}/retour/",
            {
                "lignes": [
                    {
                        "ligne": bon_a_livrer["ligne"].pk,
                        "quantite_ramassee": 4,
                    }
                ]
            },
            format="json",
        )
        force_authenticate(requete, user=magasinier)

        assert RamassageRetourView.as_view()(requete, pk=bon.pk).status_code == 200

        call_command("verifier_projection")

        assert "Aucune divergence" in capsys.readouterr().out


@pytest.mark.django_db
class TestRelectureDesLignes:
    """La projection relit les lignes, elle ne croit pas l'instance reçue."""

    def test_un_cache_perime_ne_fait_pas_mentir_la_projection(self, bon_livre):
        bon = bon_livre["reservation"]

        # Comme la vue de ramassage : précharger, et remplir le cache.
        precharge = Reservation.objects.prefetch_related("lignes").get(pk=bon.pk)
        assert list(precharge.lignes.all())

        # Puis écrire par une autre instance de la même ligne.
        ligne = LigneReservation.objects.get(pk=bon_livre["ligne"].pk)
        ligne.quantite_livree = 5
        ligne.save(update_fields=["quantite_livree"])

        projeter_le_bon(precharge)

        assert LivraisonLigne.objects.get().quantite_livree == 5
        assert divergences_du_bon(precharge) == []


@pytest.mark.django_db
class TestQuantiteDeposee:
    """« Combien a été effectivement déposé » — la valeur qu'affiche F6."""

    def test_sans_passage_rien_n_est_depose(self, bon_livre):
        ligne = bon_livre["ligne"]

        assert quantite_deposee(ligne) == 0
        assert quantite_restant_a_livrer(ligne) == 6

    def test_la_somme_porte_sur_tous_les_passages(self, bon_livre):
        ligne = bon_livre["ligne"]

        for sequence, quantite in ((1, 4), (2, 2)):
            livraison = Livraison.objects.create(
                reservation=bon_livre["reservation"], sequence=sequence
            )
            LivraisonLigne.objects.create(
                livraison=livraison, ligne=ligne, quantite_livree=quantite
            )

        assert quantite_deposee(ligne) == 6
        assert quantite_restant_a_livrer(ligne) == 0

    def test_le_cache_precharge_evite_une_requete_par_ligne(
        self, bon_livre, django_assert_num_queries
    ):
        """Le chemin que prend la liste des tournées."""

        projeter_le_bon(bon_livre["reservation"])

        bon = Reservation.objects.prefetch_related("lignes__livraisons").get(
            pk=bon_livre["reservation"].pk
        )
        lignes = list(bon.lignes.all())

        with django_assert_num_queries(0):
            assert [quantite_deposee(ligne) for ligne in lignes] == [6]


@pytest.mark.django_db
class TestHeureDuDepot:
    """L'heure réelle du dépôt, sur les deux chemins qui y mènent."""

    def test_le_bouton_du_gestionnaire_ecrit_l_heure(self, bon_a_livrer):
        bon = bon_a_livrer["reservation"]

        transition_reservation_status(bon, StatutReservation.LIVREE)
        bon.refresh_from_db()

        assert bon.date_retrait_reelle is not None
        assert Livraison.objects.get().date_reelle == bon.date_retrait_reelle

    def test_l_heure_du_livreur_n_est_pas_reecrite_par_le_service(self, bon_a_livrer):
        """Le journal écrit l'heure avant la transition : elle fait foi."""

        bon = bon_a_livrer["reservation"]
        livreur = bon_a_livrer["demandeur"]

        accepter_livraison(bon.pk, livreur)
        changer_etat_livraison(bon.pk, EtatLivraison.EN_COURS, livreur)
        changer_etat_livraison(bon.pk, EtatLivraison.LIVREE, livreur)

        bon.refresh_from_db()
        depot = bon.date_retrait_reelle

        transition_reservation_status(bon, StatutReservation.RETOURNEE)
        bon.refresh_from_db()

        assert bon.date_retrait_reelle == depot

    def test_un_passage_sans_heure_est_une_divergence(self, bon_a_livrer):
        """Ce que la vérification laissait passer avant."""

        bon = bon_a_livrer["reservation"]

        transition_reservation_status(bon, StatutReservation.LIVREE)
        bon.refresh_from_db()

        assert divergences_du_bon(bon) == []

        Livraison.objects.filter(reservation_id=bon.pk).update(date_reelle=None)

        ecarts = divergences_du_bon(bon)

        assert len(ecarts) == 1
        assert "date_reelle" in ecarts[0]
