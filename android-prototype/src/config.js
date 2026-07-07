export const API_URL = import.meta.env.VITE_API_URL || "https://pd.brittoo.xyz";
export const TAU = 0.9;
export const CONFIDENCE_THRESHOLD = 0.7;
export const GRAB_COOLDOWN = 10000;
export const DROP_COOLDOWN = 10000;
export const USER_ID = "id1";
export const RECEIVER_ID = "id2";

// Bake a mode in at build time to produce a single-mode APK for the battery
// A/B (e.g. VITE_FORCED_MODE=always npm run apk); otherwise the app shows a
// mode picker at launch.
export const FORCED_MODE = import.meta.env.VITE_FORCED_MODE || null;
