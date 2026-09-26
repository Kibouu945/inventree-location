/** Partage de la query string entre widgets du dashboard. */

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
