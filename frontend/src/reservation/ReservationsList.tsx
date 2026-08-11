// Liste des réservations + modal de création/édition (RES-03).
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Badge,
  Button,
  Chip,
  Group,
  Loader,
  Modal,
  MultiSelect,
  Stack,
  Table,
  Text,
  TextInput,
  Title
} from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import { useDebouncedValue } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { canArbitrateReservations, canWriteReservations } from '../roles';
import { ownsKeys, syncOwnedParams } from '../urlState';
import { canArbitrateReservation, transitionErrorMessage } from './formLogic';
import { ReservationForm } from './ReservationForm';
import {
  buildReservationQuery,
  DEFAULT_RESERVATION_FILTERS,
  parseReservationFilters,
  RESERVATION_URL_KEYS,
  type ReservationFiltersState,
  serializeReservationFilters
} from './reservationParams';
import type { Page, Reservation } from './types';

const RESERVATIONS_URL = '/plugin/inventree-location/reservations/';

const STATUT_COLORS: Record<string, string> = {
  brouillon: 'gray',
  soumise: 'blue',
  validee: 'green',
  refusee: 'red',
  livree: 'teal',
  retournee: 'grape',
  cloturee: 'dark'
};

// Statuts affichables dans le filtre (StatutReservation côté serveur).
const STATUT_OPTIONS = [
  { value: 'brouillon', label: 'Brouillon' },
  { value: 'soumise', label: 'Soumise' },
  { value: 'validee', label: 'Validée' },
  { value: 'refusee', label: 'Refusée' },
  { value: 'livree', label: 'Livrée' },
  { value: 'retournee', label: 'Retournée' },
  { value: 'cloturee', label: 'Clôturée' }
];

interface ModalState {
  open: boolean;
  reservationId?: number;
}

interface CategoryResponseItem {
  id?: number;
  pk?: number;
  name?: string;
}

const ownsReservationKey = ownsKeys(RESERVATION_URL_KEYS);

function syncUrl(filters: ReservationFiltersState) {
  syncOwnedParams(
    ownsReservationKey,
    new URLSearchParams(serializeReservationFilters(filters))
  );
}

function initialFilters(): ReservationFiltersState {
  if (typeof window === 'undefined') {
    return DEFAULT_RESERVATION_FILTERS;
  }

  return parseReservationFilters(window.location.search);
}

/**
 * Écran liste des réservations (RES-03).
 *
 * Tableau (numéro, demandeur, événement, dates, statut, nb objets) filtrable
 * par recherche, statut et période. Le tri par date décroissante est assuré
 * côté serveur. Ouvre le formulaire de création/édition dans une modale.
 */
export function ReservationsList({
  context
}: {
  context: InvenTreePluginContext;
}) {
  const [modalState, setModalState] = useState<ModalState>({ open: false });
  const [filters, setFilters] =
    useState<ReservationFiltersState>(initialFilters);
  const [debouncedSearch] = useDebouncedValue(filters.search, 300);

  const effectiveFilters = useMemo(
    () => ({ ...filters, search: debouncedSearch }),
    [filters, debouncedSearch]
  );

  useEffect(() => {
    syncUrl(effectiveFilters);
  }, [effectiveFilters]);

  const params = buildReservationQuery(effectiveFilters);

  const categoriesQuery = useQuery<
    CategoryResponseItem[] | { results: CategoryResponseItem[] }
  >(
    {
      queryKey: ['reservation-category-options'],
      queryFn: async () => {
        const response = await context.api.get('/api/part/category/', {
          params: { limit: 250 }
        });
        return response.data;
      }
    },
    context.queryClient
  );

  const query = useQuery<Reservation[] | Page<Reservation>>(
    {
      queryKey: ['reservations', params],
      queryFn: async () => {
        const response = await context.api.get(RESERVATIONS_URL, {
          params,
          // Clés répétées `statut=a&statut=b` (le backend lit getlist).
          paramsSerializer: { indexes: null }
        });
        return response.data;
      }
    },
    context.queryClient
  );

  const rows = Array.isArray(query.data)
    ? query.data
    : (query.data?.results ?? []);

  // Livreur / magasinier / sav / lecteur : lecture seule (cf. permissions.py).
  const canWrite = canWriteReservations(context);
  const canArbitrate = canArbitrateReservations(context);

  // Validation / refus d'une réservation soumise via l'endpoint de transition.
  const transitionMutation = useMutation(
    {
      mutationFn: async ({
        id,
        statut
      }: {
        id: number;
        statut: 'validee' | 'refusee';
      }) => {
        const response = await context.api.patch(
          `${RESERVATIONS_URL}${id}/transition/`,
          { statut }
        );
        return response.data;
      },
      onSuccess: (_data, variables) => {
        context.queryClient.invalidateQueries({ queryKey: ['reservations'] });
        notifications.show({
          title: variables.statut === 'validee' ? 'Validée' : 'Refusée',
          message:
            variables.statut === 'validee'
              ? 'Réservation validée.'
              : 'Réservation refusée.',
          color: variables.statut === 'validee' ? 'green' : 'orange'
        });
      },
      onError: (error: unknown) => {
        notifications.show({
          title: 'Action impossible',
          message: transitionErrorMessage(error),
          color: 'red'
        });
      }
    },
    context.queryClient
  );

  const categoryOptions = useMemo(() => {
    const payload = categoriesQuery.data;

    if (!payload) {
      return [];
    }

    const categories = Array.isArray(payload) ? payload : payload.results;

    return categories
      .map((category) => ({
        id: category.id ?? category.pk,
        name: category.name ?? ''
      }))
      .filter((category) => Number.isInteger(category.id) && category.name)
      .map((category) => ({
        value: String(category.id),
        label: category.name
      }));
  }, [categoriesQuery.data]);

  function updateFilters(patch: Partial<ReservationFiltersState>) {
    setFilters((current) => ({
      ...current,
      ...patch
    }));
  }

  function closeModal() {
    setModalState({ open: false });
  }

  return (
    <Stack gap='md'>
      <Group justify='space-between'>
        <Title order={4} c={context.theme.primaryColor}>
          Réservations
        </Title>
        {canWrite && (
          <Button
            onClick={() =>
              setModalState({ open: true, reservationId: undefined })
            }
          >
            Nouvelle réservation
          </Button>
        )}
      </Group>

      <Group align='flex-end' gap='md' wrap='wrap'>
        <TextInput
          label='Recherche'
          placeholder='Numéro, événement, demandeur…'
          value={filters.search}
          onChange={(event) =>
            updateFilters({ search: event.currentTarget.value })
          }
          w={260}
        />
        <MultiSelect
          label='Catégories'
          placeholder='Tous'
          data={categoryOptions}
          value={filters.categories.map(String)}
          onChange={(values) =>
            updateFilters({
              categories: values
                .map((value) => Number.parseInt(value, 10))
                .filter((value) => Number.isInteger(value))
            })
          }
          clearable
          w={240}
        />
        <DatePickerInput
          type='range'
          label='Période'
          placeholder='Retrait — Retour'
          value={filters.dateRange}
          onChange={(value) =>
            updateFilters({
              dateRange: [value[0], value[1]]
            })
          }
          clearable
          w={260}
        />
        <Button
          variant='default'
          onClick={() => setFilters(DEFAULT_RESERVATION_FILTERS)}
        >
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
          Impossible de charger les réservations.
        </Alert>
      )}

      {query.isLoading ? (
        <Group justify='center' p='xl'>
          <Loader />
        </Group>
      ) : rows.length === 0 ? (
        <Text c='dimmed'>Aucune réservation pour le moment.</Text>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Numéro</Table.Th>
              <Table.Th>Demandeur</Table.Th>
              <Table.Th>Événement</Table.Th>
              <Table.Th>Retrait prévu</Table.Th>
              <Table.Th>Retour prévu</Table.Th>
              <Table.Th>Statut</Table.Th>
              <Table.Th>Nb objets</Table.Th>
              {canArbitrate && <Table.Th>Actions</Table.Th>}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((reservation) => (
              <Table.Tr
                key={reservation.id}
                style={{ cursor: 'pointer' }}
                onClick={() =>
                  setModalState({ open: true, reservationId: reservation.id })
                }
              >
                <Table.Td>{reservation.numero}</Table.Td>
                <Table.Td>{reservation.demandeur_nom || '—'}</Table.Td>
                <Table.Td>{reservation.prestation_nom || '—'}</Table.Td>
                <Table.Td>
                  {reservation.date_retrait_prevue
                    ? new Date(reservation.date_retrait_prevue).toLocaleString()
                    : '—'}
                </Table.Td>
                <Table.Td>
                  {reservation.date_retour_prevue
                    ? new Date(reservation.date_retour_prevue).toLocaleString()
                    : '—'}
                </Table.Td>
                <Table.Td>
                  <Badge color={STATUT_COLORS[reservation.statut] ?? 'gray'}>
                    {reservation.statut}
                  </Badge>
                </Table.Td>
                <Table.Td>{reservation.lignes.length}</Table.Td>
                {canArbitrate && (
                  <Table.Td
                    // Les actions ne doivent pas ouvrir la modale de détail.
                    onClick={(event) => event.stopPropagation()}
                    style={{ cursor: 'default' }}
                  >
                    {canArbitrateReservation(reservation.statut) ? (
                      <Group gap='xs' wrap='nowrap'>
                        <Button
                          size='xs'
                          color='green'
                          loading={
                            transitionMutation.isPending &&
                            transitionMutation.variables?.id ===
                              reservation.id &&
                            transitionMutation.variables?.statut === 'validee'
                          }
                          disabled={transitionMutation.isPending}
                          onClick={() =>
                            transitionMutation.mutate({
                              id: reservation.id,
                              statut: 'validee'
                            })
                          }
                        >
                          Valider
                        </Button>
                        <Button
                          size='xs'
                          variant='light'
                          color='red'
                          loading={
                            transitionMutation.isPending &&
                            transitionMutation.variables?.id ===
                              reservation.id &&
                            transitionMutation.variables?.statut === 'refusee'
                          }
                          disabled={transitionMutation.isPending}
                          onClick={() =>
                            transitionMutation.mutate({
                              id: reservation.id,
                              statut: 'refusee'
                            })
                          }
                        >
                          Refuser
                        </Button>
                      </Group>
                    ) : (
                      <Text c='dimmed' size='sm'>
                        —
                      </Text>
                    )}
                  </Table.Td>
                )}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      <Modal
        opened={modalState.open}
        onClose={closeModal}
        size='xl'
        title={
          !canWrite
            ? 'Détail de la réservation'
            : modalState.reservationId
              ? 'Modifier la réservation'
              : 'Nouvelle réservation'
        }
      >
        <ReservationForm
          context={context}
          reservationId={modalState.reservationId}
          readOnly={!canWrite}
          onSaved={closeModal}
        />
      </Modal>
    </Stack>
  );
}
