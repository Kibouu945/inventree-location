// Types du planning (maquette « Planning » du cahier des charges).
//
// Miroir de `ManifestationSerializer` et de `PrestationSerializer` : on ne type
// que ce que l'écran affiche.

/** Avancement des livraisons : combien de bons sont sortis, sur combien. */
export interface EtatLivraison {
	bons: number;
	livres: number;
	a_livrer: number;
}

/** Ce qui se pose sur la grille : un intervalle de jours qui porte un nom.
 *
 * Le planning se lit à deux mailles — la manifestation en barre, ses
 * prestations en sous-lignes — et les deux se placent exactement de la même
 * façon. C'est ce que ce type dit, et c'est pourquoi `placer` est générique.
 */
export interface LignePlanning {
	id: number;
	nom: string;
	/** `AAAA-MM-JJ HH:MM` — une chaîne, jamais un `Date` : le serveur formate. */
	date_debut: string;
	date_fin: string;
	/** Volume d'objets engagés, annulés exclus. */
	quantite_totale: number;
	etat_livraison: EtatLivraison;
}

/** Une manifestation, telle que la lit le planning. */
export interface ManifestationPlanning extends LignePlanning {
	statut: string;
	statut_effectif: string;
	/** Couleur choisie par le gestionnaire, `#rrggbb`. */
	couleur: string;
	client_nom: string;
	organisateur_nom: string;
	contact_telephone: string;
	/** Nombre **total** de prestations, y compris hors de la fenêtre affichée. */
	prestations_count: number;
}

/** Une prestation, telle que la lit le planning déplié.
 *
 * Son volume et son avancement sont la même mesure que ceux de sa
 * manifestation, un cran plus bas : les sous-lignes d'une barre la totalisent.
 */
export interface PrestationPlanning extends LignePlanning {
	/** Identifiant de la manifestation parente — la barre sous laquelle ranger. */
	manifestation: number;
	statut: string;
	/** `null` tant que la prestation est un brouillon sans lieu. */
	lieu_detail: { nom: string } | null;
}

/** La bascule de la maquette. */
export type VuePlanning = "gantt" | "liste";

/** Ce qu'on regarde — nommé comme on en parle, pas comme c'est découpé.
 *
 * Le grain des colonnes se déduit de l'échelle : une journée tient en une
 * colonne, une semaine en sept, un mois en autant de jours qu'il en a, une
 * année en douze mois. Il ne se choisit pas séparément.
 */
export type EchellePlanning = "jour" | "semaine" | "mois" | "annee";

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

/** Placement d'une barre dans la grille : colonne de départ et largeur.
 *
 * Générique sur ce qu'elle place : une manifestation pour une barre, une
 * prestation pour une sous-ligne.
 */
export interface Barre<T extends LignePlanning = ManifestationPlanning> {
	sujet: T;
	/** Index de la colonne de départ, 1 pour la première. */
	colonne: number;
	/** Largeur en nombre de colonnes, au moins 1. */
	largeur: number;
	/** Vrai si le sujet commence avant la fenêtre. */
	deborde_avant: boolean;
	/** Vrai s'il se termine après. */
	deborde_apres: boolean;
}
