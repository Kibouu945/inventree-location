import { describe, expect, it } from "vitest";

import { toCategoryOptions } from "../catalog/useCategoryOptions";

describe("toCategoryOptions", () => {
	it("accepte les deux formes de réponse d’InvenTree", () => {
		const attendu = [{ value: "3", label: "Mobilier" }];

		expect(toCategoryOptions([{ id: 3, name: "Mobilier" }])).toEqual(attendu);
		expect(
			toCategoryOptions({ results: [{ id: 3, name: "Mobilier" }] }),
		).toEqual(attendu);
	});

	it("accepte `pk` autant que `id`", () => {
		expect(toCategoryOptions([{ pk: 7, name: "Couchage" }])).toEqual([
			{ value: "7", label: "Couchage" },
		]);
	});

	it("préfère le chemin complet au nom seul", () => {
		// Deux « Pliantes » sous deux parents différents seraient
		// indiscernables dans une liste déroulante.
		expect(
			toCategoryOptions([
				{ id: 1, name: "Pliantes", pathstring: "Mobilier/Tables/Pliantes" },
			]),
		).toEqual([{ value: "1", label: "Mobilier/Tables/Pliantes" }]);
	});

	it("écarte les entrées inexploitables", () => {
		expect(
			toCategoryOptions([
				{ id: 1, name: "" },
				{ name: "Sans identifiant" },
				{ id: 2, name: "Valide" },
			]),
		).toEqual([{ value: "2", label: "Valide" }]);
	});

	it("trie par libellé, accents compris", () => {
		expect(
			toCategoryOptions([
				{ id: 1, name: "Éclairage" },
				{ id: 2, name: "Zone technique" },
				{ id: 3, name: "Cuisine" },
			]).map((option) => option.label),
		).toEqual(["Cuisine", "Éclairage", "Zone technique"]);
	});

	it("rend une liste vide tant que la requête n’a pas répondu", () => {
		expect(toCategoryOptions(undefined)).toEqual([]);
	});
});
