import { describe, expect, it } from "vitest";

import {
	enSurplus,
	type LigneSaisie,
	manquantExcessif,
	totalSaisi,
} from "../retourRegles";

function ligne(overrides: Partial<LigneSaisie> = {}): LigneSaisie {
	return {
		partNom: "Banc brasserie 220",
		quantiteAttendue: 10,
		quantite_ramassee: 0,
		quantite_sav: 0,
		quantite_detruite: 0,
		quantite_manquante: 0,
		...overrides,
	};
}

describe("totalSaisi", () => {
	it("additionne les quatre compteurs", () => {
		expect(
			totalSaisi(
				ligne({
					quantite_ramassee: 5,
					quantite_sav: 2,
					quantite_detruite: 1,
					quantite_manquante: 2,
				}),
			),
		).toBe(10);
	});
});

describe("manquantExcessif", () => {
	it("refuse de perdre plus que ce qui est parti", () => {
		const trop = ligne({ quantite_manquante: 11 });
		expect(manquantExcessif([trop])).toEqual([trop]);
	});

	it("accepte que tout soit manquant", () => {
		// Un camion volé sur place : dix sortis, dix perdus. Cas limite, légitime.
		expect(manquantExcessif([ligne({ quantite_manquante: 10 })])).toEqual([]);
	});

	it("ignore un surplus de récupéré", () => {
		// R36 : c'est précisément ce que la recette du 11/09 demandait d'autoriser.
		expect(manquantExcessif([ligne({ quantite_ramassee: 12 })])).toEqual([]);
	});
});

describe("enSurplus", () => {
	it("signale un total supérieur à l’attendu", () => {
		const surplus = ligne({ quantite_ramassee: 12 });
		expect(enSurplus([surplus])).toEqual([surplus]);
	});

	it("ne signale rien quand le compte tombe juste", () => {
		expect(enSurplus([ligne({ quantite_ramassee: 10 })])).toEqual([]);
	});
});
