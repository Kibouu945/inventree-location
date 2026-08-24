import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Badge,
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
import { ReservationForm } from '../reservation/ReservationForm';
import { canWriteReservations } from '../roles';

interface Shortage {
  part_id: number;
  part_name: string;
  missing_quantity: number;
}

interface ConflictItem {
  id: number;
  numero: string;
  statut: string;
  date_retrait_prevue: string | null;
  date_retour_prevue: string | null;
  prestation_nom: string;
  demandeur_nom: string;
  conflict_count: number;
  conflicting_reservation_ids: number[];
  /** Articles en pénurie et quantité manquante (CON-01). */
  shortages: Shortage[];
}

interface ModalState {
  open: boolean;
  reservationId?: number;
}

const CONFLICTS_URL = '/plugin/inventree-location/conflicts/';

export function ConflictsList({
  context
}: {
  context: InvenTreePluginContext;
}) {
  const [modalState, setModalState] = useState<ModalState>({ open: false });

  // Le lecteur voit les conflits mais ne peut pas éditer les réservations.
  const canWrite = canWriteReservations(context);

  const query = useQuery<ConflictItem[]>(
    {
      queryKey: ['conflicts'],
      queryFn: async () => {
        const response = await context.api.get(CONFLICTS_URL);
        return response.data as ConflictItem[];
      }
    },
    context.queryClient
  );

  function closeModal() {
    setModalState({ open: false });
  }

  return (
    <Stack gap='md'>
      <Group justify='space-between'>
        <Title order={4} c={context.theme.primaryColor}>
          Conflits actuels
        </Title>
        <Badge color='red' size='lg'>
          {query.data?.length ?? 0}
        </Badge>
      </Group>

      {query.isError && (
        <Alert color='red' title='Erreur'>
          Impossible de charger les conflits.
        </Alert>
      )}

      {query.isLoading ? (
        <Group justify='center' p='xl'>
          <Loader />
        </Group>
      ) : query.data?.length === 0 ? (
        <Text c='dimmed'>Aucun conflit actif.</Text>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Réservation</Table.Th>
              <Table.Th>Gérant interne</Table.Th>
              <Table.Th>Événement</Table.Th>
              <Table.Th>Début</Table.Th>
              <Table.Th>Fin</Table.Th>
              <Table.Th>Manque</Table.Th>
              <Table.Th>Résas liées</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {query.data?.map((conflict) => (
              <Table.Tr
                key={conflict.id}
                style={{ cursor: 'pointer' }}
                onClick={() =>
                  setModalState({
                    open: true,
                    reservationId: conflict.id
                  })
                }
              >
                <Table.Td>{conflict.numero}</Table.Td>
                <Table.Td>{conflict.demandeur_nom}</Table.Td>
                <Table.Td>{conflict.prestation_nom}</Table.Td>
                <Table.Td>
                  {conflict.date_retrait_prevue
                    ? new Date(conflict.date_retrait_prevue).toLocaleString()
                    : '—'}
                </Table.Td>
                <Table.Td>
                  {conflict.date_retour_prevue
                    ? new Date(conflict.date_retour_prevue).toLocaleString()
                    : '—'}
                </Table.Td>
                <Table.Td>
                  {/* Une pénurie peut venir du seul prévisionnel d'une
                      prestation : c'est l'article manquant qui porte
                      l'information, pas le nombre de réservations. */}
                  <Group gap={4} wrap='wrap'>
                    {conflict.shortages.map((shortage) => (
                      <Badge key={shortage.part_id} color='red' variant='light'>
                        {shortage.part_name} −{shortage.missing_quantity}
                      </Badge>
                    ))}
                  </Group>
                </Table.Td>
                <Table.Td>{conflict.conflict_count}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      <Modal
        opened={modalState.open}
        onClose={closeModal}
        size='xl'
        title='Détail de la réservation'
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
