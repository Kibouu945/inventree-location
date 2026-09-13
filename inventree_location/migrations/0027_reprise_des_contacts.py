"""Transforme les organisateurs en contacts de leur client.

`Manifestation.organisateur` était un compte Django. Le point du 09/09/2026 a
tranché : le client externe n'accède pas à la plateforme, chaque interlocuteur
est un `Contact`. Cette migration crée l'information manquante avant que `0028`
ne supprime la colonne.

Elle préserve la sortie de `organisateur_nom` et `organisateur_telephone` du bon
de livraison : le nom et le téléphone sont recopiés depuis le compte et son
profil, seule leur provenance change.

`email` reste nul quand le compte n'en a pas. Fabriquer une adresse mettrait de
la fausse donnée en base, et l'index unique tolère plusieurs NULL.

Irréversible au sens métier : on ne re-scinde pas un contact en compte.
"""

from django.db import migrations

#: Rôles d'exploitation. Un magasinier dont quelqu'un a rempli `Profile.groupe`
#: par erreur ne doit pas atterrir dans le fichier clients.
ROLES_INTERNES = frozenset({
    "admin",
    "gestionnaire",
    "magasinier",
    "livreur",
    "sav",
    "lecteur",
    "acheteur",
})


def _nom_et_prenom(compte):
    """Nom jamais vide : c'est ce qui s'imprime sur le bon de livraison."""

    return (compte.last_name or compte.username, compte.first_name or "")


def _telephone(Profile, compte):
    profil = Profile.objects.filter(user=compte).first()

    return profil.telephone if profil else ""


def _contact(Contact, Profile, emails_pris, client, compte):
    """Contact de ce compte chez ce client, créé si besoin.

    Déduplication par e-mail, qui est unique **globalement** : un même
    interlocuteur travaillant pour deux clients ne peut pas avoir deux fiches
    portant la même adresse. À défaut d'e-mail, on déduplique sur le nom.
    """

    email = (compte.email or "").strip().lower() or None

    if email and email in emails_pris:
        return Contact.objects.filter(email=email).first()

    nom, prenom = _nom_et_prenom(compte)
    existant = Contact.objects.filter(client=client, nom=nom, prenom=prenom).first()

    if existant is not None:
        return existant

    contact = Contact.objects.create(
        client=client,
        nom=nom,
        prenom=prenom,
        email=email,
        telephone=_telephone(Profile, compte),
    )

    if email:
        emails_pris.add(email)

    return contact


def reprendre(apps, schema_editor):
    Client = apps.get_model("inventree_location", "Client")
    Contact = apps.get_model("inventree_location", "Contact")
    Manifestation = apps.get_model("inventree_location", "Manifestation")
    Profile = apps.get_model("inventree_location", "Profile")
    Group = apps.get_model("auth", "Group")

    emails_pris = {
        email.lower()
        for email in Contact.objects.exclude(email=None).values_list("email", flat=True)
    }

    # Les groupes scouts repris étaient des associations ; le libellé du choix
    # « Entreprise ou association » les couvre.
    Client.objects.filter(type_client="").update(type_client="entreprise")

    depuis_manifestations = 0

    for manifestation in Manifestation.objects.select_related(
        "client", "organisateur"
    ).iterator():
        if manifestation.contact_id or manifestation.organisateur_id is None:
            continue

        contact = _contact(
            Contact,
            Profile,
            emails_pris,
            manifestation.client,
            manifestation.organisateur,
        )
        Manifestation.objects.filter(pk=manifestation.pk).update(contact=contact)
        depuis_manifestations += 1

    # Les comptes rattachés à un client par `Profile.groupe` sans porter de rôle
    # d'exploitation : c'étaient des interlocuteurs, pas du personnel.
    depuis_profils = 0

    for profil in Profile.objects.select_related("user", "groupe").iterator():
        if profil.groupe_id is None:
            continue

        roles_du_compte = set(
            Group.objects.filter(user=profil.user).values_list("name", flat=True)
        )

        if roles_du_compte & ROLES_INTERNES:
            continue

        avant = Contact.objects.count()
        _contact(Contact, Profile, emails_pris, profil.groupe, profil.user)
        depuis_profils += Contact.objects.count() - avant

    if depuis_manifestations or depuis_profils:
        print(
            f"  inventree-location : {depuis_manifestations} manifestation(s) "
            f"rattachée(s) à un contact, {depuis_profils} contact(s) repris "
            f"d'un profil"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("inventree_location", "0026_client_et_contact"),
        ("auth", "0001_initial"),
    ]

    operations = [migrations.RunPython(reprendre, migrations.RunPython.noop)]
