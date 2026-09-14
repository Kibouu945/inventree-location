// Règles de saisie du retour de ramassage, hors React — donc testables.
//
// R36, affinée en recette le 11/09 : **ce qui revient n'a pas de plafond**. Du
// matériel circule d'un lieu à l'autre, et douze objets retrouvés pour dix
// sortis est un cas légitime ; refuser la saisie empêche le livreur de
// déclarer le contenu réel de son camion, et l'écart disparaît au lieu de se
// voir dans les chiffres.
//
// Le manquant, lui, reste borné : on ne perd pas ce qui n'est pas parti.
//
// Le serveur applique déjà exactement cette règle (`sav.py`), et son
// commentaire dit « on signale à l'écran, on ne bloque pas ». L'écran bloquait
// quand même le surplus, depuis la levée du plafond côté serveur : une règle
// et son contraire dans le même produit.

/** Ce qu'il faut d'une ligne pour juger la saisie ; le reste ne la regarde pas. */
export interface LigneSaisie {
	partNom: string;
	quantiteAttendue: number;
	quantite_ramassee: number;
	quantite_sav: number;
	quantite_detruite: number;
	quantite_manquante: number;
}

/** Tout ce qui a été déclaré sur la ligne, quel qu'en soit l'état. */
export function totalSaisi(ligne: LigneSaisie): number {
	return (
		ligne.quantite_ramassee +
		ligne.quantite_sav +
		ligne.quantite_detruite +
		ligne.quantite_manquante
	);
}

/**
 * Lignes qui déclarent plus de manquant qu'il n'est sorti.
 *
 * C'est le **seul** refus : le serveur répond 400 sur ces lignes, autant le
 * dire avant l'envoi plutôt que de laisser le livreur buter dessus.
 */
export function manquantExcessif(lignes: LigneSaisie[]): LigneSaisie[] {
	return lignes.filter(
		(ligne) => ligne.quantite_manquante > ligne.quantiteAttendue,
	);
}

/**
 * Lignes dont le total dépasse l'attendu.
 *
 * Se signale — le magasinier doit savoir qu'il compte plus que ce qui est
 * parti — mais ne bloque jamais : c'est le cas que la recette demandait
 * explicitement d'autoriser.
 */
export function enSurplus(lignes: LigneSaisie[]): LigneSaisie[] {
	return lignes.filter((ligne) => totalSaisi(ligne) > ligne.quantiteAttendue);
}
