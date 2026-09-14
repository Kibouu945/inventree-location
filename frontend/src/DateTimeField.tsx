// Champ date/heure commun à tous les formulaires du plugin.
//
// Recette Tassin du 07/09/2026, remarques 13 et 14. `DateTimePicker` était
// importé directement aux huit endroits où on saisit une date, sans jamais une
// seule prop de réglage : tout retombait sur les défauts de la bibliothèque, et
// il n'existait aucun endroit pour corriger une bonne fois.
//
// Ce que le passage par ici apporte :
//
//   `defaultTimeValue`  8h00 plutôt que minuit. Une prestation qui commence le
//                       matin ne se saisit pas à minuit, et le client le
//                       demandait explicitement.
//   `popoverProps`      le calendrier est ouvert dans un portail attaché au
//                       `body`, donc hors du `translate="no"` de `LocaleFrame` :
//                       l'attribut est reposé sur le portail, sinon la
//                       traduction automatique reprend la main sur lui seul.
//
// La hauteur constante du calendrier, elle, se règle par `consistentWeeks` dans
// `LocaleFrame` : c'est un réglage de `DatesProvider`, il vaut donc pour tous
// les calendriers d'un coup, y compris les `DatePickerInput` de filtres.
import { DateTimePicker, type DateTimePickerProps } from "@mantine/dates";

// Heure par défaut quand l'utilisateur choisit un jour au calendrier. Le CDC
// raisonne à la journée entière ; l'heure ne sert qu'à la logistique
// livraison / ramassage, et une journée de montage commence le matin.
export const HEURE_PAR_DEFAUT = "08:00";

export function DateTimeField({
	defaultTimeValue = HEURE_PAR_DEFAUT,
	popoverProps,
	...props
}: DateTimePickerProps) {
	return (
		<DateTimePicker
			defaultTimeValue={defaultTimeValue}
			popoverProps={{
				portalProps: { translate: "no" },
				...popoverProps,
			}}
			{...props}
		/>
	);
}
