// Logique du planning, sans React : colonnes, placement des barres, libellés.
//
// Séparée du rendu pour être testable — c'est le pendant côté front de ce que
// `execution.py` est à `views.py`.
//
// **Tout se calcule en UTC**, à partir de chaînes `AAAA-MM-JJ`. Construire une
// date depuis une chaîne sans fuseau la fait interpréter en heure locale du
// navigateur : la France change d'heure le 25 octobre 2026, en pleine période
// de soutenance, et une arithmétique locale y saute ou double un jour.

import type {
  Barre,
  Colonne,
  EchellePlanning,
  FenetrePlanning,
  LignePlanning,
  PrestationPlanning,
  VuePlanning
} from './types';

const MS_PAR_JOUR = 24 * 60 * 60 * 1000;

/** Largeur **minimale** d'une colonne, en pixels, selon l'échelle.
 *
 * Un mois tient trente et une colonnes : elles doivent pouvoir rester
 * étroites. Une année n'en a que douze, elles portent « janv. 26 » et ne
 * descendent pas sous la largeur du libellé. En dessous de ces valeurs, la
 * grille défile horizontalement plutôt que d'écraser les en-têtes.
 */
export const LARGEUR_MIN_COLONNE: Record<EchellePlanning, number> = {
  jour: 420,
  semaine: 92,
  mois: 34,
  annee: 74
};

/** Hauteurs de la grille, en pixels. Une barre respire dans sa ligne. */
export const HAUTEUR = {
  ligne: 30,
  barre: 24,
  sousLigne: 26,
  sousBarre: 18
};

/** Largeur de la colonne des noms, à gauche de la grille. */
export const LARGEUR_NOMS = 210;

/** Largeur réelle d'une colonne : la grille occupe la place qu'on lui donne.
 *
 * À largeur fixe, un planning au mois laissait un tiers du panneau vide et
 * tassait trente jours dans la moitié gauche. On répartit donc la place
 * disponible entre les colonnes, sans jamais descendre sous le minimum de
 * l'échelle — c'est alors le conteneur qui défile.
 *
 * `largeurDisponible` vaut 0 avant la première mesure du conteneur : on rend
 * le minimum, et la mesure suivante élargit.
 */
export function largeurDeColonne(
  echelle: EchellePlanning,
  nombreDeColonnes: number,
  largeurDisponible: number
): number {
  const minimum = LARGEUR_MIN_COLONNE[echelle];

  if (nombreDeColonnes <= 0 || largeurDisponible <= 0) {
    return minimum;
  }

  return Math.max(minimum, Math.floor(largeurDisponible / nombreDeColonnes));
}

export const ECHELLES: Array<{ value: EchellePlanning; label: string }> = [
  { value: 'jour', label: 'Jour' },
  { value: 'semaine', label: 'Semaine' },
  { value: 'mois', label: 'Mois' },
  { value: 'annee', label: 'Année' }
];

/** Le jour d'une date serveur (`AAAA-MM-JJ HH:MM`), sans son heure. */
export function jourDe(horodatage: string): string {
  return (horodatage || '').slice(0, 10);
}

/** Aujourd'hui au format `AAAA-MM-JJ`, dans le fuseau du poste. */
export function aujourdhui(maintenant: Date = new Date()): string {
  const mois = String(maintenant.getMonth() + 1).padStart(2, '0');
  const jour = String(maintenant.getDate()).padStart(2, '0');
  return `${maintenant.getFullYear()}-${mois}-${jour}`;
}

function enDate(jour: string): Date {
  return new Date(`${jour}T00:00:00Z`);
}

function enJour(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function ajouterJours(jour: string, nombre: number): string {
  return enJour(new Date(enDate(jour).getTime() + nombre * MS_PAR_JOUR));
}

function estLisible(jour: string): boolean {
  return (
    /^\d{4}-\d{2}-\d{2}$/.test(jour) && !Number.isNaN(enDate(jour).getTime())
  );
}

/** Le lundi de la semaine d'un jour donné. */
export function lundiDeLaSemaine(jour: string): string {
  // `getUTCDay()` rend 0 pour dimanche : on le ramène en fin de semaine.
  const rang = (enDate(jour).getUTCDay() + 6) % 7;

  return ajouterJours(jour, -rang);
}

/** Le premier jour du mois d'un jour donné. */
export function premierDuMois(jour: string): string {
  return `${jour.slice(0, 7)}-01`;
}

/** Nombre de jours du mois d'un jour donné. */
export function joursDuMois(jour: string): number {
  const date = enDate(premierDuMois(jour));

  return new Date(
    Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0)
  ).getUTCDate();
}

/** Fenêtre par défaut d'une échelle : la période qui contient aujourd'hui. */
export function fenetreParDefaut(
  echelle: EchellePlanning,
  maintenant: Date = new Date()
): FenetrePlanning {
  return { echelle, ancre: aujourdhui(maintenant) };
}

/** Premier jour de la période regardée. */
export function debutDeLaFenetre(fenetre: FenetrePlanning): string {
  if (!estLisible(fenetre.ancre)) {
    return aujourdhui();
  }

  if (fenetre.echelle === 'jour') {
    return fenetre.ancre;
  }

  if (fenetre.echelle === 'semaine') {
    return lundiDeLaSemaine(fenetre.ancre);
  }

  if (fenetre.echelle === 'mois') {
    return premierDuMois(fenetre.ancre);
  }

  return `${fenetre.ancre.slice(0, 4)}-01-01`;
}

/** Les colonnes de la fenêtre, de la première à la dernière.
 *
 * Le nombre se déduit de l'échelle : sept jours pour une semaine, la longueur
 * réelle du mois pour un mois — février en a vingt-huit ou vingt-neuf, et une
 * grille fixe de trente et une colonnes afficherait trois jours fantômes.
 */
export function colonnes(fenetre: FenetrePlanning): Colonne[] {
  const debut = debutDeLaFenetre(fenetre);

  if (fenetre.echelle === 'annee') {
    const annee = Number.parseInt(debut.slice(0, 4), 10);

    return Array.from({ length: 12 }, (_, index) => {
      const premier = enJour(new Date(Date.UTC(annee, index, 1)));
      const dernier = enJour(new Date(Date.UTC(annee, index + 1, 0)));

      return {
        debut: premier,
        fin: dernier,
        libelle: libelleMois(premier),
        weekend: false
      };
    });
  }

  const nombre =
    fenetre.echelle === 'jour'
      ? 1
      : fenetre.echelle === 'semaine'
        ? 7
        : joursDuMois(debut);

  return Array.from({ length: nombre }, (_, index) => {
    const jour = ajouterJours(debut, index);

    return {
      debut: jour,
      fin: jour,
      libelle:
        fenetre.echelle === 'mois' ? jour.slice(8, 10) : libelleJour(jour),
      weekend: estWeekEnd(jour)
    };
  });
}

/** Déplace la fenêtre d'une période entière — négatif pour reculer. */
export function decaler(
  fenetre: FenetrePlanning,
  pas: number
): FenetrePlanning {
  const debut = debutDeLaFenetre(fenetre);

  if (fenetre.echelle === 'jour') {
    return { ...fenetre, ancre: ajouterJours(debut, pas) };
  }

  if (fenetre.echelle === 'semaine') {
    return { ...fenetre, ancre: ajouterJours(debut, pas * 7) };
  }

  const date = enDate(debut);

  if (fenetre.echelle === 'mois') {
    return {
      ...fenetre,
      ancre: enJour(
        new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + pas, 1))
      )
    };
  }

  return {
    ...fenetre,
    ancre: enJour(new Date(Date.UTC(date.getUTCFullYear() + pas, 0, 1)))
  };
}

/** Bornes de la fenêtre, telles qu'on les passe au serveur. */
export function bornes(fenetre: FenetrePlanning): { from: string; to: string } {
  const grille = colonnes(fenetre);

  return { from: grille[0].debut, to: grille[grille.length - 1].fin };
}

/** Libellé de la période affichée : « 14 – 20 sept. 2026 », « Septembre 2026 ». */
export function libellePeriode(
  fenetre: FenetrePlanning,
  locale = 'fr-FR'
): string {
  const grille = colonnes(fenetre);
  const debut = new Date(`${grille[0].debut}T12:00:00Z`);
  const fin = new Date(`${grille[grille.length - 1].fin}T12:00:00Z`);

  if (fenetre.echelle === 'annee') {
    return grille[0].debut.slice(0, 4);
  }

  if (fenetre.echelle === 'jour') {
    const rendu = new Intl.DateTimeFormat(locale, {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      year: 'numeric',
      timeZone: 'UTC'
    }).format(debut);

    return rendu.charAt(0).toUpperCase() + rendu.slice(1);
  }

  if (fenetre.echelle === 'mois') {
    const rendu = new Intl.DateTimeFormat(locale, {
      month: 'long',
      year: 'numeric',
      timeZone: 'UTC'
    }).format(debut);

    return rendu.charAt(0).toUpperCase() + rendu.slice(1);
  }

  const jourEtMois = new Intl.DateTimeFormat(locale, {
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC'
  });

  return `${jourEtMois.format(debut)} – ${jourEtMois.format(fin)} ${fin.getUTCFullYear()}`;
}

/** Place une manifestation ou une prestation dans la grille, ou `null`.
 *
 * Le calcul est le même aux quatre échelles et aux deux mailles : la première
 * colonne qui se termine après le début du sujet, la dernière qui commence
 * avant sa fin. Un sujet qui déborde est **rogné**, pas écarté, et le rognage
 * est signalé — sinon l'écran mentirait par omission le lundi d'une
 * manifestation commencée le vendredi.
 */
export function placer<T extends LignePlanning>(
  sujet: T,
  grille: Colonne[]
): Barre<T> | null {
  if (grille.length === 0) {
    return null;
  }

  const debut = jourDe(sujet.date_debut);
  const fin = jourDe(sujet.date_fin) || debut;

  if (!debut) {
    return null;
  }

  const premiere = grille.findIndex((colonne) => colonne.fin >= debut);
  let derniere = -1;

  for (let index = grille.length - 1; index >= 0; index -= 1) {
    if (grille[index].debut <= fin) {
      derniere = index;
      break;
    }
  }

  // Entièrement après la fenêtre, ou entièrement avant.
  if (premiere === -1 || derniere === -1 || premiere > derniere) {
    return null;
  }

  return {
    sujet,
    colonne: premiere + 1,
    largeur: derniere - premiere + 1,
    deborde_avant: debut < grille[0].debut,
    deborde_apres: fin > grille[grille.length - 1].fin
  };
}

/** Les barres de la fenêtre, triées par colonne puis par nom.
 *
 * Le tri est stable et indépendant de l'ordre d'arrivée de l'API : deux
 * chargements de la même fenêtre donnent le même planning.
 */
export function barres<T extends LignePlanning>(
  sujets: T[],
  grille: Colonne[]
): Barre<T>[] {
  return sujets
    .map((sujet) => placer(sujet, grille))
    .filter((barre): barre is Barre<T> => barre !== null)
    .sort((a, b) => {
      if (a.colonne !== b.colonne) {
        return a.colonne - b.colonne;
      }

      return a.sujet.nom.localeCompare(b.sujet.nom, 'fr');
    });
}

/** Les prestations de la fenêtre, rangées sous leur manifestation.
 *
 * Le serveur les rend à plat, triées par date ; l'écran les affiche sous leur
 * barre. Une prestation ne peut pas sortir des dates de sa manifestation, donc
 * toute prestation de la fenêtre a bien sa barre affichée au-dessus d'elle.
 */
export function parManifestation(
  prestations: PrestationPlanning[]
): Map<number, PrestationPlanning[]> {
  const rangees = new Map<number, PrestationPlanning[]>();

  for (const prestation of prestations) {
    const deja = rangees.get(prestation.manifestation);

    if (deja) {
      deja.push(prestation);
    } else {
      rangees.set(prestation.manifestation, [prestation]);
    }
  }

  return rangees;
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

/** Libellé d'une colonne mois : « sept. 26 ». */
export function libelleMois(premier: string, locale = 'fr-FR'): string {
  const date = new Date(`${premier}T12:00:00Z`);

  if (Number.isNaN(date.getTime())) {
    return premier;
  }

  return new Intl.DateTimeFormat(locale, {
    month: 'short',
    year: '2-digit',
    timeZone: 'UTC'
  }).format(date);
}

/** Vrai pour un samedi ou un dimanche — la grille les grise. */
export function estWeekEnd(jour: string): boolean {
  const numero = enDate(jour).getUTCDay();

  return numero === 0 || numero === 6;
}

/** Vrai si la colonne contient aujourd'hui — elle est alors surlignée. */
export function contientAujourdhui(
  colonne: Colonne,
  jour: string = aujourdhui()
): boolean {
  return colonne.debut <= jour && jour <= colonne.fin;
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
export function libelleLivraison(sujet: LignePlanning): string {
  const etat = sujet.etat_livraison;

  if (!etat || etat.bons === 0) {
    return 'aucun bon';
  }

  return `${etat.livres}/${etat.bons} livré${etat.livres > 1 ? 's' : ''}`;
}

/** Clés d'URL du planning. Préfixées : le tableau de bord partage sa query
 * string entre tous les widgets montés. */
export const PLANNING_URL_KEYS = [
  'plan_vue',
  'plan_echelle',
  'plan_date',
  'plan_ouvertes'
];

/** Les manifestations dépliées, dans l'URL : « 3,7 ».
 *
 * Triées et sans doublon, pour que deux dépliages faits dans un ordre
 * différent donnent la même URL — sinon l'historique du navigateur se remplit
 * de variantes de la même vue.
 */
export function ouvertesEnTexte(ouvertes: Iterable<number>): string {
  return Array.from(new Set(ouvertes))
    .sort((a, b) => a - b)
    .join(',');
}

/** Relit la liste des dépliées, en écartant tout ce qui n'est pas un identifiant. */
export function ouvertesDepuisTexte(valeur: string | null): Set<number> {
  return new Set(
    (valeur || '')
      .split(',')
      .map((morceau) => Number.parseInt(morceau, 10))
      .filter((id) => Number.isInteger(id) && id > 0)
  );
}

export function urlDuPlanning(
  vue: VuePlanning,
  fenetre: FenetrePlanning,
  ouvertes: Iterable<number> = []
): URLSearchParams {
  const params = new URLSearchParams();

  params.set('plan_vue', vue);
  params.set('plan_echelle', fenetre.echelle);
  params.set('plan_date', debutDeLaFenetre(fenetre));

  const depliees = ouvertesEnTexte(ouvertes);

  // Rien de déplié : pas de clé. Une clé vide traînerait dans l'URL de tous
  // les autres widgets du tableau de bord.
  if (depliees) {
    params.set('plan_ouvertes', depliees);
  }

  return params;
}

function echelleValide(valeur: string | null): EchellePlanning {
  return valeur === 'jour' || valeur === 'semaine' || valeur === 'annee'
    ? valeur
    : 'mois';
}

/** Relit l'état depuis l'URL, en se rabattant sur les valeurs par défaut. */
export function etatDepuisUrl(
  recherche: string,
  maintenant: Date = new Date()
): { vue: VuePlanning; fenetre: FenetrePlanning; ouvertes: Set<number> } {
  const params = new URLSearchParams(recherche);
  const vue = params.get('plan_vue') === 'liste' ? 'liste' : 'gantt';
  const echelle = echelleValide(params.get('plan_echelle'));
  const date = params.get('plan_date') || '';

  return {
    vue,
    fenetre: {
      echelle,
      ancre: estLisible(date) ? date : aujourdhui(maintenant)
    },
    ouvertes: ouvertesDepuisTexte(params.get('plan_ouvertes'))
  };
}
