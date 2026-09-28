// Pop-up de création rapide d'une prestation depuis le formulaire de
// réservation (RES-08), et de modification depuis l'arborescence (4.5.3).
import type { InvenTreePluginContext } from '@inventreedb/ui';
import { Button, Group, Modal, Select, Stack, TextInput } from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import {
  DateTimeField,
  finSuivantLeDebut,
  reprendreLesDates
} from '../DateTimeField';
import { avecOptionCourante, rechercheServeur } from './formLogic';

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

  return "La prestation n'a pas pu être enregistrée.";
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

/** Manifestation porteuse : son nom, et les dates que la prestation reprend. */
interface ManifestationDatee {
  nom: string;
  date_debut: string | null;
  date_fin: string | null;
}

/** Prestation à modifier, réduite aux champs que le formulaire manipule. */
export interface PrestationAModifier {
  id: number;
  nom: string;
  manifestation: number;
  manifestation_nom?: string | null;
  lieu: number | null;
  lieu_detail?: { nom: string } | null;
  date_debut: string | null;
  date_fin: string | null;
}

/** Saisie initiale : vierge en création, l'existant en modification. */
function etatInitial(
  prestation: PrestationAModifier | null,
  manifestationId: number | null
): FormState {
  if (!prestation) {
    return emptyState(manifestationId);
  }

  return {
    nom: prestation.nom,
    manifestation: String(prestation.manifestation),
    lieu: prestation.lieu != null ? String(prestation.lieu) : null,
    date_debut: prestation.date_debut ? new Date(prestation.date_debut) : null,
    date_fin: prestation.date_fin ? new Date(prestation.date_fin) : null
  };
}

/**
 * Pop-up (modal Mantine) créant une prestation sans quitter le formulaire de
 * réservation (RES-08), ou modifiant celle qu'on lui passe (4.5.3).
 */
export function PrestationFormModal({
  context,
  opened,
  manifestationId,
  prestation = null,
  libelleAction = 'Créer et sélectionner',
  onClose,
  onSaved
}: {
  context: InvenTreePluginContext;
  opened: boolean;
  /** Manifestation à pré-sélectionner (celle de la prestation déjà choisie
   * dans le formulaire, s'il y en a une). */
  manifestationId: number | null;
  /** Renseignée : on modifie cette prestation au lieu d'en créer une. */
  prestation?: PrestationAModifier | null;
  /**
   * « et sélectionner » n'a de sens qu'appelé depuis le formulaire de
   * réservation, où la prestation créée vient se poser dans le champ.
   */
  libelleAction?: string;
  onClose: () => void;
  onSaved: (prestation: Prestation) => void;
}) {
  const [state, setState] = useState<FormState>(
    etatInitial(prestation, manifestationId)
  );
  const [manifestationSearch, setManifestationSearch] = useState('');
  const [debouncedManifestationSearch] = useDebouncedValue(
    manifestationSearch,
    300
  );
  const [lieuSearch, setLieuSearch] = useState('');
  const [debouncedLieuSearch] = useDebouncedValue(lieuSearch, 300);
  // 4.6.1 : les dates suivent la manifestation tant que l'utilisateur n'y a
  // pas touché lui-même.
  const [datesSaisies, setDatesSaisies] = useState(false);
  // Libellés des options retenues : Mantine les recopie dans les champs de
  // recherche, il ne faut pas les prendre pour une recherche de l'utilisateur.
  const [libelleManifestation, setLibelleManifestation] = useState<
    string | null
  >(null);
  const [libelleLieu, setLibelleLieu] = useState<string | null>(null);

  // Recharge la saisie à chaque ouverture, pour ne pas réafficher celle de la
  // prestation précédente.
  useEffect(() => {
    if (opened) {
      setState(etatInitial(prestation, manifestationId));
      setDatesSaisies(prestation != null);
      setLibelleManifestation(prestation?.manifestation_nom ?? null);
      setLibelleLieu(prestation?.lieu_detail?.nom ?? null);
    }
  }, [opened, manifestationId, prestation?.id]);

  // La manifestation choisie, relue par son id : la recherche paginée ne la
  // ramène pas forcément, et c'est d'elle que viennent les dates.
  const manifestationChoisie = useQuery<ManifestationDatee>(
    {
      queryKey: ['prestation-modal-manifestation', state.manifestation],
      enabled: opened && prestation == null && state.manifestation != null,
      queryFn: async () => {
        const response = await context.api.get(
          `${MANIFESTATIONS_URL}${state.manifestation}/`
        );
        return response.data as ManifestationDatee;
      }
    },
    context.queryClient
  );

  const porteuse = manifestationChoisie.data;

  useEffect(() => {
    if (!porteuse) {
      return;
    }

    // Le nom sert aussi à reconnaître ce que Mantine a recopié dans le champ
    // de recherche : sans lui, la liste se réduit à la manifestation courante.
    setLibelleManifestation(porteuse.nom);
    setState((s) => ({
      ...s,
      ...reprendreLesDates(porteuse, s, datesSaisies)
    }));
  }, [porteuse, datesSaisies]);

  const manifestationsQuery = useQuery<Page<ManifestationOption>>(
    {
      queryKey: [
        'prestation-modal-manifestations',
        debouncedManifestationSearch,
        libelleManifestation
      ],
      enabled: opened,
      queryFn: async () => {
        const response = await context.api.get(MANIFESTATIONS_URL, {
          params: {
            search: rechercheServeur(
              debouncedManifestationSearch,
              libelleManifestation
            ),
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
      queryKey: ['prestation-modal-lieux', debouncedLieuSearch, libelleLieu],
      enabled: opened,
      queryFn: async () => {
        const response = await context.api.get(LIEUX_URL, {
          params: {
            search: rechercheServeur(debouncedLieuSearch, libelleLieu),
            page_size: 20
          }
        });
        return response.data as Page<LieuSummary>;
      }
    },
    context.queryClient
  );

  const mutation = useMutation(
    {
      mutationFn: async () => {
        const payload = {
          nom: state.nom,
          manifestation: state.manifestation
            ? Number(state.manifestation)
            : null,
          lieu: state.lieu ? Number(state.lieu) : null,
          date_debut: state.date_debut?.toISOString(),
          date_fin: state.date_fin?.toISOString()
        };

        if (prestation) {
          const response = await context.api.patch(
            `${PRESTATIONS_URL}${prestation.id}/`,
            payload
          );
          return response.data as Prestation;
        }

        const response = await context.api.post(PRESTATIONS_URL, payload);
        return response.data as Prestation;
      },
      onSuccess: (enregistree) => {
        notifications.show({
          color: 'green',
          message: prestation
            ? `Prestation « ${enregistree.nom} » mise à jour.`
            : `Prestation « ${enregistree.nom} » créée et sélectionnée.`
        });
        context.queryClient.invalidateQueries({
          queryKey: ['reservation-prestations']
        });
        onSaved(enregistree);
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

  // La recherche paginée ne ramène pas forcément la manifestation ni le lieu
  // déjà posés sur la prestation qu'on modifie : on les rajoute en tête.
  const manifestationOptions = avecOptionCourante(
    (manifestationsQuery.data?.results ?? []).map((manifestation) => ({
      value: String(manifestation.id),
      label: manifestation.nom
    })),
    state.manifestation,
    prestation?.manifestation_nom
  );
  const lieuOptions = avecOptionCourante(
    (lieuxQuery.data?.results ?? []).map((lieu) => ({
      value: String(lieu.id),
      label: lieu.nom
    })),
    state.lieu,
    prestation?.lieu_detail?.nom
  );

  const canSubmit = Boolean(
    state.nom &&
      state.manifestation &&
      state.lieu &&
      state.date_debut &&
      state.date_fin
  );

  return (
    <Modal
      closeOnClickOutside={false}
      opened={opened}
      onClose={onClose}
      title={
        prestation
          ? `Modifier la prestation — ${prestation.nom}`
          : 'Nouvelle prestation'
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
          label='Manifestation'
          placeholder='Rechercher une manifestation…'
          required
          data={manifestationOptions}
          searchable
          searchValue={manifestationSearch}
          onSearchChange={setManifestationSearch}
          value={state.manifestation}
          onChange={(value) => {
            setLibelleManifestation(
              manifestationOptions.find((o) => o.value === value)?.label ?? null
            );
            setState((s) => ({ ...s, manifestation: value }));
          }}
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
          onChange={(value) => {
            setLibelleLieu(
              lieuOptions.find((o) => o.value === value)?.label ?? null
            );
            setState((s) => ({ ...s, lieu: value }));
          }}
        />
        <Group grow>
          <DateTimeField
            label='Date de début'
            required
            value={state.date_debut}
            onChange={(value) => {
              setDatesSaisies(true);
              setState((s) => {
                const debut = value ? new Date(value) : null;
                return {
                  ...s,
                  date_debut: debut,
                  date_fin: finSuivantLeDebut(debut, s.date_fin)
                };
              });
            }}
          />
          <DateTimeField
            label='Date de fin'
            required
            minDate={state.date_debut ?? undefined}
            value={state.date_fin}
            onChange={(value) => {
              setDatesSaisies(true);
              setState((s) => ({
                ...s,
                date_fin: value ? new Date(value) : null
              }));
            }}
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
            {prestation ? 'Enregistrer' : libelleAction}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
