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
