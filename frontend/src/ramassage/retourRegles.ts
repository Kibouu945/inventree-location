// Règles de saisie du retour de ramassage, hors React — donc testables.

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

/** Lignes qui déclarent plus de manquant qu'il n'est sorti. */
export function manquantExcessif(lignes: LigneSaisie[]): LigneSaisie[] {
  return lignes.filter(
    (ligne) => ligne.quantite_manquante > ligne.quantiteAttendue
  );
}

/** Lignes dont le total dépasse l'attendu. */
export function enSurplus(lignes: LigneSaisie[]): LigneSaisie[] {
  return lignes.filter((ligne) => totalSaisi(ligne) > ligne.quantiteAttendue);
}
