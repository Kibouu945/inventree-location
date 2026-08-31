import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Button,
  Group,
  Loader,
  Modal,
  Pagination,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
  Title
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { GROUPES_URL, listParams, pageCount } from './api';
import { apiErrorMessage } from './apiError';
import type {
  BackOfficeGroupe,
  BackOfficeGroupeFormValues,
  Page
} from './types';
import { usePagedSearch } from './usePagedSearch';

interface ModalState {
  open: boolean;
  groupe?: BackOfficeGroupe;
}

function emptyForm(): BackOfficeGroupeFormValues {
  return { nom: '', code: '', adresse: '' };
}

function formFromGroupe(groupe: BackOfficeGroupe): BackOfficeGroupeFormValues {
  return {
    nom: groupe.nom,
    code: groupe.code,
    adresse: groupe.adresse ?? ''
  };
}

export function GroupesTab({ context }: { context: InvenTreePluginContext }) {
  const { search, debouncedSearch, page, setPage, updateSearch } =
    usePagedSearch();

  const [modalState, setModalState] = useState<ModalState>({ open: false });
  const [formValues, setFormValues] = useState<BackOfficeGroupeFormValues>(
    emptyForm()
  );
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const groupesQuery = useQuery<Page<BackOfficeGroupe>>(
    {
      queryKey: ['backoffice-groupes', debouncedSearch, page],
      queryFn: async () => {
        const response = await context.api.get(GROUPES_URL, {
          params: listParams(page, debouncedSearch)
        });

        return response.data;
      }
    },
    context.queryClient
  );

  const rows = groupesQuery.data?.results ?? [];
  const count = groupesQuery.data?.count ?? 0;
  const pages = pageCount(count);

  function openCreateModal() {
    setFormError('');
    setFormValues(emptyForm());
    setModalState({ open: true });
  }

  function openEditModal(groupe: BackOfficeGroupe) {
    setFormError('');
    setFormValues(formFromGroupe(groupe));
    setModalState({ open: true, groupe });
  }

  function closeModal() {
    if (saving) {
      return;
    }

    setModalState({ open: false });
    setFormError('');
    setFormValues(emptyForm());
  }

  function updateField<K extends keyof BackOfficeGroupeFormValues>(
    field: K,
    value: BackOfficeGroupeFormValues[K]
  ) {
    setFormValues((current) => ({ ...current, [field]: value }));
  }

  async function saveGroupe() {
    setSaving(true);
    setFormError('');

    try {
      const payload = {
        nom: formValues.nom.trim(),
        code: formValues.code.trim(),
        adresse: formValues.adresse.trim()
      };

      if (modalState.groupe) {
        await context.api.patch(
          `${GROUPES_URL}${modalState.groupe.id}/`,
          payload
        );
      } else {
        await context.api.post(GROUPES_URL, payload);
      }

      // Le sélecteur de groupe de l'onglet utilisateurs lit une autre clé.
      await context.queryClient.invalidateQueries({
        queryKey: ['backoffice-groupes-options']
      });
      await groupesQuery.refetch();
      closeModal();
    } catch (error: unknown) {
      setFormError(
        apiErrorMessage(error, "Impossible d'enregistrer le groupe.")
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Stack gap='md'>
      <Group justify='space-between'>
        <Title order={5}>Groupes</Title>

        <Button onClick={openCreateModal}>Créer un groupe</Button>
      </Group>

      <TextInput
        label='Recherche'
        placeholder='Nom ou code…'
        value={search}
        onChange={(event) => updateSearch(event.currentTarget.value)}
        w={320}
      />

      {groupesQuery.isError && (
        <Alert color='red' title='Erreur'>
          Impossible de charger les groupes.
        </Alert>
      )}

      {groupesQuery.isLoading ? (
        <Group justify='center' p='xl'>
          <Loader />
        </Group>
      ) : rows.length === 0 ? (
        <Text c='dimmed'>Aucun groupe trouvé.</Text>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Nom</Table.Th>
              <Table.Th>Code</Table.Th>
              <Table.Th>Adresse</Table.Th>
              <Table.Th>Membres</Table.Th>
              <Table.Th>Actions</Table.Th>
            </Table.Tr>
          </Table.Thead>

          <Table.Tbody>
            {rows.map((groupe) => (
              <Table.Tr key={groupe.id}>
                <Table.Td>
                  <Text fw={600}>{groupe.nom}</Text>
                </Table.Td>

                <Table.Td>{groupe.code}</Table.Td>

                <Table.Td>{groupe.adresse || '—'}</Table.Td>

                <Table.Td>{groupe.membres}</Table.Td>

                <Table.Td>
                  <Button
                    size='xs'
                    variant='light'
                    onClick={() => openEditModal(groupe)}
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
          {count} groupe(s)
        </Text>

        {pages > 1 && (
          <Pagination total={pages} value={page} onChange={setPage} />
        )}
      </Group>

      <Modal
        opened={modalState.open}
        onClose={closeModal}
        size='lg'
        title={
          modalState.groupe
            ? `Modifier ${modalState.groupe.nom}`
            : 'Créer un groupe'
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
            placeholder='ex : Groupe Saint-Exupéry'
            required
            value={formValues.nom}
            onChange={(event) => updateField('nom', event.currentTarget.value)}
          />

          <TextInput
            label='Code'
            placeholder='ex : SEX-01'
            description='Identifiant court et unique du groupe.'
            required
            value={formValues.code}
            onChange={(event) => updateField('code', event.currentTarget.value)}
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

            <Button onClick={saveGroupe} loading={saving}>
              Enregistrer
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
