import { describe, expect, it } from "vitest";

import {
	aujourdhuiIso,
	buildDeliveryQuery,
	DEFAULT_DELIVERY_FILTERS,
	parseDeliveryFilters,
	serializeDeliveryFilters,
} from "../deliveryParams";

const AUJOURDHUI = "2026-09-08";

describe("horizon de la tournée", () => {
	it("par défaut, borne la tournée à la journée", () => {
		// Revue interne du 07/09/2026 : le livreur ouvrait son écran sur toutes
		// les livraisons, passées comprises.
		expect(DEFAULT_DELIVERY_FILTERS.horizon).toBe("jour");

		const params = buildDeliveryQuery(DEFAULT_DELIVERY_FILTERS, AUJOURDHUI);

		expect(params.date_from).toBe(AUJOURDHUI);
		expect(params.date_to).toBe(AUJOURDHUI);
	});

	it("« à venir » n’a pas de borne haute", () => {
		const params = buildDeliveryQuery(
			{ ...DEFAULT_DELIVERY_FILTERS, horizon: "avenir" },
			AUJOURDHUI,
		);

		expect(params.date_from).toBe(AUJOURDHUI);
		expect(params.date_to).toBeUndefined();
	});

	it("« tout » ne borne rien", () => {
		const params = buildDeliveryQuery(
			{ ...DEFAULT_DELIVERY_FILTERS, horizon: "tout" },
			AUJOURDHUI,
		);

		expect(params.date_from).toBeUndefined();
		expect(params.date_to).toBeUndefined();
	});

	it("une période saisie l’emporte sur l’horizon", () => {
		const params = buildDeliveryQuery(
			{
				...DEFAULT_DELIVERY_FILTERS,
				horizon: "jour",
				dateRange: ["2026-10-01", "2026-10-05"],
			},
			AUJOURDHUI,
		);

		expect(params.date_from).toBe("2026-10-01");
		expect(params.date_to).toBe("2026-10-05");
	});

	it("une borne libre seule ne réintroduit pas la journée", () => {
		// Sinon « à partir du 1er octobre » se serait vu ajouter un date_to à
		// aujourd'hui, et n'aurait plus rien rendu.
		const params = buildDeliveryQuery(
			{ ...DEFAULT_DELIVERY_FILTERS, dateRange: ["2026-10-01", null] },
			AUJOURDHUI,
		);

		expect(params.date_from).toBe("2026-10-01");
		expect(params.date_to).toBeUndefined();
	});
});

describe("horizon dans l’URL", () => {
	it("« tout » survit au rechargement", () => {
		// Une absence de clé vaut défaut : sans écrire « tout », le livreur qui
		// demande à voir l'historique retomberait sur sa journée en rechargeant.
		const filtres = { ...DEFAULT_DELIVERY_FILTERS, horizon: "tout" as const };
		const restaure = parseDeliveryFilters(serializeDeliveryFilters(filtres));

		expect(restaure.horizon).toBe("tout");
	});

	it("n’écrit pas l’horizon par défaut", () => {
		expect(serializeDeliveryFilters(DEFAULT_DELIVERY_FILTERS)).not.toContain(
			"livr_horizon",
		);
	});

	it("retombe sur le défaut devant une valeur inconnue", () => {
		expect(parseDeliveryFilters("livr_horizon=hier").horizon).toBe("jour");
		expect(parseDeliveryFilters("").horizon).toBe("jour");
	});
});

describe("aujourdhuiIso", () => {
	it("formate en AAAA-MM-JJ local, sans décalage de fuseau", () => {
		// 23h30 heure locale : un passage par toISOString() aurait basculé au
		// lendemain en UTC et vidé la tournée du soir.
		expect(aujourdhuiIso(new Date(2026, 8, 8, 23, 30))).toBe("2026-09-08");
		expect(aujourdhuiIso(new Date(2026, 0, 1, 0, 5))).toBe("2026-01-01");
	});
});
