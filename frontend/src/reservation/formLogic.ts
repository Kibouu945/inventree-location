/**
 * Logique pure du formulaire de réservation (RES-03).
 *
 * Isolée des composants React pour être testable sans rendu. Réplique côté
 * client les règles métier appliquées par `ReservationSerializer.validate`
 * côté serveur : permissives en brouillon, strictes à la soumission.
 */

import { HEURE_PAR_DEFAUT } from "../DateTimeField";
import type {
	LigneReservationLine,
	Prestation,
	Reservation,
	ReservationFormValues,
	ReservationStatut,
} from "./types";

/** Formate une date en « JJ/MM », en UTC pour rester stable quel que soit le
 * fuseau d'exécution (tests compris). */
function formatDayMonth(date: Date): string {
	const day = String(date.getUTCDate()).padStart(2, "0");
	const month = String(date.getUTCMonth() + 1).padStart(2, "0");
	return `${day}/${month}`;
}

export function emptyReservationValues(): ReservationFormValues {
	return {
		prestation: null,
		demandeur: null,
		date_retrait_prevue: null,
		date_retour_prevue: null,
		commentaire: "",
		lignes: [],
	};
}

/** Pose une heure « HH:mm » sur le jour d'une date, sans toucher au jour. */
function auMemeJourA(date: Date, heure: string): Date {
	const [h, m] = heure.split(":").map(Number);
	const resultat = new Date(date);
	resultat.setHours(h, m ?? 0, 0, 0);
	return resultat;
}

/**
 * Valeurs reprises de la prestation pour une réservation neuve.
 *
 * Recette Tassin du 07/09/2026, remarques 14 et 15 : « il serait souhaitable de
 * reprendre les dates de la prestation et de positionner l'heure à 8h00 par
 * défaut », et « il faut ressaisir toute la liste ? on devrait pouvoir
 * récupérer la liste saisie au moment de la prestation ». Les deux
 * informations étaient déjà sur le fil : `GET /prestations/{id}/` renvoie les
 * dates *et* les lignes, et le formulaire les jetait.
 *
 * L'heure de 8h00 n'est posée que si elle laisse la période couvrir la
 * prestation — règle RES-07, vérifiée aussi côté serveur
 * (`ReservationSerializer.validate`) : le retrait ne peut pas être postérieur
 * au début, ni le retour antérieur à la fin. Sur une prestation saisie à
 * minuit, 8h00 arriverait trop tard pour le retrait ; on garde alors la date
 * de la prestation telle quelle plutôt que de proposer une valeur que la
 * validation refusera. Les prestations créées désormais portent 8h00 par défaut
 * (voir `DateTimeField`), les deux bornes tombent donc juste d'elles-mêmes.
 */
export function prestationDefaults(
	prestation: Prestation,
): Pick<
	ReservationFormValues,
	"date_retrait_prevue" | "date_retour_prevue" | "lignes"
> {
	const debut = new Date(prestation.date_debut);
	const fin = new Date(prestation.date_fin);

	const retraitA8h = auMemeJourA(debut, HEURE_PAR_DEFAUT);
	const retourA8h = auMemeJourA(fin, HEURE_PAR_DEFAUT);

	return {
		date_retrait_prevue: retraitA8h <= debut ? retraitA8h : debut,
		date_retour_prevue: retourA8h >= fin ? retourA8h : fin,
		// `isVirtual` est laissé à faux : c'est `enrichLignesFromCatalog` qui
		// tranche, une fois le catalogue résolu. La règle « au moins un article
		// virtuel » reste donc évaluée sur des drapeaux vrais.
		lignes: (prestation.lignes ?? []).map((ligne) => ({
			part: ligne.part,
			partName: ligne.part_name,
			quantiteDemandee: ligne.quantite,
			isVirtual: false,
		})),
	};
}

export interface ReservationFormErrors {
	[key: string]: string | undefined;
	prestation?: string;
	demandeur?: string;
	date_retrait_prevue?: string;
	date_retour_prevue?: string;
	lignes?: string;
}

/**
 * Valide les valeurs du formulaire pour un statut donné.
 *
 * `prestation` et `demandeur` sont toujours obligatoires (ils identifient la
 * réservation). Les autres règles (dates, lignes, article virtuel, période
 * couvrant la prestation) ne s'appliquent qu'à la soumission.
 */
export function validateReservationValues(
	values: ReservationFormValues,
	prestation: Prestation | null,
	statut: ReservationStatut,
): ReservationFormErrors {
	const errors: ReservationFormErrors = {};

	if (!values.prestation) {
		errors.prestation = "La prestation est obligatoire.";
	}
	if (!values.demandeur) {
		errors.demandeur = "Le demandeur est obligatoire.";
	}

	if (statut === "brouillon") {
		return errors;
	}

	const { date_retrait_prevue: retrait, date_retour_prevue: retour } = values;

	if (!retrait) {
		errors.date_retrait_prevue =
			"La date de retrait est obligatoire pour soumettre la réservation.";
	}
	if (!retour) {
		errors.date_retour_prevue =
			"La date de retour est obligatoire pour soumettre la réservation.";
	}

	if (retrait && retour) {
		if (retrait > retour) {
			errors.date_retour_prevue =
				"La date de retour doit être postérieure ou égale à la date de retrait.";
		} else if (prestation) {
			const debut = new Date(prestation.date_debut);
			const fin = new Date(prestation.date_fin);
			const couvreDebut = retrait <= debut;
			const couvreFin = retour >= fin;

			if (!couvreDebut || !couvreFin) {
				const message =
					"La période de réservation doit couvrir les dates du " +
					`${formatDayMonth(debut)} au ${formatDayMonth(fin)}.`;

				if (!couvreDebut) {
					errors.date_retrait_prevue = message;
				}
				if (!couvreFin) {
					errors.date_retour_prevue = message;
				}
			}
		}
	}

	if (values.lignes.length === 0) {
		errors.lignes =
			"Au moins une ligne de matériel est obligatoire pour soumettre la réservation.";
	} else if (!values.lignes.some((ligne) => ligne.isVirtual)) {
		errors.lignes =
			"Au moins un article virtuel (ex: prestation de nettoyage) est obligatoire pour soumettre la réservation.";
	}

	return errors;
}

/** Construit le payload API à partir des valeurs du formulaire. */
export function buildReservationPayload(
	values: ReservationFormValues,
	statut: ReservationStatut,
) {
	return {
		prestation: values.prestation,
		demandeur: values.demandeur,
		statut,
		date_retrait_prevue: values.date_retrait_prevue
			? values.date_retrait_prevue.toISOString()
			: null,
		date_retour_prevue: values.date_retour_prevue
			? values.date_retour_prevue.toISOString()
			: null,
		commentaire: values.commentaire,
		lignes: values.lignes.map((ligne) => ({
			part: ligne.part,
			quantite_demandee: ligne.quantiteDemandee,
		})),
	};
}

/** Ajoute ou remplace une ligne de matériel (une seule ligne par part). */
export function upsertLigne(
	lignes: LigneReservationLine[],
	ligne: LigneReservationLine,
): LigneReservationLine[] {
	const withoutExisting = lignes.filter(
		(existing) => existing.part !== ligne.part,
	);
	return [...withoutExisting, ligne];
}

export function removeLigne(
	lignes: LigneReservationLine[],
	part: number,
): LigneReservationLine[] {
	return lignes.filter((ligne) => ligne.part !== part);
}

/** Reconstruit les valeurs de formulaire à partir d'une réservation chargée
 * (édition). Les lignes sont enrichies (nom, article virtuel) séparément,
 * une fois le catalogue résolu — voir `enrichLignesFromCatalog`. */
export function reservationToFormValues(
	reservation: Reservation,
): ReservationFormValues {
	return {
		prestation: reservation.prestation,
		demandeur: reservation.demandeur,
		date_retrait_prevue: reservation.date_retrait_prevue
			? new Date(reservation.date_retrait_prevue)
			: null,
		date_retour_prevue: reservation.date_retour_prevue
			? new Date(reservation.date_retour_prevue)
			: null,
		commentaire: reservation.commentaire,
		lignes: reservation.lignes.map((ligne) => ({
			part: ligne.part,
			partName: `Article #${ligne.part}`,
			quantiteDemandee: ligne.quantite_demandee,
			isVirtual: false,
		})),
	};
}

interface CatalogPartInfo {
	id: number;
	name: string;
	is_virtual: boolean;
}

/** Complète le nom et le drapeau `is_virtual` des lignes à partir du
 * catalogue (résultat de `/catalog/?ids=...`). */
export function enrichLignesFromCatalog(
	lignes: LigneReservationLine[],
	catalogParts: CatalogPartInfo[],
): LigneReservationLine[] {
	const byId = new Map(catalogParts.map((part) => [part.id, part]));

	return lignes.map((ligne) => {
		const info = byId.get(ligne.part);

		if (!info) {
			return ligne;
		}

		return { ...ligne, partName: info.name, isVirtual: info.is_virtual };
	});
}

/** Vrai si la réservation attend un arbitrage (seul « soumise » l'ouvre). */
export function canArbitrateReservation(statut: string): boolean {
	return statut === "soumise";
}

/** Statuts depuis lesquels `VALID_TRANSITIONS` autorise encore l'annulation. */
const STATUTS_ANNULABLES = [
	"brouillon",
	"soumise",
	"validee",
	"livree",
	"retournee",
];

/** Vrai si la réservation peut encore être annulée.
 *
 * C'est le seul levier d'arbitrage sur une réservation déjà validée : la fiche
 * s'ouvre alors en lecture seule et aucune autre action n'existe.
 */
export function canCancelReservation(statut: string): boolean {
	return STATUTS_ANNULABLES.includes(statut);
}

/** Pourquoi la réservation est en lecture seule, dit avec son vrai statut.
 *
 * Le message était figé sur « validée » alors que `isReservationEditable`
 * verrouille tout ce qui n'est ni brouillon ni soumise : une réservation
 * annulée ou refusée s'annonçait donc comme validée.
 */
export function readOnlyReason(statut: string): string {
	const raisons: Record<string, string> = {
		validee: "Cette réservation est validée : elle n’est plus modifiable.",
		livree: "Cette réservation est livrée : elle n’est plus modifiable.",
		retournee: "Cette réservation est retournée : elle n’est plus modifiable.",
		cloturee: "Cette réservation est clôturée : elle n’est plus modifiable.",
		refusee: "Cette réservation a été refusée : elle n’est plus modifiable.",
		annulee: "Cette réservation a été annulée : elle n’est plus modifiable.",
	};

	return raisons[statut] ?? "Cette réservation n’est plus modifiable.";
}

/** Vrai tant que la réservation est modifiable (avant validation). */
export function isReservationEditable(statut: string): boolean {
	return statut === "brouillon" || statut === "soumise";
}

/** Message d'une transition ratée : le `detail` backend, sinon un générique. */
export function transitionErrorMessage(error: unknown): string {
	const detail = (error as { response?: { data?: { detail?: unknown } } })
		?.response?.data?.detail;

	return typeof detail === "string"
		? detail
		: "Le statut n'a pas pu être changé.";
}
