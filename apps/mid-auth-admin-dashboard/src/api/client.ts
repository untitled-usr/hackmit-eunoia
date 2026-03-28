export type QueryValue = string | number | boolean | undefined | null;

export function apiBase(): string {
  const env = import.meta.env.VITE_MID_AUTH_ADMIN_BASE;
  return typeof env === "string" && env.trim() ? env.replace(/\/$/, "") : "";
}

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const base = apiBase();
  const url = base
    ? new URL(`${base}${normalizedPath}`)
    : new URL(normalizedPath, window.location.origin);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null || v === "") continue;
      url.searchParams.set(k, String(v));
    }
  }
  return base ? url.toString() : `${url.pathname}${url.search}`;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(`HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function readDetail(res: Response): Promise<unknown> {
  const contentType = res.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    try {
      return await res.json();
    } catch {
      return await res.text();
    }
  }
  return await res.text();
}

export function toErrorText(error: unknown): string {
  if (error instanceof ApiError) {
    const d = error.detail as { detail?: unknown } | unknown;
    if (typeof d === "string") return `HTTP ${error.status}: ${d}`;
    if (d && typeof d === "object" && "detail" in (d as Record<string, unknown>)) {
      const detailValue = (d as { detail?: unknown }).detail;
      return `HTTP ${error.status}: ${typeof detailValue === "string" ? detailValue : JSON.stringify(detailValue)}`;
    }
    return `HTTP ${error.status}: ${JSON.stringify(d)}`;
  }
  return error instanceof Error ? error.message : String(error);
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit & { query?: Record<string, QueryValue> } = {}
): Promise<T> {
  const { query, ...request } = init;
  const res = await fetch(buildUrl(path, query), {
    ...request,
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(request.headers ?? {})
    }
  });

  if (res.status === 204) {
    return null as T;
  }
  if (!res.ok) {
    throw new ApiError(res.status, await readDetail(res));
  }
  const text = await res.text();
  if (!text.trim()) return null as T;
  return JSON.parse(text) as T;
}
