/**
 * Partage de la query string entre widgets du dashboard.
 *
 * Plusieurs widgets du plugin (Catalogue, Réservations, …) sont montés
 * simultanément sur `/web/home` et se synchronisent tous sur la même URL. Si
 * chacun réécrit la query string entière avec sa propre sérialisation, le
 * dernier à se synchroniser efface les filtres des autres — et deux widgets
 * qui utilisent la même clé pour des filtres différents se contaminent
 * mutuellement.
 *
 * Chaque widget ne réécrit donc que les clés qu'il possède et préserve le
 * reste.
 */

/** Réécrit dans l'URL les seules clés possédées par l'appelant. */
export function syncOwnedParams(
  isOwnKey: (key: string) => boolean,
  own: URLSearchParams
) {
  if (typeof window === 'undefined' || !window.history?.replaceState) {
    return;
  }

  const merged = new URLSearchParams(window.location.search);

  for (const key of Array.from(merged.keys())) {
    if (isOwnKey(key)) {
      merged.delete(key);
    }
  }

  for (const [key, value] of own) {
    merged.append(key, value);
  }

  const query = merged.toString();
  window.history.replaceState(
    null,
    '',
    query ? `?${query}` : window.location.pathname
  );
}

/** Construit un prédicat de possession à partir d'une liste de clés. */
export function ownsKeys(keys: string[]): (key: string) => boolean {
  const owned = new Set(keys);
  return (key) => owned.has(key);
}
