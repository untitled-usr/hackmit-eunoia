import { clearActingUid } from "@/auth-state";
import { ROUTES } from "@/router/routes";

const PUBLIC_ROUTES = [ROUTES.AUTH, ROUTES.EXPLORE, "/u/", "/memos/"] as const;

function isPublicRoute(path: string): boolean {
  return PUBLIC_ROUTES.some((route) => path.startsWith(route));
}

export function redirectOnAuthFailure(forceRedirect = false): void {
  const currentPath = window.location.pathname;

  if (currentPath.startsWith(ROUTES.AUTH)) {
    return;
  }

  if (!forceRedirect && isPublicRoute(currentPath)) {
    return;
  }

  clearActingUid();
  window.location.replace(ROUTES.AUTH);
}
