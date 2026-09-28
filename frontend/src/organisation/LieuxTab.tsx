// CRUD des lieux géolocalisés
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Anchor,
  Button,
  Group,
  Loader,
  Stack,
  Table,
  Text,
  TextInput,
  Title
} from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { canWriteOrganisation } from '../roles';
import { LieuFormModal } from './LieuFormModal';
import type { Lieu, Page } from './types';

const LIEUX_URL = '/plugin/inventree-location/lieux/';

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
  const [lieuEdite, setLieuEdite] = useState<Lieu | null>(null);

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

  function openCreate() {
    setLieuEdite(null);
    setModalOpen(true);
  }

  function openEdit(lieu: Lieu) {
    setLieuEdite(lieu);
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

      <LieuFormModal
        context={context}
        opened={modalOpen}
        lieu={lieuEdite}
        peutGeocoder={canWrite}
        onClose={() => setModalOpen(false)}
        onSaved={() => setModalOpen(false)}
      />
    </Stack>
  );
}
