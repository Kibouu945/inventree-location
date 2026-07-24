import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Badge,
  Button,
  Group,
  Loader,
  Modal,
  Select,
  Stack,
  Table,
  Text,
  Title
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { ReservationForm } from '../reservation/ReservationForm';
import { canWriteReservations } from '../roles';

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
}

interface ModalState {
  open: boolean;
  reservationId?: number;
}

interface ConflictHistoryItem {
  id: number;
  conflict_type: 'stock' | 'location';
  state: 'open' | 'resolved';
  reservation_id: number;
  reservation_numero: string;
  conflicting_reservation_id: number | null;
  part_id: number | null;
  part_name: string;
  period_start: string | null;
  period_end: string | null;
  location_key: string;
  details: Record<string, any>;
  created_at: string;
  resolved_at: string | null;
  resolved_by: string;
  resolution_note: string;
}

const CONFLICTS_URL = '/plugin/inventree-location/conflicts/';
const CONFLICTS_HISTORY_URL = '/plugin/inventree-location/conflicts/history/';

export function ConflictsList({
  context
}: {
  context: InvenTreePluginContext;
}) {
  const [modalState, setModalState] = useState<ModalState>({ open: false });
  const [historyStateFilter, setHistoryStateFilter] = useState<string>('open');
  const [historyTypeFilter, setHistoryTypeFilter] = useState<string>('all');

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

  const historyQuery = useQuery<ConflictHistoryItem[]>(
    {
      queryKey: ['conflicts-history', historyStateFilter, historyTypeFilter],
      queryFn: async () => {
        const response = await context.api.get(CONFLICTS_HISTORY_URL, {
          params: {
            state: historyStateFilter,
            type: historyTypeFilter
          }
        });
        return response.data as ConflictHistoryItem[];
      }
    },
    context.queryClient
  );

  function closeModal() {
    setModalState({ open: false });
  }

  async function resolveConflict(item: ConflictHistoryItem) {
    await context.api.patch(
      `${CONFLICTS_HISTORY_URL}${item.id}/resolve/`,
      {
        note: 'Resolved from conflicts panel'
      }
    );
    await historyQuery.refetch();
    await query.refetch();
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
              <Table.Th>Demandeur</Table.Th>
              <Table.Th>Événement</Table.Th>
              <Table.Th>Début</Table.Th>
              <Table.Th>Fin</Table.Th>
              <Table.Th>Conflits</Table.Th>
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
                <Table.Td>{conflict.conflict_count}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      <Group justify='space-between' mt='lg'>
        <Title order={4} c={context.theme.primaryColor}>
          Historique des conflits
        </Title>
        <Badge color='blue' size='lg'>
          {historyQuery.data?.length ?? 0}
        </Badge>
      </Group>

      <Group align='end'>
        <Select
          label='État'
          value={historyStateFilter}
          onChange={(value) => setHistoryStateFilter(value ?? 'open')}
          data={[
            { value: 'open', label: 'Ouverts' },
            { value: 'resolved', label: 'Résolus' },
            { value: 'all', label: 'Tous' }
          ]}
          w={160}
        />
        <Select
          label='Type'
          value={historyTypeFilter}
          onChange={(value) => setHistoryTypeFilter(value ?? 'all')}
          data={[
            { value: 'all', label: 'Tous' },
            { value: 'stock', label: 'Stock' },
            { value: 'location', label: 'Lieu' }
          ]}
          w={160}
        />
      </Group>

      {historyQuery.isError && (
        <Alert color='red' title='Erreur'>
          Impossible de charger l'historique des conflits.
        </Alert>
      )}

      {historyQuery.isLoading ? (
        <Group justify='center' p='xl'>
          <Loader />
        </Group>
      ) : historyQuery.data?.length === 0 ? (
        <Text c='dimmed'>Aucune entrée d'historique.</Text>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Type</Table.Th>
              <Table.Th>État</Table.Th>
              <Table.Th>Réservation</Table.Th>
              <Table.Th>Détail</Table.Th>
              <Table.Th>Période</Table.Th>
              <Table.Th>Créé le</Table.Th>
              <Table.Th>Action</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {historyQuery.data?.map((item) => (
              <Table.Tr key={item.id}>
                <Table.Td>{item.conflict_type === 'stock' ? 'Stock' : 'Lieu'}</Table.Td>
                <Table.Td>
                  <Badge color={item.state === 'open' ? 'red' : 'green'}>
                    {item.state === 'open' ? 'Ouvert' : 'Résolu'}
                  </Badge>
                </Table.Td>
                <Table.Td>{item.reservation_numero}</Table.Td>
                <Table.Td>
                  {item.conflict_type === 'stock'
                    ? `${item.part_name || 'Article inconnu'} (manquant: ${item.details?.missing_quantity ?? 0})`
                    : item.details?.adresse || item.location_key || 'Lieu non renseigné'}
                </Table.Td>
                <Table.Td>
                  {item.period_start ? new Date(item.period_start).toLocaleDateString() : '—'}
                  {' → '}
                  {item.period_end ? new Date(item.period_end).toLocaleDateString() : '—'}
                </Table.Td>
                <Table.Td>{new Date(item.created_at).toLocaleString()}</Table.Td>
                <Table.Td>
                  {item.state === 'open' ? (
                    <Button
                      size='xs'
                      color='green'
                      onClick={() => resolveConflict(item)}
                    >
                      Résoudre
                    </Button>
                  ) : (
                    <Text c='dimmed' size='sm'>
                      {item.resolved_by || '—'}
                    </Text>
                  )}
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
