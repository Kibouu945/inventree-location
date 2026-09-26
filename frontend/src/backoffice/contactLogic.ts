// Règles d'affichage des contacts, hors React — donc testables.
import { optionsActives } from './optionsActives';

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

/**
 * C'est à ça que sert l'état : un contact qui quitte l'entreprise ne doit plus
 * être proposé.
 */
export function optionsDeContacts(
  contacts: ContactAffichable[],
  selectionne: string | null = null
): Array<{ value: string; label: string }> {
  return optionsActives(contacts, nomComplet, selectionne);
}
