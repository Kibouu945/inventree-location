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
  excludeReservationId,
  onAdd
}: {
  context: InvenTreePluginContext;
  label: string;
  virtualOnly?: boolean;
  /** Période de la prestation ciblée : la disponibilité en tient compte. */
  dateDebut?: string | null;
  dateFin?: string | null;
  /**
   * Réservation en cours d'édition : ses propres quantités ne doivent pas
   * être décomptées de ce qu'elle peut demander.
   */
  excludeReservationId?: number | null;
  onAdd: (ligne: LigneReservationLine) => void;
}) {
  const [search, setSearch] = useState('');
  const [debouncedSearch] = useDebouncedValue(search, 300);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pickedPart, setPickedPart] = useState<CatalogSearchResult | null>(
    null
  );
  const [quantite, setQuantite] = useState<number>(1);

  const query = useQuery<{ results: CatalogSearchResult[] }>(
    {
      queryKey: [
        'reservation-part-search',
        debouncedSearch,
        virtualOnly,
        dateDebut,
        dateFin,
        excludeReservationId
      ],
      queryFn: async () => {
        const response = await context.api.get(CATALOG_URL, {
          params: {
            search: debouncedSearch || undefined,
            rentable: 'all',
            // Les deux sélecteurs sont disjoints : « Matériel » ne doit pas
            // proposer les articles virtuels (services sans stock physique),
            // sinon ils échappent au garde-fou de quantité. Omettre le
            // paramètre ne filtrait rien et les faisait apparaître ici.
            virtual: virtualOnly ? 'true' : 'false',
            date_debut: dateDebut || undefined,
            date_fin: dateFin || undefined,
            exclude_reservation: excludeReservationId ?? undefined,
            page_size: 20
          }
        });
        return response.data;
      }
    },
    context.queryClient
  );

  const results = query.data?.results ?? [];

  // L'article retenu ne peut pas être dérivé des seuls résultats de recherche :
  // Mantine recopie le label de l'option dans `searchValue`, et ce label
  // ("Nom — N disponible(s)") ne correspond à aucun résultat côté serveur, qui
  // ne cherche que sur le nom. Sans ce repli, le sélecteur se vidait dès la
  // sélection et « Ajouter » restait grisé. On préfère malgré tout la version
  // fraîche quand la recherche la ramène, pour une dispo à jour.
  const selectedPart =
    results.find((part) => String(part.id) === selectedId) ??
    (pickedPart && String(pickedPart.id) === selectedId
      ? pickedPart
      : undefined);

  const optionFor = (part: CatalogSearchResult) => ({
    value: String(part.id),
    label: part.is_virtual
      ? part.name
      : `${part.name} — ${part.stock_available} disponible(s)`
  });

  const options = useMemo(() => {
    const mapped = results.map(optionFor);

    // L'option choisie doit rester présente, sinon le Select perd son libellé.
    if (
      selectedPart &&
      !mapped.some((option) => option.value === String(selectedPart.id))
    ) {
      mapped.unshift(optionFor(selectedPart));
    }

    return mapped;
    // optionFor est une fonction pure locale, pas une dépendance utile.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [results, selectedPart]);

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
    setPickedPart(null);
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
        onChange={(value) => {
          setSelectedId(value);
          setPickedPart(
            results.find((part) => String(part.id) === value) ?? null
          );
        }}
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
