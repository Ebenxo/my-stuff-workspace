import { createApi } from "@nexus/shared";
import { getRuntimeConfig } from "./runtime";

export const runtimeConfig = getRuntimeConfig();
// Look `fetch` up on every call rather than capturing it now, so the browser preview (which answers
// the API in the page) can take over requests after this module has loaded.
export const api = createApi(runtimeConfig, (input, init) => globalThis.fetch(input, init));
