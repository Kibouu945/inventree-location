export type RamassageViewMode = "hierarchique" | "liste";

export interface RamassageFiltersState {
	search: string;
	lieu: string;
	statuts: string[];
	dateRange: [string | null, string | null];
	page: number;
	viewMode?: RamassageViewMode;
}

export const RAMASSAGE_PAGE_SIZE = 20;

export const DEFAULT_RAMASSAGE_FILTERS: RamassageFiltersState = {
	search: "",
	lieu: "",
	statuts: [],
	dateRange: [null, null],
	page: 1,
	viewMode: "hierarchique",
};

export const RAMASSAGE_URL_KEYS = [
	"ram_q",
	"ram_lieu",
	"ram_statut",
	"ram_from",
	"ram_to",
	"ram_page",
	"ram_view",
];

export function buildRamassageQuery(
	filters: RamassageFiltersState,
): Record<string, string | string[]> {
	const params: Record<string, string | string[]> = {
		page: String(filters.page),
		page_size: String(RAMASSAGE_PAGE_SIZE),
	};

	if (filters.search.trim()) {
		params.search = filters.search.trim();
	}

	if (filters.lieu.trim()) {
		params.lieu = filters.lieu.trim();
	}

	if (filters.statuts.length > 0) {
		params.statut = filters.statuts;
	}

	if (filters.dateRange[0]) {
		params.date_from = filters.dateRange[0];
	}

	if (filters.dateRange[1]) {
		params.date_to = filters.dateRange[1];
	}

	return params;
}

export function serializeRamassageFilters(
	filters: RamassageFiltersState,
): string {
	const search = new URLSearchParams();

	if (filters.search.trim()) {
		search.set("ram_q", filters.search.trim());
	}

	if (filters.lieu.trim()) {
		search.set("ram_lieu", filters.lieu.trim());
	}

	if (filters.statuts.length > 0) {
		search.set("ram_statut", filters.statuts.join(","));
	}

	if (filters.dateRange[0]) {
		search.set("ram_from", filters.dateRange[0]);
	}

	if (filters.dateRange[1]) {
		search.set("ram_to", filters.dateRange[1]);
	}

	if (filters.page !== DEFAULT_RAMASSAGE_FILTERS.page) {
		search.set("ram_page", String(filters.page));
	}

	if (filters.viewMode !== DEFAULT_RAMASSAGE_FILTERS.viewMode) {
		search.set("ram_view", filters.viewMode);
	}

	return search.toString();
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

export function parseRamassageFilters(query: string): RamassageFiltersState {
	const search = new URLSearchParams(query);
	const from = search.get("ram_from");
	const to = search.get("ram_to");
	const page = Number.parseInt(search.get("ram_page") ?? "1", 10);
	const viewMode =
		search.get("ram_view") === "liste" ? "liste" : "hierarchique";

	return {
		search: search.get("ram_q") ?? "",
		lieu: search.get("ram_lieu") ?? "",
		statuts: parseStringList(search.get("ram_statut")),
		dateRange: [from || null, to || null],
		page: Number.isInteger(page) && page > 0 ? page : 1,
		viewMode,
	};
}

/** Nombre total de pages pour un compte donné. */
export function totalRamassagePages(count: number): number {
	return Math.max(1, Math.ceil(count / RAMASSAGE_PAGE_SIZE));
}
