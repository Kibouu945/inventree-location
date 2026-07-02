// Sélecteur de matériel (autocomplete + quantité), réutilisé pour le
// matériel réel et pour l'article virtuel obligatoire (RES-03).
import type { InvenTreePluginContext } from '@inventreedb/ui';
import { Button, Group, NumberInput, Select } from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import type { LigneReservationLine } from './types';

const CATALOG_URL = '/plugin/inventree-location/catalog/';

interface CatalogSearchResult {
  id: number;
  name: string;
  is_virtual: boolean;
}

export function PartPicker({
  context,
  label,
  virtualOnly = false,
  onAdd
}: {
  context: InvenTreePluginContext;
  label: string;
  virtualOnly?: boolean;
  onAdd: (ligne: LigneReservationLine) => void;
}) {
  const [search, setSearch] = useState('');
  const [debouncedSearch] = useDebouncedValue(search, 300);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [quantite, setQuantite] = useState<number>(1);

  const query = useQuery<{ results: CatalogSearchResult[] }>(
    {
      queryKey: ['reservation-part-search', debouncedSearch, virtualOnly],
      queryFn: async () => {
        const response = await context.api.get(CATALOG_URL, {
          params: {
            search: debouncedSearch || undefined,
            rentable: 'all',
            virtual: virtualOnly ? 'true' : undefined,
            page_size: 20
          }
        });
        return response.data;
      }
    },
    context.queryClient
  );

  const results = query.data?.results ?? [];

  const options = useMemo(
    () => results.map((part) => ({ value: String(part.id), label: part.name })),
    [results]
  );

  const selectedPart = results.find((part) => String(part.id) === selectedId);

  function handleAdd() {
    if (!selectedPart || quantite < 1) {
      return;
    }

    onAdd({
      part: selectedPart.id,
      partName: selectedPart.name,
      quantiteDemandee: quantite,
      isVirtual: selectedPart.is_virtual
    });

    setSelectedId(null);
    setSearch('');
    setQuantite(1);
  }

  return (
    <Group align='flex-end' gap='sm' wrap='wrap'>
      <Select
        label={label}
        placeholder='Rechercher un article…'
        data={options}
        searchable
        searchValue={search}
        onSearchChange={setSearch}
        value={selectedId}
        onChange={setSelectedId}
        nothingFoundMessage={query.isFetching ? 'Recherche…' : 'Aucun résultat'}
        w={280}
      />
      <NumberInput
        label='Quantité'
        min={1}
        value={quantite}
        onChange={(value) => setQuantite(Number(value) || 1)}
        w={100}
      />
      <Button onClick={handleAdd} disabled={!selectedPart}>
        Ajouter
      </Button>
    </Group>
  );
}
