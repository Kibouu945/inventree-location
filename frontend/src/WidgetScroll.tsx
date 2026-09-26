// Cadre commun aux widgets de dashboard du plugin, et la mesure de hauteur
// qu'il utilise — réutilisée par la coque des postes.
import {
  type ReactNode,
  type RefObject,
  useEffect,
  useRef,
  useState
} from 'react';
import { LocaleFrame } from './LocaleFrame';

/**
 * Hauteur disponible pour `element` dans la boîte du widget. `null` hors
 * dashboard : aucune boîte ne coupe, rien à borner.
 */
export function useHauteurDisponible(
  ref: RefObject<HTMLElement | null>
): number | null {
  const [hauteur, setHauteur] = useState<number | null>(null);

  useEffect(() => {
    const element = ref.current;

    if (!element) {
      return;
    }

    // Le premier ancêtre qui coupe ce qui dépasse.
    let boite = element.parentElement;

    while (boite && getComputedStyle(boite).overflowY !== 'hidden') {
      boite = boite.parentElement;
    }

    if (!boite) {
      return;
    }

    const cadre = boite;

    function mesurer() {
      const decalage =
        (element?.getBoundingClientRect().top ?? 0) -
        cadre.getBoundingClientRect().top;
      const disponible = cadre.clientHeight - decalage;

      setHauteur(disponible > 0 ? disponible : null);
    }

    mesurer();

    const observateur = new ResizeObserver(mesurer);
    observateur.observe(cadre);
    window.addEventListener('resize', mesurer);

    return () => {
      observateur.disconnect();
      window.removeEventListener('resize', mesurer);
    };
  }, [ref]);

  return hauteur;
}

export function WidgetScroll({
  children,
  locale
}: {
  children: ReactNode;
  /** `context.locale` : voir `LocaleFrame`, qui s'en sert pour déclarer la
   *  langue de la page et celle des calendriers. */
  locale?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const hauteur = useHauteurDisponible(ref);

  return (
    <div
      ref={ref}
      style={{
        maxHeight: hauteur ?? undefined,
        overflowY: 'auto',
        overflowX: 'auto',
        // La barre de défilement ne recouvre pas le bord des tableaux.
        paddingRight: 4
      }}
    >
      <LocaleFrame locale={locale}>{children}</LocaleFrame>
    </div>
  );
}
