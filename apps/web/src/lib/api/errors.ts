/** The API's one error shape (apps/api/src/agentprobe_api/errors.py): {error: {code, message, request_id, details?}}. */
type ApiErrorBody = {
  error?: {
    code?: string;
    message?: string;
    request_id?: string;
    details?: { loc: (string | number)[]; msg: string; type: string }[];
  };
};

/** A message safe to show the user: the server's own text, or a generic fallback. */
export function apiErrorMessage(error: unknown): string {
  return (error as ApiErrorBody | undefined)?.error?.message ?? "Something went wrong. Try again.";
}

/** Field name -> message, from a 422's `details` (FastAPI's loc is e.g. ["body", "email"]). */
export function apiFieldErrors(error: unknown): Record<string, string> {
  const details = (error as ApiErrorBody | undefined)?.error?.details ?? [];
  const out: Record<string, string> = {};
  for (const d of details) {
    const field = d.loc.at(-1);
    if (typeof field === "string") out[field] = d.msg;
  }
  return out;
}
