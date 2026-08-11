// Sélecteur de matériel (autocomplete + quantité), réutilisé pour le
// matériel réel et pour l'article virtuel obligatoire (RES-03).
import type { InvenTreePluginContext } from '@inventreedb/ui';
import { Button, Group, NumberInput, Select } from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import type { LigneReservationLine } from './types';

const CATALOG_URL = '/plugin/inventree-location/catalog/';

interface CatalogSearchResult {
  id: number;
  name: string;
  is_virtual: boolean;
  stock_available: number;
}

export function PartPicker({
  context,
  label,
  virtualOnly = false,
  dateDebut,
  dateFin,
  onAdd
}: {
  context: InvenTreePluginContext;
  label: string;
  virtualOnly?: boolean;
  /** Période de la prestation ciblée : la disponibilité en tient compte. */
  dateDebut?: string | null;
  dateFin?: string | null;
  onAdd: (ligne: LigneReservationLine) => void;
}) {
  const [search, setSearch] = useState('');
  const [debouncedSearch] = useDebouncedValue(search, 300);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [quantite, setQuantite] = useState<number>(1);

  const query = useQuery<{ results: CatalogSearchResult[] }>(
    {
      queryKey: [
        'reservation-part-search',
        debouncedSearch,
        virtualOnly,
        dateDebut,
        dateFin
      ],
      queryFn: async () => {
        const response = await context.api.get(CATALOG_URL, {
          params: {
            search: debouncedSearch || undefined,
            rentable: 'all',
            virtual: virtualOnly ? 'true' : undefined,
            date_debut: dateDebut || undefined,
            date_fin: dateFin || undefined,
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
    () =>
      results.map((part) => ({
        value: String(part.id),
        label: part.is_virtual
          ? part.name
          : `${part.name} — ${part.stock_available} disponible(s)`
      })),
    [results]
  );

  const selectedPart = results.find((part) => String(part.id) === selectedId);

  // La quantité par défaut retombe à 1 dès qu'un nouvel article est choisi.
  useEffect(() => {
    setQuantite(1);
  }, [selectedId]);

  const exceedsAvailable =
    !!selectedPart &&
    !selectedPart.is_virtual &&
    quantite > selectedPart.stock_available;

  function handleAdd() {
    if (!selectedPart || quantite < 1 || exceedsAvailable) {
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
        w={320}
      />
      <NumberInput
        label='Quantité'
        min={1}
        value={quantite}
        onChange={(value) => setQuantite(Number(value) || 1)}
        error={exceedsAvailable ? 'Quantité indisponible' : undefined}
        w={140}
      />
      <Button onClick={handleAdd} disabled={!selectedPart || exceedsAvailable}>
        Ajouter
      </Button>
    </Group>
  );
}
