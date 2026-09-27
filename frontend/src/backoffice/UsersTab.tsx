import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Group,
  Loader,
  Modal,
  Pagination,
  PasswordInput,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { listParams, pageCount, ROLES_URL, USERS_URL } from './api';
import { apiErrorMessage } from './apiError';
import type {
  BackOfficeRole,
  BackOfficeUser,
  BackOfficeUserFormValues,
  Page
} from './types';
import { usePagedSearch } from './usePagedSearch';

interface ModalState {
  open: boolean;
  user?: BackOfficeUser;
}

function emptyForm(): BackOfficeUserFormValues {
  return {
    username: '',
    first_name: '',
    last_name: '',
    email: '',
    password: '',
    is_active: true,
    role: null,
    telephone: ''
  };
}

function formFromUser(user: BackOfficeUser): BackOfficeUserFormValues {
  return {
    username: user.username,
    first_name: user.first_name ?? '',
    last_name: user.last_name ?? '',
    email: user.email ?? '',
    password: '',
    is_active: user.is_active,
    role: user.role,
    telephone: user.telephone ?? ''
  };
}

function userDisplayName(user: BackOfficeUser): string {
  const fullName = `${user.first_name ?? ''} ${user.last_name ?? ''}`.trim();

  return fullName || user.username;
}

function roleLabel(role: string, roles: BackOfficeRole[]): string {
  return roles.find((item) => item.name === role)?.label ?? role;
}

export function UsersTab({ context }: { context: InvenTreePluginContext }) {
  const { search, debouncedSearch, page, setPage, updateSearch } =
    usePagedSearch();

  const [modalState, setModalState] = useState<ModalState>({ open: false });
  const [formValues, setFormValues] = useState<BackOfficeUserFormValues>(
    emptyForm()
  );
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const usersQuery = useQuery<Page<BackOfficeUser>>(
    {
      queryKey: ['backoffice-users', debouncedSearch, page],
      queryFn: async () => {
        const response = await context.api.get(USERS_URL, {
          params: listParams(page, debouncedSearch)
        });

        return response.data;
      }
    },
    context.queryClient
  );

  const rolesQuery = useQuery<BackOfficeRole[]>(
    {
      queryKey: ['backoffice-roles'],
      queryFn: async () => {
        const response = await context.api.get(ROLES_URL);
        return response.data;
      }
    },
    context.queryClient
  );

  const roleOptions = (rolesQuery.data ?? []).map((role) => ({
    value: role.name,
    label: role.label
  }));

  const rows = usersQuery.data?.results ?? [];
  const count = usersQuery.data?.count ?? 0;
  const pages = pageCount(count);

  function openCreateModal() {
    setFormError('');
    setFormValues(emptyForm());
    setModalState({ open: true });
  }

  function openEditModal(user: BackOfficeUser) {
    setFormError('');
    setFormValues(formFromUser(user));
    setModalState({ open: true, user });
  }

  function closeModal() {
    if (saving) {
      return;
    }

    setModalState({ open: false });
    setFormError('');
    setFormValues(emptyForm());
  }

  function updateField<K extends keyof BackOfficeUserFormValues>(
    field: K,
    value: BackOfficeUserFormValues[K]
  ) {
    setFormValues((current) => ({
      ...current,
      [field]: value
    }));
  }

  async function saveUser() {
    setSaving(true);
    setFormError('');

    try {
      const payload: Record<string, unknown> = {
        username: formValues.username.trim(),
        first_name: formValues.first_name.trim(),
        last_name: formValues.last_name.trim(),
        email: formValues.email.trim(),
        is_active: formValues.is_active,
        role: formValues.role,
        telephone: formValues.telephone.trim()
      };

      if (formValues.password.trim()) {
        payload.password = formValues.password.trim();
      }

      if (modalState.user) {
        await context.api.patch(`${USERS_URL}${modalState.user.id}/`, payload);
      } else {
        await context.api.post(USERS_URL, payload);
      }

      await context.queryClient.invalidateQueries({
        queryKey: ['backoffice-users']
      });
      closeModal();
    } catch (error: unknown) {
      setFormError(
        apiErrorMessage(error, "Impossible d'enregistrer l'utilisateur.")
      );
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(user: BackOfficeUser) {
    try {
      await context.api.patch(`${USERS_URL}${user.id}/`, {
        is_active: !user.is_active
      });

      setFormError('');
      await context.queryClient.invalidateQueries({
        queryKey: ['backoffice-users']
      });
    } catch (error: unknown) {
      setFormError(
        apiErrorMessage(
          error,
          "Impossible de modifier l'état de l'utilisateur."
        )
      );
    }
  }

  return (
    <Stack gap='md'>
      <Group justify='space-between'>
        <Title order={5}>Utilisateurs</Title>

        <Button onClick={openCreateModal}>Créer un utilisateur</Button>
      </Group>

      <TextInput
        label='Recherche'
        placeholder='Username, prénom, nom ou email…'
        value={search}
        onChange={(event) => updateSearch(event.currentTarget.value)}
        w={320}
      />

      {/* Affiché hors modale aussi : un échec d'activation / désactivation se
          produit depuis le tableau, où la modale est fermée. */}
      {formError && !modalState.open && (
        <Alert color='red' title='Erreur'>
          {formError}
        </Alert>
      )}

      {usersQuery.isError && (
        <Alert color='red' title='Erreur'>
          Impossible de charger les utilisateurs.
        </Alert>
      )}

      {usersQuery.isLoading || rolesQuery.isLoading ? (
        <Group justify='center' p='xl'>
          <Loader />
        </Group>
      ) : rows.length === 0 ? (
        <Text c='dimmed'>Aucun utilisateur trouvé.</Text>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Identifiant</Table.Th>
              <Table.Th>Utilisateur</Table.Th>
              <Table.Th>Contact</Table.Th>
              <Table.Th>Rôle</Table.Th>
              <Table.Th>État</Table.Th>
              <Table.Th>Actions</Table.Th>
            </Table.Tr>
          </Table.Thead>

          <Table.Tbody>
            {rows.map((user) => (
              <Table.Tr key={user.id}>
                <Table.Td>
                  {/*
                    L'identifiant de connexion a sa colonne : c'est lui qu'on
                    communique, et il se lisait en gris sous le nom complet.
                    Recette Tassin du 27/09, point 4.4.
                  */}
                  <Text ff='monospace' size='sm'>
                    {user.username}
                  </Text>
                </Table.Td>

                <Table.Td>
                  <Text fw={600}>{userDisplayName(user)}</Text>
                </Table.Td>

                <Table.Td>
                  <Stack gap={0}>
                    <Text size='sm'>{user.email || '—'}</Text>
                    <Text size='xs' c={user.telephone ? 'dimmed' : 'orange'}>
                      {user.telephone || 'Téléphone manquant'}
                    </Text>
                  </Stack>
                </Table.Td>

                <Table.Td>
                  {user.role ? (
                    <Badge variant='light'>
                      {roleLabel(user.role, rolesQuery.data ?? [])}
                    </Badge>
                  ) : (
                    <Text size='sm' c='dimmed'>
                      Aucun rôle
                    </Text>
                  )}
                </Table.Td>

                <Table.Td>
                  <Badge color={user.is_active ? 'green' : 'red'}>
                    {user.is_active ? 'Actif' : 'Inactif'}
                  </Badge>
                </Table.Td>

                <Table.Td>
                  <Group gap='xs'>
                    <Button
                      size='xs'
                      variant='light'
                      onClick={() => openEditModal(user)}
                    >
                      Éditer
                    </Button>

                    <Button
                      size='xs'
                      variant='outline'
                      color={user.is_active ? 'red' : 'green'}
                      onClick={() => toggleActive(user)}
                    >
                      {user.is_active ? 'Désactiver' : 'Activer'}
                    </Button>
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      <Group justify='space-between'>
        <Text size='sm' c='dimmed'>
          {count} utilisateur(s)
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
          modalState.user
            ? `Modifier ${modalState.user.username}`
            : 'Créer un utilisateur'
        }
      >
        <Stack gap='md'>
          {formError && (
            <Alert color='red' title='Erreur'>
              {formError}
            </Alert>
          )}

          <TextInput
            label='Nom utilisateur'
            placeholder='ex : jdupont'
            required
            value={formValues.username}
            onChange={(event) =>
              updateField('username', event.currentTarget.value)
            }
          />

          <Group grow>
            <TextInput
              label='Prénom'
              value={formValues.first_name}
              onChange={(event) =>
                updateField('first_name', event.currentTarget.value)
              }
            />

            <TextInput
              label='Nom'
              value={formValues.last_name}
              onChange={(event) =>
                updateField('last_name', event.currentTarget.value)
              }
            />
          </Group>

          <Group grow>
            <TextInput
              label='Email'
              type='email'
              value={formValues.email}
              onChange={(event) =>
                updateField('email', event.currentTarget.value)
              }
            />

            <TextInput
              label='Téléphone'
              placeholder='ex : 0102030405'
              description='Imprimé sur le bon de livraison.'
              value={formValues.telephone}
              onChange={(event) =>
                updateField('telephone', event.currentTarget.value)
              }
            />
          </Group>

          <PasswordInput
            label={modalState.user ? 'Nouveau mot de passe' : 'Mot de passe'}
            description={
              modalState.user
                ? 'Laisser vide pour conserver le mot de passe actuel.'
                : 'Obligatoire pour créer un utilisateur.'
            }
            required={!modalState.user}
            value={formValues.password}
            onChange={(event) =>
              updateField('password', event.currentTarget.value)
            }
          />

          <Select
            label='Rôle'
            placeholder='Sélectionner un rôle'
            description='Un acteur interne porte un seul rôle.'
            data={roleOptions}
            value={formValues.role}
            onChange={(value) => updateField('role', value)}
            clearable
            searchable
          />

          <Checkbox
            label='Utilisateur actif'
            checked={formValues.is_active}
            onChange={(event) =>
              updateField('is_active', event.currentTarget.checked)
            }
          />

          <Group justify='flex-end'>
            <Button variant='default' onClick={closeModal} disabled={saving}>
              Annuler
            </Button>

            <Button onClick={saveUser} loading={saving}>
              Enregistrer
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
