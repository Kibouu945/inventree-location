// Liste des réservations + modal de création/édition (RES-03).
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Badge,
  Button,
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
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { ReservationForm } from './ReservationForm';
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

/** Construit les query params de la liste à partir de l'état des filtres. */
function buildQuery(
  search: string,
  statuts: string[],
  dateRange: [string | null, string | null]
): Record<string, string | string[]> {
  const params: Record<string, string | string[]> = {};

  if (search.trim()) {
    params.search = search.trim();
  }
  if (statuts.length > 0) {
    params.statut = statuts;
  }
  if (dateRange[0]) {
    params.date_from = dateRange[0];
  }
  if (dateRange[1]) {
    params.date_to = dateRange[1];
  }

  return params;
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

  const [search, setSearch] = useState('');
  const [debouncedSearch] = useDebouncedValue(search, 300);
  const [statuts, setStatuts] = useState<string[]>([]);
  const [dateRange, setDateRange] = useState<[string | null, string | null]>([
    null,
    null
  ]);

  const params = buildQuery(debouncedSearch, statuts, dateRange);

  const query = useQuery<Reservation[] | Page<Reservation>>(
    {
      queryKey: ['reservations', params],
      queryFn: async () => {
        const response = await context.api.get(RESERVATIONS_URL, { params });
        return response.data;
      }
    },
    context.queryClient
  );

  const rows = Array.isArray(query.data)
    ? query.data
    : (query.data?.results ?? []);

  function closeModal() {
    setModalState({ open: false });
  }

  return (
    <Stack gap='md'>
      <Group justify='space-between'>
        <Title order={4} c={context.theme.primaryColor}>
          Réservations
        </Title>
        <Button
          onClick={() =>
            setModalState({ open: true, reservationId: undefined })
          }
        >
          Nouvelle réservation
        </Button>
      </Group>

      <Group align='flex-end' gap='md' wrap='wrap'>
        <TextInput
          label='Recherche'
          placeholder='Numéro, événement, demandeur…'
          value={search}
          onChange={(event) => setSearch(event.currentTarget.value)}
          w={260}
        />
        <MultiSelect
          label='Statut'
          placeholder='Tous'
          data={STATUT_OPTIONS}
          value={statuts}
          onChange={setStatuts}
          clearable
          w={240}
        />
        <DatePickerInput
          type='range'
          label='Période'
          placeholder='Retrait — Retour'
          value={dateRange}
          onChange={setDateRange}
          clearable
          w={260}
        />
      </Group>

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
          modalState.reservationId
            ? 'Modifier la réservation'
            : 'Nouvelle réservation'
        }
      >
        <ReservationForm
          context={context}
          reservationId={modalState.reservationId}
          onSaved={closeModal}
        />
      </Modal>
    </Stack>
  );
}
