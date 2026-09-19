// Écran « Manifestation, prestation & lieu » — l'arborescence de la maquette
// du cahier des charges (annexe « Idées de design ») : manifestation →
// prestation → bon de réservation → articles, avec par ligne la quantité
// réservée, livrée et ramassée, et les pastilles d'état.
//
// C'est la « navigation hiérarchique sans ressaisie » demandée le 09/09/2026.
//
// Le niveau client manque toujours, mais plus faute de table : `Client` et
// `Contact` existent depuis le lot L2 (09/09). C'est la tâche F3 — poser le
// client au-dessus, dépliable sur ses manifestations. À ne pas confondre avec
// le sélecteur de client posé ici (A3) : il **filtre** la liste, il ne
// l'imbrique pas, et il devra disparaître quand le niveau arrivera — sinon on
// filtrera deux fois la même chose, une fois par le haut et une par le côté.
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
  Modal,
  Radio,
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

import type { Client, Manifestation, Page, Prestation } from '../organisation/types';
import { PrestationCreateModal } from '../reservation/PrestationCreateModal';
import { ReservationForm } from '../reservation/ReservationForm';
import type { Reservation } from '../reservation/types';
import { canWriteOrganisation, canWriteReservations } from '../roles';
import { ownsKeys, syncOwnedParams } from '../urlState';

const MANIFESTATIONS_URL = '/plugin/inventree-location/manifestations/';
const PRESTATIONS_URL = '/plugin/inventree-location/prestations/';
const RESERVATIONS_URL = '/plugin/inventree-location/reservations/';
const CLIENTS_URL = '/plugin/inventree-location/clients/';

/** Teintes des quatre niveaux, dans l'esprit de la maquette. */
const FOND = {
  client: 'var(--mantine-color-dark-0)',
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
 * Bouton d'ajout de la maquette (F4).
 *
 * Il ouvre le formulaire existant plutôt qu'un formulaire de plus : la
 * création d'une prestation et celle d'un bon vivent déjà dans
 * `PrestationCreateModal` et `ReservationForm`, tous deux écrits pour être
 * montés ailleurs. Rien n'est dupliqué — une règle de saisie corrigée l'est
 * partout à la fois.
 *
 * Rendu `null` sans le droit d'écriture : un bouton qu'on ne peut pas suivre
 * n'apprend rien à qui n'a pas le rôle.
 */
function Ajouter({
  quoi,
  onClick,
  autorise = true
}: {
  quoi: string;
  onClick: () => void;
  autorise?: boolean;
}) {
  if (!autorise) {
    return null;
  }

  return (
    <Tooltip label={`Ajouter ${quoi}`}>
      <ActionIcon
        variant='light'
        color='green'
        size='sm'
        aria-label={`Ajouter ${quoi}`}
        onClick={onClick}
      >
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
  prestation,
  indentationBase = 48
}: {
  context: InvenTreePluginContext;
  prestation: Prestation;
  indentationBase?: number;
}) {
  const [ouverts, setOuverts] = useState<Set<number>>(new Set());
  // Ajouter un article à un bon, c'est modifier le bon : on ouvre le
  // formulaire de réservation sur lui, où la liste d'articles se saisit déjà,
  // avec ses contrôles de stock et de statut.
  const [bonEdite, setBonEdite] = useState<Reservation | null>(null);
  const peutEcrire = canWriteReservations(context);

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
    return <Loader size='xs' ml={indentationBase + 12} my={4} />;
  }

  const bons = query.data?.results ?? [];

  if (bons.length === 0) {
    return (
      <Text size='xs' c='dimmed' ml={indentationBase + 12} my={4}>
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
            <Ligne fond={FOND.bon} indentation={indentationBase}>
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
                  <Ajouter
                    quoi='un article'
                    autorise={peutEcrire}
                    onClick={() => setBonEdite(bon)}
                  />
                </Group>
              </Group>
            </Ligne>

            {ouvert &&
              lignes.map((ligne) => (
                <Ligne key={ligne.id} fond={FOND.article} indentation={indentationBase + 24}>
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

      <Modal
        opened={bonEdite !== null}
        onClose={() => setBonEdite(null)}
        size='xl'
        title={`Bon de réservation ${bonEdite?.numero ?? ''}`}
      >
        {bonEdite && (
          <ReservationForm
            context={context}
            reservationId={bonEdite.id}
            onSaved={() => {
              // Les lignes voyagent dans la charge du bon : c'est la liste des
              // bons de la prestation qu'il faut relire, pas une liste
              // d'articles qui n'existe pas.
              context.queryClient.invalidateQueries({
                queryKey: ['arbo-reservations', prestation.id]
              });
              setBonEdite(null);
            }}
          />
        )}
      </Modal>
    </>
  );
}

/** Niveau 2 : les prestations d'une manifestation. */
function PrestationsDeLaManifestation({
  context,
  manifestation,
  indentationBase = 24
}: {
  context: InvenTreePluginContext;
  manifestation: Manifestation;
  indentationBase?: number;
}) {
  const [ouvertes, setOuvertes] = useState<Set<number>>(new Set());
  const [prestationDuBon, setPrestationDuBon] = useState<Prestation | null>(
    null
  );
  const peutEcrire = canWriteReservations(context);

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
    return <Loader size='xs' ml={indentationBase + 12} my={4} />;
  }

  const prestations = query.data?.results ?? [];

  if (prestations.length === 0) {
    return (
      <Text size='xs' c='dimmed' ml={indentationBase + 12} my={4}>
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
            <Ligne fond={FOND.prestation} indentation={indentationBase}>
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
                <Ajouter
                  quoi='une réservation'
                  autorise={peutEcrire}
                  onClick={() => setPrestationDuBon(prestation)}
                />
              </Group>
            </Ligne>

            {ouverte && (
              <BonsDeLaPrestation
                context={context}
                prestation={prestation}
                indentationBase={indentationBase + 24}
              />
            )}
          </Box>
        );
      })}

      <Modal
        opened={prestationDuBon !== null}
        onClose={() => setPrestationDuBon(null)}
        size='xl'
        title={`Nouveau bon — ${prestationDuBon?.nom ?? ''}`}
      >
        {prestationDuBon && (
          <ReservationForm
            context={context}
            prestationId={prestationDuBon.id}
            onSaved={() => {
              context.queryClient.invalidateQueries({
                queryKey: ['arbo-reservations', prestationDuBon.id]
              });
              setPrestationDuBon(null);
            }}
          />
        )}
      </Modal>
    </>
  );
}

/** Niveau 1 : les manifestations d'un client, chargées au dépliage. */
function ManifestationsDuClient({
  context,
  client,
  recherche,
  periode,
  ouvertes,
  setOuvertes,
  onAjouterPrestation
}: {
  context: InvenTreePluginContext;
  client: Client;
  recherche: string;
  periode: string;
  ouvertes: Set<number>;
  setOuvertes: React.Dispatch<React.SetStateAction<Set<number>>>;
  onAjouterPrestation: (manifestation: Manifestation) => void;
}) {
  const params = useMemo(() => {
    const valeurs: Record<string, string> = {
      client: String(client.id)
    };

    if (recherche.trim()) {
      valeurs.search = recherche.trim();
    }

    if (periode === 'futur' || periode === 'passe') {
      valeurs.periode = periode;
    }

    return valeurs;
  }, [client.id, recherche, periode]);

  const query = useQuery<Page<Manifestation>>(
    {
      queryKey: ['arbo-manifestations-client', client.id, params],
      queryFn: async () => {
        const reponse = await context.api.get(MANIFESTATIONS_URL, { params });
        return reponse.data as Page<Manifestation>;
      }
    },
    context.queryClient
  );

  const manifestations = query.data?.results ?? [];

  if (query.isLoading) {
    return <Loader size='xs' ml={36} my={4} />;
  }

  if (manifestations.length === 0) {
    return (
      <Text size='xs' c='dimmed' ml={36} my={4}>
        Aucune manifestation pour ce client sur cette période.
      </Text>
    );
  }

  return (
    <>
      {manifestations.map((manifestation) => {
        const ouverte = ouvertes.has(manifestation.id);

        return (
          <Box key={manifestation.id} mb={4}>
            <Ligne fond={FOND.manifestation} indentation={24}>
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

                <Ajouter
                  quoi='une prestation'
                  autorise={canWriteOrganisation(context)}
                  onClick={() => onAjouterPrestation(manifestation)}
                />
              </Group>
            </Ligne>

            {ouverte && (
              <PrestationsDeLaManifestation
                context={context}
                manifestation={manifestation}
                indentationBase={48}
              />
            )}
          </Box>
        );
      })}
    </>
  );
}

/** Arborescence F3 : client → manifestation → prestation → bon → articles. */
export function Arborescence({ context }: { context: InvenTreePluginContext }) {
  const [recherche, setRecherche] = useState('');
  const [periode, setPeriode] = useState('futur');
  const [clientsOuverts, setClientsOuverts] = useState<Set<number>>(new Set());
  const [ouvertes, setOuvertes] = useState<Set<number>>(new Set());
  const [manifestationDeLaPrestation, setManifestationDeLaPrestation] =
    useState<Manifestation | null>(null);

  const clientsQuery = useQuery<Page<Client>>(
    {
      queryKey: ['clients-arborescence'],
      queryFn: async () => {
        const reponse = await context.api.get(CLIENTS_URL, {
          params: { page_size: 200 }
        });
        return reponse.data as Page<Client>;
      }
    },
    context.queryClient
  );

  // Clé possédée, préfixée (cf. `urlState`).
  const own = new URLSearchParams();

  if (periode !== 'futur') {
    own.set('arbo_periode', periode);
  }

  syncOwnedParams(ownsKeys(['arbo_periode']), own);

  const clients = clientsQuery.data?.results ?? [];

  /** Une prestation vient de naître : la manifestation la montre aussitôt. */
  function prestationCreee() {
    const parente = manifestationDeLaPrestation;

    setManifestationDeLaPrestation(null);

    if (!parente) {
      return;
    }

    context.queryClient.invalidateQueries({
      queryKey: ['arbo-prestations', parente.id]
    });

    context.queryClient.invalidateQueries({
      queryKey: ['arbo-manifestations-client']
    });

    setOuvertes((precedent) => new Set(precedent).add(parente.id));
  }

  return (
    <Stack gap='sm'>
      <Title order={4} c={context.theme.primaryColor}>
        Client, manifestation, prestation &amp; lieu
      </Title>

      <Group justify='space-between' align='flex-end' wrap='wrap'>
        <TextInput
          placeholder='Rechercher une manifestation…'
          leftSection={<IconSearch size={16} />}
          value={recherche}
          onChange={(evenement) => setRecherche(evenement.currentTarget.value)}
          w={280}
        />

        <Radio.Group value={periode} onChange={setPeriode}>
          <Group gap='md'>
            <Radio value='futur' label='Futur' />
            <Radio value='passe' label='Passé' />
            <Radio value='tout' label='Tout' />
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

      {clientsQuery.isLoading && <Loader size='sm' />}

      {!clientsQuery.isLoading && clients.length === 0 && (
        <Text size='sm' c='dimmed'>
          Aucun client disponible.
        </Text>
      )}

      <Box>
        {clients.map((client) => {
          const ouvert = clientsOuverts.has(client.id);

          return (
            <Box key={client.id} mb={4}>
              <Ligne fond={FOND.client} indentation={0}>
                <Group justify='space-between' wrap='nowrap'>
                  <UnstyledButton
                    onClick={() =>
                      setClientsOuverts((precedent) => {
                        const suivant = new Set(precedent);
                        suivant.has(client.id)
                          ? suivant.delete(client.id)
                          : suivant.add(client.id);
                        return suivant;
                      })
                    }
                  >
                    <Group gap='xs' wrap='nowrap'>
                      <Chevron ouvert={ouvert} />
                      <Text size='sm' fw={700}>
                        Client — {client.nom}
                      </Text>
                      {client.email && (
                        <Text size='xs' c='dimmed'>
                          {client.email}
                        </Text>
                      )}
                      {client.gestionnaire_nom && (
                        <Text size='xs' c='dimmed'>
                          Gestionnaire : {client.gestionnaire_nom}
                        </Text>
                      )}
                    </Group>
                  </UnstyledButton>
                </Group>
              </Ligne>

              {ouvert && (
                <ManifestationsDuClient
                  context={context}
                  client={client}
                  recherche={recherche}
                  periode={periode}
                  ouvertes={ouvertes}
                  setOuvertes={setOuvertes}
                  onAjouterPrestation={setManifestationDeLaPrestation}
                />
              )}
            </Box>
          );
        })}
      </Box>

      <PrestationCreateModal
        context={context}
        opened={manifestationDeLaPrestation !== null}
        manifestationId={manifestationDeLaPrestation?.id ?? null}
        libelleAction='Créer la prestation'
        onClose={() => setManifestationDeLaPrestation(null)}
        onCreated={prestationCreee}
      />
    </Stack>
  );
}
