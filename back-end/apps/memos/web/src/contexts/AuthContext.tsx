import { useQueryClient } from "@tanstack/react-query";
import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from "react";
import { clearActingUid, getActingUid } from "@/auth-state";
import { shortcutServiceClient, userServiceClient } from "@/connect";
import { userKeys } from "@/hooks/useUserQueries";
import type { Shortcut } from "@/types/proto/api/v1/shortcut_service_pb";
import type { User, UserSetting_GeneralSetting, UserSetting_WebhooksSetting } from "@/types/proto/api/v1/user_service_pb";

interface AuthState {
  currentUser: User | undefined;
  userGeneralSetting: UserSetting_GeneralSetting | undefined;
  userWebhooksSetting: UserSetting_WebhooksSetting | undefined;
  shortcuts: Shortcut[];
  isInitialized: boolean;
  isLoading: boolean;
}

interface AuthContextValue extends AuthState {
  initialize: () => Promise<void>;
  logout: () => Promise<void>;
  refetchSettings: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<AuthState>({
    currentUser: undefined,
    userGeneralSetting: undefined,
    userWebhooksSetting: undefined,
    shortcuts: [],
    isInitialized: false,
    isLoading: true,
  });

  const fetchUserSettings = useCallback(async (userName: string) => {
    const [{ settings }, { shortcuts }] = await Promise.all([
      userServiceClient.listUserSettings({ parent: userName }),
      shortcutServiceClient.listShortcuts({ parent: userName }),
    ]);

    const generalSetting = settings.find((s) => s.value.case === "generalSetting");
    const webhooksSetting = settings.find((s) => s.value.case === "webhooksSetting");

    return {
      userGeneralSetting: generalSetting?.value.case === "generalSetting" ? generalSetting.value.value : undefined,
      userWebhooksSetting: webhooksSetting?.value.case === "webhooksSetting" ? webhooksSetting.value.value : undefined,
      shortcuts,
    };
  }, []);

  const initialize = useCallback(async () => {
    setState((prev) => ({ ...prev, isLoading: true }));

    const uid = getActingUid();
    if (!uid) {
      setState({
        currentUser: undefined,
        userGeneralSetting: undefined,
        userWebhooksSetting: undefined,
        shortcuts: [],
        isInitialized: true,
        isLoading: false,
      });
      return;
    }

    try {
      const currentUser = await userServiceClient.getUser({ name: `users/${uid}` });

      const settings = await fetchUserSettings(currentUser.name);

      setState({
        currentUser,
        ...settings,
        isInitialized: true,
        isLoading: false,
      });

      queryClient.setQueryData(userKeys.currentUser(), currentUser);
      queryClient.setQueryData(userKeys.detail(currentUser.name), currentUser);
    } catch (error) {
      console.error("Failed to initialize acting user:", error);
      clearActingUid();
      setState({
        currentUser: undefined,
        userGeneralSetting: undefined,
        userWebhooksSetting: undefined,
        shortcuts: [],
        isInitialized: true,
        isLoading: false,
      });
    }
  }, [fetchUserSettings, queryClient]);

  const logout = useCallback(async () => {
    clearActingUid();
    setState({
      currentUser: undefined,
      userGeneralSetting: undefined,
      userWebhooksSetting: undefined,
      shortcuts: [],
      isInitialized: true,
      isLoading: false,
    });
    queryClient.clear();
  }, [queryClient]);

  const refetchSettings = useCallback(async () => {
    setState((prev) => {
      if (!prev.currentUser) return prev;

      fetchUserSettings(prev.currentUser.name).then((settings) => {
        setState((current) => ({ ...current, ...settings }));
      });

      return prev;
    });
  }, [fetchUserSettings]);

  const value = useMemo(
    () => ({
      ...state,
      initialize,
      logout,
      refetchSettings,
    }),
    [state, initialize, logout, refetchSettings],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}

export function useCurrentUserFromAuth() {
  const { currentUser } = useAuth();
  return currentUser;
}
