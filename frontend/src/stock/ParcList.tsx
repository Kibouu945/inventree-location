// Écran « État du parc » du poste magasinier.
// Le catalogue dit ce qu'on possède ; ici on voit aussi ce qui est dehors,
// quand ça revient et ce qui dort au SAV.
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Badge,
  Group,
  Loader,
  MultiSelect,
  Pagination,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
  Title
} from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { useCategoryOptions } from '../catalog/useCategoryOptions';
import { ownsKeys, syncOwnedParams } from '../urlState';
import { WidgetScroll } from '../WidgetScroll';
import {
  buildParcQuery,
  DEFAULT_PARC_FILTERS,
  libelleMotif,
  PARC_URL_KEYS,
  type ParcFiltersState,
  parseParcFilters,
  serializeParcFilters,
  totalParcPages
} from './parcParams';

const PARC_URL = '/plugin/inventree-location/stock/parc/';

interface LigneParc {
  part_id: number;
  part_name: string;
  categorie: string;
  parc: number;
  sorti: number;
  disponible: number;
  retour_prevu: string | null;
  sav: number;
  seuil_alerte_bas: number | null;
  consommable: boolean;
  motifs_alerte: string[];
}

interface ReponseParc {
  count: number;
  results: LigneParc[];
}

function jourCourt(iso: string | null): string {
  if (!iso) {
    return '—';
  }

  const [annee, mois, jour] = iso.split('-');
  return `${jour}/${mois}/${annee.slice(2)}`;
}

export function ParcList({ context }: { context: InvenTreePluginContext }) {
  const [filters, setFilters] = useState<ParcFiltersState>(() =>
    typeof window === 'undefined'
      ? DEFAULT_PARC_FILTERS
      : parseParcFilters(window.location.search)
  );
  const [saisie, setSaisie] = useState(filters.search);
  const [rechercheDifferee] = useDebouncedValue(saisie, 350);
  const categoryOptions = useCategoryOptions(context);

  // La recherche différée pilote le filtre, et remet la pagination à zéro.
  useEffect(() => {
    setFilters((f) =>
      f.search === rechercheDifferee
        ? f
        : { ...f, search: rechercheDifferee, page: 1 }
    );
  }, [rechercheDifferee]);

  useEffect(() => {
    syncOwnedParams(
      ownsKeys(PARC_URL_KEYS),
      new URLSearchParams(serializeParcFilters(filters))
    );
  }, [filters]);

  const params = useMemo(() => buildParcQuery(filters), [filters]);

  const query = useQuery<ReponseParc>(
    {
      queryKey: ['stock-parc', params],
      queryFn: async () => {
        const reponse = await context.api.get(PARC_URL, { params });
        return reponse.data as ReponseParc;
      }
    },
    context.queryClient
  );

  const lignes = query.data?.results ?? [];
  const pages = totalParcPages(query.data?.count ?? 0);

  return (
    <WidgetScroll>
      <Stack gap='sm'>
        <Title order={4} c='blue'>
          État du parc
        </Title>

        <Group align='flex-end' gap='sm' wrap='wrap'>
          <TextInput
            label='Recherche'
            placeholder='Nom, référence…'
            value={saisie}
            onChange={(e) => setSaisie(e.currentTarget.value)}
            w={240}
          />
          <MultiSelect
            label='Catégorie'
            placeholder='Toutes'
            data={categoryOptions}
            value={filters.categories}
            onChange={(v) =>
              setFilters((f) => ({ ...f, categories: v, page: 1 }))
            }
            searchable
            clearable
            w={280}
          />
          <Switch
            label='Seulement ce qui alerte'
            checked={filters.alerteSeule}
            onChange={(e) =>
              setFilters((f) => ({
                ...f,
                alerteSeule: e.currentTarget.checked,
                page: 1
              }))
            }
            mb={6}
          />
        </Group>

        {query.isLoading && (
          <Group justify='center' p='xl'>
            <Loader />
          </Group>
        )}

        {query.isError && (
          <Alert color='red' title='État du parc'>
            Impossible de charger l’état du parc.
          </Alert>
        )}

        {!query.isLoading && !query.isError && lignes.length === 0 && (
          <Alert color='gray' title='Aucun article'>
            {filters.alerteSeule
              ? 'Rien à signaler sur le parc : aucun article sous son seuil ni sorti au-delà de ce qu’on possède.'
              : 'Aucun article ne correspond à cette recherche.'}
          </Alert>
        )}

        {lignes.length > 0 && (
          <Table striped highlightOnHover withTableBorder>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Article</Table.Th>
                <Table.Th ta='right'>Parc</Table.Th>
                <Table.Th ta='right'>Sorti</Table.Th>
                <Table.Th ta='right'>Disponible</Table.Th>
                <Table.Th>Revient</Table.Th>
                <Table.Th ta='right'>SAV</Table.Th>
                <Table.Th ta='right'>Seuil</Table.Th>
                <Table.Th>À signaler</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {lignes.map((l) => (
                <Table.Tr key={l.part_id}>
                  <Table.Td>
                    <Text size='sm' fw={600}>
                      {l.part_name}
                    </Text>
                    {l.categorie && (
                      <Text size='xs' c='dimmed'>
                        {l.categorie}
                      </Text>
                    )}
                  </Table.Td>
                  <Table.Td ta='right'>{l.parc}</Table.Td>
                  <Table.Td ta='right'>
                    <Text size='sm' c={l.sorti > 0 ? 'orange' : undefined}>
                      {l.sorti}
                    </Text>
                  </Table.Td>
                  <Table.Td ta='right' fw={600}>
                    {l.disponible}
                  </Table.Td>
                  <Table.Td>
                    <Text size='sm' c='dimmed'>
                      {jourCourt(l.retour_prevu)}
                    </Text>
                  </Table.Td>
                  <Table.Td ta='right'>
                    {l.sav > 0 ? (
                      <Badge color='grape' variant='light'>
                        {l.sav}
                      </Badge>
                    ) : (
                      <Text size='sm' c='dimmed'>
                        —
                      </Text>
                    )}
                  </Table.Td>
                  <Table.Td ta='right'>
                    <Text size='sm' c='dimmed'>
                      {l.seuil_alerte_bas ?? '—'}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4} wrap='wrap'>
                      {l.motifs_alerte.map((m) => (
                        <Badge
                          key={m}
                          color={m === 'sous_seuil' ? 'orange' : 'red'}
                          variant='light'
                        >
                          {libelleMotif(m)}
                        </Badge>
                      ))}
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}

        {pages > 1 && (
          <Group justify='space-between'>
            <Text size='xs' c='dimmed'>
              {query.data?.count} article(s)
            </Text>
            <Pagination
              value={filters.page}
              onChange={(page) => setFilters((f) => ({ ...f, page }))}
              total={pages}
              size='sm'
            />
          </Group>
        )}
      </Stack>
    </WidgetScroll>
  );
}
