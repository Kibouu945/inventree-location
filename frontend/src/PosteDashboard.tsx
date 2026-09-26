// Widget de dashboard : l'écran de travail du rôle.
import {
  checkPluginVersion,
  type InvenTreePluginContext
} from '@inventreedb/ui';
import { Alert } from '@mantine/core';

import { LocaleFrame } from './LocaleFrame';
import { posteDeLUtilisateur } from './postes/definitions';
import { Poste } from './postes/Poste';

function PosteDashboard({ context }: { context: InvenTreePluginContext }) {
  const poste = posteDeLUtilisateur(context);

  if (!poste) {
    return (
      <Alert color='gray' title='Aucun poste'>
        Aucun rôle métier n’est attribué à ce compte : demandez à un
        administrateur de vous en attribuer un.
      </Alert>
    );
  }

  return (
    <Poste
      poste={poste.cle}
      onglets={poste.definition.onglets.map((onglet) => ({
        value: onglet.value,
        label: onglet.label,
        icon: onglet.icon,
        render: () => onglet.render(context)
      }))}
    />
  );
}

export function renderInvenTreeLocationPoste(context: InvenTreePluginContext) {
  checkPluginVersion(context);

  return (
    <LocaleFrame locale={context.locale}>
      <PosteDashboard context={context} />
    </LocaleFrame>
  );
}
