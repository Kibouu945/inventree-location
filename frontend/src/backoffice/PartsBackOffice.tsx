// SCRUM-111 — Back-office front : création / édition complète d'une Part.
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Group,
  Loader,
  Modal,
  NumberInput,
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

import { canManageBackOffice } from '../roles';
import { listParams, PARTS_URL, pageCount } from './api';
import { apiErrorMessage } from './apiError';
import type {
  BackOfficePart,
  BackOfficePartFormValues,
  Page
} from './partTypes';
import { usePagedSearch } from './usePagedSearch';

interface ModalState {
  open: boolean;
  part?: BackOfficePart;
}

function emptyForm(): BackOfficePartFormValues {
  return {
    NOI: '',
    name: '',
    description: '',
    link: '',
    active: true,
    salable: false,
    virtual: false,
    is_rentable: true,
    consommable: false,
    seuil_alerte_bas: null,
    seuil_alerte_haut: null,
    alertes_desactivees: false,
    stock_initial: 0
  };
}

function formFromPart(part: BackOfficePart): BackOfficePartFormValues {
  return {
    NOI: part.NOI ?? '',
    name: part.name ?? '',
    description: part.description ?? '',
    link: part.link ?? '',
    active: part.active,
    salable: part.salable,
    virtual: part.virtual,
    is_rentable: part.is_rentable,
    consommable: part.consommable,
    seuil_alerte_bas: part.seuil_alerte_bas,
    seuil_alerte_haut: part.seuil_alerte_haut,
    alertes_desactivees: part.alertes_desactivees,
    stock_initial: 0
  };
}

function numberOrZero(value: string | number): number {
  const parsed = Number(value);

  return Number.isFinite(parsed) ? parsed : 0;
}

function nullableNumber(value: string | number): number | null {
  if (value === '') {
    return null;
  }

  const parsed = Number(value);

  return Number.isFinite(parsed) ? parsed : null;
}

export function PartsBackOffice({
  context
}: {
  context: InvenTreePluginContext;
}) {
  const canAccess = canManageBackOffice(context);

  const { search, debouncedSearch, page, setPage, updateSearch } =
    usePagedSearch();

  const [modalState, setModalState] = useState<ModalState>({ open: false });
  const [formValues, setFormValues] = useState<BackOfficePartFormValues>(
    emptyForm()
  );
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const partsQuery = useQuery<Page<BackOfficePart>>(
    {
      queryKey: ['backoffice-parts', debouncedSearch, page],
      enabled: canAccess,
      queryFn: async () => {
        const response = await context.api.get(PARTS_URL, {
          params: listParams(page, debouncedSearch)
        });

        return response.data;
      }
    },
    context.queryClient
  );

  const rows = partsQuery.data?.results ?? [];
  const count = partsQuery.data?.count ?? 0;
  const pages = pageCount(count);

  function updateField<K extends keyof BackOfficePartFormValues>(
    field: K,
    value: BackOfficePartFormValues[K]
  ) {
    setFormValues((current) => ({
      ...current,
      [field]: value
    }));
  }

  function openCreateModal() {
    setFormError('');
    setFormValues(emptyForm());
    setModalState({ open: true });
  }

  function openEditModal(part: BackOfficePart) {
    setFormError('');
    setFormValues(formFromPart(part));
    setModalState({ open: true, part });
  }

  function closeModal() {
    if (saving) {
      return;
    }

    setModalState({ open: false });
    setFormError('');
    setFormValues(emptyForm());
  }

  async function savePart() {
    setSaving(true);
    setFormError('');

    try {
      const payload = {
        NOI: formValues.NOI.trim(),
        name: formValues.name.trim(),
        description: formValues.description.trim(),
        link: formValues.link.trim(),
        active: formValues.active,
        salable: formValues.salable,
        virtual: formValues.virtual,
        is_rentable: formValues.is_rentable,
        consommable: formValues.consommable,
        seuil_alerte_bas: formValues.seuil_alerte_bas,
        seuil_alerte_haut: formValues.seuil_alerte_haut,
        alertes_desactivees: formValues.alertes_desactivees,
        stock_initial: formValues.stock_initial
      };

      if (modalState.part) {
        await context.api.patch(`${PARTS_URL}${modalState.part.id}/`, payload);
      } else {
        await context.api.post(PARTS_URL, payload);
      }

      await partsQuery.refetch();
      closeModal();
    } catch (error: unknown) {
      setFormError(apiErrorMessage(error, "Impossible d'enregistrer la Part."));
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(part: BackOfficePart) {
    try {
      await context.api.patch(`${PARTS_URL}${part.id}/`, {
        active: !part.active
      });

      setFormError('');
      await partsQuery.refetch();
    } catch (error: unknown) {
      setFormError(
        apiErrorMessage(error, "Impossible de modifier l'état de la Part.")
      );
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
          Back-office Parts
        </Title>

        <Button onClick={openCreateModal}>Créer une Part</Button>
      </Group>

      <TextInput
        label='Recherche'
        placeholder='Nom, NOI, description…'
        value={search}
        onChange={(event) => updateSearch(event.currentTarget.value)}
        w={320}
      />

      {formError && (
        <Alert color='red' title='Erreur'>
          {formError}
        </Alert>
      )}

      {partsQuery.isError && (
        <Alert color='red' title='Erreur'>
          Impossible de charger les Parts.
        </Alert>
      )}

      {partsQuery.isLoading ? (
        <Group justify='center' p='xl'>
          <Loader />
        </Group>
      ) : rows.length === 0 ? (
        <Text c='dimmed'>Aucune Part trouvée.</Text>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Nom</Table.Th>
              <Table.Th>NOI</Table.Th>
              <Table.Th>État</Table.Th>
              <Table.Th>Type</Table.Th>
              <Table.Th>Stock InvenTree</Table.Th>
              <Table.Th>Seuil bas</Table.Th>
              <Table.Th>Actions</Table.Th>
            </Table.Tr>
          </Table.Thead>

          <Table.Tbody>
            {rows.map((part) => (
              <Table.Tr key={part.id}>
                <Table.Td>
                  <Stack gap={0}>
                    <Text fw={600}>{part.name}</Text>
                    <Text size='xs' c='dimmed'>
                      {part.description || '—'}
                    </Text>
                  </Stack>
                </Table.Td>

                <Table.Td>{part.NOI || '—'}</Table.Td>

                <Table.Td>
                  <Badge color={part.active ? 'green' : 'red'}>
                    {part.active ? 'Actif' : 'Inactif'}
                  </Badge>
                </Table.Td>

                <Table.Td>
                  <Group gap='xs'>
                    {part.pack && <Badge color='violet'>PACK</Badge>}
                    {part.virtual && <Badge color='blue'>Virtuel</Badge>}
                    {part.consommable && (
                      <Badge color='orange'>Consommable</Badge>
                    )}
                    {part.is_rentable && !part.consommable && (
                      <Badge color='green'>Louable</Badge>
                    )}
                    {part.salable && <Badge color='teal'>Vendable</Badge>}
                  </Group>
                </Table.Td>

                <Table.Td>{part.stock_total}</Table.Td>

                <Table.Td>{part.seuil_alerte_bas ?? '—'}</Table.Td>

                <Table.Td>
                  <Group gap='xs'>
                    <Button
                      size='xs'
                      variant='light'
                      onClick={() => openEditModal(part)}
                    >
                      Éditer
                    </Button>

                    <Button
                      size='xs'
                      variant='outline'
                      color={part.active ? 'red' : 'green'}
                      onClick={() => toggleActive(part)}
                    >
                      {part.active ? 'Désactiver' : 'Activer'}
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
          {count} Part(s)
        </Text>

        {pages > 1 && (
          <Pagination total={pages} value={page} onChange={setPage} />
        )}
      </Group>

      <Modal
        opened={modalState.open}
        onClose={closeModal}
        size='xl'
        title={modalState.part ? 'Modifier une Part' : 'Créer une Part'}
      >
        <Stack gap='md'>
          {formError && (
            <Alert color='red' title='Erreur'>
              {formError}
            </Alert>
          )}

          <Group grow>
            <TextInput
              label='NOI'
              placeholder='NOI-001'
              value={formValues.NOI}
              onChange={(event) =>
                updateField('NOI', event.currentTarget.value)
              }
            />

            <TextInput
              label='Nom'
              placeholder='Table pliante'
              required
              value={formValues.name}
              onChange={(event) =>
                updateField('name', event.currentTarget.value)
              }
            />
          </Group>

          <Textarea
            label='Description'
            placeholder='Description de la Part'
            maxLength={500}
            value={formValues.description}
            onChange={(event) =>
              updateField('description', event.currentTarget.value)
            }
          />

          <TextInput
            label='URL'
            placeholder='https://example.com'
            value={formValues.link}
            onChange={(event) => updateField('link', event.currentTarget.value)}
          />

          <Group grow>
            <Checkbox
              label='Actif'
              checked={formValues.active}
              onChange={(event) =>
                updateField('active', event.currentTarget.checked)
              }
            />

            <Checkbox
              label='Vendable'
              checked={formValues.salable}
              onChange={(event) =>
                updateField('salable', event.currentTarget.checked)
              }
            />

            <Checkbox
              label='Virtuel'
              checked={formValues.virtual}
              onChange={(event) =>
                updateField('virtual', event.currentTarget.checked)
              }
            />
          </Group>

          <Group grow>
            <Checkbox
              label='Louable'
              checked={formValues.is_rentable}
              onChange={(event) =>
                updateField('is_rentable', event.currentTarget.checked)
              }
            />

            <Checkbox
              label='Consommable'
              checked={formValues.consommable}
              onChange={(event) =>
                updateField('consommable', event.currentTarget.checked)
              }
            />
          </Group>

          <NumberInput
            label='Stock initial à ajouter'
            min={0}
            description={
              modalState.part
                ? 'Ajoute une ligne de stock InvenTree si > 0. Le stock existant ne se modifie pas ici.'
                : 'Crée le stock initial dans InvenTree si > 0.'
            }
            value={formValues.stock_initial}
            onChange={(value) =>
              updateField('stock_initial', numberOrZero(value))
            }
          />

          <Checkbox
            label='Alertes de seuil désactivées'
            description='Conserve les seuils mais cesse de faire remonter cet article dans les alertes.'
            checked={formValues.alertes_desactivees}
            onChange={(event) =>
              updateField('alertes_desactivees', event.currentTarget.checked)
            }
          />

          {/* Les deux seuils n'alimentent une alerte que pour un consommable
              (US-09, CDC V06). Le dire ici évite de saisir une valeur inerte. */}
          <Group grow>
            <NumberInput
              label='Seuil bas'
              description={
                formValues.consommable
                  ? undefined
                  : 'Sans effet : les seuils ne valent que pour un consommable.'
              }
              min={0}
              value={formValues.seuil_alerte_bas ?? ''}
              onChange={(value) =>
                updateField('seuil_alerte_bas', nullableNumber(value))
              }
            />

            <NumberInput
              label='Seuil haut'
              description={
                formValues.consommable
                  ? undefined
                  : 'Sans effet : les seuils ne valent que pour un consommable.'
              }
              min={0}
              value={formValues.seuil_alerte_haut ?? ''}
              onChange={(value) =>
                updateField('seuil_alerte_haut', nullableNumber(value))
              }
            />
          </Group>

          {modalState.part?.pack && (
            <Alert color='violet' title='PACK détecté'>
              Cette Part est considérée comme un PACK via la BOM native
              InvenTree. Elle ne doit pas être déclarée consommable.
            </Alert>
          )}

          <Group justify='flex-end'>
            <Button variant='default' onClick={closeModal} disabled={saving}>
              Annuler
            </Button>

            <Button onClick={savePart} loading={saving}>
              Enregistrer
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
