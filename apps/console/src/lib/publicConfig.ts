/**
 * Public by design (spec 2026-10-09 §10). The hosted console reads ONE row with these: the API's current
 * quick-tunnel URL. A Supabase publishable key is meant for browsers; row-level security gives it nothing but that
 * row (`qcc_public_endpoint_policy` in services/api/schema.sql). Overridable at build time with VITE_SUPABASE_URL
 * and VITE_SUPABASE_PUBLISHABLE_KEY.
 */
export const PUBLIC_SUPABASE_URL = "https://obyexvvwlirnijucyiob.supabase.co";
export const PUBLIC_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_dFP9LtNPbfWxj3KhrM-S-Q_psFtaPnd";
