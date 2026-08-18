/**
 * Logique pure du check-in retour (SCRUM-94).
 *
 * Réplique côté client la règle serveur : somme(ok + manquant + cassé)
 * doit égaler la quantité demandée pour chaque ligne.
 */

export interface CheckinLigneValues {
  id: number;
  quantite_demandee: number;
  ok: number;
  manquant: number;
  casse: number;
  commentaire: string;
}

export interface CheckinErrors {
  [ligneId: number]: string | undefined;
}

export function checkinLigneTotal(ligne: CheckinLigneValues): number {
  return (ligne.ok || 0) + (ligne.manquant || 0) + (ligne.casse || 0);
}

export function validateCheckinLignes(
  lignes: CheckinLigneValues[]
): CheckinErrors {
  const errors: CheckinErrors = {};

  for (const ligne of lignes) {
    const total = checkinLigneTotal(ligne);

    if (total !== ligne.quantite_demandee) {
      errors[ligne.id] =
        `La somme OK + manquant + cassé (${total}) doit égaler la quantité demandée (${ligne.quantite_demandee}).`;
    }
  }

  return errors;
}

export function isCheckinValid(lignes: CheckinLigneValues[]): boolean {
  return Object.keys(validateCheckinLignes(lignes)).length === 0;
}
