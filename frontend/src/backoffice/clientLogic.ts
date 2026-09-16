// Règles d'affichage des clients, hors React — donc testables.
//
// Consommé par le sélecteur client du formulaire de manifestation : un
// client désactivé reste visible sur les manifestations existantes, mais ne
// doit plus pouvoir en recevoir de nouvelles.

/** Ce qu'il faut d'un client pour l'afficher : le reste ne regarde pas ces règles. */
export interface ClientAffichable {
  id: number;
  nom: string;
  actif: boolean;
}

/** Options d'un sélecteur de client, désactivés écartés.
 *
 * Même règle que `optionsDeContacts` : un client désactivé ne doit plus être
 * proposable pour une nouvelle manifestation. Exception, `selectionne` —
 * celui que porte déjà la manifestation qu'on édite. Sans elle, ouvrir une
 * manifestation dont le client a été désactivé viderait le champ, et
 * l'enregistrement effacerait silencieusement son client.
 */
export function optionsDeClients(
  clients: ClientAffichable[],
  selectionne: string | null = null
): Array<{ value: string; label: string }> {
  return clients
    .filter((client) => client.actif || String(client.id) === selectionne)
    .map((client) => ({
      value: String(client.id),
      label: client.actif ? client.nom : `${client.nom} (inactif)`
    }));
}
