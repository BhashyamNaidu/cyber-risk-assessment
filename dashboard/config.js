/**
 * Dashboard configuration. This is the ONLY file that should need to
 * change when Phase 1 (Windows smoke test) completes and we switch from
 * mock data to the real backend.
 */
export const USE_MOCK = false; // Phase 1 complete, Desktop Agent frozen — using real backend now
export const BACKEND_URL = "http://localhost:8000";
export const DEFAULT_DEVICE_ID = "device-614f78606300"; // in a real deployment this comes from the URL/session, not a constant
export const HISTORY_LIMIT = 10;
