// Formulaire de lieu, partagé par l'onglet Lieux et par la pop-up prestation
// (recette : créer un lieu sans quitter la saisie de la prestation).
// Le géocodage vit ici : un lieu sans coordonnées ne s'affiche pas sur la
// carte de tournée, dupliquer le formulaire reviendrait à le perdre.
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Button,
  Group,
  Modal,
  NumberInput,
  Stack,
  Text,
  Textarea,
  TextInput
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { useMutation } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { apiErrorMessage, type Lieu } from './types';

const LIEUX_URL = '/plugin/inventree-location/lieux/';
const GEOCODE_URL = '/plugin/inventree-location/geocode/';

interface FormValues {
  nom: string;
  adresse: string;
  latitude: string;
  longitude: string;
  capacite: number | '';
}

interface GeocodeCandidate {
  display_name: string;
  latitude: string | null;
  longitude: string | null;
}

function emptyValues(): FormValues {
  return { nom: '', adresse: '', latitude: '', longitude: '', capacite: '' };
}

function valuesDe(lieu: Lieu): FormValues {
  return {
    nom: lieu.nom,
    adresse: lieu.adresse,
    latitude: lieu.latitude ?? '',
    longitude: lieu.longitude ?? '',
    capacite: lieu.capacite ?? ''
  };
}

export function LieuFormModal({
  context,
  opened,
  lieu = null,
  peutGeocoder = true,
  onClose,
  onSaved
}: {
  context: InvenTreePluginContext;
  opened: boolean;
  /** Renseigné : on modifie ce lieu au lieu d'en créer un. */
  lieu?: Lieu | null;
  peutGeocoder?: boolean;
  onClose: () => void;
  onSaved: (lieu: Lieu) => void;
}) {
  const [geocoding, setGeocoding] = useState(false);
  const [candidates, setCandidates] = useState<GeocodeCandidate[]>([]);
  const [resolvedAddress, setResolvedAddress] = useState<string | null>(null);

  const form = useForm<FormValues>({ initialValues: emptyValues() });

  // Recharge la saisie à chaque ouverture, sans quoi le lieu précédent
  // resterait à l'écran.
  useEffect(() => {
    if (!opened) {
      return;
    }

    form.setValues(lieu ? valuesDe(lieu) : emptyValues());
    setCandidates([]);
    setResolvedAddress(null);
  }, [opened, lieu?.id]);

  const mutation = useMutation(
    {
      mutationFn: async (values: FormValues) => {
        const payload = {
          nom: values.nom,
          adresse: values.adresse,
          latitude: values.latitude || null,
          longitude: values.longitude || null,
          capacite: values.capacite === '' ? null : Number(values.capacite)
        };

        if (lieu) {
          const response = await context.api.patch(
            `${LIEUX_URL}${lieu.id}/`,
            payload
          );
          return response.data as Lieu;
        }

        const response = await context.api.post(LIEUX_URL, payload);
        return response.data as Lieu;
      },
      onSuccess: (enregistre) => {
        notifications.show({
          color: 'green',
          message: lieu
            ? 'Lieu mis à jour.'
            : `Lieu « ${enregistre.nom} » créé.`
        });
        context.queryClient.invalidateQueries({ queryKey: ['lieux'] });
        onSaved(enregistre);
      },
      onError: (error) => {
        notifications.show({
          color: 'red',
          title: 'Erreur',
          message: apiErrorMessage(error, "Échec de l'enregistrement.")
        });
      }
    },
    context.queryClient
  );

  function selectCandidate(candidate: GeocodeCandidate) {
    form.setFieldValue('latitude', String(candidate.latitude ?? ''));
    form.setFieldValue('longitude', String(candidate.longitude ?? ''));
    setResolvedAddress(candidate.display_name);
    setCandidates([]);
  }

  async function handleGeocode() {
    const address = form.values.adresse.trim();

    if (!address) {
      return;
    }

    setGeocoding(true);
    setCandidates([]);
    setResolvedAddress(null);

    try {
      const response = await context.api.get(GEOCODE_URL, {
        params: { address }
      });
      const results: GeocodeCandidate[] = response.data.results ?? [];

      if (results.length === 1) {
        // Résultat unique : on le retient directement.
        selectCandidate(results[0]);
      } else {
        // Plusieurs candidats : l'utilisateur choisit le bon.
        setCandidates(results);
      }
    } catch (error) {
      notifications.show({
        color: 'red',
        title: 'Géocodage',
        message: apiErrorMessage(error, 'Adresse introuvable.')
      });
    } finally {
      setGeocoding(false);
    }
  }

  return (
    <Modal
      closeOnClickOutside={false}
      opened={opened}
      onClose={onClose}
      size='lg'
      title={lieu ? 'Modifier le lieu' : 'Nouveau lieu'}
    >
      <form onSubmit={form.onSubmit((values) => mutation.mutate(values))}>
        <Stack gap='sm'>
          <TextInput label='Nom' required {...form.getInputProps('nom')} />
          <Textarea
            label='Adresse'
            autosize
            minRows={2}
            {...form.getInputProps('adresse')}
          />

          {peutGeocoder && (
            <Group>
              <Button
                variant='light'
                onClick={handleGeocode}
                loading={geocoding}
                disabled={!form.values.adresse.trim()}
              >
                Géocoder l'adresse
              </Button>
            </Group>
          )}

          {candidates.length > 0 && (
            <Alert
              color='blue'
              title='Plusieurs adresses trouvées — choisissez la bonne'
            >
              <Stack gap='xs'>
                {candidates.map((candidate) => (
                  <Button
                    key={candidate.display_name}
                    variant='default'
                    justify='space-between'
                    fullWidth
                    rightSection={
                      <Text size='xs' c='dimmed'>
                        {candidate.latitude}, {candidate.longitude}
                      </Text>
                    }
                    styles={{
                      inner: { justifyContent: 'space-between' },
                      label: { whiteSpace: 'normal', textAlign: 'left' }
                    }}
                    onClick={() => selectCandidate(candidate)}
                  >
                    {candidate.display_name}
                  </Button>
                ))}
              </Stack>
            </Alert>
          )}

          {resolvedAddress && (
            <Alert color='green' title='Adresse retenue'>
              {resolvedAddress}
            </Alert>
          )}

          <Group grow>
            <TextInput label='Latitude' {...form.getInputProps('latitude')} />
            <TextInput label='Longitude' {...form.getInputProps('longitude')} />
          </Group>

          <NumberInput
            label='Capacité'
            min={0}
            value={form.values.capacite}
            onChange={(value) =>
              form.setFieldValue('capacite', value === '' ? '' : Number(value))
            }
            w={160}
          />

          <Group justify='flex-end'>
            <Button variant='default' onClick={onClose}>
              Annuler
            </Button>
            <Button type='submit' loading={mutation.isPending}>
              Enregistrer
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
