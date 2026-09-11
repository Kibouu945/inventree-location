// Logique du planning, sans React : placement des barres, fenêtre, libellés.
//
// Séparée du rendu pour être testable — c'est le pendant côté front de ce que
// `execution.py` est à `views.py`.

import type {
  Barre,
  FenetrePlanning,
  ManifestationPlanning,
  VuePlanning
} from './types';

/** Largeur par défaut : trois semaines tiennent à l'écran sans rétrécir les
 * colonnes au point de rendre les jours illisibles. */
export const JOURS_PAR_DEFAUT = 21;

const MS_PAR_JOUR = 24 * 60 * 60 * 1000;

/** Le jour d'une date serveur (`AAAA-MM-JJ HH:MM`), sans son heure.
 *
 * Découpage de la chaîne plutôt que `new Date(...)` : construire une date
 * depuis une chaîne sans fuseau la fait interpréter en heure locale du
 * navigateur, et un poste à Tokyo verrait la manifestation glisser d'un jour.
 * Le serveur a déjà fait la conversion en Europe/Paris. */
export function jourDe(horodatage: string): string {
  return (horodatage || '').slice(0, 10);
}

/** Aujourd'hui au format `AAAA-MM-JJ`, dans le fuseau du poste. */
export function aujourdhui(maintenant: Date = new Date()): string {
  const mois = String(maintenant.getMonth() + 1).padStart(2, '0');
  const jour = String(maintenant.getDate()).padStart(2, '0');
  return `${maintenant.getFullYear()}-${mois}-${jour}`;
}

/** Les jours d'une fenêtre, du premier au dernier inclus. */
export function joursDeLaFenetre(fenetre: FenetrePlanning): string[] {
  const depart = Date.parse(`${fenetre.debut}T00:00:00Z`);

  if (Number.isNaN(depart)) {
    return [];
  }

  return Array.from({ length: Math.max(fenetre.jours, 1) }, (_, index) =>
    new Date(depart + index * MS_PAR_JOUR).toISOString().slice(0, 10)
  );
}

/** Décale la fenêtre de `pas` jours — négatif pour reculer. */
export function decaler(
  fenetre: FenetrePlanning,
  pas: number
): FenetrePlanning {
  const depart = Date.parse(`${fenetre.debut}T00:00:00Z`);

  if (Number.isNaN(depart)) {
    return fenetre;
  }

  return {
    ...fenetre,
    debut: new Date(depart + pas * MS_PAR_JOUR).toISOString().slice(0, 10)
  };
}

/** Nombre de jours entre deux jours `AAAA-MM-JJ` (b − a). */
function ecart(a: string, b: string): number {
  return Math.round(
    (Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / MS_PAR_JOUR
  );
}

/** Place une manifestation dans la grille, ou `null` si elle n'y paraît pas.
 *
 * Une manifestation qui déborde est **rognée**, pas écartée : elle commence
 * avant la fenêtre mais occupe bien les jours visibles, et le rognage est
 * signalé pour que la barre puisse le montrer. Sans ça, l'écran mentirait par
 * omission le lundi d'une manifestation commencée le vendredi.
 */
export function placer(
  manifestation: ManifestationPlanning,
  fenetre: FenetrePlanning
): Barre | null {
  const jours = Math.max(fenetre.jours, 1);
  const debut = jourDe(manifestation.date_debut);
  const fin = jourDe(manifestation.date_fin) || debut;

  if (!debut) {
    return null;
  }

  const depuisLeDebut = ecart(fenetre.debut, debut);
  const jusquALaFin = ecart(fenetre.debut, fin);

  if (Number.isNaN(depuisLeDebut) || Number.isNaN(jusquALaFin)) {
    return null;
  }

  // Entièrement avant ou entièrement après la fenêtre.
  if (jusquALaFin < 0 || depuisLeDebut > jours - 1) {
    return null;
  }

  const premiere = Math.max(depuisLeDebut, 0);
  const derniere = Math.min(jusquALaFin, jours - 1);

  return {
    manifestation,
    colonne: premiere + 1,
    largeur: Math.max(derniere - premiere + 1, 1),
    deborde_avant: depuisLeDebut < 0,
    deborde_apres: jusquALaFin > jours - 1
  };
}

/** Les barres de la fenêtre, triées par date de début puis par nom.
 *
 * Le tri est stable et indépendant de l'ordre d'arrivée de l'API : deux
 * chargements de la même fenêtre donnent le même planning.
 */
export function barres(
  manifestations: ManifestationPlanning[],
  fenetre: FenetrePlanning
): Barre[] {
  return manifestations
    .map((manifestation) => placer(manifestation, fenetre))
    .filter((barre): barre is Barre => barre !== null)
    .sort((a, b) => {
      if (a.colonne !== b.colonne) {
        return a.colonne - b.colonne;
      }

      return a.manifestation.nom.localeCompare(b.manifestation.nom, 'fr');
    });
}

/** Libellé court d'un jour : « lun. 15 ». */
export function libelleJour(jour: string, locale = 'fr-FR'): string {
  const date = new Date(`${jour}T12:00:00Z`);

  if (Number.isNaN(date.getTime())) {
    return jour;
  }

  return new Intl.DateTimeFormat(locale, {
    weekday: 'short',
    day: 'numeric',
    timeZone: 'UTC'
  }).format(date);
}

/** Vrai pour un samedi ou un dimanche — la grille les grise. */
export function estWeekEnd(jour: string): boolean {
  const date = new Date(`${jour}T12:00:00Z`);
  const numero = date.getUTCDay();

  return numero === 0 || numero === 6;
}

/** Couleurs de statut, alignées sur `STATUT_COULEURS` côté serveur. */
export const COULEUR_STATUT: Record<string, string> = {
  brouillon: 'gray',
  planifiee: 'blue',
  en_cours: 'green',
  terminee: 'dark',
  annulee: 'red'
};

/** Libellés des statuts : l'API rend le code, l'écran doit rendre du français.
 *
 * Miroir de `StatutManifestation` côté serveur. Un statut inconnu s'affiche
 * tel quel plutôt que vide — on préfère voir un code qu'une case blanche.
 */
export const LIBELLE_STATUT: Record<string, string> = {
  brouillon: 'Brouillon',
  planifiee: 'Planifiée',
  en_cours: 'En cours',
  terminee: 'Terminée',
  annulee: 'Annulée'
};

export function libelleStatut(code: string): string {
  return LIBELLE_STATUT[code] || code;
}

/** Avancement des livraisons, en texte court : « 2/5 livrés ». */
export function libelleLivraison(manifestation: ManifestationPlanning): string {
  const etat = manifestation.etat_livraison;

  if (!etat || etat.bons === 0) {
    return 'aucun bon';
  }

  return `${etat.livres}/${etat.bons} livré${etat.livres > 1 ? 's' : ''}`;
}

/** Clés d'URL du planning. Préfixées : le tableau de bord partage sa query
 * string entre tous les widgets montés. */
export const PLANNING_URL_KEYS = ['plan_vue', 'plan_debut', 'plan_jours'];

export function urlDuPlanning(
  vue: VuePlanning,
  fenetre: FenetrePlanning
): URLSearchParams {
  const params = new URLSearchParams();

  params.set('plan_vue', vue);
  params.set('plan_debut', fenetre.debut);

  if (fenetre.jours !== JOURS_PAR_DEFAUT) {
    params.set('plan_jours', String(fenetre.jours));
  }

  return params;
}

/** Relit l'état depuis l'URL, en se rabattant sur les valeurs par défaut. */
export function etatDepuisUrl(
  recherche: string,
  maintenant: Date = new Date()
): { vue: VuePlanning; fenetre: FenetrePlanning } {
  const params = new URLSearchParams(recherche);
  const vue = params.get('plan_vue') === 'liste' ? 'liste' : 'gantt';
  const debut = params.get('plan_debut');
  const jours = Number.parseInt(params.get('plan_jours') || '', 10);

  return {
    vue,
    fenetre: {
      debut: /^\d{4}-\d{2}-\d{2}$/.test(debut || '')
        ? (debut as string)
        : aujourdhui(maintenant),
      jours:
        Number.isFinite(jours) && jours > 0 && jours <= 92
          ? jours
          : JOURS_PAR_DEFAUT
    }
  };
}
