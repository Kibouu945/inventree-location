// Panel affiché sur la page d'un Part InvenTree (CAT-04 / CAT-05).
import {
  checkPluginVersion,
  type InvenTreePluginContext
} from '@inventreedb/ui';
import {
  Alert,
  Badge,
  Button,
  Group,
  Loader,
  Stack,
  Switch,
  Text,
  Title
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';

interface RentableFlags {
  part: number;
  is_rentable: boolean;
  consommable: boolean;
}

const MANAGER_ROLES = ['admin', 'gestionnaire'];

function userRoles(context: InvenTreePluginContext): string[] {
  const groups = (context.user as { groups?: unknown })?.groups;
  return Array.isArray(groups) ? groups.map((group) => String(group)) : [];
}

/**
 * Fiche location du Part courant : drapeaux louable / consommable, toggles
 * (réservés aux gestionnaires) et accès aux réservations en cours.
 */
function InvenTreeLocationPanel({
  context
}: {
  context: InvenTreePluginContext;
}) {
  const partId = useMemo(() => context.id ?? null, [context.id]);

  const canManage = useMemo(() => {
    const roles = userRoles(context);
    return (
      Boolean((context.user as { is_superuser?: boolean })?.is_superuser) ||
      roles.some((role) => MANAGER_ROLES.includes(role))
    );
  }, [context]);

  const rentableUrl = `/plugin/inventree-location/catalog/${partId}/rentable/`;

  const query = useQuery<RentableFlags>(
    {
      queryKey: ['rentable', partId],
      enabled: partId != null,
      queryFn: async () => {
        const response = await context.api.get(rentableUrl);
        return response.data as RentableFlags;
      }
    },
    context.queryClient
  );

  const mutation = useMutation(
    {
      mutationFn: async (patch: Partial<RentableFlags>) => {
        const response = await context.api.patch(rentableUrl, patch);
        return response.data as RentableFlags;
      },
      onSuccess: (data) => {
        context.queryClient.setQueryData(['rentable', partId], data);
        notifications.show({
          title: 'Enregistré',
          message: 'Drapeaux de location mis à jour.',
          color: 'green'
        });
      },
      onError: () => {
        notifications.show({
          title: 'Erreur',
          message: 'Mise à jour impossible.',
          color: 'red'
        });
      }
    },
    context.queryClient
  );

  if (partId == null) {
    return (
      <Alert color='yellow' title='Aucun article'>
        Ce panneau s'affiche sur la fiche d'un article.
      </Alert>
    );
  }

  if (query.isLoading) {
    return (
      <Group justify='center' p='xl'>
        <Loader />
      </Group>
    );
  }

  const flags = query.data;

  return (
    <Stack gap='md'>
      <Title order={4} c={context.theme.primaryColor}>
        Location
      </Title>

      <Group gap='sm'>
        {flags?.consommable ? (
          <Badge color='orange'>Consommable</Badge>
        ) : flags?.is_rentable ? (
          <Badge color='green'>Louable</Badge>
        ) : (
          <Badge color='gray'>Non-louable</Badge>
        )}
      </Group>

      <Switch
        label='Louable'
        checked={Boolean(flags?.is_rentable)}
        disabled={!canManage || mutation.isPending}
        onChange={(event) =>
          mutation.mutate({ is_rentable: event.currentTarget.checked })
        }
      />
      <Switch
        label='Consommable'
        checked={Boolean(flags?.consommable)}
        disabled={!canManage || mutation.isPending}
        onChange={(event) =>
          mutation.mutate({ consommable: event.currentTarget.checked })
        }
      />

      {!canManage && (
        <Text size='xs' c='dimmed'>
          Seuls les gestionnaires peuvent modifier ces drapeaux.
        </Text>
      )}

      <Group>
        <Button
          variant='light'
          onClick={() =>
            context.navigate(
              `/plugin/inventree-location/reservations/?part=${partId}`
            )
          }
        >
          Voir les réservations en cours
        </Button>
      </Group>
    </Stack>
  );
}

// Fonction appelée par InvenTree pour rendre le panneau.
export function renderInvenTreeLocationPanel(context: InvenTreePluginContext) {
  checkPluginVersion(context);

  return <InvenTreeLocationPanel context={context} />;
}
