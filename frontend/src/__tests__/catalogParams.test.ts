import { describe, expect, it } from "vitest";

import {
	buildCatalogQuery,
	CATALOG_PAGE_SIZE,
	DEFAULT_FILTERS,
	libelleColonneDisponibilite,
	parseFilters,
	serializeFilters,
	totalPages,
} from "../catalog/catalogParams";

describe("buildCatalogQuery", () => {
	it("inclut toujours page et page_size", () => {
		const params = buildCatalogQuery(DEFAULT_FILTERS);
		expect(params.page).toBe("1");
		expect(params.page_size).toBe(String(CATALOG_PAGE_SIZE));
	});

	it("n'envoie pas rentable quand louable (défaut)", () => {
		const params = buildCatalogQuery(DEFAULT_FILTERS);
		expect(params.rentable).toBeUndefined();
	});

	it("envoie rentable=all et rentable=false", () => {
		expect(
			buildCatalogQuery({ ...DEFAULT_FILTERS, rentable: "all" }).rentable,
		).toBe("all");
		expect(
			buildCatalogQuery({ ...DEFAULT_FILTERS, rentable: false }).rentable,
		).toBe("false");
	});

	it("sérialise les catégories en liste séparée par des virgules", () => {
		const params = buildCatalogQuery({
			...DEFAULT_FILTERS,
			categories: [3, 7],
		});
		expect(params.categories).toBe("3,7");
	});

	it("trim la recherche et omet les valeurs vides", () => {
		expect(buildCatalogQuery({ ...DEFAULT_FILTERS, search: "  " }).search).toBe(
			undefined,
		);
		expect(
			buildCatalogQuery({ ...DEFAULT_FILTERS, search: "  tente " }).search,
		).toBe("tente");
	});

	it("envoie la période quand elle est renseignée", () => {
		const params = buildCatalogQuery({
			...DEFAULT_FILTERS,
			dateDebut: "2026-09-10",
			dateFin: "2026-09-14",
		});
		expect(params.date_debut).toBe("2026-09-10");
		expect(params.date_fin).toBe("2026-09-14");
	});

	it("n'envoie aucune date par défaut — le serveur répond pour aujourd'hui", () => {
		const params = buildCatalogQuery(DEFAULT_FILTERS);
		expect(params.date_debut).toBeUndefined();
		expect(params.date_fin).toBeUndefined();
	});

	it("accepte une borne seule", () => {
		const params = buildCatalogQuery({
			...DEFAULT_FILTERS,
			dateDebut: "2026-09-10",
		});
		expect(params.date_debut).toBe("2026-09-10");
		expect(params.date_fin).toBeUndefined();
	});
});

describe("libelleColonneDisponibilite", () => {
	it("sans période, parle de la journée courante", () => {
		expect(libelleColonneDisponibilite(null, null)).toBe(
			"Disponible aujourd'hui",
		);
	});

	it("nomme la période demandée", () => {
		expect(libelleColonneDisponibilite("2026-09-10", "2026-09-14")).toBe(
			"Disponible du 10/09/2026 au 14/09/2026",
		);
	});

	it("dit « le » quand les deux bornes sont le même jour", () => {
		expect(libelleColonneDisponibilite("2026-09-10", "2026-09-10")).toBe(
			"Disponible le 10/09/2026",
		);
	});

	it("reste honnête sur une borne seule", () => {
		// Le serveur complète l'autre borne avec aujourd'hui : afficher une plage
		// laisserait croire à une date choisie.
		expect(libelleColonneDisponibilite("2026-09-10", null)).toBe(
			"Disponible à partir du 10/09/2026",
		);
		expect(libelleColonneDisponibilite(null, "2026-09-14")).toBe(
			"Disponible jusqu'au 14/09/2026",
		);
	});
});

describe("serializeFilters / parseFilters (URL state)", () => {
	it("round-trip conserve les filtres non-défaut", () => {
		const filters = {
			search: "tente",
			categories: [3, 7],
			rentable: "all" as const,
			dateDebut: "2026-09-10",
			dateFin: "2026-09-14",
			page: 2,
		};
		const restored = parseFilters(serializeFilters(filters));
		expect(restored).toEqual(filters);
	});

	it("une query string vide donne les filtres par défaut", () => {
		expect(parseFilters("")).toEqual(DEFAULT_FILTERS);
	});

	it("ignore une page invalide", () => {
		expect(parseFilters("page=0").page).toBe(1);
		expect(parseFilters("page=abc").page).toBe(1);
	});

	it("parse rentable=false", () => {
		expect(parseFilters("rentable=false").rentable).toBe(false);
	});
});

describe("totalPages", () => {
	it("au moins une page même sans résultat", () => {
		expect(totalPages(0)).toBe(1);
	});

	it("arrondit au supérieur", () => {
		expect(totalPages(CATALOG_PAGE_SIZE + 1)).toBe(2);
		expect(totalPages(CATALOG_PAGE_SIZE)).toBe(1);
	});
});
