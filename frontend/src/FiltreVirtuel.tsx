// Filtre « Virtuel » des prestations et des bons.
// Recette Tassin du 27/09, point 4.5.1 : écarter de l'écran les fiches qui ne
// portent que des services, quand on prépare le matériel à sortir.
import { Select } from '@mantine/core';

export type Virtuel = 'oui' | 'non' | null;

/** Les libellés disent ce qu'on garde : « Virtuel : oui » seul serait ambigu. */
const OPTIONS = [
  { value: 'oui', label: 'Oui (services seuls)' },
  { value: 'non', label: 'Non (avec du matériel)' }
];

export function FiltreVirtuel({
  value,
  onChange,
  w = 210
}: {
  value: Virtuel;
  onChange: (valeur: Virtuel) => void;
  w?: number;
}) {
  return (
    <Select
      label='Virtuel'
      placeholder='Tous'
      data={OPTIONS}
      value={value}
      onChange={(valeur) => onChange((valeur as Virtuel) ?? null)}
      clearable
      w={w}
    />
  );
}
