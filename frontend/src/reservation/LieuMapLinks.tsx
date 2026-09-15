// Itinéraire vers un lieu géolocalisé (US-20), extrait de ReservationForm pour
// être partagé avec les écrans de livraison.
import { Button, Group, Stack, Text } from '@mantine/core';

import type { LieuSummary } from './types';

// On privilégie les coordonnées GPS quand elles sont renseignées, sinon on
// retombe sur l'adresse texte.
export function buildGoogleMapsUrl(
  latitude: string | null,
  longitude: string | null,
  address: string
): string {
  if (latitude != null && longitude != null) {
    return `https://www.google.com/maps/search/?api=1&query=${latitude},${longitude}`;
  }

  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`;
}

export function buildApplePlansUrl(
  latitude: string | null,
  longitude: string | null,
  address: string
): string {
  if (latitude != null && longitude != null) {
    return `https://maps.apple.com/?ll=${latitude},${longitude}&q=${encodeURIComponent(
      address || 'Lieu de livraison'
    )}`;
  }

  return `https://maps.apple.com/?q=${encodeURIComponent(address)}`;
}

/** Adresse d'un lieu + raccourcis d'itinéraire (US-20). */
export function LieuMapLinks({ lieu }: { lieu: LieuSummary }) {
  const mapSeed = `${lieu.nom} ${lieu.adresse}`.trim();
  const googleUrl = buildGoogleMapsUrl(lieu.latitude, lieu.longitude, mapSeed);
  const appleUrl = buildApplePlansUrl(lieu.latitude, lieu.longitude, mapSeed);

  return (
    <Group justify='space-between' align='center' mt='xs'>
      <Stack gap={0}>
        <Text size='sm'>{lieu.nom}</Text>
        <Text size='xs' c='dimmed'>
          {lieu.adresse || 'Adresse non renseignée'}
        </Text>
      </Stack>

      <Group gap='xs'>
        <Button
          component='a'
          href={googleUrl}
          target='_blank'
          rel='noopener noreferrer'
          size='xs'
          variant='light'
        >
          Google Maps
        </Button>
        <Button
          component='a'
          href={appleUrl}
          target='_blank'
          rel='noopener noreferrer'
          size='xs'
          variant='default'
        >
          Apple Plans
        </Button>
      </Group>
    </Group>
  );
}
