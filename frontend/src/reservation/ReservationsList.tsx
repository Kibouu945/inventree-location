// Liste des réservations + modal de création/édition (RES-03).
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Badge,
  Button,
  Group,
  Loader,
  Modal,
  Stack,
  Table,
  Text,
  Title
} from '@mantine/core';
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

interface ModalState {
  open: boolean;
  reservationId?: number;
}

export function ReservationsList({
  context
}: {
  context: InvenTreePluginContext;
}) {
  const [modalState, setModalState] = useState<ModalState>({ open: false });

  const query = useQuery<Reservation[] | Page<Reservation>>(
    {
      queryKey: ['reservations'],
      queryFn: async () => {
        const response = await context.api.get(RESERVATIONS_URL);
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
              <Table.Th>Statut</Table.Th>
              <Table.Th>Retrait prévu</Table.Th>
              <Table.Th>Retour prévu</Table.Th>
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
                <Table.Td>
                  <Badge color={STATUT_COLORS[reservation.statut] ?? 'gray'}>
                    {reservation.statut}
                  </Badge>
                </Table.Td>
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
