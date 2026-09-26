import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Box,
  Chip,
  Group,
  Loader,
  Paper,
  SegmentedControl,
  Select,
  Stack,
  Table,
  Text,
  Title,
  Tooltip
} from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import { useDebouncedValue } from '@mantine/hooks';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { ownsKeys, syncOwnedParams } from '../../urlState';
import {
  borneDePeriode,
  filtrerJoursVisibles,
  type HistogramDay,
  hauteurBarrePourcent,
  type PeriodePreset,
  TENSION_COLORS
} from './histogramLogic';
import {
  defaultHistogramFilters,
  HISTOGRAM_URL_KEYS,
  type HistogramFiltersState,
  type HistogramVue,
  parseHistogramFilters,
  serializeHistogramFilters
} from './histogramParams';

const CATALOG_URL = '/plugin/inventree-location/catalog/';

const HAUTEUR_GRAPHIQUE = 180;

interface CatalogSearchResult {
  id: number;
  name: string;
}

interface HistogramResponse {
  part_id: number;
  part_name: string;
  is_virtual: boolean;
  days: HistogramDay[];
}

const JOURS_SEMAINE = [
  { value: '1', label: 'Lun' },
  { value: '2', label: 'Mar' },
  { value: '3', label: 'Mer' },
  { value: '4', label: 'Jeu' },
  { value: '5', label: 'Ven' },
  { value: '6', label: 'Sam' },
  { value: '7', label: 'Dim' }
];

const ownsHistogramKey = ownsKeys(HISTOGRAM_URL_KEYS);

function initialFilters(): HistogramFiltersState {
  if (typeof window === 'undefined') {
    return defaultHistogramFilters();
  }

  return parseHistogramFilters(window.location.search);
}

function libelleJour(date: string): string {
  return date.slice(8, 10);
}

export function HistogramView({
  context
}: {
  context: InvenTreePluginContext;
}) {
  const [filters, setFilters] = useState<HistogramFiltersState>(initialFilters);
  const [search, setSearch] = useState('');
  const [debouncedSearch] = useDebouncedValue(search, 300);

  const majFiltres = (patch: Partial<HistogramFiltersState>) =>
    setFilters((precedent) => ({ ...precedent, ...patch }));

  useEffect(() => {
    syncOwnedParams(
      ownsHistogramKey,
      new URLSearchParams(serializeHistogramFilters(filters))
    );
  }, [filters]);

  const partSearch = useQuery<{ results: CatalogSearchResult[] }>(
    {
      queryKey: ['histogram-part-search', debouncedSearch],
      queryFn: async () => {
        const response = await context.api.get(CATALOG_URL, {
          params: {
            search: debouncedSearch || undefined,
            virtual: 'false',
            page_size: 20
          }
        });
        return response.data;
      }
    },
    context.queryClient
  );

  const results = partSearch.data?.results ?? [];

  const dateFin = useMemo(
    () => borneDePeriode(filters.dateDebut, filters.preset),
    [filters.dateDebut, filters.preset]
  );

  const histogramQuery = useQuery<HistogramResponse>(
    {
      queryKey: ['histogram', filters.partId, filters.dateDebut, dateFin],
      enabled: !!filters.partId,
      queryFn: async () => {
        const response = await context.api.get(
          `${CATALOG_URL}${filters.partId}/histogram/`,
          { params: { date_debut: filters.dateDebut, date_fin: dateFin } }
        );
        return response.data as HistogramResponse;
      }
    },
    context.queryClient
  );

  // L'article restauré depuis l'URL n'est pas forcément dans les vingt
  // premiers résultats de recherche : c'est la réponse du serveur qui le
  // nomme, sans requête supplémentaire.
  const nomServeur = histogramQuery.data?.part_name;

  const options = useMemo(() => {
    const mapped = results.map((part) => ({
      value: String(part.id),
      label: part.name
    }));

    if (
      filters.partId &&
      !mapped.some((option) => option.value === filters.partId)
    ) {
      mapped.unshift({
        value: filters.partId,
        label: nomServeur ?? `Article ${filters.partId}`
      });
    }

    return mapped;
  }, [results, filters.partId, nomServeur]);

  const joursAffiches = useMemo(
    () =>
      filtrerJoursVisibles(
        histogramQuery.data?.days ?? [],
        filters.joursVisibles.map(Number)
      ),
    [histogramQuery.data, filters.joursVisibles]
  );

  const estImmateriel = histogramQuery.data?.is_virtual === true;

  return (
    <Stack gap='md'>
      <Title order={4} c={context.theme.primaryColor}>
        Histogramme de disponibilité
      </Title>

      <Group align='flex-end' gap='md' wrap='wrap'>
        <Select
          label='Article'
          placeholder='Rechercher un article…'
          data={options}
          searchable
          searchValue={search}
          onSearchChange={setSearch}
          value={filters.partId}
          onChange={(value) => majFiltres({ partId: value })}
          nothingFoundMessage={
            partSearch.isFetching ? 'Recherche…' : 'Aucun résultat'
          }
          w={280}
        />
        <DatePickerInput
          label='Début de la période'
          value={filters.dateDebut}
          onChange={(value) => value && majFiltres({ dateDebut: value })}
          valueFormat='DD/MM/YYYY'
          w={160}
        />
        <SegmentedControl
          value={filters.preset}
          onChange={(value) => majFiltres({ preset: value as PeriodePreset })}
          data={[
            { label: 'Semaine', value: 'semaine' },
            { label: 'Mois', value: 'mois' }
          ]}
        />
        <SegmentedControl
          value={filters.vue}
          onChange={(value) => majFiltres({ vue: value as HistogramVue })}
          data={[
            { label: 'Histogramme', value: 'histogramme' },
            { label: 'Tableau', value: 'tableau' }
          ]}
        />
      </Group>

      <Chip.Group
        multiple
        value={filters.joursVisibles}
        onChange={(value) => majFiltres({ joursVisibles: value })}
      >
        <Group gap='xs'>
          <Text size='xs' c='dimmed'>
            Jours affichés :
          </Text>
          {JOURS_SEMAINE.map((jour) => (
            <Chip key={jour.value} value={jour.value} size='xs'>
              {jour.label}
            </Chip>
          ))}
        </Group>
      </Chip.Group>

      {!filters.partId && (
        <Alert color='gray' title='Aucun article sélectionné'>
          Choisissez un article pour afficher sa disponibilité.
        </Alert>
      )}

      {filters.partId && histogramQuery.isLoading && (
        <Group justify='center' p='xl'>
          <Loader />
        </Group>
      )}

      {filters.partId && histogramQuery.isError && (
        <Alert color='red' title='Erreur'>
          Impossible de charger la disponibilité de cet article.
        </Alert>
      )}

      {estImmateriel && (
        <Alert color='gray' title='Article immatériel'>
          {nomServeur ?? 'Cet article'} est un service : il n’a pas de stock
          physique, donc pas de disponibilité à représenter.
        </Alert>
      )}

      {filters.partId &&
        !estImmateriel &&
        histogramQuery.data &&
        joursAffiches.length === 0 && (
          <Alert color='gray' title='Aucun jour à afficher'>
            Aucun jour de la période ne correspond au filtre choisi.
          </Alert>
        )}

      {filters.partId &&
        joursAffiches.length > 0 &&
        filters.vue === 'histogramme' && (
          <Paper withBorder p='md'>
            <Group
              align='flex-end'
              gap={4}
              h={HAUTEUR_GRAPHIQUE}
              wrap='nowrap'
              style={{ overflowX: 'auto' }}
            >
              {joursAffiches.map((jour) => (
                <Tooltip
                  key={jour.date}
                  label={`${jour.date} — disponible : ${jour.available}/${jour.total_stock}, réservé : ${jour.reserved}`}
                >
                  <Stack gap={4} align='center' style={{ minWidth: 28 }}>
                    <Box
                      w={20}
                      h={Math.max(
                        (hauteurBarrePourcent(jour) / 100) * HAUTEUR_GRAPHIQUE,
                        2
                      )}
                      bg={TENSION_COLORS[jour.tension_level]}
                    />
                    <Text size='xs' c='dimmed'>
                      {libelleJour(jour.date)}
                    </Text>
                  </Stack>
                </Tooltip>
              ))}
            </Group>
          </Paper>
        )}

      {filters.partId &&
        joursAffiches.length > 0 &&
        filters.vue === 'tableau' && (
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Jour</Table.Th>
                <Table.Th>Stock total</Table.Th>
                <Table.Th>Réservé</Table.Th>
                <Table.Th>Disponible</Table.Th>
                <Table.Th>Tension</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {joursAffiches.map((jour) => (
                <Table.Tr key={jour.date}>
                  <Table.Td>{jour.date}</Table.Td>
                  <Table.Td>{jour.total_stock}</Table.Td>
                  <Table.Td>{jour.reserved}</Table.Td>
                  <Table.Td>{jour.available}</Table.Td>
                  <Table.Td>
                    <Box
                      w={12}
                      h={12}
                      bg={TENSION_COLORS[jour.tension_level]}
                      style={{ borderRadius: '50%', display: 'inline-block' }}
                    />
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
    </Stack>
  );
}
