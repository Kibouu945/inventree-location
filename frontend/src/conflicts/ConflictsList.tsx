import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
    Alert,
    Badge,
    Group,
    Loader,
    Stack,
    Table,
    Text,
    Title
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';

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

const CONFLICTS_URL = '/plugin/inventree-location/conflicts/';

export function ConflictsList({ context }: { context: InvenTreePluginContext }) {
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
                            <Table.Tr key={conflict.id}>
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
        </Stack>
    );
}
