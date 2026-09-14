// Déclare la langue du sous-arbre du plugin, une fois pour tous les écrans.
//
// Recette Tassin du 07/09/2026, remarques 3, 9, 12 et 13. Rien ne déclarait la
// langue de cette application : ni côté serveur (`INVENTREE_LANGUAGE` était
// absent du compose, `LANGUAGE_CODE` retombait donc sur `en-us`), ni côté
// navigateur, ni côté `@mantine/dates`. Chrome concluait « page anglaise » et
// traduisait tout : nos libellés pourtant écrits en français — le code dit
// « Annuler » et « Enregistrer », le client lisait « Annuleur » et
// « Économiser » — et jusqu'aux données saisies, « Zone émargement » s'affichant
// « Zone d'émarrage » dans une liste. Aucune correction d'ergonomie n'est
// visible tant que la page est réécrite par-dessus.
//
// Trois verrous, parce qu'ils ne couvrent pas les mêmes trous :
//
//   `lang="fr"`      dit au détecteur de langue de ne pas deviner ;
//   `translate="no"` lui interdit la page même s'il devine quand même ;
//   `DatesProvider`  donne enfin le français aux calendriers, dont les en-têtes
//                    partaient en anglais (`Mo Tu We Th…`) et revenaient
//                    traduits en « Nous » / « Ème ».
//
// `consistentWeeks` est ici et pas ailleurs : c'est la cause du calendrier qui
// « bouge tout le temps d'emplacement » d'un mois à l'autre. Un mois s'affiche
// sur 5 ou 6 semaines, la hauteur du calendrier oscille d'une quarantaine de
// pixels, et le `Popover` de Mantine — `flip` + `shift` + `autoUpdate` de
// floating-ui — se réancre à chaque changement de taille. En imposant 6
// semaines partout, la hauteur devient constante et il n'y a plus rien à quoi
// se réancrer. C'est aggravé chez nous par `WidgetScroll`, qui enferme le champ
// dans une boîte d'environ 560 px : la place sous le champ manque, `flip` est
// donc presque toujours actif et la bascule devient un saut franc.
//
// À poser à chaque point d'entrée déclaré dans `vite.config.ts` : le plugin n'a
// pas de racine unique, InvenTree monte chaque widget séparément. `WidgetScroll`
// s'en charge pour les dix widgets de dashboard ; les trois entrées restantes
// (`Panel`, `PartDetail`, `Settings`) l'appellent directement.
import { DatesProvider } from "@mantine/dates";
import { type ReactNode, useEffect } from "react";
import "dayjs/locale/fr";

/** Langue posée sur les profils par `dashboard_provisioning.apply_language`. */
const LANGUE_PAR_DEFAUT = "fr";

/** Langue courte (« fr » depuis « fr-FR »), telle que l'attend dayjs. */
function langueCourte(locale: string | undefined): string {
	return (locale || LANGUE_PAR_DEFAUT).toLowerCase().split("-")[0];
}

export function LocaleFrame({
	children,
	locale,
}: {
	children: ReactNode;
	/** `context.locale` du point d'entrée. Absent, on retombe sur le défaut
	 *  provisionné côté serveur. */
	locale?: string;
}) {
	const langue = langueCourte(locale);

	// `<html lang>` est figé à « en » dans le gabarit d'InvenTree, et son
	// interface React ne le remet pas à jour quand la langue de l'utilisateur
	// change. Une page entièrement en français annoncée comme anglaise, c'est
	// exactement ce qui déclenche la traduction automatique de Chrome — donc les
	// « Annuleur », « Actions boursières », et la réécriture des données du
	// client (recette du 07/09/2026, remarques 3, 9 et 12).
	//
	// Le `translate="no"` ci-dessous protège l'arbre du plugin, mais pas les
	// écrans du cœur. On corrige donc l'attribut au niveau du document : ce
	// n'est pas imposer une langue, c'est cesser d'en déclarer une fausse. La
	// valeur vient de l'utilisateur (`context.locale`), jamais d'une supposition.
	useEffect(() => {
		const racine = document.documentElement;

		if (racine.lang !== langue) {
			racine.lang = langue;
		}
	}, [langue]);

	return (
		<div lang={langue} translate="no" className="notranslate">
			<DatesProvider
				settings={{
					locale: langue,
					// Lundi, et samedi/dimanche en week-end : les défauts de Mantine
					// conviennent déjà, on les fixe pour ne pas dépendre d'eux.
					firstDayOfWeek: 1,
					weekendDays: [0, 6],
					consistentWeeks: true,
				}}
			>
				{children}
			</DatesProvider>
		</div>
	);
}
