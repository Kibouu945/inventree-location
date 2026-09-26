// Règles de l'arborescence qui ne tiennent pas à React — donc testables.

/** Ce qu'il faut d'une manifestation pour savoir chez quel client la ranger. */
export interface ManifestationRangeable {
  client: number;
}

/** Le repérage et le dépliage interrogent la même collection. */
export function filtresManifestations(
  recherche: string,
  periode: string,
  clientId?: number
): Record<string, string> {
  const valeurs: Record<string, string> = {};

  if (clientId !== undefined) {
    valeurs.client = String(clientId);
  }

  if (recherche.trim()) {
    valeurs.search = recherche.trim();
  }

  // « Tout » n'est pas un filtre : l'absence du paramètre vaut toute période.
  if (periode === 'futur' || periode === 'passe') {
    valeurs.periode = periode;
  }

  return valeurs;
}

/**
 * Plusieurs manifestations d'un même client ne le font remonter qu'une fois.
 */
export function clientsDuReperage(
  manifestations: ManifestationRangeable[]
): Set<number> {
  return new Set(manifestations.map((manifestation) => manifestation.client));
}
