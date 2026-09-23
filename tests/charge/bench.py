#!/usr/bin/env python3
"""Mesure de charge des endpoints du plugin.

Le volume cible est de 10 000 réservations par an (réponse du client du 20 mai,
ticket PERF-01). Cette commande répond à deux questions distinctes, qu'on
confond souvent :

1. **Ce que ça coûte à ce volume.** Mode `--sequentiel` : un seul appelant,
   chaque endpoint joué plusieurs fois, aucune concurrence. C'est la mesure du
   *coût algorithmique*. Si elle se dégrade quand la base grossit, c'est le
   code qu'il faut corriger, et aucun serveur plus gros n'y changera rien.

2. **Combien d'utilisateurs simultanés ça tient.** Mode par défaut : N
   appelants pendant D secondes. C'est la mesure de *capacité*, et elle ne
   veut rien dire tant que la première n'est pas saine.

On mesure des percentiles, pas des moyennes : une moyenne de 200 ms peut
cacher un utilisateur sur vingt qui attend huit secondes, et c'est celui-là
qui appelle le support.

    python tests/charge/bench.py --sequentiel
    python tests/charge/bench.py --concurrence 10 --duree 30
    python tests/charge/bench.py --scenario ecriture --concurrence 5
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

try:
    import requests
except ImportError:  # pragma: no cover - dépendance du poste, pas du plugin
    sys.exit("Ce script demande `requests` : pip install requests")


BASE_PLUGIN = "/plugin/inventree-location"


def _mois(decalage_jours: int = 0) -> tuple[str, str]:
    """Une fenêtre de calendrier d'un mois, comme FullCalendar l'envoie."""

    debut = date.today() + timedelta(days=decalage_jours)
    debut = debut.replace(day=1)
    fin = (debut + timedelta(days=31)).replace(day=1) - timedelta(days=1)

    return debut.isoformat(), fin.isoformat()


class Appel:
    """Un appel mesurable : son nom, sa méthode, et comment le construire.

    `construire` reçoit le contexte (articles connus, tirage aléatoire) et
    rend `(chemin, params, corps)`. Il est rappelé à chaque itération : deux
    appels successifs d'un même endpoint ne doivent pas taper la même page ni
    le même mois, sinon on mesure un cache et non un serveur.
    """

    #: Codes comptés comme une réponse rendue. Un 409 « pénurie » du contrôle
    #: de stock en fait partie : c'est la réponse métier attendue quand
    #: l'article manque, pas une défaillance du serveur.
    def __init__(self, nom, methode, construire, poids=1, codes_ok=(200, 201)):
        self.nom = nom
        self.methode = methode
        self.construire = construire
        self.poids = poids
        self.codes_ok = set(codes_ok)


def _appels_lecture() -> list[Appel]:
    """Les écrans en lecture : ce que fait un utilisateur qui consulte."""

    return [
        Appel(
            "reservations/liste",
            "GET",
            lambda ctx, rng: ("/reservations/", {"limit": 25}, None),
            poids=5,
        ),
        Appel(
            "reservations/page-profonde",
            "GET",
            lambda ctx, rng: (
                "/reservations/",
                {"limit": 25, "offset": rng.randrange(0, 5000, 25)},
                None,
            ),
            poids=2,
        ),
        Appel(
            "reservations/recherche",
            "GET",
            lambda ctx, rng: (
                "/reservations/",
                {"limit": 25, "search": f"{rng.randrange(0, 999):03d}"},
                None,
            ),
            poids=2,
        ),
        Appel(
            "reservations/calendrier",
            "GET",
            lambda ctx, rng: (
                "/reservations/calendar/",
                dict(zip(("from", "to"), _mois(rng.randrange(-180, 180)))),
                None,
            ),
            poids=4,
        ),
        Appel(
            "conflits",
            "GET",
            lambda ctx, rng: ("/conflicts/", None, None),
            poids=3,
        ),
        Appel(
            "conflits/historique",
            "GET",
            lambda ctx, rng: ("/conflicts/history/", None, None),
            poids=1,
        ),
        Appel(
            "alertes/stock",
            "GET",
            lambda ctx, rng: ("/alerts/stock/", None, None),
            poids=3,
        ),
        Appel(
            "livraisons",
            "GET",
            lambda ctx, rng: ("/deliveries/", None, None),
            poids=2,
        ),
        Appel(
            "tournee-du-jour",
            "GET",
            lambda ctx, rng: (
                "/tournees/",
                {
                    "date": (
                        date.today() + timedelta(days=rng.randrange(-30, 30))
                    ).isoformat()
                },
                None,
            ),
            poids=2,
        ),
        Appel(
            "catalogue",
            "GET",
            lambda ctx, rng: ("/catalog/", {"limit": 25}, None),
            poids=3,
        ),
        Appel(
            "prestations",
            "GET",
            lambda ctx, rng: ("/prestations/", None, None),
            poids=2,
        ),
        Appel(
            "ramassages",
            "GET",
            lambda ctx, rng: ("/ramassages/", None, None),
            poids=1,
        ),
        Appel(
            "verif-stock-article",
            "GET",
            _verif_stock,
            poids=3,
            codes_ok=(200, 409),
        ),
    ]


def _verif_stock(ctx, rng):
    """Le contrôle de disponibilité joué à chaque frappe du formulaire."""

    debut = date.today() + timedelta(days=rng.randrange(0, 120))
    fin = debut + timedelta(days=rng.randrange(1, 5))

    return (
        "/reservations/check-stock/",
        {
            "part": rng.choice(ctx["articles"]) if ctx["articles"] else 1,
            "quantity": rng.randint(1, 10),
            "date_retrait_prevue": debut.isoformat(),
            "date_retour_prevue": fin.isoformat(),
        },
        None,
    )


def _appels_ecriture(ctx) -> list[Appel]:
    """La création de réservation : le seul écrit qui compte en volume."""

    def creer(ctx, rng):
        debut = date.today() + timedelta(days=rng.randrange(1, 300))
        fin = debut + timedelta(days=rng.randrange(1, 4))
        articles = ctx["articles"] or [1]

        return (
            "/reservations/",
            None,
            {
                "prestation": rng.choice(ctx["prestations"]),
                "date_retrait_prevue": f"{debut.isoformat()}T08:00:00",
                "date_retour_prevue": f"{fin.isoformat()}T18:00:00",
                "lignes": [
                    {"part": part, "quantite_demandee": rng.randint(1, 3)}
                    for part in rng.sample(articles, min(2, len(articles)))
                ],
            },
        )

    return [Appel("reservations/creation", "POST", creer, poids=1)]


class Mesures:
    """Collecte thread-safe des durées, par endpoint."""

    def __init__(self):
        self._verrou = threading.Lock()
        self.durees = defaultdict(list)
        self.codes = defaultdict(lambda: defaultdict(int))
        self.erreurs = defaultdict(list)
        self.codes_ok = {}

    def ajouter(self, nom, duree_ms, code, detail=None, codes_ok=(200, 201)):
        with self._verrou:
            self.durees[nom].append(duree_ms)
            self.codes[nom][code] += 1
            self.codes_ok.setdefault(nom, set(codes_ok))

            if detail and len(self.erreurs[nom]) < 3:
                self.erreurs[nom].append(detail)


def _percentile(valeurs, part):
    """Percentile par interpolation la plus proche, sur une liste triée."""

    if not valeurs:
        return 0.0

    triees = sorted(valeurs)
    rang = min(int(round(part * (len(triees) - 1))), len(triees) - 1)

    return triees[rang]


def _session(url, token):
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Token {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    )
    return session


def _jouer(session, url, appel, ctx, rng, mesures, timeout):
    """Joue un appel et enregistre sa durée. Ne lève jamais."""

    chemin, params, corps = appel.construire(ctx, rng)
    cible = f"{url}{BASE_PLUGIN}{chemin}"
    depart = time.perf_counter()

    try:
        reponse = session.request(
            appel.methode, cible, params=params, json=corps, timeout=timeout
        )
        duree = (time.perf_counter() - depart) * 1000
        detail = None

        if reponse.status_code not in appel.codes_ok:
            detail = reponse.text[:200]

        mesures.ajouter(appel.nom, duree, reponse.status_code, detail, appel.codes_ok)
    except requests.Timeout:
        duree = (time.perf_counter() - depart) * 1000
        # Un dépassement est une mesure, pas un incident du script : c'est
        # justement le point de rupture qu'on cherche.
        mesures.ajouter(appel.nom, duree, "timeout", f"> {timeout} s")
    except requests.RequestException as erreur:
        duree = (time.perf_counter() - depart) * 1000
        mesures.ajouter(appel.nom, duree, "erreur", str(erreur)[:200])


def _contexte(session, url, timeout):
    """Identifiants réels à réinjecter dans les appels.

    Taper `?part=1` marcherait, mais mesurerait un article qui n'existe
    peut-être pas : le serveur répondrait 404 en deux millisecondes et on
    conclurait à un serveur rapide.
    """

    articles, prestations = [], []

    try:
        reponse = session.get(
            f"{url}{BASE_PLUGIN}/catalog/", params={"limit": 50}, timeout=timeout
        )
        charge = reponse.json()
        resultats = (
            charge.get("results", charge) if isinstance(charge, dict) else charge
        )
        articles = [item["id"] for item in resultats if isinstance(item, dict)][:50]
    except Exception:
        pass

    try:
        reponse = session.get(f"{url}{BASE_PLUGIN}/prestations/", timeout=timeout)
        charge = reponse.json()
        resultats = (
            charge.get("results", charge) if isinstance(charge, dict) else charge
        )
        prestations = [item["id"] for item in resultats if isinstance(item, dict)][:50]
    except Exception:
        pass

    return {"articles": articles, "prestations": prestations}


def _rapport(mesures, titre, duree_totale, volume):
    """Tableau lisible : percentiles, erreurs, débit."""

    lignes = []
    total_appels = 0
    total_echecs = 0

    for nom in sorted(mesures.durees):
        durees = mesures.durees[nom]
        codes = mesures.codes[nom]
        attendus = mesures.codes_ok.get(nom, {200, 201})
        echecs = sum(
            nombre
            for code, nombre in codes.items()
            if not (isinstance(code, int) and code in attendus)
        )
        total_appels += len(durees)
        total_echecs += echecs

        lignes.append(
            {
                "endpoint": nom,
                "appels": len(durees),
                "echecs": echecs,
                "p50": _percentile(durees, 0.50),
                "p90": _percentile(durees, 0.90),
                "p95": _percentile(durees, 0.95),
                "p99": _percentile(durees, 0.99),
                "max": max(durees),
                "moyenne": statistics.fmean(durees),
                "codes": {str(code): nombre for code, nombre in codes.items()},
                "exemples_erreur": mesures.erreurs.get(nom, []),
            }
        )

    print()
    print("=" * 96)
    print(f"  {titre}")
    print(f"  volume en base : {volume} réservations")
    print("=" * 96)
    print(
        f"{'endpoint':<30}{'appels':>7}{'éch.':>6}"
        f"{'p50':>9}{'p90':>9}{'p95':>9}{'p99':>9}{'max':>10}"
    )
    print("-" * 96)

    for ligne in sorted(lignes, key=lambda item: item["p95"], reverse=True):
        alerte = " !" if ligne["echecs"] else ""
        print(
            f"{ligne['endpoint']:<30}{ligne['appels']:>7}{ligne['echecs']:>6}"
            f"{ligne['p50']:>9.0f}{ligne['p90']:>9.0f}{ligne['p95']:>9.0f}"
            f"{ligne['p99']:>9.0f}{ligne['max']:>10.0f}{alerte}"
        )

    print("-" * 96)
    debit = total_appels / duree_totale if duree_totale else 0
    print(
        f"{'TOTAL':<30}{total_appels:>7}{total_echecs:>6}{'':>27}{debit:>19.1f} req/s"
    )
    print(
        "  durées en millisecondes ; « éch. » = HTTP >= 400, timeout ou erreur réseau"
    )

    for ligne in lignes:
        if ligne["exemples_erreur"]:
            print(f"\n  {ligne['endpoint']} — {ligne['codes']}")
            for exemple in ligne["exemples_erreur"]:
                print(f"      {exemple}")

    return {
        "titre": titre,
        "volume": volume,
        "duree_s": duree_totale,
        "debit_req_s": debit,
        "appels": total_appels,
        "echecs": total_echecs,
        "endpoints": lignes,
    }


def _volume_en_base(session, url, timeout):
    """Nombre de réservations que le serveur déclare, pour titrer le rapport."""

    try:
        reponse = session.get(
            f"{url}{BASE_PLUGIN}/reservations/",
            params={"limit": 1, "include_archived": "true"},
            timeout=timeout,
        )
        return reponse.json().get("count", "?")
    except Exception:
        return "?"


def main():
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--url", default="http://localhost:8000")
    parseur.add_argument("--utilisateur", default="admin")
    parseur.add_argument("--mot-de-passe", default="admin123")
    parseur.add_argument("--token", help="Jeton déjà obtenu (évite l'authentification)")
    parseur.add_argument(
        "--scenario",
        choices=["lecture", "ecriture", "tout"],
        default="lecture",
        help="lecture : les écrans de consultation. ecriture : création de réservation.",
    )
    parseur.add_argument(
        "--concurrence", type=int, default=10, help="Appelants simultanés."
    )
    parseur.add_argument(
        "--duree", type=float, default=30.0, help="Durée de la mesure, en secondes."
    )
    parseur.add_argument(
        "--sequentiel",
        action="store_true",
        help="Un seul appelant, chaque endpoint joué --repetitions fois. Mesure du coût.",
    )
    parseur.add_argument("--repetitions", type=int, default=5)
    parseur.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Au-delà, l'appel est compté en échec (c'est la rupture qu'on cherche).",
    )
    parseur.add_argument(
        "--exclure",
        default="",
        help=(
            "Endpoints à retirer du scénario, séparés par des virgules. Sert à "
            "mesurer ce que tient le reste de l'application quand un endpoint "
            "connu pour s'effondrer monopolise sinon tous les workers."
        ),
    )
    parseur.add_argument("--graine", type=int, default=20260922)
    parseur.add_argument("--json", help="Écrit le rapport brut dans ce fichier.")
    arguments = parseur.parse_args()

    token = arguments.token

    if not token:
        reponse = requests.get(
            f"{arguments.url}/api/user/token/",
            auth=(arguments.utilisateur, arguments.mot_de_passe),
            timeout=30,
        )
        reponse.raise_for_status()
        token = reponse.json()["token"]

    session = _session(arguments.url, token)
    ctx = _contexte(session, arguments.url, arguments.timeout)
    volume = _volume_en_base(session, arguments.url, arguments.timeout)

    appels = []

    if arguments.scenario in ("lecture", "tout"):
        appels += _appels_lecture()

    if arguments.scenario in ("ecriture", "tout"):
        if not ctx["prestations"]:
            sys.exit(
                "Aucune prestation en base : le scénario d'écriture n'a rien à "
                "rattacher. Lancer d'abord `seed_charge`."
            )
        appels += _appels_ecriture(ctx)

    exclus = {nom.strip() for nom in arguments.exclure.split(",") if nom.strip()}

    if exclus:
        inconnus = exclus - {appel.nom for appel in appels}

        if inconnus:
            sys.exit(f"--exclure : endpoint(s) inconnu(s) {sorted(inconnus)}")

        appels = [appel for appel in appels if appel.nom not in exclus]

    mesures = Mesures()
    depart = time.perf_counter()

    if arguments.sequentiel:
        rng = random.Random(arguments.graine)

        for appel in appels:
            for _ in range(arguments.repetitions):
                _jouer(
                    session,
                    arguments.url,
                    appel,
                    ctx,
                    rng,
                    mesures,
                    arguments.timeout,
                )

        titre = f"Coût par endpoint — 1 appelant, {arguments.repetitions} passages"
    else:
        # Chaque worker a sa session : `requests.Session` n'est pas conçue pour
        # être partagée entre threads, et un pool partagé sérialiserait les
        # connexions — on mesurerait le client, pas le serveur.
        pondere = [appel for appel in appels for _ in range(appel.poids)]
        fin = time.perf_counter() + arguments.duree

        def travailler(indice):
            propre = _session(arguments.url, token)
            rng = random.Random(arguments.graine + indice)

            while time.perf_counter() < fin:
                _jouer(
                    propre,
                    arguments.url,
                    rng.choice(pondere),
                    ctx,
                    rng,
                    mesures,
                    arguments.timeout,
                )

        with ThreadPoolExecutor(max_workers=arguments.concurrence) as pool:
            list(pool.map(travailler, range(arguments.concurrence)))

        titre = (
            f"Capacité — {arguments.concurrence} appelants simultanés "
            f"pendant {arguments.duree:.0f} s ({arguments.scenario}"
            + (f", sans {', '.join(sorted(exclus))}" if exclus else "")
            + ")"
        )

    duree_totale = time.perf_counter() - depart
    rapport = _rapport(mesures, titre, duree_totale, volume)
    rapport["concurrence"] = 1 if arguments.sequentiel else arguments.concurrence
    rapport["scenario"] = arguments.scenario
    rapport["exclus"] = sorted(exclus)

    if arguments.json:
        with open(arguments.json, "w", encoding="utf-8") as fichier:
            json.dump(rapport, fichier, ensure_ascii=False, indent=2)
        print(f"\n  rapport brut : {arguments.json}")


if __name__ == "__main__":
    main()
