// SCRUM-108 — Back-office front : gestion des utilisateurs et des rôles.
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Group,
  Loader,
  Modal,
  MultiSelect,
  PasswordInput,
  Stack,
  Table,
  Text,
  TextInput,
  Title
} from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { canManageBackOffice } from '../roles';
import type {
  BackOfficeRole,
  BackOfficeUser,
  BackOfficeUserFormValues
} from './types';

const USERS_URL = '/plugin/inventree-location/backoffice/users/';
const ROLES_URL = '/plugin/inventree-location/backoffice/roles/';

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
    roles: []
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
    roles: user.roles ?? []
  };
}

function userDisplayName(user: BackOfficeUser): string {
  const fullName = `${user.first_name ?? ''} ${user.last_name ?? ''}`.trim();

  return fullName || user.username;
}

function roleLabel(role: string, roles: BackOfficeRole[]): string {
  return roles.find((item) => item.name === role)?.label ?? role;
}

export function UsersBackOffice({
  context
}: {
  context: InvenTreePluginContext;
}) {
  const canAccess = canManageBackOffice(context);

  const [search, setSearch] = useState('');
  const [debouncedSearch] = useDebouncedValue(search, 300);

  const [modalState, setModalState] = useState<ModalState>({ open: false });
  const [formValues, setFormValues] = useState<BackOfficeUserFormValues>(
    emptyForm()
  );
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const usersQuery = useQuery<BackOfficeUser[]>(
    {
      queryKey: ['backoffice-users', debouncedSearch],
      enabled: canAccess,
      queryFn: async () => {
        const response = await context.api.get(USERS_URL, {
          params: debouncedSearch.trim()
            ? { search: debouncedSearch.trim() }
            : {}
        });

        return response.data;
      }
    },
    context.queryClient
  );

  const rolesQuery = useQuery<BackOfficeRole[]>(
    {
      queryKey: ['backoffice-roles'],
      enabled: canAccess,
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
        roles: formValues.roles
      };

      if (formValues.password.trim()) {
        payload.password = formValues.password.trim();
      }

      if (modalState.user) {
        await context.api.patch(`${USERS_URL}${modalState.user.id}/`, payload);
      } else {
        await context.api.post(USERS_URL, payload);
      }

      await usersQuery.refetch();
      closeModal();
    } catch (error: unknown) {
      const apiError = error as {
        response?: { data?: Record<string, unknown> | string };
      };

      const data = apiError.response?.data;

      if (typeof data === 'string') {
        setFormError(data);
      } else if (data) {
        setFormError(JSON.stringify(data));
      } else {
        setFormError("Impossible d'enregistrer l'utilisateur.");
      }
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(user: BackOfficeUser) {
    try {
      await context.api.patch(`${USERS_URL}${user.id}/`, {
        is_active: !user.is_active
      });

      await usersQuery.refetch();
    } catch {
      setFormError("Impossible de modifier l'état de l'utilisateur.");
    }
  }

  if (!canAccess) {
    return (
      <Alert color='red' title='Accès refusé'>
        Cette interface est réservée aux administrateurs du module.
      </Alert>
    );
  }

  return (
    <Stack gap='md'>
      <Group justify='space-between'>
        <Title order={4} c={context.theme.primaryColor}>
          Back-office utilisateurs
        </Title>

        <Button onClick={openCreateModal}>Créer un utilisateur</Button>
      </Group>

      <TextInput
        label='Recherche'
        placeholder='Username, prénom, nom ou email…'
        value={search}
        onChange={(event) => setSearch(event.currentTarget.value)}
        w={320}
      />

      {usersQuery.isError && (
        <Alert color='red' title='Erreur'>
          Impossible de charger les utilisateurs.
        </Alert>
      )}

      {usersQuery.isLoading || rolesQuery.isLoading ? (
        <Group justify='center' p='xl'>
          <Loader />
        </Group>
      ) : (usersQuery.data ?? []).length === 0 ? (
        <Text c='dimmed'>Aucun utilisateur trouvé.</Text>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Utilisateur</Table.Th>
              <Table.Th>Email</Table.Th>
              <Table.Th>Rôles</Table.Th>
              <Table.Th>État</Table.Th>
              <Table.Th>Actions</Table.Th>
            </Table.Tr>
          </Table.Thead>

          <Table.Tbody>
            {(usersQuery.data ?? []).map((user) => (
              <Table.Tr key={user.id}>
                <Table.Td>
                  <Stack gap={0}>
                    <Text fw={600}>{userDisplayName(user)}</Text>
                    <Text size='xs' c='dimmed'>
                      @{user.username}
                    </Text>
                  </Stack>
                </Table.Td>

                <Table.Td>{user.email || '—'}</Table.Td>

                <Table.Td>
                  <Group gap='xs'>
                    {user.roles.length === 0 ? (
                      <Text size='sm' c='dimmed'>
                        Aucun rôle
                      </Text>
                    ) : (
                      user.roles.map((role) => (
                        <Badge key={role} variant='light'>
                          {roleLabel(role, rolesQuery.data ?? [])}
                        </Badge>
                      ))
                    )}
                  </Group>
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

      <Modal
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

          <TextInput
            label='Email'
            type='email'
            value={formValues.email}
            onChange={(event) => updateField('email', event.currentTarget.value)}
          />

          <PasswordInput
            label={
              modalState.user
                ? 'Nouveau mot de passe'
                : 'Mot de passe'
            }
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

          <MultiSelect
            label='Rôles'
            placeholder='Sélectionner un ou plusieurs rôles'
            data={roleOptions}
            value={formValues.roles}
            onChange={(value) => updateField('roles', value)}
            clearable
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