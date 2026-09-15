/**
 * Impression d'un bon affiché dans une modale Mantine.
 *
 * Deux pièges, tous deux vérifiés au navigateur :
 *
 * 1. `window.print()` imprime la page entière. Le dashboard monte plusieurs
 *    widgets : sans masquer le reste, le bon part noyé au milieu.
 * 2. Masquer le reste ne suffit pas. `.mantine-Modal-content` défile
 *    (`overflow: auto`, `max-height`) et `.mantine-Modal-inner` est en
 *    `position: fixed` : la modale ne laissait donc imprimer que sa partie
 *    visible à l'écran — le bon de ramassage sortait coupé après sa première
 *    ligne de tableau. Il faut remettre ces conteneurs à plat.
 *
 * Usage : envelopper le contenu à imprimer dans `className={PRINT_AREA}`, les
 * boutons dans `className={PRINT_HIDE}`, et monter `<PrintableModalStyles />`
 * dans la modale.
 */

export const PRINT_AREA = 'inventree-location-print-area';
export const PRINT_HIDE = 'inventree-location-print-hide';

const CSS = `
@media print {
  body * { visibility: hidden; }

  /* visibility:hidden masque sans libérer la place : le dashboard laissait
     quatre pages blanches derrière le bon. La modale est montée dans un portail
     frère de #root (le point de montage de l'interface InvenTree), qu'on peut
     donc retirer entièrement du flux d'impression. */
  #root { display: none !important; }

  .${PRINT_AREA}, .${PRINT_AREA} * { visibility: visible; }

  .mantine-Modal-root,
  .mantine-Modal-inner,
  .mantine-Modal-content,
  .mantine-Modal-body {
    position: static !important;
    overflow: visible !important;
    max-height: none !important;
    height: auto !important;
    /* Un ancêtre transformé sert de bloc conteneur à un descendant absolu :
       le bon repartait alors à l'ordonnée de la modale dans la page, laissant
       une première page vide. */
    transform: none !important;
    filter: none !important;
  }

  .${PRINT_AREA} {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
  }

  .${PRINT_HIDE} { display: none !important; }
}
`;

export function PrintableModalStyles() {
  return <style>{CSS}</style>;
}
