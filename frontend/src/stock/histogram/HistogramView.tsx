import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Badge,
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
  CLASSES_TENSION,
  type ClasseTension,
  capitaliser,
  classeDeTension,
  estWeekEnd,
  etiquetteColonne,
  filtrerJoursVisibles,
  graduations,
  type HistogramDay,
  hauteurRemplissagePourcent,
  jourLePlusTendu,
  libelleJourLong,
  libelleJournees,
  ORDRE_CLASSES,
  type PeriodePreset,
  resumeTension,
  tauxOccupationArrondi
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

const HAUTEUR_TRACE = 200;
const LARGEUR_BARRE = 18;
const GOUTTIERE = 4;
// Air au-dessus des colonnes : sans elle le défilement rogne l'étiquette du pic.
const MARGE_HAUTE = 18;

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

function Pastille({
  classe,
  taille = 10
}: {
  classe: ClasseTension;
  taille?: number;
}) {
  return (
    <Box
      w={taille}
      h={taille}
      style={{
        background: CLASSES_TENSION[classe].couleur,
        borderRadius: 3,
        flexShrink: 0
      }}
    />
  );
}

function Resume({ jours }: { jours: HistogramDay[] }) {
  const compte = resumeTension(jours);

  return (
    <Group gap='lg' wrap='wrap'>
      {ORDRE_CLASSES.map((classe) => (
        <Group key={classe} gap={6} wrap='nowrap'>
          <Pastille classe={classe} />
          <Text
            size='sm'
            fw={600}
            style={{ fontVariantNumeric: 'tabular-nums' }}
          >
            {compte[classe]}
          </Text>
          <Text size='sm' c='dimmed'>
            {libelleJournees(classe, compte[classe])}
          </Text>
        </Group>
      ))}
    </Group>
  );
}

function Legende() {
  return (
    <Group gap='lg' wrap='wrap'>
      {ORDRE_CLASSES.map((classe) => (
        <Group key={classe} gap={6} wrap='nowrap'>
          <Pastille classe={classe} />
          <Text size='xs'>{CLASSES_TENSION[classe].libelle}</Text>
          <Text size='xs' c='dimmed'>
            {CLASSES_TENSION[classe].seuil}
          </Text>
        </Group>
      ))}
    </Group>
  );
}

function infobulle(jour: HistogramDay): string {
  return [
    libelleJourLong(jour.date),
    `${jour.reserved} engagé(s) sur ${jour.total_stock}`,
    `${jour.available} disponible(s) — ${tauxOccupationArrondi(jour)} %`
  ].join(' · ');
}

function Colonne({ jour, pic }: { jour: HistogramDay; pic: boolean }) {
  const classe = classeDeTension(jour.tension_level);
  const { couleur, piste } = CLASSES_TENSION[classe];
  const remplissage = hauteurRemplissagePourcent(jour);
  const { numero, semaine } = etiquetteColonne(jour.date);
  const weekEnd = estWeekEnd(jour.date);

  return (
    <Tooltip label={infobulle(jour)} withArrow>
      <Stack gap={4} align='center' style={{ flexShrink: 0 }}>
        <Box
          w={LARGEUR_BARRE}
          h={HAUTEUR_TRACE}
          style={{ background: piste, borderRadius: 4, position: 'relative' }}
        >
          {pic && (
            <Text
              size='10px'
              c='dimmed'
              style={{
                position: 'absolute',
                bottom: `calc(${remplissage}% + 4px)`,
                left: '50%',
                transform: 'translateX(-50%)',
                whiteSpace: 'nowrap',
                fontVariantNumeric: 'tabular-nums'
              }}
            >
              {tauxOccupationArrondi(jour)} %
            </Text>
          )}
          <Box
            style={{
              position: 'absolute',
              bottom: 0,
              left: 0,
              right: 0,
              height: `${remplissage}%`,
              background: couleur,
              borderRadius: remplissage >= 99 ? 4 : '4px 4px 0 0'
            }}
          />
        </Box>
        <Text
          size='xs'
          c={weekEnd ? 'dimmed' : undefined}
          fw={weekEnd ? 400 : 500}
          style={{ fontVariantNumeric: 'tabular-nums' }}
        >
          {numero}
        </Text>
        <Text size='10px' c='dimmed'>
          {semaine}
        </Text>
      </Stack>
    </Tooltip>
  );
}

function Graphique({ jours }: { jours: HistogramDay[] }) {
  const total = jours[0]?.total_stock ?? 0;
  const ticks = graduations(total);
  const pic = jourLePlusTendu(jours);

  return (
    <Stack gap='md'>
      <Group align='flex-start' gap='xs' wrap='nowrap'>
        <Box
          h={HAUTEUR_TRACE}
          mt={MARGE_HAUTE}
          style={{ position: 'relative', width: 34 }}
        >
          {ticks.map((valeur) => (
            <Text
              key={valeur}
              size='10px'
              c='dimmed'
              ta='right'
              style={{
                position: 'absolute',
                right: 0,
                bottom: total > 0 ? `${(valeur / total) * 100}%` : 0,
                transform: 'translateY(50%)',
                fontVariantNumeric: 'tabular-nums'
              }}
            >
              {valeur}
            </Text>
          ))}
        </Box>

        <Box style={{ overflowX: 'auto', flex: 1 }}>
          <Box
            style={{
              width: 'max-content',
              position: 'relative',
              paddingTop: MARGE_HAUTE
            }}
          >
            {ticks.map((valeur) => (
              <Box
                key={valeur}
                style={{
                  position: 'absolute',
                  left: 0,
                  right: 0,
                  // Le conteneur descend sous la zone tracée : on repère
                  // la grille depuis le haut.
                  top:
                    MARGE_HAUTE +
                    (total > 0
                      ? HAUTEUR_TRACE - (valeur / total) * HAUTEUR_TRACE
                      : HAUTEUR_TRACE),
                  height: 1,
                  background: 'var(--mantine-color-default-border)'
                }}
              />
            ))}
            <Group gap={GOUTTIERE} align='flex-start' wrap='nowrap'>
              {jours.map((jour) => (
                <Colonne
                  key={jour.date}
                  jour={jour}
                  pic={pic?.date === jour.date}
                />
              ))}
            </Group>
          </Box>
        </Box>
      </Group>

      <Legende />
    </Stack>
  );
}

function JaugeLigne({ jour }: { jour: HistogramDay }) {
  const classe = classeDeTension(jour.tension_level);
  const { couleur, piste } = CLASSES_TENSION[classe];

  return (
    <Group gap='xs' wrap='nowrap'>
      <Box
        w={64}
        h={6}
        style={{ background: piste, borderRadius: 3, overflow: 'hidden' }}
      >
        <Box
          h={6}
          style={{
            width: `${hauteurRemplissagePourcent(jour)}%`,
            background: couleur,
            borderRadius: 3
          }}
        />
      </Box>
      <Text size='sm' style={{ fontVariantNumeric: 'tabular-nums' }}>
        {tauxOccupationArrondi(jour)} %
      </Text>
    </Group>
  );
}

function Tableau({ jours }: { jours: HistogramDay[] }) {
  return (
    <Table striped highlightOnHover verticalSpacing='xs'>
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Jour</Table.Th>
          <Table.Th ta='right'>Stock total</Table.Th>
          <Table.Th ta='right'>Engagé</Table.Th>
          <Table.Th ta='right'>Disponible</Table.Th>
          <Table.Th>Occupation</Table.Th>
          <Table.Th>Tension</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {jours.map((jour) => {
          const classe = classeDeTension(jour.tension_level);
          const nombre = { fontVariantNumeric: 'tabular-nums' } as const;

          return (
            <Table.Tr key={jour.date}>
              <Table.Td>
                <Text size='sm'>{capitaliser(libelleJourLong(jour.date))}</Text>
              </Table.Td>
              <Table.Td ta='right' style={nombre}>
                {jour.total_stock}
              </Table.Td>
              <Table.Td ta='right' style={nombre}>
                {jour.reserved}
              </Table.Td>
              <Table.Td
                ta='right'
                style={nombre}
                fw={jour.available <= 0 ? 700 : undefined}
              >
                {jour.available}
              </Table.Td>
              <Table.Td>
                <JaugeLigne jour={jour} />
              </Table.Td>
              <Table.Td>
                {/* `light-dark(…)` n'est pas une couleur de thème Mantine. */}
                <Badge
                  variant='default'
                  leftSection={<Pastille classe={classe} taille={8} />}
                >
                  {CLASSES_TENSION[classe].libelle}
                </Badge>
              </Table.Td>
            </Table.Tr>
          );
        })}
      </Table.Tbody>
    </Table>
  );
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

  // L'article restauré depuis l'URL n'est pas forcément dans les résultats de
  // recherche : c'est la réponse du serveur qui le nomme.
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

      {filters.partId && joursAffiches.length > 0 && (
        <Paper withBorder p='md' radius='md'>
          <Stack gap='md'>
            <Resume jours={joursAffiches} />
            {filters.vue === 'histogramme' ? (
              <Graphique jours={joursAffiches} />
            ) : (
              <Tableau jours={joursAffiches} />
            )}
          </Stack>
        </Paper>
      )}
    </Stack>
  );
}
