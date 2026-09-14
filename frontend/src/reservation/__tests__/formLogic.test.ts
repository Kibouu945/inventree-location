import { describe, expect, it } from "vitest";

import {
	buildReservationPayload,
	canArbitrateReservation,
	canCancelReservation,
	emptyReservationValues,
	enrichLignesFromCatalog,
	isReservationEditable,
	prestationDefaults,
	readOnlyReason,
	removeLigne,
	reservationToFormValues,
	transitionErrorMessage,
	upsertLigne,
	validateReservationValues,
} from "../formLogic";
import type {
	LigneReservationLine,
	Prestation,
	Reservation,
	ReservationFormValues,
} from "../types";

const PRESTATION: Prestation = {
	id: 1,
	nom: "Installation",
	date_debut: "2026-07-10T08:00:00Z",
	date_fin: "2026-07-10T18:00:00Z",
	manifestation: 1,
	manifestation_nom: "Camp été 2026",
	lieu: 1,
	lieu_detail: {
		id: 1,
		nom: "Terrain central",
		adresse: "",
		latitude: null,
		longitude: null,
	},
};

function values(
	overrides: Partial<ReservationFormValues> = {},
): ReservationFormValues {
	return { ...emptyReservationValues(), ...overrides };
}

const MATERIEL: LigneReservationLine = {
	part: 10,
	partName: "Tente 4 places",
	quantiteDemandee: 2,
	isVirtual: false,
};

const ARTICLE_VIRTUEL: LigneReservationLine = {
	part: 20,
	partName: "Prestation nettoyage",
	quantiteDemandee: 1,
	isVirtual: true,
};

describe("validateReservationValues", () => {
	it("exige prestation et demandeur même en brouillon", () => {
		const errors = validateReservationValues(values(), null, "brouillon");
		expect(errors.prestation).toBeTruthy();
		expect(errors.demandeur).toBeTruthy();
	});

	it("brouillon : dates et lignes facultatives une fois prestation/demandeur fournis", () => {
		const errors = validateReservationValues(
			values({ prestation: 1, demandeur: 2 }),
			PRESTATION,
			"brouillon",
		);
		expect(errors).toEqual({});
	});

	it("soumission : refuse sans dates ni lignes", () => {
		const errors = validateReservationValues(
			values({ prestation: 1, demandeur: 2 }),
			PRESTATION,
			"soumise",
		);
		expect(errors.date_retrait_prevue).toBeTruthy();
		expect(errors.date_retour_prevue).toBeTruthy();
		expect(errors.lignes).toBeTruthy();
	});

	it("soumission : refuse une période qui ne couvre pas la prestation", () => {
		const errors = validateReservationValues(
			values({
				prestation: 1,
				demandeur: 2,
				date_retrait_prevue: new Date("2026-07-10T09:00:00Z"),
				date_retour_prevue: new Date(PRESTATION.date_fin),
				lignes: [MATERIEL, ARTICLE_VIRTUEL],
			}),
			PRESTATION,
			"soumise",
		);
		expect(errors.date_retrait_prevue).toBeTruthy();
	});

	it("soumission : refuse sans article virtuel parmi les lignes", () => {
		const errors = validateReservationValues(
			values({
				prestation: 1,
				demandeur: 2,
				date_retrait_prevue: new Date(PRESTATION.date_debut),
				date_retour_prevue: new Date(PRESTATION.date_fin),
				lignes: [MATERIEL],
			}),
			PRESTATION,
			"soumise",
		);
		expect(errors.lignes).toBeTruthy();
	});

	it("soumission : accepte avec matériel + article virtuel + période couvrante", () => {
		const errors = validateReservationValues(
			values({
				prestation: 1,
				demandeur: 2,
				date_retrait_prevue: new Date(PRESTATION.date_debut),
				date_retour_prevue: new Date(PRESTATION.date_fin),
				lignes: [MATERIEL, ARTICLE_VIRTUEL],
			}),
			PRESTATION,
			"soumise",
		);
		expect(errors).toEqual({});
	});
});

describe("prestationDefaults", () => {
	it("reprend la liste d’articles de la prestation", () => {
		const defaults = prestationDefaults({
			...PRESTATION,
			lignes: [
				{
					id: 1,
					part: 7,
					part_name: "Table brasserie pliante 8 pers",
					quantite: 6,
					commentaire: "",
				},
				{
					id: 2,
					part: 9,
					part_name: "Barrière Vauban",
					quantite: 8,
					commentaire: "",
				},
			],
		});

		expect(defaults.lignes).toEqual([
			{
				part: 7,
				partName: "Table brasserie pliante 8 pers",
				quantiteDemandee: 6,
				isVirtual: false,
			},
			{
				part: 9,
				partName: "Barrière Vauban",
				quantiteDemandee: 8,
				isVirtual: false,
			},
		]);
	});

	it("rend une liste vide quand la prestation n’a pas de prévisionnel", () => {
		expect(prestationDefaults(PRESTATION).lignes).toEqual([]);
		expect(prestationDefaults({ ...PRESTATION, lignes: [] }).lignes).toEqual(
			[],
		);
	});

	it("pose 8h00 quand la période couvre encore la prestation", () => {
		// Prestation de 10h à 16h, heure locale : 8h00 est bien avant le début
		// pour le retrait, et bien après la fin pour le retour.
		const debut = new Date(2026, 6, 10, 10, 0);
		const fin = new Date(2026, 6, 10, 16, 0);

		const defaults = prestationDefaults({
			...PRESTATION,
			date_debut: debut.toISOString(),
			date_fin: fin.toISOString(),
		});

		expect(defaults.date_retrait_prevue).toEqual(new Date(2026, 6, 10, 8, 0));
		expect(defaults.date_retour_prevue).toEqual(fin);
	});

	it("garde la date de la prestation quand 8h00 arriverait trop tard", () => {
		// Prestation saisie à minuit : proposer un retrait à 8h00 donnerait une
		// valeur que la validation RES-07 refuse (retrait postérieur au début).
		const debut = new Date(2026, 6, 10, 0, 0);
		const fin = new Date(2026, 6, 11, 0, 0);

		const defaults = prestationDefaults({
			...PRESTATION,
			date_debut: debut.toISOString(),
			date_fin: fin.toISOString(),
		});

		expect(defaults.date_retrait_prevue).toEqual(debut);
		expect(defaults.date_retour_prevue).toEqual(new Date(2026, 6, 11, 8, 0));
	});

	it("propose une période que la validation accepte", () => {
		const defaults = prestationDefaults({
			...PRESTATION,
			lignes: [
				{
					id: 1,
					part: 7,
					part_name: "Nettoyage",
					quantite: 1,
					commentaire: "",
				},
			],
		});

		const errors = validateReservationValues(
			values({
				prestation: 1,
				demandeur: 2,
				...defaults,
				// `isVirtual` est résolu par le catalogue, pas par la prestation.
				lignes: defaults.lignes.map((ligne) => ({ ...ligne, isVirtual: true })),
			}),
			PRESTATION,
			"soumise",
		);

		expect(errors).toEqual({});
	});
});

describe("buildReservationPayload", () => {
	it("mappe les lignes vers le format API (part, quantite_demandee)", () => {
		const payload = buildReservationPayload(
			values({ prestation: 1, demandeur: 2, lignes: [MATERIEL] }),
			"soumise",
		);
		expect(payload.lignes).toEqual([{ part: 10, quantite_demandee: 2 }]);
		expect(payload.statut).toBe("soumise");
	});

	it("sérialise les dates en ISO et null si absentes", () => {
		const payload = buildReservationPayload(
			values({ prestation: 1, demandeur: 2 }),
			"brouillon",
		);
		expect(payload.date_retrait_prevue).toBeNull();
		expect(payload.date_retour_prevue).toBeNull();
	});
});

describe("upsertLigne / removeLigne", () => {
	it("ajoute une nouvelle ligne", () => {
		const result = upsertLigne([], MATERIEL);
		expect(result).toEqual([MATERIEL]);
	});

	it("remplace une ligne existante pour le même article", () => {
		const updated = { ...MATERIEL, quantiteDemandee: 5 };
		const result = upsertLigne([MATERIEL], updated);
		expect(result).toEqual([updated]);
	});

	it("retire une ligne par identifiant de part", () => {
		const result = removeLigne([MATERIEL, ARTICLE_VIRTUEL], MATERIEL.part);
		expect(result).toEqual([ARTICLE_VIRTUEL]);
	});
});

describe("reservationToFormValues / enrichLignesFromCatalog", () => {
	const RESERVATION: Reservation = {
		id: 5,
		numero: "RES-2026-0001",
		prestation: 1,
		prestation_nom: "Prestation test",
		demandeur: 2,
		demandeur_nom: "Jean Dupont (jdupont)",
		validateur: null,
		statut: "brouillon",
		forced: false,
		date_demande: "2026-07-01T00:00:00Z",
		date_retrait_prevue: PRESTATION.date_debut,
		date_retour_prevue: PRESTATION.date_fin,
		date_retrait_reelle: null,
		date_retour_reelle: null,
		commentaire: "RAS",
		lignes: [
			{
				id: 1,
				part: 10,
				quantite_demandee: 2,
				quantite_livree: 0,
				quantite_retournee: 0,
				etat_retour: "",
				commentaire: "",
			},
		],
		created_at: "2026-07-01T00:00:00Z",
		updated_at: "2026-07-01T00:00:00Z",
	};

	it("reconstruit les valeurs de base depuis une réservation", () => {
		const result = reservationToFormValues(RESERVATION);
		expect(result.prestation).toBe(1);
		expect(result.demandeur).toBe(2);
		expect(result.date_retrait_prevue).toEqual(new Date(PRESTATION.date_debut));
		expect(result.lignes[0].part).toBe(10);
	});

	it("enrichit les lignes avec le nom et le drapeau virtuel du catalogue", () => {
		const base = reservationToFormValues(RESERVATION).lignes;
		const enriched = enrichLignesFromCatalog(base, [
			{ id: 10, name: "Tente 4 places", is_virtual: false },
		]);
		expect(enriched[0].partName).toBe("Tente 4 places");
		expect(enriched[0].isVirtual).toBe(false);
	});

	it("laisse la ligne inchangée si le part est absent du catalogue", () => {
		const base = reservationToFormValues(RESERVATION).lignes;
		const enriched = enrichLignesFromCatalog(base, []);
		expect(enriched).toEqual(base);
	});
});

describe("canArbitrateReservation", () => {
	it("ouvre l’arbitrage uniquement sur une réservation soumise", () => {
		expect(canArbitrateReservation("soumise")).toBe(true);
	});

	it("n’ouvre pas l’arbitrage sur les autres statuts", () => {
		for (const statut of [
			"brouillon",
			"validee",
			"refusee",
			"livree",
			"retournee",
			"cloturee",
		]) {
			expect(canArbitrateReservation(statut)).toBe(false);
		}
	});
});

describe("transitionErrorMessage", () => {
	it("remonte le detail backend (ex. conflit de stock)", () => {
		const error = {
			response: { data: { detail: "Validation refusée : conflit de stock." } },
		};
		expect(transitionErrorMessage(error)).toBe(
			"Validation refusée : conflit de stock.",
		);
	});

	it("retombe sur un message générique sans detail exploitable", () => {
		expect(transitionErrorMessage(new Error("boom"))).toBe(
			"Le statut n'a pas pu être changé.",
		);
		expect(transitionErrorMessage(undefined)).toBe(
			"Le statut n'a pas pu être changé.",
		);
	});
});

describe("isReservationEditable", () => {
	it("éditable en brouillon et soumise", () => {
		expect(isReservationEditable("brouillon")).toBe(true);
		expect(isReservationEditable("soumise")).toBe(true);
	});

	it("verrouillée dès validée et au-delà", () => {
		for (const statut of [
			"validee",
			"refusee",
			"livree",
			"retournee",
			"cloturee",
		]) {
			expect(isReservationEditable(statut)).toBe(false);
		}
	});
});

describe("canCancelReservation", () => {
	it("autorise l’annulation tant que la réservation est vivante", () => {
		for (const statut of [
			"brouillon",
			"soumise",
			"validee",
			"livree",
			"retournee",
		]) {
			expect(canCancelReservation(statut)).toBe(true);
		}
	});

	it("la refuse sur un dossier clos", () => {
		for (const statut of ["cloturee", "refusee", "annulee"]) {
			expect(canCancelReservation(statut)).toBe(false);
		}
	});
});

describe("readOnlyReason", () => {
	it("nomme le vrai statut, pas « validée » par défaut", () => {
		expect(readOnlyReason("annulee")).toContain("annulée");
		expect(readOnlyReason("refusee")).toContain("refusée");
		expect(readOnlyReason("livree")).toContain("livrée");
		expect(readOnlyReason("cloturee")).toContain("clôturée");
		expect(readOnlyReason("validee")).toContain("validée");
	});

	it("reste neutre sur un statut inconnu", () => {
		expect(readOnlyReason("zzz")).toBe(
			"Cette réservation n’est plus modifiable.",
		);
	});
});
