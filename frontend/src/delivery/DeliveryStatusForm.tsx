// Progression de l'état d'une livraison assignée (US-19) : boutons
// contextuels selon l'état courant, photo et commentaire optionnels.
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Button,
  FileInput,
  Group,
  Modal,
  Stack,
  Text,
  Textarea
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';

import type { Delivery, EtatLivraison } from './types';

const DELIVERIES_URL = '/plugin/inventree-location/deliveries/';

function apiErrorDetail(error: unknown): string {
  const data = (error as { response?: { data?: { detail?: string } } })
    ?.response?.data;
  return data?.detail ?? "Impossible de mettre à jour l'état de la livraison.";
}

export function DeliveryStatusForm({
  context,
  delivery,
  onClose
}: {
  context: InvenTreePluginContext;
  delivery: Delivery | null;
  onClose: () => void;
}) {
  const [commentaire, setCommentaire] = useState('');
  const [photo, setPhoto] = useState<File | null>(null);

  const mutation = useMutation(
    {
      mutationFn: async (etat: EtatLivraison) => {
        const form = new FormData();
        form.append('etat', etat);
        if (commentaire.trim()) {
          form.append('commentaire', commentaire.trim());
        }
        if (photo) {
          form.append('photo', photo);
        }

        const response = await context.api.patch(
          `${DELIVERIES_URL}${delivery?.id}/etat/`,
          form
        );
        return response.data;
      },
      onSuccess: () => {
        context.queryClient.invalidateQueries({ queryKey: ['deliveries'] });
        setCommentaire('');
        setPhoto(null);
        onClose();
      },
      onError: (error: unknown) => {
        notifications.show({
          title: 'Action impossible',
          message: apiErrorDetail(error),
          color: 'red'
        });
      }
    },
    context.queryClient
  );

  function close() {
    setCommentaire('');
    setPhoto(null);
    onClose();
  }

  const etat = delivery?.etat_livraison;

  return (
    <Modal
      opened={delivery != null}
      onClose={close}
      title={delivery ? `Livraison ${delivery.numero}` : ''}
    >
      {delivery && (
        <Stack gap='md'>
          <Text size='sm' c='dimmed'>
            État actuel : {delivery.etat_livraison_display || 'Non assignée'}
          </Text>

          {(etat === 'en_cours' || etat === 'assignee') && (
            <>
              <Textarea
                label='Commentaire'
                placeholder='Optionnel'
                value={commentaire}
                onChange={(event) => setCommentaire(event.currentTarget.value)}
                autosize
                minRows={2}
              />
              <FileInput
                label='Photo'
                placeholder='Optionnelle'
                accept='image/*'
                value={photo}
                onChange={setPhoto}
                clearable
              />
            </>
          )}

          <Group justify='flex-end'>
            {etat === 'assignee' && (
              <Button
                loading={mutation.isPending}
                onClick={() => mutation.mutate('en_cours')}
              >
                Démarrer la livraison
              </Button>
            )}
            {etat === 'en_cours' && (
              <>
                <Button
                  color='red'
                  variant='light'
                  loading={mutation.isPending}
                  onClick={() => mutation.mutate('probleme')}
                >
                  Signaler un problème
                </Button>
                <Button
                  color='teal'
                  loading={mutation.isPending}
                  onClick={() => mutation.mutate('livree')}
                >
                  Marquer livrée
                </Button>
              </>
            )}
          </Group>
        </Stack>
      )}
    </Modal>
  );
}
