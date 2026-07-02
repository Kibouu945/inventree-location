import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Badge,
  Button,
  Group,
  Image,
  Loader,
  Stack,
  Text,
  Title
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

import type { CatalogPart } from './types';

const DETAIL_URL = '/plugin/inventree-location/catalog/';

export function renderInvenTreeLocationPartDetail(context: InvenTreePluginContext) {
  const partId = useMemo(() => context.id ?? null, [context.id]);

  const query = useQuery<CatalogPart>(
    {
      queryKey: ['catalog-detail', partId],
      enabled: partId != null,
      queryFn: async () => {
        const response = await context.api.get(`${DETAIL_URL}${partId}/`);
        return response.data as CatalogPart;
      }
    },
    context.queryClient
  );

  if (partId == null) {
    return (
      <Alert color='yellow' title='Aucun article'>
        Cette vue s'affiche sur la fiche d'un article.
      </Alert>
    );
  }

  if (query.isLoading) {
    return (
      <Group justify='center' p='xl'>
        <Loader />
      </Group>
    );
  }

  if (query.isError || !query.data) {
    return (
      <Alert color='red' title='Erreur'>
        Impossible de charger la fiche détail.
      </Alert>
    );
  }

  const part = query.data;

  return (
    <Stack gap='md'>
      <Group justify='space-between' align='flex-start'>
        <Stack gap={4}>
          <Title order={4}>{part.name}</Title>
          <Text c='dimmed'>
            {part.category_name || 'Sans catégorie'}
          </Text>
        </Stack>
        {part.consommable ? (
          <Badge color='orange'>Consommable</Badge>
        ) : part.rentable ? (
          <Badge color='green'>Louable</Badge>
        ) : (
          <Badge color='gray'>Non-louable</Badge>
        )}
      </Group>

      {part.image_url ? (
        <Image src={part.image_url} alt={part.name} fit='contain' h={220} />
      ) : (
        <Alert color='gray' title='Aucune photo'>Aucune photo disponible.</Alert>
      )}

      <Stack gap={4}>
        <Text fw={600}>Description</Text>
        <Text>{part.description || 'Aucune description.'}</Text>
      </Stack>

      <Group grow>
        <Stack gap={4}>
          <Text fw={600}>Stock disponible</Text>
          <Text>{part.stock_available ?? 0}</Text>
        </Stack>
        <Stack gap={4}>
          <Text fw={600}>Référence</Text>
          <Text>{part.IPN || '—'}</Text>
        </Stack>
      </Group>

      <Group grow>
        <Button
          variant='light'
          onClick={() => context.navigate('/plugin/inventree-location/catalog/')}
        >
          Retour à la liste
        </Button>
        <Button
          variant='outline'
          color='blue'
          onClick={() => context.navigate(`/plugin/inventree-location/reservations/?part=${partId}`)}
        >
          Voir les réservations en cours
        </Button>
      </Group>
    </Stack>
  );
}
