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

/** Fenêtre affichée, en nombre de jours à partir du premier. */
export interface FenetrePlanning {
  /** Premier jour affiché, `AAAA-MM-JJ`. */
  debut: string;
  /** Nombre de jours de la fenêtre. */
  jours: number;
}

/** Placement d'une barre dans la grille : colonne de départ et largeur. */
export interface Barre {
  manifestation: ManifestationPlanning;
  /** Colonne de départ, 1 pour le premier jour de la fenêtre. */
  colonne: number;
  /** Largeur en nombre de colonnes, au moins 1. */
  largeur: number;
  /** Vrai si la manifestation commence avant la fenêtre. */
  deborde_avant: boolean;
  /** Vrai si elle se termine après. */
  deborde_apres: boolean;
}
