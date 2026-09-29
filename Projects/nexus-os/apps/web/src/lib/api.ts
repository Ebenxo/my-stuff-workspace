import { createApi } from "@nexus/shared";
import { getRuntimeConfig } from "./runtime";

export const runtimeConfig = getRuntimeConfig();
export const api = createApi(runtimeConfig);
