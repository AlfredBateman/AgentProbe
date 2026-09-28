/** Client-side checks mirroring the server's own rules (auth.py: Registration/Login), so a
 * bad value never round-trips before the user sees why. The server is still the source of
 * truth: its 422 details win if these ever disagree. */

export function emailError(email: string): string | null {
  if (!email.trim()) return "Email is required.";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return "Enter a valid email address.";
  return null;
}

export function loginPasswordError(password: string): string | null {
  return password ? null : "Password is required.";
}

/** Registration only (auth.py: Field(min_length=12, max_length=128)); NIST 800-63B length over composition. */
export function newPasswordError(password: string): string | null {
  if (password.length < 12) return "Use at least 12 characters.";
  if (password.length > 128) return "Use at most 128 characters.";
  return null;
}

export function requiredError(value: string, label: string): string | null {
  return value.trim() ? null : `${label} is required.`;
}
