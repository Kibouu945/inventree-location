/** Types de l'API ramassages (`/plugin/inventree-location/ramassages/`). */

export interface Page<T> {
	count: number;
	next: string | null;
	previous: string | null;
	results: T[];
}

export interface LieuRamassage {
	id: number;
	nom: string;
	adresse: string;
	latitude: string | null;
	longitude: string | null;
}

export interface RecapVehicule {
	vehicule: string;
	quantite_totale: number;
}

export interface LigneBonRamassage {
	/** Id de la ligne de réservation : c'est lui que la saisie retour renvoie. */
	id: number;
	part: number;
	part_nom: string;
	quantite_demandee: number;
	quantite_livree: number;
	quantite_a_ramasser: number;
	quantite_retournee: number;
	// Ventilation du retour réel (SCRUM-112) : ce qui revient en état, ce qui
	// part au SAV, ce qui est détruit, ce qui manque.
	quantite_ramassee: number;
	quantite_sav: number;
	quantite_detruite: number;
	quantite_manquante: number;
	facturer_client: boolean;
	etat_retour: string;
	commentaire: string;
}

export interface RetourRamassageLignePayload {
	ligne: number;
	quantite_ramassee: number;
	quantite_sav: number;
	quantite_detruite: number;
	quantite_manquante: number;
	facturer_client: boolean;
	commentaire: string;
}

export interface RetourRamassagePayload {
	commentaire: string;
	lignes: RetourRamassageLignePayload[];
}

export interface RetourRamassageResponse {
	reservation: number;
	numero: string;
	statut: string;
	updated_lines: Array<{
		id: number;
		part: number;
		quantite_ramassee: number;
		quantite_sav: number;
		quantite_detruite: number;
		quantite_manquante: number;
		facturer_client: boolean;
		etat_retour: string;
	}>;
	/** Ids des tickets SAV ouverts par la saisie. */
	sav_tickets: number[];
}

export interface Ramassage {
	id: number;
	numero: string;
	prestation: number;
	prestation_nom: string;
	manifestation_nom: string;
	client_nom?: string;
	demandeur: number;
	demandeur_nom: string;
	statut: string;
	date_ramassage: string | null;
	date_retrait_prevue: string | null;
	date_retour_prevue: string | null;
	lieu: LieuRamassage | null;
	nb_objets: number;
	quantite_totale: number;
	recap_par_vehicule: RecapVehicule[];
	lignes?: LigneBonRamassage[];
}

export interface BonRamassageResponse {
	titre: string;
	generated_at: string;
	reservation: Ramassage & {
		lignes: LigneBonRamassage[];
		commentaire: string;
	};
}
