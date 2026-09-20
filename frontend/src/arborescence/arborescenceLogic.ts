// Règles de l'arborescence qui ne tiennent pas à React — donc testables.
//
// L'arbre va du client aux articles, et deux appels parlent de la même
// collection de manifestations : le repérage de la recherche, qui cherche à
// travers tout l'arbre, et le dépliage d'un client, qui n'en veut qu'une
// branche. C'est leur accord qui vit ici.

/** Ce qu'il faut d'une manifestation pour savoir chez quel client la ranger. */
export interface ManifestationRangeable {
  client: number;
}

/** Filtres de l'appel manifestations, écrits une seule fois.
 *
 * Le repérage et le dépliage interrogent la même collection. Filtrer
 * différemment les ferait mentir l'un sur l'autre : un client remonterait à la
 * recherche, puis s'ouvrirait sur « aucune manifestation ». D'où la fonction
 * commune — `clientId` omis donne la portée de l'arbre entier.
 */
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

/** Les clients que la recherche a touchés, dédoublonnés.
 *
 * Plusieurs manifestations d'un même client ne le font remonter qu'une fois.
 */
export function clientsDuReperage(
  manifestations: ManifestationRangeable[]
): Set<number> {
  return new Set(manifestations.map((manifestation) => manifestation.client));
}
