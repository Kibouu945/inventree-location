// La règle de désactivation, une fois pour toutes.
//
// Un client comme un contact se **désactive**, il ne se supprime pas : la base
// protège les manifestations qui les référencent, et un devis doit rester
// lisible tel qu'il a été signé. Le drapeau `actif` sert donc à une seule
// chose — sortir des sélecteurs sans sortir de l'historique.
//
// Écrite ici plutôt que dans chaque écran : la règle a d'abord existé pour les
// contacts, et l'étiquette du back-office promettait déjà la même chose des
// clients sans que rien ne l'applique.

/** Ce qu'il faut d'un élément pour juger s'il se propose encore. */
export interface Desactivable {
  id: number;
  actif: boolean;
}

/**
 * Options d'un sélecteur, désactivés écartés — sauf celui déjà choisi.
 *
 * L'exception `selectionne` est le cœur de la règle : sans elle, rouvrir une
 * manifestation dont le client ou le contact a été désactivé viderait le
 * champ, et le premier enregistrement effacerait silencieusement le lien. On
 * le garde donc visible, marqué `(inactif)`, pour qu'on sache pourquoi il est
 * encore là.
 */
export function optionsActives<T extends Desactivable>(
  elements: T[],
  libelle: (element: T) => string,
  selectionne: string | null = null
): Array<{ value: string; label: string }> {
  return elements
    .filter((element) => element.actif || String(element.id) === selectionne)
    .map((element) => ({
      value: String(element.id),
      label: element.actif ? libelle(element) : `${libelle(element)} (inactif)`
    }));
}
