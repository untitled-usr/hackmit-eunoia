import { browser } from '$app/environment';
import { env } from '$env/dynamic/public';

/** localStorage key for the internal user id sent as ``X-Acting-Uid`` */
export const ACTING_USER_STORAGE_KEY = 'actingUid';

export const DEFAULT_ACTING_HEADER = 'X-Acting-Uid';

export function getActingUserId(): string {
	if (!browser) return '';
	const fromLs = localStorage.getItem(ACTING_USER_STORAGE_KEY);
	const fromEnv = (env as { PUBLIC_ACTING_USER_ID?: string }).PUBLIC_ACTING_USER_ID ?? '';
	return (fromLs || fromEnv || '').trim();
}

export function setActingUserId(id: string) {
	if (!browser) return;
	const v = id.trim();
	if (v) localStorage.setItem(ACTING_USER_STORAGE_KEY, v);
	else localStorage.removeItem(ACTING_USER_STORAGE_KEY);
}

export function clearActingUserId() {
	if (!browser) return;
	localStorage.removeItem(ACTING_USER_STORAGE_KEY);
}

let fetchPatched = false;

/** Paths proxied to the Open WebUI backend that still require ``X-Acting-Uid`` (not only ``/api``). */
function shouldAttachActingUidToUrl(urlStr: string): boolean {
	try {
		const u = new URL(urlStr, typeof window !== 'undefined' ? window.location.origin : 'http://localhost');
		const p = u.pathname;
		return p.startsWith('/api') || p.startsWith('/ollama') || p.startsWith('/openai');
	} catch {
		return (
			urlStr.includes('/api/') ||
			urlStr.includes('/ollama/') ||
			urlStr.includes('/openai/')
		);
	}
}

/**
 * Patch ``window.fetch`` so backend requests include the acting-user header.
 * Covers ``/api``, ``/ollama``, and ``/openai`` (admin connection settings use the latter two).
 * Call once from the root layout on the client.
 */
export function installActingUidFetch(): void {
	if (!browser || fetchPatched) return;
	fetchPatched = true;

	const hdrName =
		(env as { PUBLIC_ACTING_USER_ID_HEADER?: string }).PUBLIC_ACTING_USER_ID_HEADER ||
		DEFAULT_ACTING_HEADER;
	const orig = window.fetch.bind(window);

	window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
		let url = '';
		if (typeof input === 'string') url = input;
		else if (input instanceof URL) url = input.href;
		else url = input.url;

		const uid = getActingUserId();
		if (!uid || !shouldAttachActingUidToUrl(url)) {
			return orig(input, init);
		}

		const headers = new Headers(init?.headers ?? {});
		if (!headers.has(hdrName)) {
			headers.set(hdrName, uid);
		}
		return orig(input, { ...init, headers });
	};
}
