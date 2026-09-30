// Onglet « Contacts » du back-office — créer et éditer les interlocuteurs d'un
// client (F1).
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
  TextInput,
  Title
} from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { CLIENTS_URL, CONTACTS_URL, listParams, pageCount } from './api';
import { apiErrorMessage } from './apiError';
import { nomComplet } from './contactLogic';
import type {
  BackOfficeClient,
  BackOfficeContact,
  BackOfficeContactFormValues,
  Page
} from './types';
import { usePagedSearch } from './usePagedSearch';

/**
 * `null` ne convient pas : un `Select` Mantine rend `null` quand on efface, et
 * on ne distinguerait plus « aucun filtre » de « filtre vidé ».
 */
const TOUS = 'tous';

/** Assez pour alimenter un sélecteur : le filtre n'est pas une liste paginée. */
const CLIENTS_PAR_PAGE = 200;

interface ModalState {
  open: boolean;
  contact?: BackOfficeContact;
}

/** Le formulaire porte le client à part : il est imposé quand on filtre. */
interface FormValues extends BackOfficeContactFormValues {
  client: string | null;
}

function emptyForm(client: string | null): FormValues {
  return {
    client,
    nom: '',
    prenom: '',
    email: '',
    telephone: '',
    actif: true
  };
}

function formFromContact(contact: BackOfficeContact): FormValues {
  return {
    client: String(contact.client),
    nom: contact.nom,
    prenom: contact.prenom ?? '',
    email: contact.email ?? '',
    telephone: contact.telephone ?? '',
    actif: contact.actif
  };
}

export function ContactsTab({
  context,
  clientAEnchainer,
  onEnchainementFait
}: {
  context: InvenTreePluginContext;
  /** Client tout juste créé : on ouvre directement son premier contact. */
  clientAEnchainer?: { id: number; nom: string } | null;
  onEnchainementFait?: () => void;
}) {
  const { search, debouncedSearch, page, setPage, updateSearch } =
    usePagedSearch();

  const [clientFiltre, setClientFiltre] = useState<string>(TOUS);
  const [modalState, setModalState] = useState<ModalState>({ open: false });
  const [formValues, setFormValues] = useState<FormValues>(emptyForm(null));
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const clientsQuery = useQuery<Page<BackOfficeClient>>(
    {
      queryKey: ['backoffice-clients-options'],
      queryFn: async () => {
        const response = await context.api.get(CLIENTS_URL, {
          params: { page_size: String(CLIENTS_PAR_PAGE) }
        });

        return response.data;
      }
    },
    context.queryClient
  );

  const contactsQuery = useQuery<Page<BackOfficeContact>>(
    {
      queryKey: ['backoffice-contacts', debouncedSearch, clientFiltre, page],
      queryFn: async () => {
        const params = listParams(page, debouncedSearch);

        if (clientFiltre !== TOUS) {
          params.client = clientFiltre;
        }

        const response = await context.api.get(CONTACTS_URL, { params });

        return response.data;
      }
    },
    context.queryClient
  );

  const clients = clientsQuery.data?.results ?? [];
  const rows = contactsQuery.data?.results ?? [];
  const count = contactsQuery.data?.count ?? 0;
  const pages = pageCount(count);

  const clientOptions = clients.map((client) => ({
    value: String(client.id),
    // Un client inactif garde ses contacts et reste donc proposé, mais il se
    // signale : on n'y crée plus de manifestation.
    label: client.actif ? client.nom : `${client.nom} (inactif)`
  }));

  function changerFiltre(valeur: string | null) {
    // Comme pour la recherche : rester en page 3 d'un filtre qui n'a plus
    // qu'une page afficherait une liste vide.
    setClientFiltre(valeur ?? TOUS);
    setPage(1);
  }

  // Créer un client sans son interlocuteur oblige à revenir plus tard : on
  // enchaîne sur le contact, client déjà choisi.
  useEffect(() => {
    if (!clientAEnchainer) {
      return;
    }

    setFormError('');
    setClientFiltre(String(clientAEnchainer.id));
    setFormValues(emptyForm(String(clientAEnchainer.id)));
    setModalState({ open: true });
    onEnchainementFait?.();
  }, [clientAEnchainer, onEnchainementFait]);

  function openCreateModal() {
    setFormError('');
    // Le client filtré est préchoisi : on crée presque toujours un contact
    // depuis la liste du client concerné.
    setFormValues(emptyForm(clientFiltre === TOUS ? null : clientFiltre));
    setModalState({ open: true });
  }

  function openEditModal(contact: BackOfficeContact) {
    setFormError('');
    setFormValues(formFromContact(contact));
    setModalState({ open: true, contact });
  }

  function closeModal() {
    if (saving) {
      return;
    }

    setModalState({ open: false });
    setFormError('');
    setFormValues(emptyForm(null));
  }

  function updateField<K extends keyof FormValues>(
    field: K,
    value: FormValues[K]
  ) {
    setFormValues((current) => ({ ...current, [field]: value }));
  }

  /** Rafraîchit tout ce qui compte ou liste des contacts ailleurs. */
  async function rafraichir() {
    await context.queryClient.invalidateQueries({
      // Le compteur « Contacts » de l'onglet Clients.
      queryKey: ['backoffice-clients']
    });
    await context.queryClient.invalidateQueries({
      // Le sélecteur « Contact référent » de l'écran Manifestations.
      queryKey: ['contacts']
    });
    await contactsQuery.refetch();
  }

  async function saveContact() {
    if (!formValues.client) {
      setFormError('Choisissez le client auquel rattacher ce contact.');
      return;
    }

    setSaving(true);
    setFormError('');

    try {
      const payload = {
        client: Number(formValues.client),
        nom: formValues.nom.trim(),
        prenom: formValues.prenom.trim(),
        // Chaîne vide envoyée en `null` : l'unicité de l'e-mail tolère
        // plusieurs absences, pas plusieurs chaînes vides.
        email: formValues.email.trim() || null,
        telephone: formValues.telephone.trim(),
        actif: formValues.actif
      };

      if (modalState.contact) {
        await context.api.patch(
          `${CONTACTS_URL}${modalState.contact.id}/`,
          payload
        );
      } else {
        await context.api.post(CONTACTS_URL, payload);
      }

      await rafraichir();
      closeModal();
    } catch (error: unknown) {
      setFormError(
        apiErrorMessage(error, "Impossible d'enregistrer le contact.")
      );
    }

    setSaving(false);
  }

  /** Bascule l'état d'un contact sans passer par le formulaire. */
  async function basculerActif(contact: BackOfficeContact) {
    try {
      await context.api.patch(`${CONTACTS_URL}${contact.id}/`, {
        actif: !contact.actif
      });
      await rafraichir();
    } catch (error: unknown) {
      setFormError(
        apiErrorMessage(error, "Impossible de changer l'état du contact.")
      );
    }
  }

  return (
    <Stack gap='md'>
      <Group justify='space-between'>
        <Title order={5}>Contacts</Title>

        <Button onClick={openCreateModal}>Créer un contact</Button>
      </Group>

      {formError && !modalState.open && (
        <Alert color='red' title='Erreur'>
          {formError}
        </Alert>
      )}

      <Group align='flex-end' gap='md'>
        <TextInput
          label='Recherche'
          placeholder='Nom, prénom ou e-mail…'
          value={search}
          onChange={(event) => updateSearch(event.currentTarget.value)}
          w={320}
        />

        <Select
          label='Client'
          data={[{ value: TOUS, label: 'Tous les clients' }, ...clientOptions]}
          value={clientFiltre}
          onChange={changerFiltre}
          searchable
          w={280}
        />
      </Group>

      {contactsQuery.isError && (
        <Alert color='red' title='Erreur'>
          Impossible de charger les contacts.
        </Alert>
      )}

      {contactsQuery.isLoading ? (
        <Group justify='center' p='xl'>
          <Loader />
        </Group>
      ) : rows.length === 0 ? (
        <Text c='dimmed'>Aucun contact trouvé.</Text>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Contact</Table.Th>
              <Table.Th>Client</Table.Th>
              <Table.Th>E-mail</Table.Th>
              <Table.Th>Téléphone</Table.Th>
              <Table.Th>État</Table.Th>
              <Table.Th>Actions</Table.Th>
            </Table.Tr>
          </Table.Thead>

          <Table.Tbody>
            {rows.map((contact) => (
              <Table.Tr key={contact.id}>
                <Table.Td>
                  <Text fw={600}>{nomComplet(contact)}</Text>
                </Table.Td>

                <Table.Td>{contact.client_nom}</Table.Td>

                <Table.Td>{contact.email || '—'}</Table.Td>

                <Table.Td>{contact.telephone || '—'}</Table.Td>

                <Table.Td>
                  <Badge color={contact.actif ? 'green' : 'gray'} size='sm'>
                    {contact.actif ? 'Actif' : 'Inactif'}
                  </Badge>
                </Table.Td>

                <Table.Td>
                  <Group gap='xs' wrap='nowrap'>
                    <Button
                      size='xs'
                      variant='light'
                      onClick={() => openEditModal(contact)}
                    >
                      Éditer
                    </Button>

                    <Button
                      size='xs'
                      variant='subtle'
                      color={contact.actif ? 'red' : 'green'}
                      onClick={() => basculerActif(contact)}
                    >
                      {contact.actif ? 'Désactiver' : 'Réactiver'}
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
          {count} contact(s)
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
          modalState.contact
            ? `Modifier ${nomComplet(modalState.contact)}`
            : 'Créer un contact'
        }
      >
        <Stack gap='md'>
          {formError && (
            <Alert color='red' title='Erreur'>
              {formError}
            </Alert>
          )}

          <Select
            label='Client'
            description='Le client auquel ce contact appartient.'
            required
            data={clientOptions}
            value={formValues.client}
            onChange={(valeur) => updateField('client', valeur)}
            searchable
            nothingFoundMessage='Aucun client'
          />

          <Group grow>
            <TextInput
              label='Prénom'
              value={formValues.prenom}
              onChange={(event) =>
                updateField('prenom', event.currentTarget.value)
              }
            />
            <TextInput
              label='Nom'
              required
              value={formValues.nom}
              onChange={(event) =>
                updateField('nom', event.currentTarget.value)
              }
            />
          </Group>

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

          <Switch
            label='Contact actif'
            description="Un contact inactif sort des sélecteurs, mais reste lisible sur les devis qu'il a signés."
            checked={formValues.actif}
            onChange={(event) =>
              updateField('actif', event.currentTarget.checked)
            }
          />

          <Group justify='flex-end'>
            <Button variant='default' onClick={closeModal} disabled={saving}>
              Annuler
            </Button>

            <Button onClick={saveContact} loading={saving}>
              Enregistrer
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
