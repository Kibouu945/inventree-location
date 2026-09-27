// Écran « tournée du jour » (LIV-04) : les livraisons et les ramassages de la
// période, rangés dans un ordre de passage que le livreur peut optimiser puis
import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Grid,
  Group,
  Paper,
  ScrollArea,
  Stack,
  Text
} from '@mantine/core';
import { useMemo } from 'react';

import type { Ramassage } from '../ramassage/types';
import { TourneeMap } from './TourneeMap';
import {
  appliquerOrdre,
  compterSansCoordonnees,
  construireItineraireUrl,
  construireStops,
  deplacerStop,
  distanceRouteKm,
  dureeEstimeeMin,
  formaterDuree,
  optimiserOrdre,
  serialiserOrdre,
  stopsHorsItineraire,
  type TourneeStop
} from './tournee';
import type { Delivery } from './types';

const COULEUR_KIND: Record<string, string> = {
  livraison: 'blue',
  ramassage: 'grape'
};

function heureCourte(iso: string | null): string {
  if (!iso) {
    return '—';
  }

  return new Date(iso).toLocaleString(undefined, {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
}

export function TourneeView({
  deliveries,
  ramassages,
  ordre,
  onOrdreChange
}: {
  deliveries: Delivery[];
  ramassages: Ramassage[];
  ordre: string[];
  onOrdreChange: (ordre: string[]) => void;
}) {
  const stopsChronologiques = useMemo(
    () => construireStops(deliveries, ramassages),
    [deliveries, ramassages]
  );

  const stops = useMemo(
    () => appliquerOrdre(stopsChronologiques, ordre),
    [stopsChronologiques, ordre]
  );

  const sansCoordonnees = useMemo(
    () => compterSansCoordonnees(deliveries, ramassages),
    [deliveries, ramassages]
  );

  const itineraireUrl = construireItineraireUrl(stops);
  const horsItineraire = stopsHorsItineraire(stops);
  const distance = distanceRouteKm(stops);
  const duree = dureeEstimeeMin(stops);

  function appliquer(nouveaux: TourneeStop[]) {
    onOrdreChange(serialiserOrdre(nouveaux).split(',').filter(Boolean));
  }

  if (stops.length === 0) {
    // Deux situations très différentes, que le même message confondait :
    // rien à livrer ce jour-là, ou des livraisons sans adresse géocodée.
    // « Aucun arrêt géolocalisé » laissait croire à une panne de carte.
    // Recette Tassin du 27/09, points 4.8.2 et 4.8.3.
    const rienDuTout = deliveries.length === 0 && ramassages.length === 0;

    return (
      <Alert
        color={rienDuTout ? 'blue' : 'orange'}
        title={
          rienDuTout
            ? 'Aucune livraison sur cette période'
            : 'Aucun lieu géolocalisé'
        }
      >
        {rienDuTout ? (
          <Text size='sm'>
            Il n’y a rien à livrer ni à ramasser sur la période choisie. Le
            filtre <strong>Quand</strong> est sans doute sur «&nbsp;Aujourd’hui
            »&nbsp;: passez sur <strong>À venir</strong> ou{' '}
            <strong>Tout</strong> pour voir les tournées des prochains jours.
          </Text>
        ) : (
          <Text size='sm'>
            {sansCoordonnees} entrée(s) sont prévues sur cette période mais leur
            lieu n’a pas de coordonnées GPS. Renseignez l’adresse du lieu pour
            les faire apparaître sur la carte ; elles restent visibles dans les
            vues <strong>Liste</strong> et <strong>Arborescence</strong>.
          </Text>
        )}
      </Alert>
    );
  }

  return (
    <Stack gap='sm'>
      <Group justify='space-between' align='flex-end' wrap='wrap'>
        <Group gap='xs'>
          <Badge variant='light'>{stops.length} arrêts</Badge>
          <Badge variant='light' color='gray'>
            ≈ {distance.toFixed(1)} km
          </Badge>
          <Badge variant='light' color='gray'>
            ≈ {formaterDuree(duree)}
          </Badge>
        </Group>

        <Group gap='xs'>
          <Button
            size='xs'
            variant='light'
            onClick={() => appliquer(optimiserOrdre(stops))}
          >
            Optimiser l'ordre
          </Button>
          <Button size='xs' variant='default' onClick={() => onOrdreChange([])}>
            Ordre chronologique
          </Button>
          <Button
            size='xs'
            component='a'
            href={itineraireUrl ?? undefined}
            target='_blank'
            rel='noopener noreferrer'
            disabled={!itineraireUrl}
          >
            Itinéraire Google Maps
          </Button>
        </Group>
      </Group>

      <Text size='xs' c='dimmed'>
        La tournée mélange les livraisons (retrait) et les ramassages (retour)
        de la période filtrée. Distance et durée sont des estimations à vol
        d'oiseau, temps de chargement inclus.
      </Text>

      {sansCoordonnees > 0 && (
        <Alert color='yellow' variant='light'>
          {sansCoordonnees} entrée(s) sans coordonnées GPS ne figurent pas dans
          la tournée.
        </Alert>
      )}

      {horsItineraire > 0 && (
        <Alert color='yellow' variant='light'>
          Google Maps n'accepte pas plus de 11 points par lien : les{' '}
          {horsItineraire} dernier(s) arrêt(s) ne sont pas dans l'itinéraire.
        </Alert>
      )}

      <Grid gutter='md'>
        <Grid.Col span={{ base: 12, md: 5 }}>
          <ScrollArea.Autosize mah={480} type='auto'>
            <Stack gap={6} pr='xs'>
              {stops.map((stop, index) => (
                <Paper key={stop.key} p='xs' withBorder>
                  <Group justify='space-between' wrap='nowrap' gap='xs'>
                    <Group gap='xs' wrap='nowrap'>
                      <Badge
                        circle
                        size='lg'
                        color={COULEUR_KIND[stop.kind] ?? 'gray'}
                      >
                        {index + 1}
                      </Badge>
                      <Stack gap={0}>
                        <Text size='sm' fw={500}>
                          {stop.lieuNom}
                        </Text>
                        <Text size='xs' c='dimmed'>
                          {stop.kind === 'livraison'
                            ? 'Livraison'
                            : 'Ramassage'}{' '}
                          {stop.numero} · {heureCourte(stop.heure)} ·{' '}
                          {stop.quantite} article(s)
                        </Text>
                        <Text size='xs' c='dimmed'>
                          {stop.adresse || 'Adresse non renseignée'}
                        </Text>
                      </Stack>
                    </Group>

                    <Stack gap={2}>
                      <ActionIcon
                        size='sm'
                        variant='default'
                        aria-label={`Monter l'arrêt ${index + 1}`}
                        disabled={index === 0}
                        onClick={() =>
                          appliquer(deplacerStop(stops, index, -1))
                        }
                      >
                        ↑
                      </ActionIcon>
                      <ActionIcon
                        size='sm'
                        variant='default'
                        aria-label={`Descendre l'arrêt ${index + 1}`}
                        disabled={index === stops.length - 1}
                        onClick={() => appliquer(deplacerStop(stops, index, 1))}
                      >
                        ↓
                      </ActionIcon>
                    </Stack>
                  </Group>
                </Paper>
              ))}
            </Stack>
          </ScrollArea.Autosize>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 7 }}>
          <TourneeMap stops={stops} />
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
