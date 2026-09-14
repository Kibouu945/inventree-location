import type { LieuSummary } from "../reservation/types";

export interface DeliveryLigne {
	id: number;
	part: number;
	part_name: string;
	quantite_demandee: number;
	quantite_livree?: number;
	quantite_retournee?: number;
	is_virtual: boolean;
}

export type EtatLivraison =
	| ""
	| "assignee"
	| "en_cours"
	| "livree"
	| "probleme";

export interface LivraisonStatusLogEntry {
	id: number;
	from_etat: EtatLivraison;
	to_etat: EtatLivraison;
	to_etat_display: string;
	changed_by_nom: string;
	commentaire: string;
	photo: string | null;
	created_at: string;
}

export interface Delivery {
	id: number;
	numero: string;
	statut: string;
	prestation_nom: string;
	manifestation_nom?: string;
	client_nom?: string;
	demandeur_nom: string;
	lieu_detail: LieuSummary | null;
	organisateur_nom: string;
	organisateur_telephone: string;
	date_retrait_prevue: string | null;
	date_retour_prevue: string | null;
	commentaire: string;
	lignes: DeliveryLigne[];
	quantite_totale: number;
	livreur_assigne: number | null;
	livreur_assigne_nom: string;
	date_assignation: string | null;
	etat_livraison: EtatLivraison;
	etat_livraison_display: string;
	livraison_status_logs: LivraisonStatusLogEntry[];
}
