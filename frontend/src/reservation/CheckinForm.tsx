// Écran de check-in retour (SCRUM-94) : pointage OK / manquant / cassé.
//
// Adaptation d'architecture : le plugin ne dispose pas de routeur client
// (pages rendues par InvenTree via des dashboard items), donc la « page »
// `/reservations/:id/checkin` de la spec est portée par une modale ouverte
// depuis la liste des réservations, plutôt qu'une route dédiée.
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Button,
  Group,
  Loader,
  NumberInput,
  Stack,
  Table,
  Text,
  Textarea
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import {
  type CheckinErrors,
  type CheckinLigneValues,
  validateCheckinLignes
} from './checkinLogic';

const RESERVATIONS_URL = '/plugin/inventree-location/reservations/';

interface CheckinLigneApi {
  id: number;
  part: number;
  part_name: string;
  quantite_demandee: number;
  quantite_retour_ok: number;
  quantite_retour_manquant: number;
  quantite_retour_casse: number;
  commentaire: string;
}

interface CheckinResponse {
  reservation: number;
  numero: string;
  statut: string;
  lignes: CheckinLigneApi[];
}

function toFormLignes(lignes: CheckinLigneApi[]): CheckinLigneValues[] {
  return lignes.map((ligne) => ({
    id: ligne.id,
    quantite_demandee: ligne.quantite_demandee,
    ok: ligne.quantite_retour_ok || ligne.quantite_demandee,
    manquant: ligne.quantite_retour_manquant || 0,
    casse: ligne.quantite_retour_casse || 0,
    commentaire: ligne.commentaire || ''
  }));
}

/**
 * Formulaire de check-in retour ligne par ligne d'une réservation livrée.
 */
export function CheckinForm({
  context,
  reservationId,
  onSaved
}: {
  context: InvenTreePluginContext;
  reservationId: number;
  onSaved: () => void;
}) {
  const [lignes, setLignes] = useState<CheckinLigneValues[]>([]);
  const [errors, setErrors] = useState<CheckinErrors>({});
  const [partNames, setPartNames] = useState<Record<number, string>>({});

  const query = useQuery<CheckinResponse>(
    {
      queryKey: ['reservation-checkin', reservationId],
      queryFn: async () => {
        const response = await context.api.get(
          `${RESERVATIONS_URL}${reservationId}/checkin/`
        );
        return response.data;
      }
    },
    context.queryClient
  );

  useEffect(() => {
    if (query.data) {
      setLignes(toFormLignes(query.data.lignes));
      setPartNames(
        Object.fromEntries(
          query.data.lignes.map((ligne) => [ligne.id, ligne.part_name])
        )
      );
    }
  }, [query.data]);

  const saveMutation = useMutation(
    {
      mutationFn: async (payload: CheckinLigneValues[]) => {
        const response = await context.api.post(
          `${RESERVATIONS_URL}${reservationId}/checkin/`,
          {
            lignes: payload.map((ligne) => ({
              id: ligne.id,
              ok: ligne.ok,
              manquant: ligne.manquant,
              casse: ligne.casse,
              commentaire: ligne.commentaire
            }))
          }
        );
        return response.data;
      },
      onSuccess: () => {
        context.queryClient.invalidateQueries({ queryKey: ['reservations'] });
        notifications.show({
          title: 'Check-in enregistré',
          message: 'La réservation a été clôturée.',
          color: 'green'
        });
        onSaved();
      },
      onError: (error: unknown) => {
        const data = (
          error as {
            response?: { data?: { lignes?: CheckinErrors; detail?: string } };
          }
        )?.response?.data;

        if (data?.lignes) {
          setErrors(data.lignes);
        }

        notifications.show({
          title: 'Check-in impossible',
          message: data?.detail || 'Vérifiez les quantités saisies.',
          color: 'red'
        });
      }
    },
    context.queryClient
  );

  function updateLigne(id: number, patch: Partial<CheckinLigneValues>) {
    setLignes((current) =>
      current.map((ligne) => (ligne.id === id ? { ...ligne, ...patch } : ligne))
    );
  }

  function handleSubmit() {
    const validationErrors = validateCheckinLignes(lignes);
    setErrors(validationErrors);

    if (Object.keys(validationErrors).length > 0) {
      return;
    }

    saveMutation.mutate(lignes);
  }

  if (query.isLoading) {
    return (
      <Group justify='center' p='xl'>
        <Loader />
      </Group>
    );
  }

  if (query.isError) {
    const detail = (
      query.error as { response?: { data?: { detail?: string } } }
    )?.response?.data?.detail;

    return (
      <Alert color='red' title='Check-in indisponible'>
        {detail || 'Impossible de charger le check-in de cette réservation.'}
      </Alert>
    );
  }

  return (
    <Stack gap='md'>
      <Text size='sm' c='dimmed'>
        Réservation {query.data?.numero} — saisissez OK / manquant / cassé pour
        chaque ligne. La somme doit égaler la quantité demandée.
      </Text>

      <Table striped>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Article</Table.Th>
            <Table.Th>Qté demandée</Table.Th>
            <Table.Th>OK</Table.Th>
            <Table.Th>Manquant</Table.Th>
            <Table.Th>Cassé</Table.Th>
            <Table.Th>Commentaire</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {lignes.map((ligne) => (
            <Table.Tr key={ligne.id}>
              <Table.Td>{partNames[ligne.id] || '—'}</Table.Td>
              <Table.Td>{ligne.quantite_demandee}</Table.Td>
              <Table.Td>
                <NumberInput
                  value={ligne.ok}
                  min={0}
                  w={90}
                  onChange={(value) =>
                    updateLigne(ligne.id, { ok: Number(value) || 0 })
                  }
                />
              </Table.Td>
              <Table.Td>
                <NumberInput
                  value={ligne.manquant}
                  min={0}
                  w={90}
                  onChange={(value) =>
                    updateLigne(ligne.id, { manquant: Number(value) || 0 })
                  }
                />
              </Table.Td>
              <Table.Td>
                <NumberInput
                  value={ligne.casse}
                  min={0}
                  w={90}
                  onChange={(value) =>
                    updateLigne(ligne.id, { casse: Number(value) || 0 })
                  }
                />
              </Table.Td>
              <Table.Td>
                <Textarea
                  value={ligne.commentaire}
                  autosize
                  minRows={1}
                  w={200}
                  onChange={(event) =>
                    updateLigne(ligne.id, {
                      commentaire: event.currentTarget.value
                    })
                  }
                />
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>

      {Object.entries(errors).map(([id, message]) =>
        message ? (
          <Alert
            key={id}
            color='red'
            title={`Ligne ${partNames[Number(id)] || id}`}
          >
            {message}
          </Alert>
        ) : null
      )}

      <Group justify='flex-end'>
        <Button
          onClick={handleSubmit}
          loading={saveMutation.isPending}
          disabled={lignes.length === 0}
        >
          Valider le check-in et clôturer
        </Button>
      </Group>
    </Stack>
  );
}
