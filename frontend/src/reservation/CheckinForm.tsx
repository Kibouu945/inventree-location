// Écran de check-in retour (SCRUM-94) : pointage OK / manquant / cassé.
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
import { useEffect, useRef, useState } from 'react';

import {
  type CheckinErrors,
  type CheckinLigneValues,
  summarizeCheckin,
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
  return lignes.map((ligne) => {
    // Un check-in déjà pointé est rechargé tel quel (y compris un « OK = 0 »,
    // que le `||` d'origine remplaçait à tort par la quantité demandée) ;
    const dejaPointee =
      ligne.quantite_retour_ok +
        ligne.quantite_retour_manquant +
        ligne.quantite_retour_casse >
      0;

    return {
      id: ligne.id,
      quantite_demandee: ligne.quantite_demandee,
      ok: dejaPointee ? ligne.quantite_retour_ok : ligne.quantite_demandee,
      manquant: dejaPointee ? ligne.quantite_retour_manquant : 0,
      casse: dejaPointee ? ligne.quantite_retour_casse : 0,
      commentaire: ligne.commentaire || ''
    };
  });
}

/** Formulaire de check-in retour ligne par ligne d'une réservation livrée. */
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
  const [confirming, setConfirming] = useState(false);
  // Le formulaire n'est initialisé qu'une fois par réservation : un refetch
  // (retour de focus sur l'onglet, invalidation) ne doit pas écraser la saisie
  const seededFor = useRef<number | null>(null);

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
    if (!query.data || seededFor.current === reservationId) {
      return;
    }

    seededFor.current = reservationId;
    setLignes(toFormLignes(query.data.lignes));
    setPartNames(
      Object.fromEntries(
        query.data.lignes.map((ligne) => [ligne.id, ligne.part_name])
      )
    );
  }, [query.data, reservationId]);

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
        notifications.show({
          title: 'Check-in enregistré',
          message: 'La réservation a été clôturée.',
          color: 'green'
        });
        onSaved();

        // Rendue à react-query plutôt qu'abandonnée : la mutation reste
        // « pending » jusqu'au rafraîchissement de la liste.
        return context.queryClient.invalidateQueries({
          queryKey: ['reservations']
        });
      },
      onError: (error: unknown) => {
        const data = (
          error as {
            response?: { data?: { lignes?: CheckinErrors; detail?: string } };
          }
        )?.response?.data;

        setConfirming(false);

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
    // Toute modification invalide la confirmation en cours.
    setConfirming(false);
    setLignes((current) =>
      current.map((ligne) => (ligne.id === id ? { ...ligne, ...patch } : ligne))
    );
  }

  function handleSubmit() {
    const validationErrors = validateCheckinLignes(lignes);
    setErrors(validationErrors);

    if (Object.keys(validationErrors).length > 0) {
      setConfirming(false);
      return;
    }

    // La clôture est définitive : premier clic = récapitulatif, second clic =
    // envoi.
    if (!confirming) {
      setConfirming(true);
      return;
    }

    saveMutation.mutate(lignes);
  }

  const totals = summarizeCheckin(lignes);

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

      {confirming && (
        <Alert color='orange' title='Confirmer la clôture'>
          {totals.manquant === 0 && totals.casse === 0
            ? 'Aucun incident déclaré : tout le matériel est rendu en bon état.'
            : `${totals.manquant} article(s) manquant(s) et ${totals.casse} article(s) cassé(s) vont être déclarés.`}{' '}
          La réservation sera clôturée définitivement.
        </Alert>
      )}

      <Group justify='flex-end'>
        {confirming && (
          <Button variant='default' onClick={() => setConfirming(false)}>
            Revenir à la saisie
          </Button>
        )}
        <Button
          onClick={handleSubmit}
          color={confirming ? 'orange' : undefined}
          loading={saveMutation.isPending}
          disabled={lignes.length === 0}
        >
          {confirming
            ? 'Confirmer et clôturer'
            : 'Valider le check-in et clôturer'}
        </Button>
      </Group>
    </Stack>
  );
}
