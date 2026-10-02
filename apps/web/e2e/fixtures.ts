// A fixed roster of emails, one per spec file that needs to register: the e2e API's
// SIGNUP_ALLOWED_EMAILS lists exactly these (playwright.config.ts), and globalSetup resets the
// whole database before every invocation, so there's no cross-run collision to guard against —
// unlike the old dev-DB setup, no spec needs to clean up its own account any more.
export const E2E_EMAIL = "you@example.com"; // 01/02/03: auth and session mechanics
export const E2E_PASSWORD = "correct horse battery staple e2e"; // fake credential, 12+ chars

// example.com, not the RFC 2606 .test TLD: pydantic's email-validator rejects .test/.invalid/
// .localhost outright as "special-use or reserved", but allows example.com (it's what
// E2E_EMAIL below already uses).
export const MAIN_FLOW_EMAIL = "main-flow@example.com";
export const SSRF_EMAIL = "ssrf@example.com";
export const INVALID_YAML_EMAIL = "invalid-yaml@example.com";
export const VISUAL_EMAIL = "visual@example.com";
export const OVERVIEW_EMAIL = "overview@example.com";
export const AGENTS_SUITES_EMAIL = "agents-suites@example.com";

// playwright.config.ts starts its own demo agents here with FLAKY_RATE=0.5.
export const DEMO_AGENTS_URL = "http://127.0.0.1:9100";
