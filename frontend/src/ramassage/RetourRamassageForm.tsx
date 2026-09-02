// SCRUM-112 — Saisie du retour d'un ramassage : ce qui revient en état, ce qui
// part au SAV, ce qui est détruit, ce qui manque.
//
// Composant séparé du bon de ramassage : le bon s'imprime (cf. printableModal),
// la saisie non. Les deux vivaient dans le même bloc et partaient à
// l'imprimante avec leurs champs de formulaire.
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Group,
  NumberInput,
  Stack,
  Table,
  Text,
  Textarea,
  Title
} from '@mantine/core';
import { useState } from 'react';

import { apiErrorMessage } from '../backoffice/apiError';
import { canCheckinReturns } from '../roles';
import type {
  LigneBonRamassage,
  RetourRamassagePayload,
  RetourRamassageResponse
} from './types';

export interface RetourLineForm {
  ligne: number;
  partNom: string;
  quantiteAttendue: number;
  quantite_ramassee: number;
  quantite_sav: number;
  quantite_detruite: number;
  quantite_manquante: number;
  facturer_client: boolean;
  commentaire: string;
}

function numberValue(value: string | number | null | undefined): number {
  const parsed = typeof value === 'number' ? value : Number(value);

  return Number.isFinite(parsed) ? parsed : 0;
}

/** Quantité que l'on s'attend à voir revenir : livrée à défaut de demandée. */
export function quantiteAttendue(ligne: LigneBonRamassage): number {
  return (
    ligne.quantite_a_ramasser ||
    ligne.quantite_livree ||
    ligne.quantite_demandee ||
    0
  );
}

export function formFromLigne(ligne: LigneBonRamassage): RetourLineForm {
  return {
    ligne: ligne.id,
    partNom: ligne.part_nom,
    quantiteAttendue: quantiteAttendue(ligne),
    quantite_ramassee: ligne.quantite_ramassee || ligne.quantite_retournee || 0,
    quantite_sav: ligne.quantite_sav || 0,
    quantite_detruite: ligne.quantite_detruite || 0,
    quantite_manquante: ligne.quantite_manquante || 0,
    facturer_client: Boolean(ligne.facturer_client),
    commentaire: ligne.commentaire || ''
  };
}

export function totalSaisi(line: RetourLineForm): number {
  return (
    line.quantite_ramassee +
    line.quantite_sav +
    line.quantite_detruite +
    line.quantite_manquante
  );
}

export function buildRetourPayload(
  lines: RetourLineForm[],
  commentaire: string
): RetourRamassagePayload {
  return {
    commentaire,
    lignes: lines.map((line) => ({
      ligne: line.ligne,
      quantite_ramassee: line.quantite_ramassee,
      quantite_sav: line.quantite_sav,
      quantite_detruite: line.quantite_detruite,
      quantite_manquante: line.quantite_manquante,
      facturer_client: line.facturer_client,
      commentaire: line.commentaire
    }))
  };
}

export function RetourRamassageForm({
  context,
  reservationId,
  lignes,
  onSaved
}: {
  context: InvenTreePluginContext;
  reservationId: number;
  lignes: LigneBonRamassage[];
  onSaved: () => Promise<void> | void;
}) {
  const [lines, setLines] = useState<RetourLineForm[]>(() =>
    lignes.map(formFromLigne)
  );
  const [commentaire, setCommentaire] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Le backend refuse la saisie hors magasinier (`ReturnCheckinPermission`) :
  // on masque le formulaire plutôt que de laisser l'utilisateur buter sur 403.
  if (!canCheckinReturns(context)) {
    return null;
  }

  const enTrop = lines.filter(
    (line) => totalSaisi(line) > line.quantiteAttendue
  );

  function updateLine(index: number, patch: Partial<RetourLineForm>) {
    setLines((current) =>
      current.map((line, i) => (i === index ? { ...line, ...patch } : line))
    );
  }

  async function save() {
    setSaving(true);
    setError('');
    setSuccess('');

    try {
      const response = await context.api.patch(
        `/plugin/inventree-location/ramassages/${reservationId}/retour/`,
        buildRetourPayload(lines, commentaire)
      );

      const data = response.data as RetourRamassageResponse;
      const tickets = data.sav_tickets?.length ?? 0;

      setSuccess(
        `Retour enregistré pour ${data.numero} (statut ${data.statut})` +
          (tickets > 0 ? ` — ${tickets} ticket(s) SAV ouvert(s).` : '.')
      );

      await onSaved();
    } catch (err: unknown) {
      setError(apiErrorMessage(err, "Impossible d'enregistrer le retour."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Stack gap='sm'>
      <Title order={5}>Saisie du retour</Title>

      {error && (
        <Alert color='red' title='Erreur'>
          {error}
        </Alert>
      )}

      {success && (
        <Alert color='green' title='Retour enregistré'>
          {success}
        </Alert>
      )}

      <Table.ScrollContainer minWidth={900}>
        <Table striped withTableBorder>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Article</Table.Th>
              <Table.Th>Attendue</Table.Th>
              <Table.Th>Revenue OK</Table.Th>
              <Table.Th>SAV</Table.Th>
              <Table.Th>Détruite</Table.Th>
              <Table.Th>Manquante</Table.Th>
              <Table.Th>Facturer</Table.Th>
              <Table.Th>Commentaire</Table.Th>
              <Table.Th>Total</Table.Th>
            </Table.Tr>
          </Table.Thead>

          <Table.Tbody>
            {lines.map((line, index) => {
              const total = totalSaisi(line);
              const invalide = total > line.quantiteAttendue;

              return (
                <Table.Tr key={line.ligne}>
                  <Table.Td>
                    <Text fw={500}>{line.partNom}</Text>
                  </Table.Td>
                  <Table.Td>{line.quantiteAttendue}</Table.Td>

                  {(
                    [
                      'quantite_ramassee',
                      'quantite_sav',
                      'quantite_detruite',
                      'quantite_manquante'
                    ] as const
                  ).map((champ) => (
                    <Table.Td key={champ}>
                      <NumberInput
                        min={0}
                        max={line.quantiteAttendue}
                        value={line[champ]}
                        onChange={(value) =>
                          updateLine(index, { [champ]: numberValue(value) })
                        }
                        w={90}
                      />
                    </Table.Td>
                  ))}

                  <Table.Td>
                    <Checkbox
                      checked={line.facturer_client}
                      onChange={(event) =>
                        updateLine(index, {
                          facturer_client: event.currentTarget.checked
                        })
                      }
                    />
                  </Table.Td>

                  <Table.Td>
                    <Textarea
                      autosize
                      minRows={1}
                      value={line.commentaire}
                      onChange={(event) =>
                        updateLine(index, {
                          commentaire: event.currentTarget.value
                        })
                      }
                      placeholder='État, casse, remarque…'
                      w={200}
                    />
                  </Table.Td>

                  <Table.Td>
                    <Badge color={invalide ? 'red' : 'green'}>
                      {total} / {line.quantiteAttendue}
                    </Badge>
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>

      {enTrop.length > 0 && (
        <Alert color='red' title='Quantités invalides'>
          {enTrop.map((line) => line.partNom).join(', ')} : le total saisi
          dépasse la quantité attendue.
        </Alert>
      )}

      <Textarea
        label='Commentaire du retour'
        value={commentaire}
        onChange={(event) => setCommentaire(event.currentTarget.value)}
        placeholder='Ex : retour terrain, contrôle magasinier à prévoir…'
        autosize
        minRows={2}
      />

      <Group justify='flex-end'>
        <Button
          onClick={save}
          loading={saving}
          disabled={enTrop.length > 0 || lines.length === 0}
        >
          Enregistrer le retour
        </Button>
      </Group>
    </Stack>
  );
}
