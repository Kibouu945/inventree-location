// Sélecteur de matériel (autocomplete + quantité), réutilisé pour le
// matériel réel et pour l'article virtuel obligatoire (RES-03).
import type { InvenTreePluginContext } from '@inventreedb/ui';
import { Button, Group, NumberInput, Select } from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import type { LigneReservationLine } from './types';

const CATALOG_URL = '/plugin/inventree-location/catalog/';
const STOCK_AVAILABILITY_URL =
  '/plugin/inventree-location/reservations/check-stock/';

interface CatalogSearchResult {
  id: number;
  name: string;
  is_virtual: boolean;
}

export function PartPicker({
  context,
  label,
  virtualOnly = false,
  dateRetraitPrevue,
  dateRetourPrevue,
  reservationId,
  onConflict,
  onAdd
}: {
  context: InvenTreePluginContext;
  label: string;
  virtualOnly?: boolean;
  dateRetraitPrevue?: Date | null;
  dateRetourPrevue?: Date | null;
  reservationId?: number;
  onConflict?: (message: string) => void;
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

  async function handleAdd() {
    if (!selectedPart || quantite < 1) {
      return;
    }

    if (!selectedPart.is_virtual && dateRetraitPrevue && dateRetourPrevue) {
      try {
        await context.api.get(STOCK_AVAILABILITY_URL, {
          params: {
            part: selectedPart.id,
            quantity: quantite,
            date_retrait_prevue: dateRetraitPrevue.toISOString(),
            date_retour_prevue: dateRetourPrevue.toISOString(),
            reservation: reservationId
          }
        });
      } catch (error) {
        const response = (error as { response?: { data?: any } }).response;
        const payload = response?.data ?? {};
        const missing = Number(payload?.missing_quantity ?? 0);
        const available = Number(payload?.available_quantity ?? 0);
        const partName = payload?.part_name || selectedPart.name;

        if (response?.status === 409) {
          onConflict?.(
            `Stock insuffisant pour ${partName}: disponible ${available}, manquant ${missing}.`
          );
          return;
        }

        onConflict?.('Impossible de vérifier le stock en temps réel.');
        return;
      }
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
