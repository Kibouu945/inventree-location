/**
 * Logique pure de la déclaration de retour d'une prestation (SCRUM-95).
 *
 * Calcule le statut de retour du bon (aucun / partiel / complet) à partir des
 * quantités demandées et rendues par ligne — réplique la règle serveur.
 */

export interface RetourLigneValues {
  id: number;
  quantite_demandee: number;
  quantite_rendue: number;
}

export type StatutRetour = 'aucun' | 'partiel' | 'complet';

export function computeStatutRetour(lignes: RetourLigneValues[]): StatutRetour {
  const totalDemandee = lignes.reduce(
    (sum, ligne) => sum + (ligne.quantite_demandee || 0),
    0
  );
  const totalRendue = lignes.reduce(
    (sum, ligne) =>
      sum + Math.min(ligne.quantite_rendue || 0, ligne.quantite_demandee || 0),
    0
  );

  if (totalDemandee <= 0 || totalRendue <= 0) {
    return 'aucun';
  }

  if (totalRendue >= totalDemandee) {
    return 'complet';
  }

  return 'partiel';
}

export interface RetourErrors {
  [ligneId: number]: string | undefined;
}

export function validateRetourLignes(
  lignes: RetourLigneValues[]
): RetourErrors {
  const errors: RetourErrors = {};

  for (const ligne of lignes) {
    if (ligne.quantite_rendue < 0) {
      errors[ligne.id] = 'La quantité rendue ne peut pas être négative.';
      continue;
    }

    if (ligne.quantite_rendue > ligne.quantite_demandee) {
      errors[ligne.id] =
        `La quantité rendue (${ligne.quantite_rendue}) ne peut pas dépasser la quantité demandée (${ligne.quantite_demandee}).`;
    }
  }

  return errors;
}

/**
 * Normalise les erreurs `lignes` renvoyées par le serveur.
 *
 * Deux formes coexistent : la vue renvoie un objet `{ "<id>": "message" }`,
 * mais une erreur de champ DRF (`quantite_rendue` non entier, par exemple)
 * arrive sous forme de *liste* alignée sur l'ordre envoyé. Rendue telle
 * quelle, cette liste d'objets était passée à React comme enfant et faisait
 * planter le widget.
 */
export function normalizeRetourErrors(
  data: unknown,
  envoyees: RetourLigneValues[]
): RetourErrors {
  const errors: RetourErrors = {};

  if (!data || typeof data !== 'object') {
    return errors;
  }

  const lignes = (data as { lignes?: unknown }).lignes;

  if (Array.isArray(lignes)) {
    lignes.forEach((entry, index) => {
      const ligne = envoyees[index];

      if (!ligne || !entry || typeof entry !== 'object') {
        return;
      }

      const messages = Object.values(entry as Record<string, unknown>)
        .flat()
        .map((message) => String(message));

      if (messages.length > 0) {
        errors[ligne.id] = messages.join(' ');
      }
    });

    return errors;
  }

  if (lignes && typeof lignes === 'object') {
    for (const [id, message] of Object.entries(
      lignes as Record<string, unknown>
    )) {
      errors[Number(id)] = Array.isArray(message)
        ? message.map(String).join(' ')
        : String(message);
    }
  }

  return errors;
}
