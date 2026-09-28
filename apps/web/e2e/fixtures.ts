// SIGNUP_ALLOWED_EMAILS only allows one address against the dev DB, so every e2e spec shares
// it and cleans up after itself (see cleanup.ts) rather than registering a fresh address.
export const E2E_EMAIL = "you@example.com";
export const E2E_PASSWORD = "correct horse battery staple e2e"; // fake credential, 12+ chars
// playwright.config.ts starts its own demo agents here with FLAKY_RATE=0.5, so the flaky
// case is flaky in all but a negligible share of runs (the dev instance on :9000 uses 0.2).
export const DEMO_AGENTS_URL = "http://127.0.0.1:9100";
