// Règles d'affichage des contacts, hors React — donc testables.
//
// Deux écrans les partagent : l'onglet Contacts du back-office, qui les gère,
// et le sélecteur « Contact référent » de l'écran Manifestations, qui les
// consomme.

/** Ce qu'il faut d'un contact pour l'afficher : le reste ne regarde pas ces règles. */
export interface ContactAffichable {
	id: number;
	nom: string;
	prenom: string;
	actif: boolean;
}

/** « Paule Durand », ou le seul nom quand le prénom manque. */
export function nomComplet(contact: { nom: string; prenom: string }): string {
	return `${contact.prenom} ${contact.nom}`.trim();
}

/** Options d'un sélecteur de contact, désactivés écartés.
 *
 * C'est à ça que sert l'état : un contact qui quitte l'entreprise ne doit plus
 * être proposé. Avec une exception, `selectionne` — celui que porte déjà
 * l'objet qu'on édite. Sans elle, ouvrir une manifestation dont le contact a
 * été désactivé viderait le champ, et l'enregistrement effacerait
 * silencieusement son interlocuteur.
 */
export function optionsDeContacts(
	contacts: ContactAffichable[],
	selectionne: string | null = null,
): Array<{ value: string; label: string }> {
	return contacts
		.filter((contact) => contact.actif || String(contact.id) === selectionne)
		.map((contact) => ({
			value: String(contact.id),
			label: contact.actif
				? nomComplet(contact)
				: `${nomComplet(contact)} (inactif)`,
		}));
}
