// Pop-up de création rapide d'une prestation depuis le formulaire de
// réservation (RES-08) : évite de quitter le formulaire pour rattacher une
// nouvelle prestation à une manifestation existante. La prestation créée est
// renvoyée via `onCreated` pour sélection automatique côté appelant.
import type { InvenTreePluginContext } from '@inventreedb/ui';
import { Button, Group, Modal, Select, Stack, TextInput } from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { DateTimeField } from '../DateTimeField';

import type {
  LieuSummary,
  ManifestationOption,
  Page,
  Prestation
} from './types';

const MANIFESTATIONS_URL = '/plugin/inventree-location/manifestations/';
const LIEUX_URL = '/plugin/inventree-location/lieux/';
const PRESTATIONS_URL = '/plugin/inventree-location/prestations/';

function firstErrorMessage(error: unknown): string {
  const data = (error as { response?: { data?: unknown } })?.response?.data;

  if (typeof data === 'string') {
    return data;
  }

  if (data && typeof data === 'object') {
    const record = data as Record<string, unknown>;

    if (typeof record.detail === 'string') {
      return record.detail;
    }

    for (const value of Object.values(record)) {
      if (typeof value === 'string') {
        return value;
      }
      if (Array.isArray(value) && typeof value[0] === 'string') {
        return value[0];
      }
    }
  }

  return "La prestation n'a pas pu être créée.";
}

interface FormState {
  nom: string;
  manifestation: string | null;
  lieu: string | null;
  date_debut: Date | null;
  date_fin: Date | null;
}

function emptyState(manifestationId: number | null): FormState {
  return {
    nom: '',
    manifestation: manifestationId != null ? String(manifestationId) : null,
    lieu: null,
    date_debut: null,
    date_fin: null
  };
}

/**
 * Pop-up (modal Mantine) créant une prestation sans quitter le formulaire de
 * réservation (RES-08). Pré-rattachée à `manifestationId` quand la
 * réservation en cours en connaît déjà une (via sa prestation courante) ;
 * sinon l'utilisateur choisit la manifestation dans la pop-up.
 */
export function PrestationCreateModal({
  context,
  opened,
  manifestationId,
  onClose,
  onCreated
}: {
  context: InvenTreePluginContext;
  opened: boolean;
  /** Manifestation à pré-sélectionner (celle de la prestation déjà choisie
   * dans le formulaire, s'il y en a une). */
  manifestationId: number | null;
  onClose: () => void;
  onCreated: (prestation: Prestation) => void;
}) {
  const [state, setState] = useState<FormState>(emptyState(manifestationId));
  const [manifestationSearch, setManifestationSearch] = useState('');
  const [debouncedManifestationSearch] = useDebouncedValue(
    manifestationSearch,
    300
  );
  const [lieuSearch, setLieuSearch] = useState('');
  const [debouncedLieuSearch] = useDebouncedValue(lieuSearch, 300);

  // Repart d'un état vierge (rattaché à la manifestation courante) à chaque
  // ouverture, pour ne pas réafficher la saisie d'une création précédente.
  // `manifestationId` est volontairement absent des deps : un changement en
  // arrière-plan pendant que la pop-up est ouverte ne doit pas écraser la
  // saisie en cours de l'utilisateur.
  useEffect(() => {
    if (opened) {
      setState(emptyState(manifestationId));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened]);

  const manifestationsQuery = useQuery<Page<ManifestationOption>>(
    {
      queryKey: [
        'prestation-modal-manifestations',
        debouncedManifestationSearch
      ],
      enabled: opened,
      queryFn: async () => {
        const response = await context.api.get(MANIFESTATIONS_URL, {
          params: {
            search: debouncedManifestationSearch || undefined,
            page_size: 20
          }
        });
        return response.data as Page<ManifestationOption>;
      }
    },
    context.queryClient
  );

  const lieuxQuery = useQuery<Page<LieuSummary>>(
    {
      queryKey: ['prestation-modal-lieux', debouncedLieuSearch],
      enabled: opened,
      queryFn: async () => {
        const response = await context.api.get(LIEUX_URL, {
          params: { search: debouncedLieuSearch || undefined, page_size: 20 }
        });
        return response.data as Page<LieuSummary>;
      }
    },
    context.queryClient
  );

  const mutation = useMutation(
    {
      mutationFn: async () => {
        const response = await context.api.post(PRESTATIONS_URL, {
          nom: state.nom,
          manifestation: state.manifestation
            ? Number(state.manifestation)
            : null,
          lieu: state.lieu ? Number(state.lieu) : null,
          date_debut: state.date_debut?.toISOString(),
          date_fin: state.date_fin?.toISOString()
        });
        return response.data as Prestation;
      },
      onSuccess: (prestation) => {
        notifications.show({
          color: 'green',
          message: `Prestation « ${prestation.nom} » créée et sélectionnée.`
        });
        context.queryClient.invalidateQueries({
          queryKey: ['reservation-prestations']
        });
        onCreated(prestation);
      },
      onError: (error: unknown) => {
        notifications.show({
          color: 'red',
          title: 'Erreur',
          message: firstErrorMessage(error)
        });
      }
    },
    context.queryClient
  );

  const manifestationOptions = (manifestationsQuery.data?.results ?? []).map(
    (manifestation) => ({
      value: String(manifestation.id),
      label: manifestation.nom
    })
  );
  const lieuOptions = (lieuxQuery.data?.results ?? []).map((lieu) => ({
    value: String(lieu.id),
    label: lieu.nom
  }));

  const canSubmit = Boolean(
    state.nom &&
      state.manifestation &&
      state.lieu &&
      state.date_debut &&
      state.date_fin
  );

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title='Nouvelle prestation'
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
          label='Manifestation'
          placeholder='Rechercher une manifestation…'
          required
          data={manifestationOptions}
          searchable
          searchValue={manifestationSearch}
          onSearchChange={setManifestationSearch}
          value={state.manifestation}
          onChange={(value) =>
            setState((s) => ({ ...s, manifestation: value }))
          }
        />
        <Select
          label='Lieu'
          placeholder='Rechercher un lieu…'
          required
          data={lieuOptions}
          searchable
          searchValue={lieuSearch}
          onSearchChange={setLieuSearch}
          value={state.lieu}
          onChange={(value) => setState((s) => ({ ...s, lieu: value }))}
        />
        <Group grow>
          <DateTimeField
            label='Date de début'
            required
            value={state.date_debut}
            onChange={(value) =>
              setState((s) => ({
                ...s,
                date_debut: value ? new Date(value) : null
              }))
            }
          />
          <DateTimeField
            label='Date de fin'
            required
            value={state.date_fin}
            onChange={(value) =>
              setState((s) => ({
                ...s,
                date_fin: value ? new Date(value) : null
              }))
            }
          />
        </Group>
        <Group justify='flex-end'>
          <Button variant='default' onClick={onClose}>
            Annuler
          </Button>
          <Button
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
            disabled={!canSubmit}
          >
            Créer et sélectionner
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
