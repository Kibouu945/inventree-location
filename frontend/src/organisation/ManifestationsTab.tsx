// CRUD des manifestations (ORG-01).
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
  Textarea,
  TextInput,
  Title
} from '@mantine/core';
import { DateTimePicker } from '@mantine/dates';
import { useForm } from '@mantine/form';
import { useDebouncedValue } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { canWriteOrganisation } from '../roles';
import { apiErrorMessage, type Manifestation, type Page } from './types';

const MANIFESTATIONS_URL = '/plugin/inventree-location/manifestations/';
const GROUPES_URL = '/plugin/inventree-location/groupes/';
const USERS_URL = '/plugin/inventree-location/users/';

// en_cours / terminée sont dérivés des dates côté serveur, pas posables ici.
const STATUT_OPTIONS = [
  { value: 'brouillon', label: 'Brouillon' },
  { value: 'planifiee', label: 'Planifiée' },
  { value: 'annulee', label: 'Annulée' }
];

const STATUT_COLORS: Record<string, string> = {
  brouillon: 'gray',
  planifiee: 'blue',
  en_cours: 'teal',
  terminee: 'green',
  annulee: 'red'
};

interface FormValues {
  nom: string;
  description: string;
  statut: string;
  organisateur: string | null;
  groupe: string | null;
  date_debut: Date | null;
  date_fin: Date | null;
}

function emptyValues(): FormValues {
  return {
    nom: '',
    description: '',
    statut: 'brouillon',
    organisateur: null,
    groupe: null,
    date_debut: null,
    date_fin: null
  };
}

export function ManifestationsTab({
  context
}: {
  context: InvenTreePluginContext;
}) {
  const canWrite = canWriteOrganisation(context);

  const [search, setSearch] = useState('');
  const [debouncedSearch] = useDebouncedValue(search, 300);
  const [modalOpen, setModalOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);

  const form = useForm<FormValues>({ initialValues: emptyValues() });

  const listQuery = useQuery<Manifestation[] | Page<Manifestation>>(
    {
      queryKey: ['manifestations', debouncedSearch],
      queryFn: async () => {
        const response = await context.api.get(MANIFESTATIONS_URL, {
          params: debouncedSearch ? { search: debouncedSearch } : {}
        });
        return response.data;
      }
    },
    context.queryClient
  );

  const groupesQuery = useQuery<{
    results: Array<{ id: number; nom: string }>;
  }>(
    {
      queryKey: ['groupes'],
      queryFn: async () => {
        const response = await context.api.get(GROUPES_URL);
        return response.data;
      }
    },
    context.queryClient
  );

  const usersQuery = useQuery<{
    results: Array<{
      id: number;
      username: string;
      first_name: string;
      last_name: string;
    }>;
  }>(
    {
      queryKey: ['users-organisateur'],
      queryFn: async () => {
        const response = await context.api.get(USERS_URL);
        return response.data;
      }
    },
    context.queryClient
  );

  const rows = Array.isArray(listQuery.data)
    ? listQuery.data
    : (listQuery.data?.results ?? []);

  const groupeOptions = (groupesQuery.data?.results ?? []).map((g) => ({
    value: String(g.id),
    label: g.nom
  }));

  const userOptions = (usersQuery.data?.results ?? []).map((u) => {
    const fullName = `${u.first_name} ${u.last_name}`.trim();
    return {
      value: String(u.id),
      label: fullName ? `${fullName} (${u.username})` : u.username
    };
  });

  const mutation = useMutation(
    {
      mutationFn: async (values: FormValues) => {
        const payload = {
          nom: values.nom,
          description: values.description,
          statut: values.statut,
          organisateur: values.organisateur
            ? Number(values.organisateur)
            : null,
          groupe: values.groupe ? Number(values.groupe) : null,
          date_debut: values.date_debut?.toISOString(),
          date_fin: values.date_fin?.toISOString()
        };

        if (editId != null) {
          const response = await context.api.patch(
            `${MANIFESTATIONS_URL}${editId}/`,
            payload
          );
          return response.data;
        }

        const response = await context.api.post(MANIFESTATIONS_URL, payload);
        return response.data;
      },
      onSuccess: () => {
        notifications.show({
          color: 'green',
          message:
            editId != null
              ? 'Manifestation mise à jour.'
              : 'Manifestation créée.'
        });
        context.queryClient.invalidateQueries({ queryKey: ['manifestations'] });
        setModalOpen(false);
      },
      onError: (error) => {
        notifications.show({
          color: 'red',
          title: 'Erreur',
          message: apiErrorMessage(error, "Échec de l'enregistrement.")
        });
      }
    },
    context.queryClient
  );

  function openCreate() {
    setEditId(null);
    form.setValues(emptyValues());
    setModalOpen(true);
  }

  function openEdit(manifestation: Manifestation) {
    setEditId(manifestation.id);
    form.setValues({
      nom: manifestation.nom,
      description: manifestation.description,
      statut: manifestation.statut,
      organisateur: String(manifestation.organisateur),
      groupe: String(manifestation.groupe),
      date_debut: new Date(manifestation.date_debut),
      date_fin: new Date(manifestation.date_fin)
    });
    setModalOpen(true);
  }

  return (
    <Stack gap='md'>
      <Group justify='space-between'>
        <Title order={5}>Manifestations</Title>
        {canWrite && (
          <Button onClick={openCreate}>Nouvelle manifestation</Button>
        )}
      </Group>

      <TextInput
        label='Recherche'
        placeholder='Nom de la manifestation…'
        value={search}
        onChange={(event) => setSearch(event.currentTarget.value)}
        w={280}
      />

      {listQuery.isError && (
        <Alert color='red' title='Erreur'>
          Impossible de charger les manifestations.
        </Alert>
      )}

      {listQuery.isLoading ? (
        <Group justify='center' p='xl'>
          <Loader />
        </Group>
      ) : rows.length === 0 ? (
        <Text c='dimmed'>Aucune manifestation pour le moment.</Text>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Nom</Table.Th>
              <Table.Th>Début</Table.Th>
              <Table.Th>Fin</Table.Th>
              <Table.Th>Statut</Table.Th>
              <Table.Th>Prestations</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((manifestation) => (
              <Table.Tr
                key={manifestation.id}
                style={{ cursor: canWrite ? 'pointer' : 'default' }}
                onClick={() => canWrite && openEdit(manifestation)}
              >
                <Table.Td>{manifestation.nom}</Table.Td>
                <Table.Td>
                  {new Date(manifestation.date_debut).toLocaleDateString()}
                </Table.Td>
                <Table.Td>
                  {new Date(manifestation.date_fin).toLocaleDateString()}
                </Table.Td>
                <Table.Td>
                  <Badge
                    color={
                      STATUT_COLORS[
                        manifestation.statut_effectif ?? manifestation.statut
                      ] ?? 'gray'
                    }
                  >
                    {manifestation.statut_effectif ?? manifestation.statut}
                  </Badge>
                </Table.Td>
                <Table.Td>{manifestation.prestations_count}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      <Modal
        opened={modalOpen}
        onClose={() => setModalOpen(false)}
        size='lg'
        title={
          editId != null
            ? 'Modifier la manifestation'
            : 'Nouvelle manifestation'
        }
      >
        <form onSubmit={form.onSubmit((values) => mutation.mutate(values))}>
          <Stack gap='sm'>
            <TextInput label='Nom' required {...form.getInputProps('nom')} />
            <Textarea
              label='Description'
              autosize
              minRows={2}
              {...form.getInputProps('description')}
            />
            <Group grow>
              <DateTimePicker
                label='Date de début'
                required
                value={form.values.date_debut}
                onChange={(value) =>
                  form.setFieldValue(
                    'date_debut',
                    value ? new Date(value) : null
                  )
                }
              />
              <DateTimePicker
                label='Date de fin'
                required
                value={form.values.date_fin}
                onChange={(value) =>
                  form.setFieldValue('date_fin', value ? new Date(value) : null)
                }
              />
            </Group>
            <Group grow>
              <Select
                label='Organisateur'
                required
                data={userOptions}
                searchable
                {...form.getInputProps('organisateur')}
              />
              <Select
                label='Groupe'
                required
                data={groupeOptions}
                {...form.getInputProps('groupe')}
              />
            </Group>
            <Select
              label='Statut'
              data={STATUT_OPTIONS}
              {...form.getInputProps('statut')}
            />
            <Group justify='flex-end'>
              <Button variant='default' onClick={() => setModalOpen(false)}>
                Annuler
              </Button>
              <Button type='submit' loading={mutation.isPending}>
                Enregistrer
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </Stack>
  );
}
