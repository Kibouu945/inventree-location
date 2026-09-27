// Création rapide d'une manifestation depuis la ligne d'un client.
// Recette Tassin du 27/09, point 4.5.2 : « pourrait-on copier [le bouton vert
// '+' de la manifestation] au niveau du client pour créer une manifestation ? »
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Button,
  Group,
  Modal,
  Select,
  Stack,
  Textarea,
  TextInput
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { optionsDeContacts } from '../backoffice/contactLogic';
import { DateTimeField, finSuivantLeDebut } from '../DateTimeField';
import { apiErrorMessage, type Manifestation } from './types';

const MANIFESTATIONS_URL = '/plugin/inventree-location/manifestations/';
const CONTACTS_URL = '/plugin/inventree-location/backoffice/contacts/';

interface FormState {
  nom: string;
  description: string;
  contact: string | null;
  date_debut: Date | null;
  date_fin: Date | null;
}

function emptyState(): FormState {
  return {
    nom: '',
    description: '',
    contact: null,
    date_debut: null,
    date_fin: null
  };
}

export function ManifestationCreateModal({
  context,
  opened,
  client,
  onClose,
  onCreated
}: {
  context: InvenTreePluginContext;
  opened: boolean;
  /** Client porteur : c'est lui qui ouvre la pop-up, il n'est pas à choisir. */
  client: { id: number; nom: string } | null;
  onClose: () => void;
  onCreated: (manifestation: Manifestation) => void;
}) {
  const [state, setState] = useState<FormState>(emptyState());

  // Repart d'une saisie vierge à chaque ouverture, sans quoi la manifestation
  // précédente resterait à l'écran.
  useEffect(() => {
    if (opened) {
      setState(emptyState());
    }
  }, [opened]);

  const contactsQuery = useQuery<{
    results: Array<{ id: number; nom: string; prenom: string; actif: boolean }>;
  }>(
    {
      queryKey: ['manifestation-modal-contacts', client?.id],
      enabled: opened && client != null,
      queryFn: async () => {
        const response = await context.api.get(CONTACTS_URL, {
          params: { client: client?.id, page_size: 100 }
        });
        return response.data;
      }
    },
    context.queryClient
  );

  const mutation = useMutation(
    {
      mutationFn: async () => {
        const response = await context.api.post(MANIFESTATIONS_URL, {
          nom: state.nom,
          description: state.description,
          // Une manifestation naît en brouillon, comme depuis l'onglet.
          statut: 'brouillon',
          client: client?.id ?? null,
          contact: state.contact ? Number(state.contact) : null,
          date_debut: state.date_debut?.toISOString(),
          date_fin: state.date_fin?.toISOString()
        });
        return response.data as Manifestation;
      },
      onSuccess: (manifestation) => {
        notifications.show({
          color: 'green',
          message: `Manifestation « ${manifestation.nom} » créée.`
        });
        onCreated(manifestation);
      },
      onError: (error: unknown) => {
        notifications.show({
          color: 'red',
          title: 'Erreur',
          message: apiErrorMessage(
            error,
            "La manifestation n'a pas pu être créée."
          )
        });
      }
    },
    context.queryClient
  );

  const contactOptions = optionsDeContacts(
    contactsQuery.data?.results ?? [],
    state.contact
  );

  const canSubmit = Boolean(
    state.nom && client && state.date_debut && state.date_fin
  );

  return (
    <Modal
      closeOnClickOutside={false}
      opened={opened}
      onClose={onClose}
      title={
        client
          ? `Nouvelle manifestation — ${client.nom}`
          : 'Nouvelle manifestation'
      }
      size='lg'
    >
      <Stack gap='sm'>
        <TextInput
          label='Nom'
          required
          value={state.nom}
          onChange={(event) => {
            const nom = event.currentTarget.value;
            setState((s) => ({ ...s, nom }));
          }}
        />

        <Select
          label='Contact'
          placeholder={
            contactOptions.length === 0
              ? 'Aucun contact pour ce client'
              : 'Choisir un contact…'
          }
          data={contactOptions}
          value={state.contact}
          onChange={(valeur) => setState((s) => ({ ...s, contact: valeur }))}
          searchable
          clearable
        />

        <Group grow>
          <DateTimeField
            label='Date de début'
            required
            value={state.date_debut}
            onChange={(valeur) =>
              setState((s) => {
                const debut = valeur ? new Date(valeur) : null;
                return {
                  ...s,
                  date_debut: debut,
                  date_fin: finSuivantLeDebut(debut, s.date_fin)
                };
              })
            }
          />
          <DateTimeField
            label='Date de fin'
            required
            minDate={state.date_debut ?? undefined}
            value={state.date_fin}
            onChange={(valeur) =>
              setState((s) => ({
                ...s,
                date_fin: valeur ? new Date(valeur) : null
              }))
            }
          />
        </Group>

        <Textarea
          label='Description'
          autosize
          minRows={2}
          value={state.description}
          onChange={(event) => {
            const description = event.currentTarget.value;
            setState((s) => ({ ...s, description }));
          }}
        />

        <Group justify='flex-end'>
          <Button variant='default' onClick={onClose}>
            Annuler
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
            disabled={!canSubmit}
          >
            Créer la manifestation
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
