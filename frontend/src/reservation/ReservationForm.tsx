// Formulaire de création/édition d'une réservation (RES-03).
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Badge,
  Button,
  Group,
  Loader,
  Select,
  Stack,
  Table,
  Text,
  Textarea,
  Title
} from '@mantine/core';
import { DateTimePicker } from '@mantine/dates';
import { useForm } from '@mantine/form';
import { useDebouncedValue } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import {
  buildReservationPayload,
  emptyReservationValues,
  enrichLignesFromCatalog,
  removeLigne,
  reservationToFormValues,
  upsertLigne,
  validateReservationValues
} from './formLogic';
import { PartPicker } from './PartPicker';
import type {
  Page,
  Prestation,
  Reservation,
  ReservationFormValues,
  ReservationStatut,
  UserOption
} from './types';

const RESERVATIONS_URL = '/plugin/inventree-location/reservations/';
const PRESTATIONS_URL = '/plugin/inventree-location/prestations/';
const USERS_URL = '/plugin/inventree-location/users/';
const CATALOG_URL = '/plugin/inventree-location/catalog/';

function userLabel(user: UserOption): string {
  const fullName = `${user.first_name} ${user.last_name}`.trim();
  return fullName ? `${fullName} (${user.username})` : user.username;
}

function apiErrorFields(error: unknown): Record<string, string> {
  const data =
    (error as { response?: { data?: Record<string, string | string[]> } })
      ?.response?.data ?? {};
  const flattened: Record<string, string> = {};

  for (const [field, messages] of Object.entries(data)) {
    flattened[field] = Array.isArray(messages)
      ? messages.join(' ')
      : String(messages);
  }

  return flattened;
}

/**
 * Formulaire unique de création et d'édition d'une réservation.
 *
 * En édition (`reservationId` fourni), charge la réservation existante et
 * enrichit ses lignes (nom, drapeau virtuel) via le catalogue avant de
 * pré-remplir le formulaire.
 */
export function ReservationForm({
  context,
  reservationId,
  onSaved
}: {
  context: InvenTreePluginContext;
  reservationId?: number;
  onSaved?: () => void;
}) {
  const isEdit = reservationId != null;

  const form = useForm<ReservationFormValues>({
    initialValues: emptyReservationValues(),
    validate: {}
  });

  const [prestationSearch, setPrestationSearch] = useState('');
  const [debouncedPrestationSearch] = useDebouncedValue(prestationSearch, 300);
  const [userSearch, setUserSearch] = useState('');
  const [debouncedUserSearch] = useDebouncedValue(userSearch, 300);

  const existingQuery = useQuery<Reservation>(
    {
      queryKey: ['reservation', reservationId],
      enabled: isEdit,
      queryFn: async () => {
        const response = await context.api.get(
          `${RESERVATIONS_URL}${reservationId}/`
        );
        return response.data as Reservation;
      }
    },
    context.queryClient
  );

  const prestationsQuery = useQuery<Page<Prestation>>(
    {
      queryKey: ['reservation-prestations', debouncedPrestationSearch],
      queryFn: async () => {
        const response = await context.api.get(PRESTATIONS_URL, {
          params: {
            search: debouncedPrestationSearch || undefined,
            page_size: 20
          }
        });
        return response.data as Page<Prestation>;
      }
    },
    context.queryClient
  );

  const usersQuery = useQuery<Page<UserOption>>(
    {
      queryKey: ['reservation-users', debouncedUserSearch],
      queryFn: async () => {
        const response = await context.api.get(USERS_URL, {
          params: { search: debouncedUserSearch || undefined, page_size: 20 }
        });
        return response.data as Page<UserOption>;
      }
    },
    context.queryClient
  );

  // Pré-remplissage à l'édition : on attend le catalogue pour connaître le
  // nom et le drapeau virtuel des lignes déjà enregistrées.
  useEffect(() => {
    if (!existingQuery.data) {
      return;
    }

    const reservation = existingQuery.data;
    const partIds = reservation.lignes.map((ligne) => ligne.part);

    if (partIds.length === 0) {
      form.setValues(reservationToFormValues(reservation));
      return;
    }

    context.api
      .get(CATALOG_URL, { params: { ids: partIds.join(','), rentable: 'all' } })
      .then((response) => {
        const values = reservationToFormValues(reservation);
        values.lignes = enrichLignesFromCatalog(
          values.lignes,
          response.data.results
        );
        form.setValues(values);
      });
    // form est volontairement absent des deps : ce pré-remplissage ne doit
    // se déclencher qu'au chargement de la réservation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existingQuery.data]);

  const selectedPrestation = useMemo(
    () =>
      prestationsQuery.data?.results.find(
        (prestation) => prestation.id === form.values.prestation
      ) ?? null,
    [prestationsQuery.data, form.values.prestation]
  );

  const mutation = useMutation(
    {
      mutationFn: async (statut: ReservationStatut) => {
        const payload = buildReservationPayload(form.values, statut);

        const response = isEdit
          ? await context.api.patch(
              `${RESERVATIONS_URL}${reservationId}/`,
              payload
            )
          : await context.api.post(RESERVATIONS_URL, payload);

        return response.data as Reservation;
      },
      onSuccess: (data) => {
        form.clearErrors();
        context.queryClient.invalidateQueries({ queryKey: ['reservations'] });
        notifications.show({
          title: 'Enregistré',
          message: `Réservation ${data.numero} enregistrée.`,
          color: 'green'
        });
        onSaved?.();
      },
      onError: (error: unknown) => {
        form.setErrors(apiErrorFields(error));
        notifications.show({
          title: 'Erreur',
          message: "La réservation n'a pas pu être enregistrée.",
          color: 'red'
        });
      }
    },
    context.queryClient
  );

  function submit(statut: ReservationStatut) {
    const clientErrors = validateReservationValues(
      form.values,
      selectedPrestation,
      statut
    );

    if (Object.keys(clientErrors).length > 0) {
      form.setErrors(clientErrors);
      return;
    }

    mutation.mutate(statut);
  }

  if (isEdit && existingQuery.isLoading) {
    return (
      <Group justify='center' p='xl'>
        <Loader />
      </Group>
    );
  }

  const prestationOptions = (prestationsQuery.data?.results ?? []).map(
    (prestation) => ({
      value: String(prestation.id),
      label: `${prestation.nom} — ${prestation.manifestation_nom}`
    })
  );

  const userOptions = (usersQuery.data?.results ?? []).map((user) => ({
    value: String(user.id),
    label: userLabel(user)
  }));

  return (
    <Stack gap='md'>
      <Group justify='space-between'>
        <Title order={4} c={context.theme.primaryColor}>
          {isEdit ? 'Modifier la réservation' : 'Nouvelle réservation'}
        </Title>
        {existingQuery.data?.numero && (
          <Badge>{existingQuery.data.numero}</Badge>
        )}
      </Group>

      <Select
        label='Événement / Prestation'
        placeholder='Rechercher une prestation…'
        data={prestationOptions}
        searchable
        searchValue={prestationSearch}
        onSearchChange={setPrestationSearch}
        value={
          form.values.prestation != null ? String(form.values.prestation) : null
        }
        onChange={(value) =>
          form.setFieldValue('prestation', value ? Number(value) : null)
        }
        error={form.errors.prestation}
        required
      />

      {selectedPrestation && (
        <Alert color='gray' title='Événement / Lieu(x)'>
          <Text size='sm'>{selectedPrestation.manifestation_nom}</Text>
          <Text size='sm' c='dimmed'>
            {selectedPrestation.lieux.length > 0
              ? selectedPrestation.lieux.map((lieu) => lieu.nom).join(', ')
              : 'Aucun lieu associé à cette prestation.'}
          </Text>
        </Alert>
      )}

      <Select
        label='Demandeur'
        placeholder='Rechercher un utilisateur…'
        data={userOptions}
        searchable
        searchValue={userSearch}
        onSearchChange={setUserSearch}
        value={
          form.values.demandeur != null ? String(form.values.demandeur) : null
        }
        onChange={(value) =>
          form.setFieldValue('demandeur', value ? Number(value) : null)
        }
        error={form.errors.demandeur}
        required
      />

      <Group grow>
        <DateTimePicker
          label='Date de retrait prévue'
          value={form.values.date_retrait_prevue}
          onChange={(value) =>
            form.setFieldValue(
              'date_retrait_prevue',
              value ? new Date(value) : null
            )
          }
          error={form.errors.date_retrait_prevue}
          clearable
        />
        <DateTimePicker
          label='Date de retour prévue'
          value={form.values.date_retour_prevue}
          onChange={(value) =>
            form.setFieldValue(
              'date_retour_prevue',
              value ? new Date(value) : null
            )
          }
          error={form.errors.date_retour_prevue}
          clearable
        />
      </Group>

      <Textarea
        label='Notes'
        placeholder='Commentaire…'
        value={form.values.commentaire}
        onChange={(event) =>
          form.setFieldValue('commentaire', event.currentTarget.value)
        }
        minRows={2}
      />

      <Title order={5}>Matériel</Title>
      <PartPicker
        context={context}
        label='Ajouter un article'
        onAdd={(ligne) =>
          form.setFieldValue('lignes', upsertLigne(form.values.lignes, ligne))
        }
      />

      <Title order={5}>Article virtuel (obligatoire à la soumission)</Title>
      <PartPicker
        context={context}
        label='Ajouter une prestation (ex: nettoyage)'
        virtualOnly
        onAdd={(ligne) =>
          form.setFieldValue('lignes', upsertLigne(form.values.lignes, ligne))
        }
      />

      {form.errors.lignes && (
        <Alert color='red' title='Matériel'>
          {form.errors.lignes}
        </Alert>
      )}

      {form.values.lignes.length > 0 && (
        <Table striped>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Article</Table.Th>
              <Table.Th>Quantité</Table.Th>
              <Table.Th>Type</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {form.values.lignes.map((ligne) => (
              <Table.Tr key={ligne.part}>
                <Table.Td>{ligne.partName}</Table.Td>
                <Table.Td>{ligne.quantiteDemandee}</Table.Td>
                <Table.Td>
                  {ligne.isVirtual ? (
                    <Badge color='orange'>Virtuel</Badge>
                  ) : (
                    <Badge color='green'>Matériel</Badge>
                  )}
                </Table.Td>
                <Table.Td>
                  <Button
                    size='xs'
                    variant='subtle'
                    color='red'
                    onClick={() =>
                      form.setFieldValue(
                        'lignes',
                        removeLigne(form.values.lignes, ligne.part)
                      )
                    }
                  >
                    Retirer
                  </Button>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      <Group justify='flex-end'>
        <Button
          variant='light'
          loading={mutation.isPending}
          onClick={() => submit('brouillon')}
        >
          Enregistrer en brouillon
        </Button>
        <Button loading={mutation.isPending} onClick={() => submit('soumise')}>
          Soumettre
        </Button>
      </Group>
    </Stack>
  );
}
