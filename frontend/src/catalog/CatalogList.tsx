import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Badge,
  Group,
  Loader,
  MultiSelect,
  Pagination,
  SegmentedControl,
  Stack,
  Table,
  Text,
  TextInput,
  Title
} from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import {
  buildCatalogQuery,
  type CatalogFiltersState,
  DEFAULT_FILTERS,
  parseFilters,
  serializeFilters,
  totalPages
} from './catalogParams';
import type { CatalogPage } from './types';

const CATALOG_URL = '/plugin/inventree-location/catalog/';

/** Reflète l'état des filtres dans la query string sans recharger la page. */
function syncUrl(filters: CatalogFiltersState) {
  if (typeof window === 'undefined' || !window.history?.replaceState) {
    return;
  }
  const query = serializeFilters(filters);
  const url = query ? `?${query}` : window.location.pathname;
  window.history.replaceState(null, '', url);
}

function initialFilters(): CatalogFiltersState {
  if (typeof window === 'undefined') {
    return DEFAULT_FILTERS;
  }
  return parseFilters(window.location.search);
}

/**
 * Écran liste du catalogue louable (CAT-02 / CAT-03).
 *
 * Tableau paginé du matériel InvenTree exposé par le plugin, avec recherche
 * debouncée, filtre par catégorie (multi), filtre louable et état porté par
 * l'URL.
 */
export function CatalogList({ context }: { context: InvenTreePluginContext }) {
  const [filters, setFilters] = useState<CatalogFiltersState>(initialFilters);
  const [debouncedSearch] = useDebouncedValue(filters.search, 300);

  // L'état effectif envoyé à l'API utilise la recherche debouncée (CAT-03).
  const effectiveFilters = useMemo<CatalogFiltersState>(
    () => ({ ...filters, search: debouncedSearch }),
    [filters, debouncedSearch]
  );

  useEffect(() => {
    syncUrl(effectiveFilters);
  }, [effectiveFilters]);

  const query = useQuery<CatalogPage>(
    {
      queryKey: ['catalog', buildCatalogQuery(effectiveFilters)],
      queryFn: async () => {
        const response = await context.api.get(CATALOG_URL, {
          params: buildCatalogQuery(effectiveFilters)
        });
        return response.data as CatalogPage;
      }
    },
    context.queryClient
  );

  const rows = query.data?.results ?? [];

  // Options de catégories dérivées des résultats chargés (MVP).
  const categoryOptions = useMemo(() => {
    const seen = new Map<number, string>();
    for (const part of rows) {
      if (part.category != null && part.category_name) {
        seen.set(part.category, part.category_name);
      }
    }
    return Array.from(seen.entries()).map(([id, name]) => ({
      value: String(id),
      label: name
    }));
  }, [rows]);

  const pages = totalPages(query.data?.count ?? 0);

  function update(patch: Partial<CatalogFiltersState>) {
    // Tout changement de filtre (hors page) réinitialise la pagination.
    const resetsPage = !('page' in patch);
    setFilters((current) => ({
      ...current,
      ...patch,
      ...(resetsPage ? { page: 1 } : {})
    }));
  }

  return (
    <Stack gap='md'>
      <Title order={4} c={context.theme.primaryColor}>
        Catalogue du matériel
      </Title>

      <Group align='flex-end' gap='md' wrap='wrap'>
        <TextInput
          label='Recherche'
          placeholder='Nom, description, référence…'
          value={filters.search}
          onChange={(event) => update({ search: event.currentTarget.value })}
          w={260}
        />
        <MultiSelect
          label='Catégories'
          placeholder='Toutes'
          data={categoryOptions}
          value={filters.categories.map(String)}
          onChange={(values) =>
            update({ categories: values.map((value) => Number(value)) })
          }
          clearable
          w={240}
        />
        <SegmentedControl
          value={String(filters.rentable)}
          onChange={(value) =>
            update({
              rentable: value === 'all' ? 'all' : value === 'true'
            })
          }
          data={[
            { label: 'Louable', value: 'true' },
            { label: 'Non-louable', value: 'false' },
            { label: 'Tout', value: 'all' }
          ]}
        />
      </Group>

      {query.isError && (
        <Alert color='red' title='Erreur'>
          Impossible de charger le catalogue.
        </Alert>
      )}

      {query.isLoading ? (
        <Group justify='center' p='xl'>
          <Loader />
        </Group>
      ) : rows.length === 0 ? (
        <Alert color='gray' title='Aucun résultat'>
          Aucun matériel ne correspond aux filtres.
        </Alert>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Nom</Table.Th>
              <Table.Th>Référence</Table.Th>
              <Table.Th>Catégorie</Table.Th>
              <Table.Th>Louable</Table.Th>
              <Table.Th>Disponible aujourd'hui</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((part) => (
              <Table.Tr
                key={part.id}
                style={{ cursor: 'pointer' }}
                onClick={() => context.navigate(`/part/${part.id}/`)}
              >
                <Table.Td>{part.name}</Table.Td>
                <Table.Td>{part.IPN || '—'}</Table.Td>
                <Table.Td>{part.category_name || '—'}</Table.Td>
                <Table.Td>
                  {part.consommable ? (
                    <Badge color='orange'>Consommable</Badge>
                  ) : part.rentable ? (
                    <Badge color='green'>Louable</Badge>
                  ) : (
                    <Badge color='gray'>Non-louable</Badge>
                  )}
                </Table.Td>
                <Table.Td>
                  {part.is_virtual ? (
                    '—'
                  ) : (
                    <Badge color={part.stock_available > 0 ? 'blue' : 'red'} variant='light'>
                      {part.stock_available}
                    </Badge>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      <Group justify='space-between'>
        <Text size='sm' c='dimmed'>
          {query.data?.count ?? 0} article(s)
        </Text>
        {pages > 1 && (
          <Pagination
            total={pages}
            value={filters.page}
            onChange={(page) => update({ page })}
          />
        )}
      </Group>
    </Stack>
  );
}
