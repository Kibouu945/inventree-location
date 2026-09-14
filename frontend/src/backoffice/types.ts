/** Types de l'API back-office : utilisateurs, rôles, clients et contacts. */

/** Réponse paginée DRF, commune aux listes back-office. */
export interface Page<T> {
	count: number;
	next: string | null;
	previous: string | null;
	results: T[];
}

export interface BackOfficeRole {
	name: string;
	label: string;
}

export interface BackOfficeUser {
	id: number;
	username: string;
	first_name: string;
	last_name: string;
	email: string;
	is_active: boolean;
	is_staff: boolean;
	is_superuser: boolean;
	role: string | null;
	/** Porté par le `Profile`, imprimé sur le bon de livraison. */
	telephone: string;
}

export interface BackOfficeUserFormValues {
	username: string;
	first_name: string;
	last_name: string;
	email: string;
	password: string;
	is_active: boolean;
	role: string | null;
	telephone: string;
}

export interface BackOfficeClient {
	id: number;
	nom: string;
	adresse: string;
	email: string | null;
	telephone: string;
	type_client: string;
	siret: string;
	gestionnaire: number | null;
	gestionnaire_nom: string;
	actif: boolean;
	contacts: number;
}

export interface BackOfficeClientFormValues {
	nom: string;
	adresse: string;
	email: string;
	telephone: string;
	type_client: string;
	siret: string;
	actif: boolean;
}

export interface BackOfficeContact {
	id: number;
	client: number;
	client_nom: string;
	nom: string;
	prenom: string;
	email: string | null;
	telephone: string;
	actif: boolean;
}

export interface BackOfficeContactFormValues {
	nom: string;
	prenom: string;
	email: string;
	telephone: string;
	actif: boolean;
}
