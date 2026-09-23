#!/usr/bin/env python3
"""Croise les rapports d'une campagne et rend deux tableaux.

Le premier lit le coût par endpoint à mesure que la base grossit : c'est celui
qui désigne les endpoints dont le coût suit le volume, et donc le code à
corriger. Le second lit la capacité à volume fixé : c'est celui qui donne le
nombre d'utilisateurs simultanés tenus.

    python tests/charge/synthese.py tests/charge/resultats/
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _charger(dossier: Path):
    couts, capacites = {}, {}

    for fichier in sorted(dossier.glob("*.json")):
        rapport = json.loads(fichier.read_text(encoding="utf-8"))
        cout = re.match(r"cout-(\d+)\.json$", fichier.name)
        capacite = re.match(r"capacite-(\d+)-c(\d+)\.json$", fichier.name)

        if cout:
            couts[int(cout.group(1))] = rapport
        elif capacite:
            capacites[(int(capacite.group(1)), int(capacite.group(2)))] = rapport

    return couts, capacites


def _tableau_cout(couts):
    if not couts:
        return

    volumes = sorted(couts)
    endpoints = sorted(
        {
            ligne["endpoint"]
            for rapport in couts.values()
            for ligne in rapport["endpoints"]
        }
    )

    print()
    print("=" * (34 + 12 * len(volumes)))
    print("  COÛT — p95 en ms, un seul appelant, par volume de réservations")
    print("=" * (34 + 12 * len(volumes)))
    entete = f"{'endpoint':<30}" + "".join(f"{volume:>12}" for volume in volumes)
    print(entete + f"{'  facteur':>12}")
    print("-" * (34 + 12 * len(volumes)))

    lignes = []

    for endpoint in endpoints:
        valeurs = []

        for volume in volumes:
            trouve = next(
                (
                    ligne
                    for ligne in couts[volume]["endpoints"]
                    if ligne["endpoint"] == endpoint
                ),
                None,
            )
            valeurs.append(trouve["p95"] if trouve else None)

        connus = [valeur for valeur in valeurs if valeur]
        facteur = (connus[-1] / connus[0]) if len(connus) > 1 and connus[0] else 0
        lignes.append((endpoint, valeurs, facteur))

    for endpoint, valeurs, facteur in sorted(
        lignes, key=lambda item: item[2], reverse=True
    ):
        cellules = "".join(
            f"{valeur:>12.0f}" if valeur is not None else f"{'—':>12}"
            for valeur in valeurs
        )
        print(f"{endpoint:<30}{cellules}{facteur:>11.1f}×")

    print("-" * (34 + 12 * len(volumes)))
    print(
        "  « facteur » = p95 au dernier palier / p95 au premier. Proche de 1 :\n"
        "  le coût ne suit pas le volume. Au-delà du rapport des volumes :\n"
        "  le coût croît plus vite que la base — c'est une boucle, pas un index."
    )


def _tableau_capacite(capacites):
    if not capacites:
        return

    print()
    print("=" * 86)
    print("  CAPACITÉ — par volume et nombre d'appelants simultanés")
    print("=" * 86)
    print(
        f"{'volume':>8}{'appelants':>11}{'req/s':>9}{'appels':>9}"
        f"{'échecs':>9}{'% éch.':>9}{'p95 global':>13}{'p99 global':>13}"
    )
    print("-" * 86)

    for volume, concurrence in sorted(capacites):
        rapport = capacites[(volume, concurrence)]
        toutes = [
            (ligne["p95"], ligne["p99"], ligne["appels"])
            for ligne in rapport["endpoints"]
        ]
        appels = rapport["appels"] or 1
        p95 = max((valeur for valeur, _, _ in toutes), default=0)
        p99 = max((valeur for _, valeur, _ in toutes), default=0)
        taux = 100 * rapport["echecs"] / appels

        print(
            f"{volume:>8}{concurrence:>11}{rapport['debit_req_s']:>9.1f}"
            f"{rapport['appels']:>9}{rapport['echecs']:>9}{taux:>8.1f}%"
            f"{p95:>13.0f}{p99:>13.0f}"
        )

    print("-" * 86)
    print("  p95/p99 « global » = le pire endpoint du scénario, pas la moyenne.")


def main():
    dossier = Path(sys.argv[1] if len(sys.argv) > 1 else "tests/charge/resultats")

    if not dossier.is_dir():
        sys.exit(f"Dossier introuvable : {dossier}")

    couts, capacites = _charger(dossier)

    if not couts and not capacites:
        sys.exit(f"Aucun rapport dans {dossier}")

    _tableau_cout(couts)
    _tableau_capacite(capacites)


if __name__ == "__main__":
    main()
