/** Statuts de réservation : une seule table de couleurs pour tous les écrans. */

/** Miroir de `StatutReservation` (inventree_location/models.py). */
export const COULEURS_STATUT: Record<string, string> = {
  brouillon: 'gray',
  soumise: 'blue',
  validee: 'green',
  refusee: 'red',
  annulee: 'orange',
  livree: 'teal',
  retournee: 'grape',
  cloturee: 'dark'
};

export function couleurDuStatut(statut: string): string {
  return COULEURS_STATUT[statut] ?? 'gray';
}
