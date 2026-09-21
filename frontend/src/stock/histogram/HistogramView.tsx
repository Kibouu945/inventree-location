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
import { useMemo, useState } from 'react';

import {
  aujourdhui,
  borneDePeriode,
  filtrerJoursVisibles,
  type HistogramDay,
  hauteurBarrePourcent,
  type PeriodePreset,
  TENSION_COLORS
} from './histogramLogic';

const CATALOG_URL = '/plugin/inventree-location/catalog/';

const HAUTEUR_GRAPHIQUE = 180;

interface CatalogSearchResult {
  id: number;
  name: string;
}

interface HistogramResponse {
  part_id: number;
  part_name: string;
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

function libelleJour(date: string): string {
  return date.slice(8, 10);
}

export function HistogramView({
  context
}: {
  context: InvenTreePluginContext;
}) {
  const [search, setSearch] = useState('');
  const [debouncedSearch] = useDebouncedValue(search, 300);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pickedPart, setPickedPart] = useState<CatalogSearchResult | null>(
    null
  );
  const [preset, setPreset] = useState<PeriodePreset>('semaine');
  const [dateDebut, setDateDebut] = useState<string>(() => aujourdhui());
  const [vue, setVue] = useState<'histogramme' | 'tableau'>('histogramme');
  const [joursVisibles, setJoursVisibles] = useState<string[]>([]);

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

  const selectedPart =
    results.find((part) => String(part.id) === selectedId) ??
    (pickedPart && String(pickedPart.id) === selectedId
      ? pickedPart
      : undefined);

  const options = useMemo(() => {
    const mapped = results.map((part) => ({
      value: String(part.id),
      label: part.name
    }));

    if (
      selectedPart &&
      !mapped.some((option) => option.value === String(selectedPart.id))
    ) {
      mapped.unshift({
        value: String(selectedPart.id),
        label: selectedPart.name
      });
    }

    return mapped;
  }, [results, selectedPart]);

  const dateFin = useMemo(
    () => borneDePeriode(dateDebut, preset),
    [dateDebut, preset]
  );

  const histogramQuery = useQuery<HistogramResponse>(
    {
      queryKey: ['histogram', selectedPart?.id, dateDebut, dateFin],
      enabled: !!selectedPart,
      queryFn: async () => {
        const response = await context.api.get(
          `${CATALOG_URL}${selectedPart?.id}/histogram/`,
          { params: { date_debut: dateDebut, date_fin: dateFin } }
        );
        return response.data as HistogramResponse;
      }
    },
    context.queryClient
  );

  const joursAffiches = useMemo(
    () =>
      filtrerJoursVisibles(
        histogramQuery.data?.days ?? [],
        joursVisibles.map(Number)
      ),
    [histogramQuery.data, joursVisibles]
  );

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
          value={selectedId}
          onChange={(value) => {
            setSelectedId(value);
            setPickedPart(
              results.find((part) => String(part.id) === value) ?? null
            );
          }}
          nothingFoundMessage={
            partSearch.isFetching ? 'Recherche…' : 'Aucun résultat'
          }
          w={280}
        />
        <DatePickerInput
          label='Début de la période'
          value={dateDebut}
          onChange={(value) => value && setDateDebut(value)}
          valueFormat='DD/MM/YYYY'
          w={160}
        />
        <SegmentedControl
          value={preset}
          onChange={(value) => setPreset(value as PeriodePreset)}
          data={[
            { label: 'Semaine', value: 'semaine' },
            { label: 'Mois', value: 'mois' }
          ]}
        />
        <SegmentedControl
          value={vue}
          onChange={(value) => setVue(value as 'histogramme' | 'tableau')}
          data={[
            { label: 'Histogramme', value: 'histogramme' },
            { label: 'Tableau', value: 'tableau' }
          ]}
        />
      </Group>

      <Chip.Group multiple value={joursVisibles} onChange={setJoursVisibles}>
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

      {!selectedPart && (
        <Alert color='gray' title='Aucun article sélectionné'>
          Choisissez un article pour afficher sa disponibilité.
        </Alert>
      )}

      {selectedPart && histogramQuery.isLoading && (
        <Group justify='center' p='xl'>
          <Loader />
        </Group>
      )}

      {selectedPart && histogramQuery.isError && (
        <Alert color='red' title='Erreur'>
          Impossible de charger la disponibilité de cet article.
        </Alert>
      )}

      {selectedPart && histogramQuery.data && joursAffiches.length === 0 && (
        <Alert color='gray' title='Aucun jour à afficher'>
          Aucun jour de la période ne correspond au filtre choisi.
        </Alert>
      )}

      {selectedPart && joursAffiches.length > 0 && vue === 'histogramme' && (
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

      {selectedPart && joursAffiches.length > 0 && vue === 'tableau' && (
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
