import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Checkbox,
  FileInput,
  Group,
  Image,
  Modal,
  NumberInput,
  SegmentedControl,
  Stack,
  Switch,
  Text,
  Tooltip,
  UnstyledButton
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import {
  IconCamera,
  IconCheck,
  IconChevronDown,
  IconChevronRight,
  IconMinus,
  IconPlus,
  IconPrinter,
  IconUpload
} from '@tabler/icons-react';
import { useMemo, useState } from 'react';

import { apiErrorMessage } from '../backoffice/apiError';
import { canCheckinReturns } from '../roles';
import type { LigneBonRamassage, Ramassage } from './types';

export type RamassageAvancementFilter =
  | 'tous'
  | 'a_faire'
  | 'partiel'
  | 'complet';

const FOND = {
  manifestation: 'var(--mantine-color-gray-3)',
  prestation: 'var(--mantine-color-blue-1)',
  bon: 'var(--mantine-color-red-0)',
  article: 'var(--mantine-color-yellow-0)'
};

type Avancement = 'rien' | 'partiel' | 'complet';

export function quantiteAttendue(ligne: LigneBonRamassage): number {
  return (
    ligne.quantite_a_ramasser ||
    ligne.quantite_livree ||
    ligne.quantite_demandee ||
    0
  );
}

function computeRamassageAvancement(
  ramassee: number,
  sav: number,
  detruite: number,
  attendue: number
): Avancement {
  const total = ramassee + sav + detruite;
  if (attendue <= 0 || total <= 0) {
    return 'rien';
  }
  return total >= attendue ? 'complet' : 'partiel';
}

function agregerAvancement(etats: Avancement[]): Avancement {
  if (etats.length === 0 || etats.every((e) => e === 'rien')) {
    return 'rien';
  }
  return etats.every((e) => e === 'complet') ? 'complet' : 'partiel';
}

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
      <Tooltip label={`${libelle} : à faire`}>
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
        borderRadius: 4,
        marginBottom: 3
      }}
      px='sm'
      py={6}
    >
      {children}
    </Box>
  );
}

export interface RamassageLigneState {
  quantiteRamassee: number;
  quantiteSav: number;
  quantiteDetruite: number;
  quantiteManquante: number;
  facturerClient: boolean;
  commentaire: string;
  photoUrl: string | null;
}

export function deduireManquant(
  attendue: number,
  ramassee: number,
  sav: number,
  detruite: number,
  isComplet: boolean
): number {
  if (!isComplet) {
    return 0;
  }
  const traite = ramassee + sav + detruite;
  return Math.max(0, attendue - traite);
}

export function RamassagesHierarchicalTable({
  context,
  ramassages,
  onOpenBon,
  onSaved
}: {
  context: InvenTreePluginContext;
  ramassages: Ramassage[];
  onOpenBon?: (ramassage: Ramassage) => void;
  onSaved?: () => Promise<void> | void;
}) {
  const [filterAvancement, setFilterAvancement] =
    useState<RamassageAvancementFilter>('tous');
  const [ouverts, setOuverts] = useState<Set<string>>(new Set());
  const [completPrestations, setCompletPrestations] = useState<
    Record<string, boolean>
  >({});
  const [lignesState, setLignesState] = useState<
    Record<number, RamassageLigneState>
  >({});
  const [photoModal, setPhotoModal] = useState<{
    ligneId: number;
    partNom: string;
  } | null>(null);
  const [savingBonId, setSavingBonId] = useState<number | null>(null);

  const canEdit = canCheckinReturns(context);

  function getLigneState(
    ligne: LigneBonRamassage,
    isPrestComplet: boolean
  ): RamassageLigneState {
    const existing = lignesState[ligne.id];
    if (existing) {
      return existing;
    }
    const attendue = quantiteAttendue(ligne);
    const defaultRamassee =
      ligne.quantite_ramassee || ligne.quantite_retournee || 0;
    const defaultSav = ligne.quantite_sav || 0;
    const defaultDetruite = ligne.quantite_detruite || 0;
    const defaultManquante =
      ligne.quantite_manquante ||
      deduireManquant(
        attendue,
        defaultRamassee,
        defaultSav,
        defaultDetruite,
        isPrestComplet
      );

    return {
      quantiteRamassee: defaultRamassee,
      quantiteSav: defaultSav,
      quantiteDetruite: defaultDetruite,
      quantiteManquante: defaultManquante,
      facturerClient: Boolean(ligne.facturer_client),
      commentaire: ligne.commentaire || '',
      photoUrl: null
    };
  }

  function setLigneState(ligneId: number, patch: Partial<RamassageLigneState>) {
    setLignesState((prev) => {
      const current = prev[ligneId] ?? {
        quantiteRamassee: 0,
        quantiteSav: 0,
        quantiteDetruite: 0,
        quantiteManquante: 0,
        facturerClient: false,
        commentaire: '',
        photoUrl: null
      };
      return {
        ...prev,
        [ligneId]: { ...current, ...patch }
      };
    });
  }

  function toggleOuvert(cle: string) {
    setOuverts((prev) => {
      const next = new Set(prev);
      if (next.has(cle)) {
        next.delete(cle);
      } else {
        next.add(cle);
      }
      return next;
    });
  }

  function handlePrestationCompletToggle(
    prestKey: string,
    prestBons: Ramassage[],
    complet: boolean
  ) {
    setCompletPrestations((prev) => ({ ...prev, [prestKey]: complet }));
    for (const bon of prestBons) {
      for (const ligne of bon.lignes ?? []) {
        const attendue = quantiteAttendue(ligne);
        const st = getLigneState(ligne, complet);
        const newManquant = deduireManquant(
          attendue,
          st.quantiteRamassee,
          st.quantiteSav,
          st.quantiteDetruite,
          complet
        );
        setLigneState(ligne.id, { quantiteManquante: newManquant });
      }
    }
  }

  const hierarchicalData = useMemo(() => {
    const manifestationsMap = new Map<
      string,
      {
        nom: string;
        clientNom: string;
        prestationsMap: Map<
          string,
          {
            nom: string;
            lieuNom: string;
            dateRetour: string | null;
            bons: Ramassage[];
          }
        >;
      }
    >();

    for (const r of ramassages) {
      const manifNom =
        r.manifestation_nom ||
        r.prestation_nom ||
        r.lieu?.nom ||
        'Manifestation générale';
      const prestNom = r.prestation_nom || 'Prestation standard';

      if (!manifestationsMap.has(manifNom)) {
        manifestationsMap.set(manifNom, {
          nom: manifNom,
          clientNom: r.client_nom || '',
          prestationsMap: new Map()
        });
      }
      const manif = manifestationsMap.get(manifNom)!;
      if (!manif.prestationsMap.has(prestNom)) {
        manif.prestationsMap.set(prestNom, {
          nom: prestNom,
          lieuNom: r.lieu?.nom || r.lieu?.adresse || '—',
          dateRetour: r.date_retour_prevue || r.date_ramassage,
          bons: []
        });
      }
      manif.prestationsMap.get(prestNom)?.bons.push(r);
    }

    return Array.from(manifestationsMap.values()).map((manif) => ({
      nom: manif.nom,
      clientNom: manif.clientNom,
      prestations: Array.from(manif.prestationsMap.values()).map((prest) => ({
        nom: prest.nom,
        lieuNom: prest.lieuNom,
        dateRetour: prest.dateRetour,
        bons: prest.bons
      }))
    }));
  }, [ramassages]);

  const filteredHierarchy = useMemo(() => {
    if (filterAvancement === 'tous') {
      return hierarchicalData;
    }

    return hierarchicalData
      .map((manif) => {
        const filteredPrestations = manif.prestations
          .map((prest) => {
            const prestKey = `prest-${manif.nom}-${prest.nom}`;
            const isPrestComplet = Boolean(completPrestations[prestKey]);

            const filteredBons = prest.bons.filter((bon) => {
              const lignes = bon.lignes ?? [];
              const etats = lignes.map((l) => {
                const st = getLigneState(l, isPrestComplet);
                return computeRamassageAvancement(
                  st.quantiteRamassee,
                  st.quantiteSav,
                  st.quantiteDetruite,
                  quantiteAttendue(l)
                );
              });
              const bonAvancement = agregerAvancement(etats);

              if (filterAvancement === 'a_faire') {
                return bonAvancement === 'rien';
              }
              if (filterAvancement === 'partiel') {
                return bonAvancement === 'partiel';
              }
              if (filterAvancement === 'complet') {
                return bonAvancement === 'complet';
              }
              return true;
            });

            return { ...prest, bons: filteredBons };
          })
          .filter((prest) => prest.bons.length > 0);

        return { ...manif, prestations: filteredPrestations };
      })
      .filter((manif) => manif.prestations.length > 0);
  }, [hierarchicalData, filterAvancement, completPrestations, getLigneState]);

  async function handleSaveBon(bon: Ramassage, isPrestComplet: boolean) {
    const lignes = bon.lignes ?? [];
    if (lignes.length === 0) {
      return;
    }

    setSavingBonId(bon.id);
    try {
      const payloadLignes = lignes.map((l) => {
        const st = getLigneState(l, isPrestComplet);
        return {
          ligne: l.id,
          quantite_ramassee: st.quantiteRamassee,
          quantite_sav: st.quantiteSav,
          quantite_detruite: st.quantiteDetruite,
          quantite_manquante: st.quantiteManquante,
          facturer_client: st.facturerClient,
          commentaire: st.commentaire
        };
      });

      await context.api.patch(
        `/plugin/inventree-location/ramassages/${bon.id}/retour/`,
        {
          commentaire: `Retour ramassage ${bon.numero}`,
          lignes: payloadLignes
        }
      );

      notifications.show({
        title: 'Retour enregistré',
        message: `Ramassage mis à jour pour le bon ${bon.numero}.`,
        color: 'green'
      });

      if (onSaved) {
        await onSaved();
      }
    } catch (err) {
      notifications.show({
        title: 'Erreur',
        message: apiErrorMessage(err, "Impossible d'enregistrer le ramassage."),
        color: 'red'
      });
    } finally {
      setSavingBonId(null);
    }
  }

  return (
    <Stack gap='sm'>
      <Group justify='space-between' align='center' wrap='wrap'>
        <Group gap='xs'>
          <Text size='sm' fw={500}>
            Filtre avancement :
          </Text>
          <SegmentedControl
            size='xs'
            value={filterAvancement}
            onChange={(val) =>
              setFilterAvancement(val as RamassageAvancementFilter)
            }
            data={[
              { label: 'Tous', value: 'tous' },
              { label: 'À faire', value: 'a_faire' },
              { label: 'Partiel', value: 'partiel' },
              { label: 'Complet', value: 'complet' }
            ]}
          />
        </Group>
      </Group>

      {filteredHierarchy.length === 0 ? (
        <Text c='dimmed' size='sm'>
          Aucun ramassage ne correspond aux critères.
        </Text>
      ) : (
        <Stack gap={4}>
          {filteredHierarchy.map((manif) => {
            const manifKey = `manif-${manif.nom}`;
            const manifOuvert = ouverts.has(manifKey);

            const allManifLignes: {
              l: LigneBonRamassage;
              isPrestComplet: boolean;
            }[] = [];
            for (const p of manif.prestations) {
              const pKey = `prest-${manif.nom}-${p.nom}`;
              const pComplet = Boolean(completPrestations[pKey]);
              for (const b of p.bons) {
                for (const l of b.lignes ?? []) {
                  allManifLignes.push({ l, isPrestComplet: pComplet });
                }
              }
            }

            const manifEtat = agregerAvancement(
              allManifLignes.map(({ l, isPrestComplet }) => {
                const st = getLigneState(l, isPrestComplet);
                return computeRamassageAvancement(
                  st.quantiteRamassee,
                  st.quantiteSav,
                  st.quantiteDetruite,
                  quantiteAttendue(l)
                );
              })
            );

            return (
              <Box key={manifKey}>
                <Ligne fond={FOND.manifestation} indentation={0}>
                  <Group justify='space-between' wrap='nowrap'>
                    <UnstyledButton onClick={() => toggleOuvert(manifKey)}>
                      <Group gap='xs' wrap='nowrap'>
                        <Chevron ouvert={manifOuvert} />
                        <Text size='sm' fw={700}>
                          {manif.nom}
                        </Text>
                        {manif.clientNom && (
                          <Text size='xs' c='dimmed'>
                            · Client : {manif.clientNom}
                          </Text>
                        )}
                        <Text size='xs' c='dimmed'>
                          ({manif.prestations.length} prestation
                          {manif.prestations.length > 1 ? 's' : ''})
                        </Text>
                      </Group>
                    </UnstyledButton>
                    <Group gap='xs' wrap='nowrap'>
                      <Pastille
                        lettre='R'
                        etat={manifEtat}
                        libelle='Ramassage'
                      />
                    </Group>
                  </Group>
                </Ligne>

                {manifOuvert &&
                  manif.prestations.map((prest) => {
                    const prestKey = `prest-${manif.nom}-${prest.nom}`;
                    const prestOuvert = ouverts.has(prestKey);
                    const isPrestComplet = Boolean(
                      completPrestations[prestKey]
                    );

                    const prestLignes: LigneBonRamassage[] = [];
                    for (const b of prest.bons) {
                      for (const l of b.lignes ?? []) {
                        prestLignes.push(l);
                      }
                    }

                    const prestEtat = agregerAvancement(
                      prestLignes.map((l) => {
                        const st = getLigneState(l, isPrestComplet);
                        return computeRamassageAvancement(
                          st.quantiteRamassee,
                          st.quantiteSav,
                          st.quantiteDetruite,
                          quantiteAttendue(l)
                        );
                      })
                    );

                    return (
                      <Box key={prestKey}>
                        <Ligne fond={FOND.prestation} indentation={24}>
                          <Group justify='space-between' wrap='nowrap'>
                            <Group gap='xs' wrap='nowrap'>
                              <UnstyledButton
                                onClick={() => toggleOuvert(prestKey)}
                              >
                                <Group gap='xs' wrap='nowrap'>
                                  <Chevron ouvert={prestOuvert} />
                                  <Text size='sm' fw={600}>
                                    {prest.nom}
                                  </Text>
                                  <Text size='xs' c='dimmed'>
                                    Lieu : {prest.lieuNom}
                                  </Text>
                                </Group>
                              </UnstyledButton>
                            </Group>

                            <Group gap='md' wrap='nowrap'>
                              <Checkbox
                                size='xs'
                                label='Ramassage complet du lieu'
                                checked={isPrestComplet}
                                onChange={(e) =>
                                  handlePrestationCompletToggle(
                                    prestKey,
                                    prest.bons,
                                    e.currentTarget.checked
                                  )
                                }
                              />
                              <Pastille
                                lettre='R'
                                etat={prestEtat}
                                libelle='Ramassage'
                              />
                            </Group>
                          </Group>
                        </Ligne>

                        {prestOuvert &&
                          prest.bons.map((bon) => {
                            const bonKey = `bon-${bon.id}`;
                            const bonOuvert = ouverts.has(bonKey);
                            const lignes = bon.lignes ?? [];

                            const bonEtat = agregerAvancement(
                              lignes.map((l) => {
                                const st = getLigneState(l, isPrestComplet);
                                return computeRamassageAvancement(
                                  st.quantiteRamassee,
                                  st.quantiteSav,
                                  st.quantiteDetruite,
                                  quantiteAttendue(l)
                                );
                              })
                            );

                            return (
                              <Box key={bonKey}>
                                <Ligne fond={FOND.bon} indentation={48}>
                                  <Group justify='space-between' wrap='nowrap'>
                                    <UnstyledButton
                                      onClick={() => toggleOuvert(bonKey)}
                                    >
                                      <Group gap='xs' wrap='nowrap'>
                                        <Chevron ouvert={bonOuvert} />
                                        <Text size='sm' fw={600}>
                                          Bon {bon.numero}
                                        </Text>
                                        <Badge size='xs' color='grape'>
                                          {bon.statut}
                                        </Badge>
                                        <Text size='xs' c='dimmed'>
                                          {lignes.length} article
                                          {lignes.length > 1 ? 's' : ''}
                                        </Text>
                                      </Group>
                                    </UnstyledButton>

                                    <Group gap='xs' wrap='nowrap'>
                                      {onOpenBon && (
                                        <Button
                                          size='compact-xs'
                                          variant='light'
                                          leftSection={
                                            <IconPrinter size={12} />
                                          }
                                          onClick={() => onOpenBon(bon)}
                                        >
                                          Bon
                                        </Button>
                                      )}
                                      {canEdit && (
                                        <Button
                                          size='compact-xs'
                                          color='green'
                                          leftSection={<IconCheck size={12} />}
                                          loading={savingBonId === bon.id}
                                          onClick={() =>
                                            handleSaveBon(bon, isPrestComplet)
                                          }
                                        >
                                          Enregistrer
                                        </Button>
                                      )}
                                      <Pastille
                                        lettre='R'
                                        etat={bonEtat}
                                        libelle='Ramassage'
                                      />
                                    </Group>
                                  </Group>
                                </Ligne>

                                {bonOuvert &&
                                  lignes.map((ligne) => {
                                    const attendue = quantiteAttendue(ligne);
                                    const st = getLigneState(
                                      ligne,
                                      isPrestComplet
                                    );
                                    const ligneEtat =
                                      computeRamassageAvancement(
                                        st.quantiteRamassee,
                                        st.quantiteSav,
                                        st.quantiteDetruite,
                                        attendue
                                      );

                                    return (
                                      <Ligne
                                        key={ligne.id}
                                        fond={FOND.article}
                                        indentation={72}
                                      >
                                        <Group
                                          justify='space-between'
                                          wrap='nowrap'
                                          align='center'
                                        >
                                          <Box w={160}>
                                            <Text size='sm' fw={600} truncate>
                                              {ligne.part_nom}
                                            </Text>
                                            <Text size='xs' c='dimmed'>
                                              Attendu : <b>{attendue}</b>
                                            </Text>
                                          </Box>

                                          <Group gap='sm' wrap='nowrap'>
                                            <Group gap={4} wrap='nowrap'>
                                              <Text
                                                size='xs'
                                                c='green'
                                                fw={500}
                                              >
                                                OK:
                                              </Text>
                                              <ActionIcon
                                                size='xs'
                                                variant='default'
                                                disabled={
                                                  !canEdit ||
                                                  st.quantiteRamassee <= 0
                                                }
                                                onClick={() => {
                                                  const n = Math.max(
                                                    0,
                                                    st.quantiteRamassee - 1
                                                  );
                                                  const manq = deduireManquant(
                                                    attendue,
                                                    n,
                                                    st.quantiteSav,
                                                    st.quantiteDetruite,
                                                    isPrestComplet
                                                  );
                                                  setLigneState(ligne.id, {
                                                    quantiteRamassee: n,
                                                    quantiteManquante: manq
                                                  });
                                                }}
                                              >
                                                <IconMinus size={10} />
                                              </ActionIcon>
                                              <NumberInput
                                                size='xs'
                                                w={50}
                                                min={0}
                                                disabled={!canEdit}
                                                value={st.quantiteRamassee}
                                                onChange={(val) => {
                                                  const n =
                                                    typeof val === 'number'
                                                      ? val
                                                      : Number(val) || 0;
                                                  const manq = deduireManquant(
                                                    attendue,
                                                    n,
                                                    st.quantiteSav,
                                                    st.quantiteDetruite,
                                                    isPrestComplet
                                                  );
                                                  setLigneState(ligne.id, {
                                                    quantiteRamassee: n,
                                                    quantiteManquante: manq
                                                  });
                                                }}
                                              />
                                              <ActionIcon
                                                size='xs'
                                                variant='default'
                                                disabled={!canEdit}
                                                onClick={() => {
                                                  const n =
                                                    st.quantiteRamassee + 1;
                                                  const manq = deduireManquant(
                                                    attendue,
                                                    n,
                                                    st.quantiteSav,
                                                    st.quantiteDetruite,
                                                    isPrestComplet
                                                  );
                                                  setLigneState(ligne.id, {
                                                    quantiteRamassee: n,
                                                    quantiteManquante: manq
                                                  });
                                                }}
                                              >
                                                <IconPlus size={10} />
                                              </ActionIcon>
                                            </Group>

                                            <Group gap={4} wrap='nowrap'>
                                              <Text
                                                size='xs'
                                                c='orange'
                                                fw={500}
                                              >
                                                SAV:
                                              </Text>
                                              <ActionIcon
                                                size='xs'
                                                variant='default'
                                                disabled={
                                                  !canEdit ||
                                                  st.quantiteSav <= 0
                                                }
                                                onClick={() => {
                                                  const n = Math.max(
                                                    0,
                                                    st.quantiteSav - 1
                                                  );
                                                  const manq = deduireManquant(
                                                    attendue,
                                                    st.quantiteRamassee,
                                                    n,
                                                    st.quantiteDetruite,
                                                    isPrestComplet
                                                  );
                                                  setLigneState(ligne.id, {
                                                    quantiteSav: n,
                                                    quantiteManquante: manq
                                                  });
                                                }}
                                              >
                                                <IconMinus size={10} />
                                              </ActionIcon>
                                              <NumberInput
                                                size='xs'
                                                w={50}
                                                min={0}
                                                disabled={!canEdit}
                                                value={st.quantiteSav}
                                                onChange={(val) => {
                                                  const n =
                                                    typeof val === 'number'
                                                      ? val
                                                      : Number(val) || 0;
                                                  const manq = deduireManquant(
                                                    attendue,
                                                    st.quantiteRamassee,
                                                    n,
                                                    st.quantiteDetruite,
                                                    isPrestComplet
                                                  );
                                                  setLigneState(ligne.id, {
                                                    quantiteSav: n,
                                                    quantiteManquante: manq
                                                  });
                                                }}
                                              />
                                              <ActionIcon
                                                size='xs'
                                                variant='default'
                                                disabled={!canEdit}
                                                onClick={() => {
                                                  const n = st.quantiteSav + 1;
                                                  const manq = deduireManquant(
                                                    attendue,
                                                    st.quantiteRamassee,
                                                    n,
                                                    st.quantiteDetruite,
                                                    isPrestComplet
                                                  );
                                                  setLigneState(ligne.id, {
                                                    quantiteSav: n,
                                                    quantiteManquante: manq
                                                  });
                                                }}
                                              >
                                                <IconPlus size={10} />
                                              </ActionIcon>
                                            </Group>

                                            <Group gap={4} wrap='nowrap'>
                                              <Text size='xs' c='red' fw={500}>
                                                Détruit:
                                              </Text>
                                              <ActionIcon
                                                size='xs'
                                                variant='default'
                                                disabled={
                                                  !canEdit ||
                                                  st.quantiteDetruite <= 0
                                                }
                                                onClick={() => {
                                                  const n = Math.max(
                                                    0,
                                                    st.quantiteDetruite - 1
                                                  );
                                                  const manq = deduireManquant(
                                                    attendue,
                                                    st.quantiteRamassee,
                                                    st.quantiteSav,
                                                    n,
                                                    isPrestComplet
                                                  );
                                                  setLigneState(ligne.id, {
                                                    quantiteDetruite: n,
                                                    quantiteManquante: manq
                                                  });
                                                }}
                                              >
                                                <IconMinus size={10} />
                                              </ActionIcon>
                                              <NumberInput
                                                size='xs'
                                                w={50}
                                                min={0}
                                                disabled={!canEdit}
                                                value={st.quantiteDetruite}
                                                onChange={(val) => {
                                                  const n =
                                                    typeof val === 'number'
                                                      ? val
                                                      : Number(val) || 0;
                                                  const manq = deduireManquant(
                                                    attendue,
                                                    st.quantiteRamassee,
                                                    st.quantiteSav,
                                                    n,
                                                    isPrestComplet
                                                  );
                                                  setLigneState(ligne.id, {
                                                    quantiteDetruite: n,
                                                    quantiteManquante: manq
                                                  });
                                                }}
                                              />
                                              <ActionIcon
                                                size='xs'
                                                variant='default'
                                                disabled={!canEdit}
                                                onClick={() => {
                                                  const n =
                                                    st.quantiteDetruite + 1;
                                                  const manq = deduireManquant(
                                                    attendue,
                                                    st.quantiteRamassee,
                                                    st.quantiteSav,
                                                    n,
                                                    isPrestComplet
                                                  );
                                                  setLigneState(ligne.id, {
                                                    quantiteDetruite: n,
                                                    quantiteManquante: manq
                                                  });
                                                }}
                                              >
                                                <IconPlus size={10} />
                                              </ActionIcon>
                                            </Group>

                                            <Group gap={4} wrap='nowrap'>
                                              <Text size='xs' c='gray' fw={500}>
                                                Manquant:
                                              </Text>
                                              <NumberInput
                                                size='xs'
                                                w={50}
                                                min={0}
                                                disabled={!canEdit}
                                                value={st.quantiteManquante}
                                                onChange={(val) => {
                                                  const n =
                                                    typeof val === 'number'
                                                      ? val
                                                      : Number(val) || 0;
                                                  setLigneState(ligne.id, {
                                                    quantiteManquante: n
                                                  });
                                                }}
                                              />
                                            </Group>

                                            <Switch
                                              size='xs'
                                              label='Facturer'
                                              disabled={!canEdit}
                                              checked={st.facturerClient}
                                              onChange={(e) =>
                                                setLigneState(ligne.id, {
                                                  facturerClient:
                                                    e.currentTarget.checked
                                                })
                                              }
                                            />

                                            <Tooltip
                                              label={
                                                st.photoUrl
                                                  ? 'Photo jointe'
                                                  : 'Prendre ou joindre une photo'
                                              }
                                            >
                                              <ActionIcon
                                                size='sm'
                                                variant={
                                                  st.photoUrl
                                                    ? 'filled'
                                                    : 'light'
                                                }
                                                color={
                                                  st.photoUrl ? 'blue' : 'gray'
                                                }
                                                onClick={() =>
                                                  setPhotoModal({
                                                    ligneId: ligne.id,
                                                    partNom: ligne.part_nom
                                                  })
                                                }
                                              >
                                                <IconCamera size={14} />
                                              </ActionIcon>
                                            </Tooltip>

                                            <Pastille
                                              lettre='R'
                                              etat={ligneEtat}
                                              libelle='Ramassage'
                                            />
                                          </Group>
                                        </Group>
                                      </Ligne>
                                    );
                                  })}
                              </Box>
                            );
                          })}
                      </Box>
                    );
                  })}
              </Box>
            );
          })}
        </Stack>
      )}

      <Modal
        opened={photoModal !== null}
        onClose={() => setPhotoModal(null)}
        title={`Photo du retour — ${photoModal?.partNom ?? ''}`}
      >
        {photoModal && (
          <Stack gap='md'>
            {lignesState[photoModal.ligneId]?.photoUrl ? (
              <Box>
                <Image
                  src={lignesState[photoModal.ligneId]?.photoUrl}
                  alt='Preuve de ramassage'
                  radius='md'
                  mah={300}
                  fit='contain'
                />
                <Button
                  mt='xs'
                  color='red'
                  variant='subtle'
                  size='xs'
                  onClick={() =>
                    setLigneState(photoModal.ligneId, { photoUrl: null })
                  }
                >
                  Supprimer la photo
                </Button>
              </Box>
            ) : (
              <FileInput
                label='Joindre une photo'
                placeholder='Sélectionner un fichier image'
                accept='image/*'
                leftSection={<IconUpload size={14} />}
                onChange={(file) => {
                  if (file) {
                    const reader = new FileReader();
                    reader.onload = () => {
                      setLigneState(photoModal.ligneId, {
                        photoUrl: reader.result as string
                      });
                    };
                    reader.readAsDataURL(file);
                  }
                }}
              />
            )}
            <Group justify='flex-end'>
              <Button size='xs' onClick={() => setPhotoModal(null)}>
                Fermer
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </Stack>
  );
}
