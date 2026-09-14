// Options de catégories d'articles, pour tous les filtres qui en proposent.
//
// Trois écrans en avaient besoin et s'y prenaient de trois façons : la liste
// des réservations interrogeait `/api/part/category/` (la bonne source), le
// catalogue déduisait ses options des seules lignes de la page courante — donc
// une liste incomplète, qui se réduisait encore en filtrant — et le sélecteur
// d'articles d'une prestation n'en proposait aucune. Recette Tassin du
// 07/09/2026, remarque 4 : « on aurait gagné en ergonomie et efficacité à
// reprendre le type de recherche fait pour le catalogue avec les libellés et
// les catégories, les sous-catégories ».
//
// Le tri est fait ici plutôt que côté serveur : InvenTree renvoie les
// catégories dans l'ordre de l'arbre, et un `Select` se parcourt à l'œil.
import type { InvenTreePluginContext } from "@inventreedb/ui";
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

/** Une catégorie telle qu'InvenTree la renvoie, selon la version : `id` ou
 * `pk`, avec ou sans enveloppe paginée. */
interface CategoryResponseItem {
	id?: number;
	pk?: number;
	name?: string;
	pathstring?: string;
}

export interface CategoryOption {
	value: string;
	label: string;
}

/** Nombre de catégories chargées d'un coup. La base de Jambville en compte
 * quelques dizaines ; la marge évite une pagination pour un filtre. */
const CATEGORY_LIMIT = 250;

export function useCategoryOptions(
	context: InvenTreePluginContext,
): CategoryOption[] {
	const query = useQuery<
		CategoryResponseItem[] | { results: CategoryResponseItem[] }
	>(
		{
			queryKey: ["part-category-options"],
			queryFn: async () => {
				const response = await context.api.get("/api/part/category/", {
					params: { limit: CATEGORY_LIMIT },
				});
				return response.data;
			},
		},
		context.queryClient,
	);

	return useMemo(() => toCategoryOptions(query.data), [query.data]);
}

/** Mise en forme pure, testable sans rendu ni requête. */
export function toCategoryOptions(
	payload:
		| CategoryResponseItem[]
		| { results: CategoryResponseItem[] }
		| undefined,
): CategoryOption[] {
	if (!payload) {
		return [];
	}

	const categories = Array.isArray(payload) ? payload : (payload.results ?? []);

	return categories
		.map((category) => ({
			id: category.id ?? category.pk,
			// `pathstring` (« Mobilier/Tables ») lève l'ambiguïté entre deux
			// sous-catégories de même nom sous deux parents différents.
			name: category.pathstring || category.name || "",
		}))
		.filter(
			(category): category is { id: number; name: string } =>
				Number.isInteger(category.id) && category.name.length > 0,
		)
		.sort((a, b) => a.name.localeCompare(b.name, "fr"))
		.map((category) => ({
			value: String(category.id),
			label: category.name,
		}));
}
