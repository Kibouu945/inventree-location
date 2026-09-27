import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Badge,
  Button,
  Group,
  Loader,
  Modal,
  Pagination,
  Select,
  Stack,
  Switch,
  Table,
  Text,
  Textarea,
  TextInput,
  Title
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { CLIENTS_URL, listParams, pageCount } from './api';
import { apiErrorMessage } from './apiError';
import type {
  BackOfficeClient,
  BackOfficeClientFormValues,
  Page
} from './types';
import { usePagedSearch } from './usePagedSearch';

interface ModalState {
  open: boolean;
  client?: BackOfficeClient;
}

function emptyForm(): BackOfficeClientFormValues {
  return {
    nom: '',
    adresse: '',
    email: '',
    telephone: '',
    type_client: 'entreprise',
    siret: '',
    actif: true
  };
}

function formFromClient(client: BackOfficeClient): BackOfficeClientFormValues {
  return {
    nom: client.nom,
    adresse: client.adresse ?? '',
    email: client.email ?? '',
    telephone: client.telephone ?? '',
    type_client: client.type_client || 'entreprise',
    siret: client.siret ?? '',
    actif: client.actif
  };
}

export function ClientsTab({ context }: { context: InvenTreePluginContext }) {
  const { search, debouncedSearch, page, setPage, updateSearch } =
    usePagedSearch();

  const [modalState, setModalState] = useState<ModalState>({ open: false });
  const [formValues, setFormValues] = useState<BackOfficeClientFormValues>(
    emptyForm()
  );
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const clientsQuery = useQuery<Page<BackOfficeClient>>(
    {
      queryKey: ['backoffice-clients', debouncedSearch, page],
      queryFn: async () => {
        const response = await context.api.get(CLIENTS_URL, {
          params: listParams(page, debouncedSearch)
        });

        return response.data;
      }
    },
    context.queryClient
  );

  const rows = clientsQuery.data?.results ?? [];
  const count = clientsQuery.data?.count ?? 0;
  const pages = pageCount(count);

  function openCreateModal() {
    setFormError('');
    setFormValues(emptyForm());
    setModalState({ open: true });
  }

  function openEditModal(client: BackOfficeClient) {
    setFormError('');
    setFormValues(formFromClient(client));
    setModalState({ open: true, client });
  }

  function closeModal() {
    if (saving) {
      return;
    }

    setModalState({ open: false });
    setFormError('');
    setFormValues(emptyForm());
  }

  function updateField<K extends keyof BackOfficeClientFormValues>(
    field: K,
    value: BackOfficeClientFormValues[K]
  ) {
    setFormValues((current) => ({ ...current, [field]: value }));
  }

  async function saveClient() {
    setSaving(true);
    setFormError('');

    try {
      const payload = {
        nom: formValues.nom.trim(),
        adresse: formValues.adresse.trim(),
        // Chaîne vide envoyée en `null` : l'unicité de l'e-mail tolère
        // plusieurs absences, pas plusieurs chaînes vides.
        email: formValues.email.trim() || null,
        telephone: formValues.telephone.trim(),
        type_client: formValues.type_client,
        siret: formValues.siret.trim(),
        actif: formValues.actif
      };

      if (modalState.client) {
        await context.api.patch(
          `${CLIENTS_URL}${modalState.client.id}/`,
          payload
        );
      } else {
        await context.api.post(CLIENTS_URL, payload);
      }

      // Le sélecteur de client de l'onglet utilisateurs lit une autre clé.
      await context.queryClient.invalidateQueries({
        queryKey: ['backoffice-clients-options']
      });
      await clientsQuery.refetch();
      closeModal();
    } catch (error: unknown) {
      setFormError(
        apiErrorMessage(error, "Impossible d'enregistrer le client.")
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Stack gap='md'>
      <Group justify='space-between'>
        <Title order={5}>Clients</Title>

        <Button onClick={openCreateModal}>Créer un client</Button>
      </Group>

      <TextInput
        label='Recherche'
        placeholder='Nom ou e-mail…'
        value={search}
        onChange={(event) => updateSearch(event.currentTarget.value)}
        w={320}
      />

      {clientsQuery.isError && (
        <Alert color='red' title='Erreur'>
          Impossible de charger les clients.
        </Alert>
      )}

      {clientsQuery.isLoading ? (
        <Group justify='center' p='xl'>
          <Loader />
        </Group>
      ) : rows.length === 0 ? (
        <Text c='dimmed'>Aucun client trouvé.</Text>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Nom</Table.Th>
              <Table.Th>Type</Table.Th>
              <Table.Th>Contact</Table.Th>
              <Table.Th>Adresse</Table.Th>
              <Table.Th>Contacts</Table.Th>
              <Table.Th>État</Table.Th>
              <Table.Th>Actions</Table.Th>
            </Table.Tr>
          </Table.Thead>

          <Table.Tbody>
            {rows.map((client) => (
              <Table.Tr key={client.id}>
                <Table.Td>
                  <Text fw={600}>{client.nom}</Text>
                </Table.Td>

                <Table.Td>
                  {client.type_client === 'particulier'
                    ? 'Particulier'
                    : 'Entreprise'}
                </Table.Td>

                <Table.Td>
                  <Text size='sm'>{client.email || '—'}</Text>
                  <Text size='xs' c='dimmed'>
                    {client.telephone || '—'}
                  </Text>
                </Table.Td>

                <Table.Td>{client.adresse || '—'}</Table.Td>

                <Table.Td>{client.contacts}</Table.Td>

                <Table.Td>
                  <Badge color={client.actif ? 'green' : 'gray'} size='sm'>
                    {client.actif ? 'Actif' : 'Inactif'}
                  </Badge>
                </Table.Td>

                <Table.Td>
                  <Button
                    size='xs'
                    variant='light'
                    onClick={() => openEditModal(client)}
                  >
                    Éditer
                  </Button>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      <Group justify='space-between'>
        <Text size='sm' c='dimmed'>
          {count} client(s)
        </Text>

        {pages > 1 && (
          <Pagination total={pages} value={page} onChange={setPage} />
        )}
      </Group>

      <Modal
        closeOnClickOutside={false}
        opened={modalState.open}
        onClose={closeModal}
        size='lg'
        title={
          modalState.client
            ? `Modifier ${modalState.client.nom}`
            : 'Créer un client'
        }
      >
        <Stack gap='md'>
          {formError && (
            <Alert color='red' title='Erreur'>
              {formError}
            </Alert>
          )}

          <TextInput
            label='Nom'
            placeholder='ex : Client Saint-Exupéry'
            required
            value={formValues.nom}
            onChange={(event) => updateField('nom', event.currentTarget.value)}
          />

          <Select
            label='Type'
            data={[
              { value: 'entreprise', label: 'Entreprise ou association' },
              { value: 'particulier', label: 'Particulier' }
            ]}
            value={formValues.type_client}
            onChange={(value) =>
              updateField('type_client', value ?? 'entreprise')
            }
          />

          <Group grow>
            <TextInput
              label='E-mail'
              description='Facultatif, mais unique quand il est renseigné.'
              value={formValues.email}
              onChange={(event) =>
                updateField('email', event.currentTarget.value)
              }
            />
            <TextInput
              label='Téléphone'
              value={formValues.telephone}
              onChange={(event) =>
                updateField('telephone', event.currentTarget.value)
              }
            />
          </Group>

          <TextInput
            label='SIRET'
            value={formValues.siret}
            onChange={(event) =>
              updateField('siret', event.currentTarget.value)
            }
          />

          <Switch
            label='Client actif'
            description='Un client inactif reste consultable, mais on ne peut plus créer de manifestation dessus.'
            checked={formValues.actif}
            onChange={(event) =>
              updateField('actif', event.currentTarget.checked)
            }
          />

          <Textarea
            label='Adresse'
            autosize
            minRows={2}
            value={formValues.adresse}
            onChange={(event) =>
              updateField('adresse', event.currentTarget.value)
            }
          />

          <Group justify='flex-end'>
            <Button variant='default' onClick={closeModal} disabled={saving}>
              Annuler
            </Button>

            <Button onClick={saveClient} loading={saving}>
              Enregistrer
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
