// Écran "Tournées livreur" : livraisons à effectuer, filtrables par date /
// lieu / statut, avec bascule liste / calendrier / carte et bon de livraison
// imprimable par ligne.
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Badge,
  Button,
  Chip,
  Group,
  Loader,
  MultiSelect,
  SegmentedControl,
  Stack,
  Table,
  Text,
  Title
} from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { ownsKeys, syncOwnedParams } from '../urlState';
import { DeliveryCalendar } from './DeliveryCalendar';
import {
  buildDeliveryQuery,
  DEFAULT_DELIVERY_FILTERS,
  DELIVERY_URL_KEYS,
  type DeliveryFiltersState,
  parseDeliveryFilters,
  serializeDeliveryFilters
} from './deliveryParams';
import { DeliveryMap } from './DeliveryMap';
import { DeliveryNote } from './DeliveryNote';
import type { Delivery } from './types';

const DELIVERIES_URL = '/plugin/inventree-location/deliveries/';
const LIEUX_URL = '/plugin/inventree-location/lieux/';

const STATUT_COLORS: Record<string, string> = {
  validee: 'green',
  livree: 'teal'
};

const STATUT_OPTIONS = [
  { value: 'validee', label: 'À livrer (validée)' },
  { value: 'livree', label: 'Livrée' }
];

const VIEW_OPTIONS = [
  { value: 'liste', label: 'Liste' },
  { value: 'calendrier', label: 'Calendrier' },
  { value: 'carte', label: 'Carte' }
];

interface LieuOption {
  id: number;
  nom: string;
}

const ownsDeliveryKey = ownsKeys(DELIVERY_URL_KEYS);

function syncUrl(filters: DeliveryFiltersState) {
  syncOwnedParams(
    ownsDeliveryKey,
    new URLSearchParams(serializeDeliveryFilters(filters))
  );
}

function initialFilters(): DeliveryFiltersState {
  if (typeof window === 'undefined') {
    return DEFAULT_DELIVERY_FILTERS;
  }

  return parseDeliveryFilters(window.location.search);
}

export function DeliveriesList({
  context
}: {
  context: InvenTreePluginContext;
}) {
  const [filters, setFilters] = useState<DeliveryFiltersState>(initialFilters);
  const [noteDelivery, setNoteDelivery] = useState<Delivery | null>(null);

  useEffect(() => {
    syncUrl(filters);
  }, [filters]);

  const params = buildDeliveryQuery(filters);

  const query = useQuery<Delivery[]>(
    {
      queryKey: ['deliveries', params],
      queryFn: async () => {
        const response = await context.api.get(DELIVERIES_URL, {
          params,
          // Clés répétées `statut=a&statut=b` (le backend lit getlist).
          paramsSerializer: { indexes: null }
        });
        return response.data as Delivery[];
      }
    },
    context.queryClient
  );

  const lieuxQuery = useQuery<{ id: number; nom: string }[] | { results: LieuOption[] }>(
    {
      queryKey: ['delivery-lieu-options'],
      queryFn: async () => {
        const response = await context.api.get(LIEUX_URL, {
          params: { page_size: 100 }
        });
        return response.data;
      }
    },
    context.queryClient
  );

  const lieuOptions = useMemo(() => {
    const payload = lieuxQuery.data;

    if (!payload) {
      return [];
    }

    const lieux = Array.isArray(payload) ? payload : payload.results;

    return lieux.map((lieu) => ({ value: String(lieu.id), label: lieu.nom }));
  }, [lieuxQuery.data]);

  const rows = query.data ?? [];

  function updateFilters(patch: Partial<DeliveryFiltersState>) {
    setFilters((current) => ({ ...current, ...patch }));
  }

  return (
    <Stack gap='md'>
      <Group justify='space-between'>
        <Title order={4} c={context.theme.primaryColor}>
          Tournées livreur
        </Title>
        <SegmentedControl
          value={filters.viewMode}
          onChange={(value) =>
            updateFilters({ viewMode: value as DeliveryFiltersState['viewMode'] })
          }
          data={VIEW_OPTIONS}
        />
      </Group>

      <Group align='flex-end' gap='md' wrap='wrap'>
        <DatePickerInput
          type='range'
          label='Période'
          placeholder="Aujourd'hui ou une période"
          value={filters.dateRange}
          onChange={(value) => updateFilters({ dateRange: [value[0], value[1]] })}
          clearable
          w={260}
        />
        <MultiSelect
          label='Lieu'
          placeholder='Tous'
          data={lieuOptions}
          value={filters.lieux.map(String)}
          onChange={(values) =>
            updateFilters({
              lieux: values
                .map((value) => Number.parseInt(value, 10))
                .filter((value) => Number.isInteger(value))
            })
          }
          clearable
          w={240}
        />
        <Button variant='default' onClick={() => setFilters(DEFAULT_DELIVERY_FILTERS)}>
          Reset filtres
        </Button>
      </Group>

      <Stack gap={6}>
        <Text size='sm' fw={500}>
          Statuts
        </Text>
        <Chip.Group
          multiple
          value={filters.statuts}
          onChange={(values) => updateFilters({ statuts: values })}
        >
          <Group gap='xs' wrap='wrap'>
            {STATUT_OPTIONS.map((option) => (
              <Chip key={option.value} value={option.value}>
                {option.label}
              </Chip>
            ))}
          </Group>
        </Chip.Group>
      </Stack>

      {query.isError && (
        <Alert color='red' title='Erreur'>
          Impossible de charger les livraisons.
        </Alert>
      )}

      {query.isLoading ? (
        <Group justify='center' p='xl'>
          <Loader />
        </Group>
      ) : rows.length === 0 ? (
        <Text c='dimmed'>Aucune livraison sur cette période.</Text>
      ) : filters.viewMode === 'calendrier' ? (
        <DeliveryCalendar
          deliveries={rows}
          onSelectDay={(day) => updateFilters({ dateRange: [day, day] })}
        />
      ) : filters.viewMode === 'carte' ? (
        <DeliveryMap deliveries={rows} />
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Numéro</Table.Th>
              <Table.Th>Horaire prévu</Table.Th>
              <Table.Th>Prestation</Table.Th>
              <Table.Th>Lieu</Table.Th>
              <Table.Th>Organisateur</Table.Th>
              <Table.Th>Quantité totale</Table.Th>
              <Table.Th>Statut</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((delivery) => (
              <Table.Tr key={delivery.id}>
                <Table.Td>{delivery.numero}</Table.Td>
                <Table.Td>
                  {delivery.date_retrait_prevue
                    ? new Date(delivery.date_retrait_prevue).toLocaleString()
                    : '—'}
                </Table.Td>
                <Table.Td>{delivery.prestation_nom || '—'}</Table.Td>
                <Table.Td>{delivery.lieu_detail?.nom ?? '—'}</Table.Td>
                <Table.Td>{delivery.organisateur_nom || '—'}</Table.Td>
                <Table.Td>{delivery.quantite_totale}</Table.Td>
                <Table.Td>
                  <Badge color={STATUT_COLORS[delivery.statut] ?? 'gray'}>
                    {delivery.statut}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Button size='xs' variant='light' onClick={() => setNoteDelivery(delivery)}>
                    Détails / Imprimer
                  </Button>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      <DeliveryNote delivery={noteDelivery} onClose={() => setNoteDelivery(null)} />
    </Stack>
  );
}
