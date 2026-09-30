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

/**
 * Les listes séparées par des virgules, dédoublonnées.
 *
 * L'URL est éditable à la main et partagée entre widgets : une entrée vide ou
 * répétée ne doit pas se retrouver dans le filtre.
 */
export function parseStringList(value: string | null): string[] {
  if (!value) {
    return [];
  }

  const seen = new Set<string>();

  for (const entry of value.split(',')) {
    const normalized = entry.trim();

    if (normalized) {
      seen.add(normalized);
    }
  }

  return Array.from(seen);
}

/** Même chose pour des identifiants : ce qui n'est pas un entier est écarté. */
export function parseIntList(value: string | null): number[] {
  if (!value) {
    return [];
  }

  const seen = new Set<number>();

  for (const entry of value.split(',')) {
    const parsed = Number.parseInt(entry, 10);

    if (Number.isInteger(parsed)) {
      seen.add(parsed);
    }
  }

  return Array.from(seen);
}

/** Filtre « Virtuel » : une valeur inconnue vaut « pas de filtre ». */
export function parseVirtuel(value: string | null): string | null {
  return value === 'oui' || value === 'non' ? value : null;
}

/** Nombre de pages pour un compte donné, jamais moins d'une. */
export function pageCount(count: number, pageSize: number): number {
  return Math.max(1, Math.ceil(count / pageSize));
}
