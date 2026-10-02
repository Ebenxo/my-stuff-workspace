/**
 * True only in the browser preview build (`vite build --mode browser-preview`). Written as a direct
 * `import.meta.env.…` read so Vite replaces it at build time and the normal build drops the preview.
 */
export const IS_PREVIEW = import.meta.env.VITE_NEXUS_PREVIEW === "1";
