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
import { notifications } from '@mantine/notifications';
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
  conflicting_reservation_numeros: string[];
  /** Articles en pénurie et quantité manquante (CON-01). */
  shortages: Shortage[];
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
  //: Motif de refus par entrée, renvoyé par le serveur quand la cause tient.
  const [blocages, setBlocages] = useState<Record<number, string>>({});
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

  /** Ce qui décrit le conflit en une ligne : l'article manquant ou le lieu. */
  function libelleConflit(item: ConflictHistoryItem): string {
    if (item.conflict_type === 'stock') {
      return `${item.part_name || 'Article inconnu'} (manquant: ${item.details?.missing_quantity ?? 0})`;
    }

    return item.details?.adresse || item.location_key || 'Lieu non renseigné';
  }

  async function resolveConflict(item: ConflictHistoryItem) {
    try {
      await context.api.patch(`${CONFLICTS_HISTORY_URL}${item.id}/resolve/`, {
        note: 'Resolved from conflicts panel'
      });
      setBlocages((current) => {
        const suite = { ...current };
        delete suite[item.id];
        return suite;
      });
      // La ligne quitte la vue, filtrée sur « ouverts » : sans confirmation on
      // ne distinguait pas une résolution réussie d'un échec silencieux.
      notifications.show({
        title: 'Conflit résolu',
        message: `${item.reservation_numero} — ${libelleConflit(item)}`,
        color: 'green'
      });
      await historyQuery.refetch();
      await query.refetch();
    } catch (error: unknown) {
      // Le serveur refuse de clore un conflit dont la cause tient : on garde
      // le motif sous la ligne plutôt que dans une notification fugace.
      const data = (error as { response?: { data?: { detail?: string } } })
        ?.response?.data;
      const motif =
        data?.detail ??
        'Résolution impossible : le conflit est toujours actif.';

      setBlocages((current) => ({ ...current, [item.id]: motif }));
      notifications.show({
        title: 'Résolution refusée',
        message: motif,
        color: 'red'
      });
    }
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
                <Table.Td>
                  {conflict.conflicting_reservation_numeros?.length ? (
                    <Group gap={4}>
                      {conflict.conflicting_reservation_numeros.map(
                        (numero) => (
                          <Badge key={numero} variant='light' color='orange'>
                            {numero}
                          </Badge>
                        )
                      )}
                    </Group>
                  ) : (
                    // Une pénurie peut venir du seul prévisionnel d'une
                    // prestation : personne à désigner en face.
                    <Text size='sm' c='dimmed'>
                      —
                    </Text>
                  )}
                </Table.Td>
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
                <Table.Td>
                  {item.conflict_type === 'stock' ? 'Stock' : 'Lieu'}
                </Table.Td>
                <Table.Td>
                  <Badge color={item.state === 'open' ? 'red' : 'green'}>
                    {item.state === 'open' ? 'Ouvert' : 'Résolu'}
                  </Badge>
                </Table.Td>
                <Table.Td>{item.reservation_numero}</Table.Td>
                <Table.Td>{libelleConflit(item)}</Table.Td>
                <Table.Td>
                  {item.period_start
                    ? new Date(item.period_start).toLocaleDateString()
                    : '—'}
                  {' → '}
                  {item.period_end
                    ? new Date(item.period_end).toLocaleDateString()
                    : '—'}
                </Table.Td>
                <Table.Td>
                  {new Date(item.created_at).toLocaleString()}
                </Table.Td>
                <Table.Td>
                  {item.state === 'open' ? (
                    <Stack gap={4}>
                      <Button
                        size='xs'
                        color='green'
                        onClick={() => resolveConflict(item)}
                      >
                        Résoudre
                      </Button>
                      {blocages[item.id] && (
                        <Text size='xs' c='red' maw={280}>
                          {blocages[item.id]}
                        </Text>
                      )}
                    </Stack>
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
