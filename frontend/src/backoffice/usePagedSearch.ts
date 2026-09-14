import { useDebouncedValue } from "@mantine/hooks";
import { useState } from "react";

/** Recherche débouncée et pagination, partagées par les listes back-office. */
export function usePagedSearch() {
	const [search, setSearch] = useState("");
	const [debouncedSearch] = useDebouncedValue(search, 300);
	const [page, setPage] = useState(1);

	function updateSearch(value: string) {
		// Changer la recherche renvoie en première page : rester sur la page 3
		// d'un résultat qui n'en compte plus qu'une afficherait une liste vide.
		setSearch(value);
		setPage(1);
	}

	return { search, debouncedSearch, page, setPage, updateSearch };
}
