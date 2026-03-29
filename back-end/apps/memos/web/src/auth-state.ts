// Acting user is selected via numeric user id stored in localStorage.
// It is sent on each API request as the X-Acting-Uid header.

const ACTING_UID_KEY = "memos_acting_uid";

let actingUidCache: string | null | undefined = undefined;

function readActingUidFromStorage(): string | null {
  try {
    const v = localStorage.getItem(ACTING_UID_KEY);
    if (!v || !v.trim()) {
      return null;
    }
    return v.trim();
  } catch (e) {
    console.warn("Failed to read acting uid from localStorage:", e);
    return null;
  }
}

/** Returns the stored acting user id (numeric string), or null if unset. */
export function getActingUid(): string | null {
  if (actingUidCache === undefined) {
    actingUidCache = readActingUidFromStorage();
  }
  return actingUidCache;
}

/** Persist acting user id (numeric string). Pass null to clear. */
export function setActingUid(uid: string | null): void {
  if (uid && !uid.trim()) {
    uid = null;
  }
  actingUidCache = uid?.trim() ?? null;

  try {
    if (actingUidCache) {
      localStorage.setItem(ACTING_UID_KEY, actingUidCache);
    } else {
      localStorage.removeItem(ACTING_UID_KEY);
    }
  } catch (e) {
    console.warn("Failed to write acting uid to localStorage:", e);
  }
}

export function hasStoredActingUid(): boolean {
  return getActingUid() != null;
}

export function clearActingUid(): void {
  setActingUid(null);
}
