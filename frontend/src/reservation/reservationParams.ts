export interface ReservationFiltersState {
  search: string;
  statuts: string[];
  categories: number[];
  dateRange: [string | null, string | null];
}

export const DEFAULT_RESERVATION_FILTERS: ReservationFiltersState = {
  search: "",
  statuts: [],
  categories: [],
  dateRange: [null, null],
};

export function buildReservationQuery(
  filters: ReservationFiltersState,
): Record<string, string | string[]> {
  const params: Record<string, string | string[]> = {};

  if (filters.search.trim()) {
    params.search = filters.search.trim();
  }

  if (filters.statuts.length > 0) {
    params.statut = filters.statuts;
  }

  if (filters.categories.length > 0) {
    params.categories = filters.categories.join(",");
  }

  if (filters.dateRange[0]) {
    params.date_from = filters.dateRange[0];
  }

  if (filters.dateRange[1]) {
    params.date_to = filters.dateRange[1];
  }

  return params;
}

export function serializeReservationFilters(
  filters: ReservationFiltersState,
): string {
  const search = new URLSearchParams();

  if (filters.search.trim()) {
    search.set("q", filters.search.trim());
  }

  if (filters.statuts.length > 0) {
    search.set("statut", filters.statuts.join(","));
  }

  if (filters.categories.length > 0) {
    search.set("cat", filters.categories.join(","));
  }

  if (filters.dateRange[0]) {
    search.set("from", filters.dateRange[0]);
  }

  if (filters.dateRange[1]) {
    search.set("to", filters.dateRange[1]);
  }

  return search.toString();
}

function parseIntList(value: string | null): number[] {
  if (!value) {
    return [];
  }

  const seen = new Set<number>();

  for (const entry of value.split(",")) {
    const parsed = Number.parseInt(entry, 10);

    if (Number.isInteger(parsed)) {
      seen.add(parsed);
    }
  }

  return Array.from(seen);
}

function parseStringList(value: string | null): string[] {
  if (!value) {
    return [];
  }

  const seen = new Set<string>();

  for (const entry of value.split(",")) {
    const normalized = entry.trim();

    if (normalized) {
      seen.add(normalized);
    }
  }

  return Array.from(seen);
}

export function parseReservationFilters(
  query: string,
): ReservationFiltersState {
  const search = new URLSearchParams(query);
  const from = search.get("from");
  const to = search.get("to");

  return {
    search: search.get("q") ?? "",
    statuts: parseStringList(search.get("statut")),
    categories: parseIntList(search.get("cat")),
    dateRange: [from || null, to || null],
  };
}
