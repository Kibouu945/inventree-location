// Coque commune aux postes de travail : navigation verticale + contenu.
import { ActionIcon, Group, Loader, Paper, Tabs, Tooltip } from '@mantine/core';
import {
  IconLayoutSidebarLeftCollapse,
  IconLayoutSidebarRightCollapse
} from '@tabler/icons-react';
import {
  type ReactNode,
  Suspense,
  useEffect,
  useMemo,
  useRef,
  useState
} from 'react';
import { ownsKeys, syncOwnedParams } from '../urlState';
import { useHauteurDisponible } from '../WidgetScroll';

export interface OngletPoste {
  /** Identifiant stable, repris dans l'URL. */
  value: string;
  label: string;
  icon?: ReactNode;
  /** Appelé seulement quand l'entrée est active. */
  render: () => ReactNode;
}

/** Clé d'URL, préfixée : la query string est partagée (cf. `urlState`). */
function cleOnglet(poste: string): string {
  return `${poste}_ecran`;
}

export function Poste({
  poste,
  onglets
}: {
  /** Identifiant du poste, ex. `livreur`. Sert de préfixe d'URL. */
  poste: string;
  onglets: OngletPoste[];
}) {
  const cle = cleOnglet(poste);
  const defaut = onglets[0]?.value ?? '';
  const [deplie, setDeplie] = useState(true);
  const cadre = useRef<HTMLDivElement>(null);
  const hauteur = useHauteurDisponible(cadre);

  const [actif, setActif] = useState<string>(() => {
    if (typeof window === 'undefined') {
      return defaut;
    }

    const demande = new URLSearchParams(window.location.search).get(cle);

    // Entrée inconnue (lien périmé) : on retombe sur la première.
    return onglets.some((onglet) => onglet.value === demande)
      ? (demande as string)
      : defaut;
  });

  useEffect(() => {
    const own = new URLSearchParams();

    // La première entrée est le défaut : ne pas polluer l'URL.
    if (actif && actif !== defaut) {
      own.set(cle, actif);
    }

    syncOwnedParams(ownsKeys([cle]), own);
  }, [actif, cle, defaut]);

  const courant = useMemo(
    () => onglets.find((onglet) => onglet.value === actif) ?? onglets[0],
    [onglets, actif]
  );

  return (
    <Paper
      ref={cadre}
      p='sm'
      radius='xs'
      shadow='xs'
      aria-label={`poste-${poste}`}
      style={{
        height: hauteur ?? undefined,
        display: 'flex',
        overflow: 'hidden'
      }}
    >
      <Tabs
        value={actif}
        onChange={(valeur) => setActif(valeur ?? defaut)}
        orientation='vertical'
        keepMounted={false}
        aria-label={`poste-navigation-${poste}`}
        style={{ flex: 1, minHeight: 0 }}
      >
        <Tabs.List
          justify='left'
          style={{
            minWidth: deplie ? 190 : undefined,
            flex: '0 0 auto',
            alignSelf: 'stretch',
            overflowY: 'auto'
          }}
        >
          <Group justify={deplie ? 'right' : 'center'} p={4} w='100%'>
            <Tooltip
              label={deplie ? 'Réduire le menu' : 'Déplier le menu'}
              position='right'
            >
              <ActionIcon
                variant='subtle'
                size='sm'
                onClick={() => setDeplie((valeur) => !valeur)}
                aria-label='replier-le-menu-du-poste'
              >
                {deplie ? (
                  <IconLayoutSidebarLeftCollapse size={18} />
                ) : (
                  <IconLayoutSidebarRightCollapse size={18} />
                )}
              </ActionIcon>
            </Tooltip>
          </Group>
          {onglets.map((onglet) => (
            <Tooltip
              key={onglet.value}
              label={onglet.label}
              disabled={deplie}
              position='right'
            >
              <Tabs.Tab
                p='xs'
                w='100%'
                value={onglet.value}
                leftSection={onglet.icon}
                style={{
                  cursor: 'pointer',
                  background:
                    onglet.value === actif
                      ? 'var(--mantine-primary-color-light)'
                      : undefined
                }}
              >
                <Group justify='left' gap='xs' wrap='nowrap'>
                  {deplie && onglet.label}
                </Group>
              </Tabs.Tab>
            </Tooltip>
          ))}
        </Tabs.List>
        <Tabs.Panel
          value={actif}
          pl='md'
          style={{
            flex: 1,
            minWidth: 0,
            minHeight: 0,
            overflowY: 'auto',
            overflowX: 'auto',
            // La barre de défilement ne recouvre pas le bord des tableaux.
            paddingRight: 4
          }}
        >
          {/* Chargement paresseux : cf. `definitions.tsx`. */}
          <Suspense fallback={<Loader size='sm' />}>
            {courant?.render()}
          </Suspense>
        </Tabs.Panel>
      </Tabs>
    </Paper>
  );
}
