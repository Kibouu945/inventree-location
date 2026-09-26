// La règle de désactivation, une fois pour toutes.

/** Ce qu'il faut d'un élément pour juger s'il se propose encore. */
export interface Desactivable {
  id: number;
  actif: boolean;
}

/** Options d'un sélecteur, désactivés écartés — sauf celui déjà choisi. */
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
