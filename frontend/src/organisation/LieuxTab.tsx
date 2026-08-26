// CRUD des lieux géolocalisés
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Anchor,
  Button,
  Group,
  Loader,
  Modal,
  NumberInput,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
  Title
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useDebouncedValue } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { canWriteOrganisation } from '../roles';
import { apiErrorMessage, type Lieu, type Page } from './types';

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

/** Lien Google Maps si le lieu porte des coordonnées. */
function mapsUrl(lieu: Lieu): string | null {
  if (lieu.latitude == null || lieu.longitude == null) {
    return null;
  }
  return `https://www.google.com/maps/search/?api=1&query=${lieu.latitude},${lieu.longitude}`;
}

export function LieuxTab({ context }: { context: InvenTreePluginContext }) {
  const canWrite = canWriteOrganisation(context);

  const [search, setSearch] = useState('');
  const [debouncedSearch] = useDebouncedValue(search, 300);
  const [modalOpen, setModalOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [geocoding, setGeocoding] = useState(false);
  const [candidates, setCandidates] = useState<GeocodeCandidate[]>([]);
  const [resolvedAddress, setResolvedAddress] = useState<string | null>(null);

  const form = useForm<FormValues>({ initialValues: emptyValues() });

  const listQuery = useQuery<Lieu[] | Page<Lieu>>(
    {
      queryKey: ['lieux', debouncedSearch],
      queryFn: async () => {
        const response = await context.api.get(LIEUX_URL, {
          params: debouncedSearch ? { search: debouncedSearch } : {}
        });
        return response.data;
      }
    },
    context.queryClient
  );

  const rows = Array.isArray(listQuery.data)
    ? listQuery.data
    : (listQuery.data?.results ?? []);

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

        if (editId != null) {
          const response = await context.api.patch(
            `${LIEUX_URL}${editId}/`,
            payload
          );
          return response.data;
        }

        const response = await context.api.post(LIEUX_URL, payload);
        return response.data;
      },
      onSuccess: () => {
        notifications.show({
          color: 'green',
          message: editId != null ? 'Lieu mis à jour.' : 'Lieu créé.'
        });
        context.queryClient.invalidateQueries({ queryKey: ['lieux'] });
        setModalOpen(false);
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

  function resetGeocode() {
    setCandidates([]);
    setResolvedAddress(null);
  }

  function openCreate() {
    setEditId(null);
    form.setValues(emptyValues());
    resetGeocode();
    setModalOpen(true);
  }

  function openEdit(lieu: Lieu) {
    setEditId(lieu.id);
    form.setValues({
      nom: lieu.nom,
      adresse: lieu.adresse,
      latitude: lieu.latitude ?? '',
      longitude: lieu.longitude ?? '',
      capacite: lieu.capacite ?? ''
    });
    resetGeocode();
    setModalOpen(true);
  }

  return (
    <Stack gap='md'>
      <Group justify='space-between'>
        <Title order={5}>Lieux</Title>
        {canWrite && <Button onClick={openCreate}>Nouveau lieu</Button>}
      </Group>

      <TextInput
        label='Recherche'
        placeholder='Nom ou adresse…'
        value={search}
        onChange={(event) => setSearch(event.currentTarget.value)}
        w={280}
      />

      {listQuery.isError && (
        <Alert color='red' title='Erreur'>
          Impossible de charger les lieux.
        </Alert>
      )}

      {listQuery.isLoading ? (
        <Group justify='center' p='xl'>
          <Loader />
        </Group>
      ) : rows.length === 0 ? (
        <Text c='dimmed'>Aucun lieu pour le moment.</Text>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Nom</Table.Th>
              <Table.Th>Adresse</Table.Th>
              <Table.Th>GPS</Table.Th>
              <Table.Th>Capacité</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((lieu) => {
              const url = mapsUrl(lieu);
              return (
                <Table.Tr
                  key={lieu.id}
                  style={{ cursor: canWrite ? 'pointer' : 'default' }}
                  onClick={() => canWrite && openEdit(lieu)}
                >
                  <Table.Td>{lieu.nom}</Table.Td>
                  <Table.Td>{lieu.adresse || '—'}</Table.Td>
                  <Table.Td onClick={(event) => event.stopPropagation()}>
                    {url ? (
                      <Anchor
                        href={url}
                        target='_blank'
                        rel='noreferrer'
                        size='sm'
                      >
                        {lieu.latitude}, {lieu.longitude}
                      </Anchor>
                    ) : (
                      '—'
                    )}
                  </Table.Td>
                  <Table.Td>{lieu.capacite ?? '—'}</Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      )}

      <Modal
        opened={modalOpen}
        onClose={() => {
          setModalOpen(false);
          resetGeocode();
        }}
        size='lg'
        title={editId != null ? 'Modifier le lieu' : 'Nouveau lieu'}
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
            {canWrite && (
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
              <TextInput
                label='Longitude'
                {...form.getInputProps('longitude')}
              />
            </Group>
            <NumberInput
              label='Capacité'
              min={0}
              value={form.values.capacite}
              onChange={(value) =>
                form.setFieldValue(
                  'capacite',
                  value === '' ? '' : Number(value)
                )
              }
              w={160}
            />
            <Group justify='flex-end'>
              <Button variant='default' onClick={() => setModalOpen(false)}>
                Annuler
              </Button>
              <Button type='submit' loading={mutation.isPending}>
                Enregistrer
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </Stack>
  );
}
