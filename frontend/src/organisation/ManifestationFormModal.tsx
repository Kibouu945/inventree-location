// Création et modification d'une manifestation depuis l'arborescence,
// sans passer par l'onglet Manifestations.
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

/** Saisie initiale : vierge en création, l'existant en modification. */
function etatInitial(manifestation: Manifestation | null): FormState {
  if (!manifestation) {
    return emptyState();
  }

  return {
    nom: manifestation.nom,
    description: manifestation.description ?? '',
    contact:
      manifestation.contact != null ? String(manifestation.contact) : null,
    date_debut: manifestation.date_debut
      ? new Date(manifestation.date_debut)
      : null,
    date_fin: manifestation.date_fin ? new Date(manifestation.date_fin) : null
  };
}

function titreDuFormulaire(
  manifestation: Manifestation | null,
  client: { nom: string } | null
): string {
  if (manifestation) {
    return `Modifier la manifestation — ${manifestation.nom}`;
  }

  return client
    ? `Nouvelle manifestation — ${client.nom}`
    : 'Nouvelle manifestation';
}

export function ManifestationFormModal({
  context,
  opened,
  client,
  manifestation = null,
  onClose,
  onSaved
}: {
  context: InvenTreePluginContext;
  opened: boolean;
  /** Client porteur : c'est lui qui ouvre la pop-up, il n'est pas à choisir. */
  client: { id: number; nom: string } | null;
  /** Renseignée : on modifie cette manifestation au lieu d'en créer une. */
  manifestation?: Manifestation | null;
  onClose: () => void;
  onSaved: (manifestation: Manifestation) => void;
}) {
  const [state, setState] = useState<FormState>(etatInitial(manifestation));

  // Recharge la saisie à chaque ouverture, sans quoi la manifestation
  // précédente resterait à l'écran.
  useEffect(() => {
    if (opened) {
      setState(etatInitial(manifestation));
    }
  }, [opened, manifestation?.id]);

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
        const payload = {
          nom: state.nom,
          description: state.description,
          client: client?.id ?? null,
          contact: state.contact ? Number(state.contact) : null,
          date_debut: state.date_debut?.toISOString(),
          date_fin: state.date_fin?.toISOString()
        };

        if (manifestation) {
          const response = await context.api.patch(
            `${MANIFESTATIONS_URL}${manifestation.id}/`,
            payload
          );
          return response.data as Manifestation;
        }

        const response = await context.api.post(MANIFESTATIONS_URL, {
          ...payload,
          // Une manifestation naît en brouillon, comme depuis l'onglet.
          statut: 'brouillon'
        });
        return response.data as Manifestation;
      },
      onSuccess: (enregistree) => {
        notifications.show({
          color: 'green',
          message: manifestation
            ? `Manifestation « ${enregistree.nom} » mise à jour.`
            : `Manifestation « ${enregistree.nom} » créée.`
        });
        onSaved(enregistree);
      },
      onError: (error: unknown) => {
        notifications.show({
          color: 'red',
          title: 'Erreur',
          message: apiErrorMessage(
            error,
            "La manifestation n'a pas pu être enregistrée."
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
      title={titreDuFormulaire(manifestation, client)}
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
            {manifestation ? 'Enregistrer' : 'Créer la manifestation'}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
