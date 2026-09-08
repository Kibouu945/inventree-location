// Cadre commun à tous les widgets de dashboard du plugin.
//
// InvenTree enferme chaque widget dans une boîte de hauteur fixe — 560 px de
// contenu pour un widget `height: 8` — posée en `overflow-y: hidden`. Tout ce
// qui dépasse est purement coupé : la page ne défile pas plus loin et il
// n'existe aucun moyen d'atteindre le bas d'une liste. Chaque écran défile donc
// à l'intérieur de sa propre boîte.
//
// Un simple `height: 100%` ne suffit pas : InvenTree intercale un `Stack`
// Mantine sans hauteur définie entre sa boîte et le contenu du plugin, et un
// pourcentage posé sur un parent en hauteur automatique retombe sur la hauteur
// du contenu. On mesure donc la place réellement disponible dans la boîte, et
// on la suit au redimensionnement du widget.
import { type ReactNode, useEffect, useRef, useState } from 'react';
import { LocaleFrame } from './LocaleFrame';

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
  const [hauteur, setHauteur] = useState<number | null>(null);

  useEffect(() => {
    const element = ref.current;

    if (!element) {
      return;
    }

    // La boîte du widget : le premier ancêtre qui coupe ce qui dépasse. Hors
    // dashboard (panneau de fiche article), il n'y en a pas — on ne touche
    // alors à rien.
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

    return () => observateur.disconnect();
  }, []);

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
