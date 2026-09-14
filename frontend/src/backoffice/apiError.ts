/**
 * Mise en forme des erreurs DRF pour les écrans back-office.
 *
 * Les vues renvoient soit `{"detail": "…"}`, soit `{"champ": ["…", "…"]}`.
 * Afficher le `JSON.stringify` brut donnait des messages du genre
 * `{"password":["Ce mot de passe est trop courant."]}` à l'utilisateur.
 */

type ApiErrorLike = {
	response?: { data?: Record<string, unknown> | string };
};

function flatten(value: unknown): string[] {
	if (typeof value === "string") {
		return [value];
	}

	if (Array.isArray(value)) {
		return value.flatMap(flatten);
	}

	if (value && typeof value === "object") {
		return Object.values(value).flatMap(flatten);
	}

	return [];
}

export function apiErrorMessage(error: unknown, fallback: string): string {
	const data = (error as ApiErrorLike)?.response?.data;

	if (typeof data === "string") {
		return data || fallback;
	}

	if (!data) {
		return fallback;
	}

	const messages = flatten(data);

	return messages.length > 0 ? messages.join(" ") : fallback;
}
