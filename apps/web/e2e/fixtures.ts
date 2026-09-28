// SIGNUP_ALLOWED_EMAILS only allows one address against the dev DB, so every e2e spec shares
// it and cleans up after itself (see cleanup.ts) rather than registering a fresh address.
export const E2E_EMAIL = "you@example.com";
export const E2E_PASSWORD = "correct horse battery staple e2e"; // fake credential, 12+ chars
