// Écran « Manifestation, prestation & lieu » — l'arborescence de la maquette
// du cahier des charges (annexe « Idées de design ») : manifestation →
// prestation → bon de réservation → articles, avec par ligne la quantité
// réservée, livrée et ramassée, et les pastilles d'état.
//
// C'est la « navigation hiérarchique sans ressaisie » demandée le 09/09/2026.
// Le niveau client manque : `Client` et `Contact` n'existent pas encore en base.
//
// Chargement **au dépliage**, un niveau à la fois : l'arbre entier aurait
// demandé un endpoint dédié et ramené toute la base à chaque affichage.
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  ActionIcon,
  Badge,
  Box,
  Group,
  Loader,
  Radio,
  Select,
  Stack,
  Text,
  TextInput,
  Title,
  Tooltip,
  UnstyledButton
} from '@mantine/core';
import {
  IconChevronDown,
  IconChevronRight,
  IconPlus,
  IconSearch
} from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import type { Manifestation, Page, Prestation } from '../organisation/types';
import type { Reservation } from '../reservation/types';
import { ownsKeys, syncOwnedParams } from '../urlState';

const MANIFESTATIONS_URL = '/plugin/inventree-location/manifestations/';
const PRESTATIONS_URL = '/plugin/inventree-location/prestations/';
const RESERVATIONS_URL = '/plugin/inventree-location/reservations/';
const CLIENTS_URL = '/plugin/inventree-location/clients/';

/** Teintes des quatre niveaux, dans l'esprit de la maquette. */
const FOND = {
  manifestation: 'var(--mantine-color-gray-3)',
  prestation: 'var(--mantine-color-blue-1)',
  bon: 'var(--mantine-color-red-0)',
  article: 'var(--mantine-color-yellow-0)'
};

type Avancement = 'rien' | 'partiel' | 'complet';

/** `attendu` nul renvoie « rien » : une ligne sans demande n'est pas servie. */
function avancement(fait: number, attendu: number): Avancement {
  if (attendu <= 0 || fait <= 0) {
    return 'rien';
  }

  return fait >= attendu ? 'complet' : 'partiel';
}

/** Le moins avancé de plusieurs états — un seul partiel suffit à dégrader. */
function agreger(etats: Avancement[]): Avancement {
  if (etats.length === 0 || etats.every((e) => e === 'rien')) {
    return 'rien';
  }

  return etats.every((e) => e === 'complet') ? 'complet' : 'partiel';
}

/** Pastille d'état (légende de la maquette). */
function Pastille({
  lettre,
  etat,
  libelle
}: {
  lettre: 'L' | 'R';
  etat: Avancement;
  libelle: string;
}) {
  if (etat === 'rien') {
    return (
      <Tooltip label={`${libelle} : rien`}>
        <Badge
          circle
          variant='outline'
          color='gray'
          styles={{ label: { fontSize: 10 } }}
        >
          {lettre}
        </Badge>
      </Tooltip>
    );
  }

  // Couleurs de la légende du CDC : ramassage complet en magenta, pour le
  // distinguer d'une livraison complète.
  const couleur =
    etat === 'complet' ? (lettre === 'R' ? 'grape' : 'green') : 'yellow';

  return (
    <Tooltip label={`${libelle} : ${etat}`}>
      <Badge circle color={couleur} styles={{ label: { fontSize: 10 } }}>
        {lettre}
      </Badge>
    </Tooltip>
  );
}

function Chevron({ ouvert }: { ouvert: boolean }) {
  return ouvert ? (
    <IconChevronDown size={16} />
  ) : (
    <IconChevronRight size={16} />
  );
}

/**
 * Bouton d'ajout de la maquette, désactivé : la création passe par l'écran
 * « Fiches », qui porte les formulaires. Les brancher ici suppose de les en
 * extraire — lot à part. Visible et inactif, il dit ce qui reste à faire.
 */
function Ajouter({ quoi }: { quoi: string }) {
  return (
    <Tooltip label={`Ajouter ${quoi} — passe par l'écran dédié pour l'instant`}>
      <ActionIcon variant='light' color='green' size='sm' disabled>
        <IconPlus size={14} />
      </ActionIcon>
    </Tooltip>
  );
}

function Ligne({
  fond,
  indentation,
  children
}: {
  fond: string;
  indentation: number;
  children: React.ReactNode;
}) {
  return (
    <Box
      style={{
        background: fond,
        marginLeft: indentation,
        borderRadius: 3,
        marginBottom: 2
      }}
      px='xs'
      py={4}
    >
      {children}
    </Box>
  );
}

function dateCourte(iso: string | null | undefined): string {
  if (!iso) {
    return '—';
  }

  return new Date(iso).toLocaleString('fr-FR', {
    day: '2-digit',
    month: 'short',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
}

/** Niveaux 3 et 4 : bons d'une prestation et leurs articles. */
function BonsDeLaPrestation({
  context,
  prestation
}: {
  context: InvenTreePluginContext;
  prestation: Prestation;
}) {
  const [ouverts, setOuverts] = useState<Set<number>>(new Set());

  const query = useQuery<Page<Reservation>>(
    {
      queryKey: ['arbo-reservations', prestation.id],
      queryFn: async () => {
        const reponse = await context.api.get(RESERVATIONS_URL, {
          params: { prestation: prestation.id }
        });
        return reponse.data as Page<Reservation>;
      }
    },
    context.queryClient
  );

  if (query.isLoading) {
    return <Loader size='xs' ml={60} my={4} />;
  }

  const bons = query.data?.results ?? [];

  if (bons.length === 0) {
    return (
      <Text size='xs' c='dimmed' ml={60} my={4}>
        Aucun bon de réservation sur cette prestation.
      </Text>
    );
  }

  return (
    <>
      {bons.map((bon) => {
        const ouvert = ouverts.has(bon.id);
        const lignes = bon.lignes ?? [];

        const etatLivraison = agreger(
          lignes.map((l) => avancement(l.quantite_livree, l.quantite_demandee))
        );
        const etatRamassage = agreger(
          lignes.map((l) => avancement(l.quantite_retournee, l.quantite_livree))
        );

        return (
          <Box key={bon.id}>
            <Ligne fond={FOND.bon} indentation={48}>
              <Group justify='space-between' wrap='nowrap'>
                <UnstyledButton
                  onClick={() =>
                    setOuverts((precedent) => {
                      const suivant = new Set(precedent);
                      suivant.has(bon.id)
                        ? suivant.delete(bon.id)
                        : suivant.add(bon.id);
                      return suivant;
                    })
                  }
                >
                  <Group gap='xs' wrap='nowrap'>
                    <Chevron ouvert={ouvert} />
                    <Text size='sm' fw={600}>
                      Bon de réservation {bon.numero}
                    </Text>
                    <Text size='xs' c='dimmed'>
                      {lignes.length} article{lignes.length > 1 ? 's' : ''}
                    </Text>
                  </Group>
                </UnstyledButton>
                <Group gap={6} wrap='nowrap'>
                  <Pastille
                    lettre='L'
                    etat={etatLivraison}
                    libelle='Livraison'
                  />
                  <Pastille
                    lettre='R'
                    etat={etatRamassage}
                    libelle='Ramassage'
                  />
                  <Ajouter quoi='un article' />
                </Group>
              </Group>
            </Ligne>

            {ouvert &&
              lignes.map((ligne) => (
                <Ligne key={ligne.id} fond={FOND.article} indentation={72}>
                  <Group justify='space-between' wrap='nowrap'>
                    <Box>
                      <Text size='sm' fw={600}>
                        {ligne.part_name ?? `Article #${ligne.part}`}
                      </Text>
                      <Text size='xs' c='dimmed'>
                        Réf. {ligne.part_noi || '—'}
                      </Text>
                    </Box>
                    <Group gap='lg' wrap='nowrap'>
                      <Text size='xs'>
                        Qté réservée : <b>{ligne.quantite_demandee}</b>
                      </Text>
                      <Text size='xs'>
                        Livré : <b>{ligne.quantite_livree}</b>
                      </Text>
                      <Text size='xs'>
                        Ramassé : <b>{ligne.quantite_retournee}</b>
                      </Text>
                      <Pastille
                        lettre='L'
                        etat={avancement(
                          ligne.quantite_livree,
                          ligne.quantite_demandee
                        )}
                        libelle='Livraison'
                      />
                      <Pastille
                        lettre='R'
                        etat={avancement(
                          ligne.quantite_retournee,
                          ligne.quantite_livree
                        )}
                        libelle='Ramassage'
                      />
                    </Group>
                  </Group>
                </Ligne>
              ))}
          </Box>
        );
      })}
    </>
  );
}

/** Niveau 2 : les prestations d'une manifestation. */
function PrestationsDeLaManifestation({
  context,
  manifestation
}: {
  context: InvenTreePluginContext;
  manifestation: Manifestation;
}) {
  const [ouvertes, setOuvertes] = useState<Set<number>>(new Set());

  const query = useQuery<Page<Prestation>>(
    {
      queryKey: ['arbo-prestations', manifestation.id],
      queryFn: async () => {
        const reponse = await context.api.get(PRESTATIONS_URL, {
          params: { manifestation: manifestation.id }
        });
        return reponse.data as Page<Prestation>;
      }
    },
    context.queryClient
  );

  if (query.isLoading) {
    return <Loader size='xs' ml={36} my={4} />;
  }

  const prestations = query.data?.results ?? [];

  if (prestations.length === 0) {
    return (
      <Text size='xs' c='dimmed' ml={36} my={4}>
        Aucune prestation sur cette manifestation.
      </Text>
    );
  }

  return (
    <>
      {prestations.map((prestation) => {
        const ouverte = ouvertes.has(prestation.id);

        return (
          <Box key={prestation.id}>
            <Ligne fond={FOND.prestation} indentation={24}>
              <Group justify='space-between' wrap='nowrap'>
                <UnstyledButton
                  onClick={() =>
                    setOuvertes((precedent) => {
                      const suivant = new Set(precedent);
                      suivant.has(prestation.id)
                        ? suivant.delete(prestation.id)
                        : suivant.add(prestation.id);
                      return suivant;
                    })
                  }
                >
                  <Group gap='xs' wrap='nowrap'>
                    <Chevron ouvert={ouverte} />
                    <Text size='sm' fw={600}>
                      {prestation.nom}
                    </Text>
                    <Text size='xs' c='dimmed'>
                      {prestation.lieu_detail?.nom ?? 'Lieu à définir'}
                    </Text>
                    <Text size='xs' c='dimmed'>
                      {dateCourte(prestation.date_debut)} →{' '}
                      {dateCourte(prestation.date_fin)}
                    </Text>
                  </Group>
                </UnstyledButton>
                <Ajouter quoi='une réservation' />
              </Group>
            </Ligne>

            {ouverte && (
              <BonsDeLaPrestation context={context} prestation={prestation} />
            )}
          </Box>
        );
      })}
    </>
  );
}

/** Niveau 1 : les manifestations, filtrées par recherche et période. */
export function Arborescence({ context }: { context: InvenTreePluginContext }) {
  const [recherche, setRecherche] = useState('');
  const [periode, setPeriode] = useState('futur');
  const [client, setClient] = useState<string | null>(null);
  const [ouvertes, setOuvertes] = useState<Set<number>>(new Set());

  const params = useMemo(() => {
    const valeurs: Record<string, string> = {};

    if (recherche.trim()) {
      valeurs.search = recherche.trim();
    }

    // « Tout » est l'absence de filtre côté serveur, pas une valeur.
    if (periode === 'futur' || periode === 'passe') {
      valeurs.periode = periode;
    }

    // « Retrouver les manifestations d'un client au téléphone » (09/09). La
    // recherche texte porte sur le nom de la manifestation : sans ce filtre,
    // il fallait connaître le nom de l'évènement pour retrouver le client.
    if (client) {
      valeurs.client = client;
    }

    return valeurs;
  }, [recherche, periode, client]);

  // Le sélecteur de client se remplit une fois : la liste ne bouge pas au fil
  // des filtres, et elle est partagée avec les autres écrans qui la lisent.
  const clientsQuery = useQuery<Page<{ id: number; nom: string }>>(
    {
      queryKey: ['clients'],
      queryFn: async () => {
        const reponse = await context.api.get(CLIENTS_URL);
        return reponse.data as Page<{ id: number; nom: string }>;
      }
    },
    context.queryClient
  );

  // Clés possédées, préfixées (cf. `urlState`).
  const own = new URLSearchParams();
  if (periode !== 'futur') {
    own.set('arbo_periode', periode);
  }
  if (client) {
    own.set('arbo_client', client);
  }
  syncOwnedParams(ownsKeys(['arbo_periode', 'arbo_client']), own);

  const query = useQuery<Page<Manifestation>>(
    {
      queryKey: ['arbo-manifestations', params],
      queryFn: async () => {
        const reponse = await context.api.get(MANIFESTATIONS_URL, { params });
        return reponse.data as Page<Manifestation>;
      }
    },
    context.queryClient
  );

  const manifestations = query.data?.results ?? [];

  return (
    <Stack gap='sm'>
      <Title order={4} c={context.theme.primaryColor}>
        Manifestation, prestation &amp; lieu
      </Title>

      <Group justify='space-between' align='flex-end' wrap='wrap'>
        <TextInput
          placeholder='Rechercher une manifestation…'
          leftSection={<IconSearch size={16} />}
          value={recherche}
          onChange={(evenement) => setRecherche(evenement.currentTarget.value)}
          w={280}
        />
        <Select
          placeholder='Tous les clients'
          data={(clientsQuery.data?.results ?? []).map((c) => ({
            value: String(c.id),
            label: c.nom
          }))}
          value={client}
          onChange={setClient}
          clearable
          searchable
          w={220}
          aria-label='Client'
        />
        <Radio.Group value={periode} onChange={setPeriode}>
          <Group gap='md'>
            <Radio value='futur' label='Futur' />
            <Radio value='passe' label='Passé' />
            <Radio value='tout' label='Tout' />
            {/* Tables créées, montants non : montré mais désactivé, pour que
                l'écart avec la maquette se voie. */}
            <Tooltip label='À venir : la facturation est au modèle, pas encore aux écrans'>
              <Radio value='facturer' label='À facturer' disabled />
            </Tooltip>
          </Group>
        </Radio.Group>
        <Group gap={6}>
          <Pastille lettre='L' etat='partiel' libelle='Livraison' />
          <Text size='xs' c='dimmed'>
            partielle
          </Text>
          <Pastille lettre='L' etat='complet' libelle='Livraison' />
          <Text size='xs' c='dimmed'>
            complète
          </Text>
          <Pastille lettre='R' etat='partiel' libelle='Ramassage' />
          <Text size='xs' c='dimmed'>
            partiel
          </Text>
          <Pastille lettre='R' etat='complet' libelle='Ramassage' />
          <Text size='xs' c='dimmed'>
            complet
          </Text>
        </Group>
      </Group>

      {query.isLoading && <Loader size='sm' />}

      {!query.isLoading && manifestations.length === 0 && (
        <Text size='sm' c='dimmed'>
          Aucune manifestation sur cette période.
        </Text>
      )}

      <Box>
        {manifestations.map((manifestation) => {
          const ouverte = ouvertes.has(manifestation.id);

          return (
            <Box key={manifestation.id} mb={4}>
              <Ligne fond={FOND.manifestation} indentation={0}>
                <Group justify='space-between' wrap='nowrap'>
                  <UnstyledButton
                    onClick={() =>
                      setOuvertes((precedent) => {
                        const suivant = new Set(precedent);
                        suivant.has(manifestation.id)
                          ? suivant.delete(manifestation.id)
                          : suivant.add(manifestation.id);
                        return suivant;
                      })
                    }
                  >
                    <Group gap='xs' wrap='nowrap'>
                      <Chevron ouvert={ouverte} />
                      <Text size='sm' fw={700}>
                        {manifestation.nom}
                      </Text>
                      <Text size='xs' c='dimmed'>
                        {dateCourte(manifestation.date_debut)} →{' '}
                        {dateCourte(manifestation.date_fin)}
                      </Text>
                      <Text size='xs' c='dimmed'>
                        {manifestation.organisateur_nom}
                      </Text>
                      <Badge size='xs' variant='light'>
                        {manifestation.statut_effectif}
                      </Badge>
                      <Text size='xs' c='dimmed'>
                        {manifestation.prestations_count} prestation
                        {manifestation.prestations_count > 1 ? 's' : ''}
                      </Text>
                    </Group>
                  </UnstyledButton>
                  <Ajouter quoi='une prestation' />
                </Group>
              </Ligne>

              {ouverte && (
                <PrestationsDeLaManifestation
                  context={context}
                  manifestation={manifestation}
                />
              )}
            </Box>
          );
        })}
      </Box>
    </Stack>
  );
}
