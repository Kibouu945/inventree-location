// Types du planning (maquette « Planning » du cahier des charges).
//
// Miroir de `ManifestationSerializer` : on ne type que ce que l'écran affiche.

/** Avancement des livraisons d'une manifestation. */
export interface EtatLivraison {
  bons: number;
  livres: number;
  a_livrer: number;
}

/** Une manifestation, telle que la lit le planning. */
export interface ManifestationPlanning {
  id: number;
  nom: string;
  /** `AAAA-MM-JJ HH:MM` — une chaîne, jamais un `Date` : le serveur formate. */
  date_debut: string;
  date_fin: string;
  statut: string;
  statut_effectif: string;
  /** Couleur choisie par le gestionnaire, `#rrggbb`. */
  couleur: string;
  client_nom: string;
  organisateur_nom: string;
  contact_telephone: string;
  quantite_totale: number;
  etat_livraison: EtatLivraison;
  prestations_count: number;
}

/** La bascule de la maquette. */
export type VuePlanning = 'gantt' | 'liste';

/** Ce qu'on regarde — nommé comme on en parle, pas comme c'est découpé.
 *
 * Le grain des colonnes se déduit de l'échelle : une journée tient en une
 * colonne, une semaine en sept, un mois en autant de jours qu'il en a, une
 * année en douze mois. Il ne se choisit pas séparément.
 */
export type EchellePlanning = 'jour' | 'semaine' | 'mois' | 'annee';

/** Fenêtre affichée : une échelle et un point d'ancrage.
 *
 * Le nombre de colonnes n'est pas stocké — il se déduit : sept pour une
 * semaine, la longueur du mois pour un mois, douze pour une année. Le stocker
 * autoriserait un février de trente-et-un jours.
 */
export interface FenetrePlanning {
  echelle: EchellePlanning;
  /** Un jour de la période regardée, `AAAA-MM-JJ`. */
  ancre: string;
}

/** Une colonne de la grille — un jour, ou un mois à l'échelle de l'année. */
export interface Colonne {
  /** Premier jour couvert, `AAAA-MM-JJ`. */
  debut: string;
  /** Dernier jour couvert, inclus. */
  fin: string;
  /** Ce qui s'écrit en en-tête : « lundi 15 », « lun. 15 », « 15 », « janv. 26 ». */
  libelle: string;
  /** Vrai pour un samedi ou un dimanche. */
  weekend: boolean;
}

/** Placement d'une barre dans la grille : colonne de départ et largeur. */
export interface Barre {
  manifestation: ManifestationPlanning;
  /** Index de la colonne de départ, 1 pour la première. */
  colonne: number;
  /** Largeur en nombre de colonnes, au moins 1. */
  largeur: number;
  /** Vrai si la manifestation commence avant la fenêtre. */
  deborde_avant: boolean;
  /** Vrai si elle se termine après. */
  deborde_apres: boolean;
}
