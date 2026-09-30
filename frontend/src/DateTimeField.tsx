// Champ date/heure commun à tous les formulaires du plugin.
import { DateTimePicker, type DateTimePickerProps } from '@mantine/dates';

// Heure par défaut quand l'utilisateur choisit un jour au calendrier.
export const HEURE_PAR_DEFAUT = '08:00';

export function DateTimeField({
  defaultTimeValue = HEURE_PAR_DEFAUT,
  popoverProps,
  ...props
}: DateTimePickerProps) {
  return (
    <DateTimePicker
      defaultTimeValue={defaultTimeValue}
      popoverProps={{
        portalProps: { translate: 'no' },
        ...popoverProps
      }}
      {...props}
    />
  );
}

/** Un jour en millisecondes. */
const UN_JOUR = 24 * 60 * 60 * 1000;

/**
 * La fin qu'il faut retenir quand la date de début vient de changer.
 *
 * Saisir un début laissait la fin vide, et son calendrier s'ouvrait sur le
 * mois courant : il fallait renaviguer jusqu'à la bonne date. La fin
 * suit désormais le début d'un jour, tant qu'elle n'a pas été fixée à la
 * main ou qu'elle est devenue antérieure au début.
 * Recette Tassin du 27/09.
 */
export function finSuivantLeDebut(
  debut: Date | null,
  finActuelle: Date | null
): Date | null {
  if (!debut) {
    return finActuelle;
  }

  // Une fin déjà cohérente est le choix de l'utilisateur : on n'y touche pas.
  if (finActuelle && finActuelle.getTime() > debut.getTime()) {
    return finActuelle;
  }

  return new Date(debut.getTime() + UN_JOUR);
}

/**
 * Dates reprises de la manifestation à la création d'une prestation.
 * Une saisie de l'utilisateur prime : on ne la réécrit pas s'il change ensuite
 * de manifestation.
 */
export function reprendreLesDates(
  manifestation:
    | { date_debut?: string | null; date_fin?: string | null }
    | null
    | undefined,
  actuel: { date_debut: Date | null; date_fin: Date | null },
  saisieManuelle: boolean
): { date_debut: Date | null; date_fin: Date | null } {
  if (saisieManuelle || !manifestation) {
    return actuel;
  }

  return {
    date_debut: manifestation.date_debut
      ? new Date(manifestation.date_debut)
      : actuel.date_debut,
    date_fin: manifestation.date_fin
      ? new Date(manifestation.date_fin)
      : actuel.date_fin
  };
}
