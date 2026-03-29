import { createApi } from "@reduxjs/toolkit/query/react";

import { CredentialResponse } from "@/types/auth";
import { UserRegDTO } from "@/types/user";
import { resetAuthData, setAuthData } from "../slices/auth.data";
import baseQuery from "./base.query";
import { setReady, updateSSEStatus } from "../slices/ui";
import { User } from "@/types/user";
import { upsertUser, type StoredUser } from "../slices/users";

/** Matches server `UserInfo` / OpenAPI. */
export interface SessionUserInfo {
  uid: number;
  name: string;
  gender: number;
  language: string;
  is_admin: boolean;
  is_bot: boolean;
  avatar_updated_at: number;
  create_by: string;
}

export function sessionToUser(info: SessionUserInfo): User {
  return {
    uid: info.uid,
    name: info.name,
    gender: (info.gender as 0 | 1) ?? 0,
    language: info.language,
    is_admin: info.is_admin,
    avatar_updated_at: info.avatar_updated_at,
    create_by: info.create_by,
    is_bot: info.is_bot
  };
}

function sessionInfoToStoredUser(info: SessionUserInfo): StoredUser {
  return {
    uid: info.uid,
    name: info.name,
    gender: (info.gender as 0 | 1) ?? 0,
    language: info.language,
    is_admin: info.is_admin,
    avatar_updated_at: info.avatar_updated_at,
    create_by: info.create_by,
    is_bot: info.is_bot,
    status: "added",
    avatar: "",
  };
}

function registeredUserToStoredUser(user: User): StoredUser {
  return {
    ...user,
    status: "added",
    avatar: "",
  };
}

/** Registration API returns admin `User` shape (includes password in JSON — strip client-side). */
function registerResponseToUser(raw: User & { password?: string }): User {
  const { password: _p, ...rest } = raw;
  return rest;
}

export const authApi = createApi({
  reducerPath: "authApi",
  baseQuery,
  endpoints: (builder) => ({
    getMe: builder.query<SessionUserInfo, void>({
      query: () => ({ url: "user/me" }),
      async onQueryStarted(_a, { dispatch, queryFulfilled }) {
        try {
          const { data } = await queryFulfilled;
          if (data) {
            const user = sessionToUser(data);
            dispatch(setAuthData({ user }));
            dispatch(upsertUser(sessionInfoToStoredUser(data)));
            dispatch(setReady(false));
            dispatch(updateSSEStatus("disconnected"));
          }
        } catch {
          console.warn("getMe failed");
        }
      }
    }),
    register: builder.mutation<User, UserRegDTO>({
      query: (data) => {
        const body: Record<string, unknown> = {
          gender: data.gender ?? 0,
          language: data.language ?? "en-US"
        };
        if (data.name) body.name = data.name;
        if (data.password) body.password = data.password;
        return {
          url: `user/register`,
          method: "POST",
          body
        };
      },
      transformResponse: (raw: User & { password?: string }) => registerResponseToUser(raw),
      async onQueryStarted(_p, { dispatch, queryFulfilled }) {
        try {
          const { data } = await queryFulfilled;
          if (data) {
            dispatch(setAuthData({ user: data }));
            dispatch(upsertUser(registeredUserToStoredUser(data)));
            dispatch(setReady(false));
            dispatch(updateSSEStatus("disconnected"));
          }
        } catch {
          console.log("register error");
        }
      }
    }),
    updatePassword: builder.mutation<void, { old_password: string; new_password: string }>({
      query: (data) => ({
        url: "user/change_password",
        method: "POST",
        body: data
      })
    }),
    logout: builder.query<void, void>({
      queryFn: async () => {
        return { data: undefined };
      },
      async onQueryStarted(_p, { dispatch, queryFulfilled }) {
        try {
          await queryFulfilled;
          dispatch(resetAuthData());
          location.href = "/#/login";
        } catch {
          console.log("logout error");
        }
      }
    }),
    getInitialized: builder.query<boolean, void>({
      // Memos-style fork: keep auth guard probe side-effect free.
      queryFn: () => ({ data: true })
    }),
    deleteCurrentAccount: builder.query<void, void>({
      query: () => ({
        url: `/user/delete`,
        method: "DELETE"
      })
    }),
    getCredentials: builder.query<CredentialResponse, void>({
      queryFn: () => ({
        data: { password: false, google: "", metamask: "", oidc: [] }
      })
    }),
    getUserPasskeys: builder.query<import("@/types/auth").UserPasskey[], void>({
      queryFn: () => ({ data: [] })
    }),
    updateDeviceToken: builder.mutation<void, string>({
      queryFn: async () => ({ data: undefined })
    })
  })
});

export const {
  useLazyGetMeQuery,
  useGetMeQuery,
  useRegisterMutation,
  useUpdatePasswordMutation,
  useGetInitializedQuery,
  useLazyGetInitializedQuery,
  useLazyLogoutQuery,
  useLazyDeleteCurrentAccountQuery,
  useGetCredentialsQuery,
  useGetUserPasskeysQuery,
  useLazyGetUserPasskeysQuery,
  useUpdateDeviceTokenMutation
} = authApi;
