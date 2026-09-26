// Déclare la langue du sous-arbre du plugin, une fois pour tous les écrans.
import { DatesProvider } from '@mantine/dates';
import { type ReactNode, useEffect } from 'react';
import 'dayjs/locale/fr';

/** Langue posée sur les profils par `dashboard_provisioning.apply_language`. */
const LANGUE_PAR_DEFAUT = 'fr';

/** Langue courte (« fr » depuis « fr-FR »), telle que l'attend dayjs. */
function langueCourte(locale: string | undefined): string {
  return (locale || LANGUE_PAR_DEFAUT).toLowerCase().split('-')[0];
}

export function LocaleFrame({
  children,
  locale
}: {
  children: ReactNode;
  /** `context.locale` du point d'entrée. Absent, on retombe sur le défaut
   *  provisionné côté serveur. */
  locale?: string;
}) {
  const langue = langueCourte(locale);

  // `<html lang>` est figé à « en » dans le gabarit d'InvenTree, et son
  // interface React ne le remet pas à jour quand la langue de l'utilisateur
  useEffect(() => {
    const racine = document.documentElement;

    if (racine.lang !== langue) {
      racine.lang = langue;
    }
  }, [langue]);

  return (
    <div lang={langue} translate='no' className='notranslate'>
      <DatesProvider
        settings={{
          locale: langue,
          // Lundi, et samedi/dimanche en week-end : les défauts de Mantine
          // conviennent déjà, on les fixe pour ne pas dépendre d'eux.
          firstDayOfWeek: 1,
          weekendDays: [0, 6],
          consistentWeeks: true
        }}
      >
        {children}
      </DatesProvider>
    </div>
  );
}
