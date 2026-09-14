import { describe, expect, it } from "vitest";

import {
	checkinLigneTotal,
	isCheckinValid,
	summarizeCheckin,
	validateCheckinLignes,
} from "../checkinLogic";

function makeLigne(
	overrides: Partial<Parameters<typeof checkinLigneTotal>[0]> = {},
) {
	return {
		id: 1,
		quantite_demandee: 5,
		ok: 5,
		manquant: 0,
		casse: 0,
		commentaire: "",
		...overrides,
	};
}

describe("checkinLigneTotal", () => {
	it("sums ok + manquant + casse", () => {
		expect(checkinLigneTotal(makeLigne({ ok: 2, manquant: 1, casse: 2 }))).toBe(
			5,
		);
	});
});

describe("validateCheckinLignes", () => {
	it("returns no error when the sum matches the requested quantity", () => {
		const errors = validateCheckinLignes([
			makeLigne({ ok: 3, manquant: 1, casse: 1 }),
		]);
		expect(errors).toEqual({});
	});

	it("returns an error when the sum is below the requested quantity", () => {
		const errors = validateCheckinLignes([
			makeLigne({ id: 7, quantite_demandee: 5, ok: 2, manquant: 0, casse: 0 }),
		]);
		expect(errors[7]).toBeDefined();
	});

	it("returns an error when the sum exceeds the requested quantity", () => {
		const errors = validateCheckinLignes([
			makeLigne({ id: 9, quantite_demandee: 3, ok: 2, manquant: 1, casse: 1 }),
		]);
		expect(errors[9]).toBeDefined();
	});

	it("validates multiple lines independently", () => {
		const errors = validateCheckinLignes([
			makeLigne({ id: 1, quantite_demandee: 5, ok: 5 }),
			makeLigne({ id: 2, quantite_demandee: 2, ok: 1, manquant: 0, casse: 0 }),
		]);
		expect(errors[1]).toBeUndefined();
		expect(errors[2]).toBeDefined();
	});
});

describe("isCheckinValid", () => {
	it("is true when every line balances", () => {
		expect(
			isCheckinValid([
				makeLigne({ id: 1, quantite_demandee: 5, ok: 5 }),
				makeLigne({ id: 2, quantite_demandee: 3, ok: 3 }),
			]),
		).toBe(true);
	});

	it("is false when at least one line is unbalanced", () => {
		expect(
			isCheckinValid([makeLigne({ id: 1, quantite_demandee: 5, ok: 4 })]),
		).toBe(false);
	});
});

describe("summarizeCheckin", () => {
	it("adds up missing and broken quantities across lines", () => {
		expect(
			summarizeCheckin([
				makeLigne({
					id: 1,
					quantite_demandee: 5,
					ok: 3,
					manquant: 1,
					casse: 1,
				}),
				makeLigne({
					id: 2,
					quantite_demandee: 4,
					ok: 2,
					manquant: 0,
					casse: 2,
				}),
			]),
		).toEqual({ manquant: 1, casse: 3 });
	});

	it("reports no incident when everything comes back OK", () => {
		expect(
			summarizeCheckin([makeLigne({ id: 1, quantite_demandee: 5, ok: 5 })]),
		).toEqual({ manquant: 0, casse: 0 });
	});
});
