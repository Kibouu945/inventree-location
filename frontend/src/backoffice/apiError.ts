/** Mise en forme des erreurs DRF pour les écrans back-office. */

type ApiErrorLike = {
  response?: { data?: Record<string, unknown> | string };
};

function flatten(value: unknown): string[] {
  if (typeof value === 'string') {
    return [value];
  }

  if (Array.isArray(value)) {
    return value.flatMap(flatten);
  }

  if (value && typeof value === 'object') {
    return Object.values(value).flatMap(flatten);
  }

  return [];
}

export function apiErrorMessage(error: unknown, fallback: string): string {
  const data = (error as ApiErrorLike)?.response?.data;

  if (typeof data === 'string') {
    return data || fallback;
  }

  if (!data) {
    return fallback;
  }

  const messages = flatten(data);

  return messages.length > 0 ? messages.join(' ') : fallback;
}
