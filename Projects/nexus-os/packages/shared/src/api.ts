import createClient from "openapi-fetch";
import type { paths } from "@nexus/schemas";

export interface ApiConfig {
  /** Empty string means same-origin (the Vite dev proxy). */
  baseUrl: string;
  token?: string | undefined;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }
}

export function authHeaders(token: string | undefined): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function createApi(config: ApiConfig, fetchImpl?: typeof fetch) {
  return createClient<paths>({
    baseUrl: config.baseUrl,
    headers: authHeaders(config.token),
    ...(fetchImpl ? { fetch: fetchImpl as never } : {}),
  });
}

export type Api = ReturnType<typeof createApi>;

interface Envelope {
  error?: { code?: string; message?: string; details?: unknown };
}

/** Turn an openapi-fetch result into data, or throw a typed ApiError with the server's envelope. */
export async function unwrap<T>(
  promise: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  let result: { data?: T; error?: unknown; response: Response };
  try {
    result = await promise;
  } catch (cause) {
    throw new ApiError(
      cause instanceof Error ? cause.message : "Network error",
      0,
      "network_error",
    );
  }
  if (result.error !== undefined || !result.response.ok) {
    const env = (result.error ?? {}) as Envelope;
    throw new ApiError(
      env.error?.message ?? `Request failed (${result.response.status})`,
      result.response.status,
      env.error?.code ?? "http_error",
      env.error?.details,
    );
  }
  return result.data as T;
}
