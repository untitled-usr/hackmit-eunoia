import { createApi, type BaseQueryApi } from "@reduxjs/toolkit/query/react";
import type { FetchBaseQueryError, FetchBaseQueryMeta, QueryReturnValue } from "@reduxjs/toolkit/query";

/** RTK `queryFn` 第 4 参需与 `baseQuery` 签名一致（`arg: any`），否则 TS 不兼容 */
type BaseQueryFn = (
  arg: any
) => Promise<QueryReturnValue<unknown, FetchBaseQueryError, FetchBaseQueryMeta>>;

import { Channel } from "@/types/channel";
import { ContentTypeKey } from "@/types/message";
import {
  AgoraConfig,
  AgoraTokenResponse,
  AgoraVoicingListResponse,
  FALLBACK_MEMOS_STYLE_LOGIN_CONFIG,
  FirebaseConfig,
  GithubAuthConfig,
  GoogleAuthConfig,
  LicenseResponse,
  LoginConfig,
  RenewLicense,
  RenewLicenseResponse,
  Server,
  SMTPConfig,
  SystemCommon,
  TestEmailDTO,
  VocespaceConfig,
} from "@/types/server";
import { User } from "@/types/user";
import { compareVersion, encodeBase64 } from "@/utils";
import BASE_URL, {
  ContentTypes,
  IS_OFFICIAL_DEMO,
  KEY_SERVER_VERSION,
  PAYMENT_URL_PREFIX,
} from "../config";
import { updateInfo } from "../slices/server";
import { updateCallInfo, upsertVoiceList } from "../slices/voice";
import { RootState } from "../store";
import baseQuery from "./base.query";
import { GetFilesDTO, VoceChatFile } from "@/types/resource";
import { GroupAnnouncement } from "@/types/sse";

/** vocechat-server fork (e.g. 0.3.x) has no `/admin/agora/channel/*` or `/admin/vocespace/*`; avoid 404 spam. */
const EMPTY_AGORA_VOICE_LIST: AgoraVoicingListResponse = {
  success: true,
  data: { channels: [], total_size: 0 }
};

const DISABLED_VOCESPACE_CONFIG: VocespaceConfig = {
  enabled: false,
  password: "",
  url: "",
  license: "",
  state: ""
};

/** No `GET/PUT /admin/system/common` in this vocechat-server fork — keep UI/preload stable. */
const FORK_DEFAULT_SYSTEM_COMMON: SystemCommon = {
  show_user_online_status: false,
  webclient_auto_update: true,
  contact_verification_enable: false,
  chat_layout_mode: "Left",
  max_file_expiry_mode: "Off",
  only_admin_can_create_group: false,
  who_can_invite_users: true,
  ext_setting: null,
  msg_smtp_notify_enable: false,
  msg_smtp_notify_delay_seconds: 0
};

const FORK_NO_GROUP_ANNOUNCEMENT: { announcement: GroupAnnouncement | null } = {
  announcement: null
};

export const serverApi = createApi({
  reducerPath: "serverApi",
  baseQuery,
  tagTypes: ["GroupAnnouncements"],
  endpoints: (builder) => ({
    getServer: builder.query<Server, void>({
      query: () => ({ url: `/admin/system/organization` }),
      async onQueryStarted(data, { dispatch, queryFulfilled }) {
        try {
          const { data: server } = await queryFulfilled;
          const logo = `${BASE_URL}/resource/organization/logo?t=${+new Date()}`;
          dispatch(updateInfo({ ...server, logo }));
        } catch {
          console.error("get server info error");
        }
      },
    }),
    getThirdPartySecret: builder.query<string, void>({
      query: () => ({
        url: `/admin/system/third_party_secret`,
        responseHandler: "text",
      }),
      keepUnusedDataFor: 0,
    }),
    updateThirdPartySecret: builder.mutation<string, void>({
      query: () => ({
        url: `/admin/system/third_party_secret`,
        method: "POST",
        responseHandler: "text",
      }),
    }),
    getServerVersion: builder.query<string, void>({
      query: () => ({
        headers: {
          accept: "text/plain",
        },
        url: `/admin/system/version`,
        responseHandler: "text",
      }),
      async onQueryStarted(data, { dispatch, queryFulfilled }) {
        try {
          const resp = await queryFulfilled;
          localStorage.setItem(KEY_SERVER_VERSION, resp.data);
          dispatch(updateInfo({ version: resp.data }));
        } catch {
          console.error("get server version error");
        }
      },
    }),
    getFirebaseConfig: builder.query<FirebaseConfig, void>({
      query: () => ({ url: `/admin/fcm/config` }),
    }),
    getGoogleAuthConfig: builder.query<GoogleAuthConfig, void>({
      queryFn: async (): Promise<{ data: GoogleAuthConfig }> => ({ data: { client_id: "" } }),
    }),
    getGoogleAuthPublicConfig: builder.query<GoogleAuthConfig, void>({
      queryFn: async (): Promise<{ data: GoogleAuthConfig }> => ({ data: { client_id: "" } }),
    }),
    updateGoogleAuthConfig: builder.mutation<void, GoogleAuthConfig>({
      queryFn: async () => ({ data: undefined }),
    }),
    getGithubAuthConfig: builder.query<GithubAuthConfig, void>({
      queryFn: async (): Promise<{ data: GithubAuthConfig }> => ({ data: { client_id: "" } }),
    }),
    getGithubAuthPublicConfig: builder.query<Pick<GithubAuthConfig, "client_id">, void>({
      queryFn: async (): Promise<{ data: Pick<GithubAuthConfig, "client_id"> }> => ({
        data: { client_id: "" }
      }),
    }),
    updateGithubAuthConfig: builder.mutation<void, GithubAuthConfig>({
      queryFn: async () => ({ data: undefined }),
    }),
    sendTestEmail: builder.mutation<void, TestEmailDTO>({
      query: (data) => ({
        url: `/admin/system/send_mail`,
        method: "POST",
        body: data,
      }),
    }),
    updateFirebaseConfig: builder.mutation<void, FirebaseConfig>({
      query: (data) => ({
        url: `/admin/fcm/config`,
        method: "POST",
        body: data,
      }),
    }),
    getVocespaceConfig: builder.query<VocespaceConfig, void>({
      queryFn: async () => ({ data: DISABLED_VOCESPACE_CONFIG }),
    }),
    getAgoraConfig: builder.query<AgoraConfig, void>({
      query: () => ({ url: `/admin/agora/config` }),
    }),
    getAgoraChannels: builder.query<
      AgoraVoicingListResponse,
      { page_no: number; page_size: number }
    >({
      queryFn: async () => ({ data: EMPTY_AGORA_VOICE_LIST }),
      async onQueryStarted(data, { dispatch, queryFulfilled, getState }) {
        try {
          const {
            voice: { callingFrom },
            authData,
          } = getState() as RootState;
          const { data: resp } = await queryFulfilled;
          const { success } = resp;
          if (success) {
            const arr = resp.data.channels.map((data) => {
              const [type, id] = data.channel_name.split(":").slice(-2);
              const count = data.user_count;
              const context = type === "group" ? ("channel" as const) : ("dm" as const);
              return {
                id: +id,
                context,
                memberCount: count,
                channelName: data.channel_name,
              };
            });
            dispatch(upsertVoiceList(arr));
            const hasMyself = arr.some(
              (data) => data.context === "dm" && data.id == authData?.user?.uid
            );
            const sendByMe = callingFrom && callingFrom === authData?.user?.uid;
            // reset dm call setting
            if (callingFrom && !sendByMe && !hasMyself) {
              dispatch(updateCallInfo({ from: 0, to: 0, calling: false }));
            }
          }
        } catch {
          console.error("get voice list error");
        }
      },
    }),
    /** 后端无对应列表接口时返回空；`queryFn` 的 `data` 须与 `QueryReturnValue` 的最终类型一致，不能再用 `transformResponse` 做二次变换 */
    getAgoraUsersByChannel: builder.query<number[], string>({
      queryFn: async (
        _channelName: string,
        _api: BaseQueryApi,
        _extra: unknown,
        _bq: BaseQueryFn
      ) => ({ data: [] as number[] }),
    }),
    updateAgoraConfig: builder.mutation<void, AgoraConfig>({
      query: (data) => ({
        url: `/admin/agora/config`,
        method: "POST",
        body: data,
      }),
    }),
    updateVocespaceConfig: builder.mutation<void, VocespaceConfig>({
      queryFn: async () => ({ data: undefined }),
    }),
    healthCheckVocespace: builder.mutation<boolean, { url: string }>({
      queryFn: async () => ({ data: false }),
    }),
    getAgoraStatus: builder.query<boolean, void>({
      // Newer server route exposes enabled flag via /admin/agora/config.
      query: () => ({ url: `/admin/agora/config` }),
      transformResponse: (resp: { enabled?: boolean }) => Boolean(resp?.enabled),
    }),
    generateAgoraToken: builder.mutation<AgoraTokenResponse, { uid: number } | { gid: number }>({
      async queryFn(
        arg: { uid: number } | { gid: number },
        _api: BaseQueryApi,
        _extra: unknown,
        fetchWithBQ: BaseQueryFn
      ) {
        if ("gid" in arg) {
          const res = await fetchWithBQ({
            url: `/group/${arg.gid}/agora_token`,
            method: "GET"
          });
          if ("error" in res && res.error !== undefined) {
            return { error: res.error };
          }
          if ("data" in res && res.data !== undefined) {
            return { data: res.data as AgoraTokenResponse };
          }
          return {
            error: {
              status: "CUSTOM_ERROR",
              error: "agora_token_empty",
              data: "agora_token_empty"
            } as FetchBaseQueryError
          };
        }
        return {
          error: {
            status: 501,
            data: "dm_voice_unsupported"
          }
        };
      }
    }),
    getSystemCommon: builder.query<SystemCommon, void>({
      queryFn: async (): Promise<{ data: SystemCommon }> => {
        const tmp: SystemCommon = { ...FORK_DEFAULT_SYSTEM_COMMON };
        tmp.chat_layout_mode = tmp.chat_layout_mode ?? "Left";
        tmp.contact_verification_enable = tmp.contact_verification_enable ?? false;
        tmp.max_file_expiry_mode = tmp.max_file_expiry_mode ?? "Off";
        return { data: tmp };
      },
      async onQueryStarted(data, { dispatch, queryFulfilled }) {
        try {
          const resp = await queryFulfilled;
          dispatch(updateInfo(resp.data));
        } catch {
          console.error("get server common error");
        }
      },
    }),
    updateSystemCommon: builder.mutation<void, Partial<SystemCommon>>({
      queryFn: async () => ({ data: undefined }),
      async onQueryStarted(data, { dispatch, queryFulfilled }) {
        try {
          await queryFulfilled;
          dispatch(updateInfo(data));
        } catch {
          console.error("update server common error");
        }
      },
    }),
    getSMTPConfig: builder.query<SMTPConfig, void>({
      query: () => ({ url: `/admin/smtp/config` }),
    }),
    getSMTPStatus: builder.query<boolean, void>({
      query: () => ({ url: `/admin/smtp/enabled` }),
    }),
    updateSMTPConfig: builder.mutation<void, SMTPConfig>({
      query: (data) => ({
        url: `/admin/smtp/config`,
        method: "POST",
        body: data,
      }),
    }),
    getLoginConfig: builder.query<LoginConfig, void>({
      queryFn: () => ({ data: FALLBACK_MEMOS_STYLE_LOGIN_CONFIG })
    }),
    getFiles: builder.query<VoceChatFile[], GetFilesDTO>({
      queryFn: async () => ({ data: [] }),
    }),
    updateLoginConfig: builder.mutation<void, Partial<LoginConfig>>({
      // vocechat-server (this fork) has no `POST /admin/login/config`. That route belonged to
      // upstream VoceChat; hitting it returns 404 → RTK shows "Request Not Found".
      // This app talks to vocechat-server only (dev: same-origin `/api` → webpack proxy → :7922),
      // not mid-auth. Sign-up policy is enforced server-side via organization
      // `disallow_user_registration` and `POST /user/register`, not login-config JSON.
      queryFn: async () => ({ data: undefined }),
    }),
    updateLogo: builder.mutation<void, File>({
      query: (data) => ({
        headers: {
          "content-type": "image/png",
        },
        url: `/admin/system/organization/logo`,
        method: "POST",
        body: data,
      }),
      async onQueryStarted(data, { dispatch, queryFulfilled }) {
        try {
          await queryFulfilled;
          dispatch(
            updateInfo({
              logo: `${BASE_URL}/resource/organization/logo?t=${+new Date()}`,
            })
          );
        } catch {
          console.error("update server logo error");
        }
      },
    }),
    updateServer: builder.mutation<void, Partial<Server>>({
      query: (data) => ({
        url: "admin/system/organization",
        method:
          compareVersion(localStorage.getItem(KEY_SERVER_VERSION) ?? "", "0.3.8") > 0
            ? "PUT"
            : "POST",
        body: data,
      }),
      async onQueryStarted(data, { dispatch, queryFulfilled, getState }) {
        const rootStore = getState() as RootState;
        const { name: prevName, description: prevDesc } = rootStore.server;
        dispatch(updateInfo(data));
        try {
          await queryFulfilled;
        } catch {
          dispatch(updateInfo({ name: prevName, description: prevDesc }));
        }
      },
    }),
    getFrontendUrl: builder.query<string, void>({
      query: () => ({
        url: `/admin/system/frontend_url`,
        responseHandler: "text",
      }),
    }),
    updateFrontendUrl: builder.mutation<void, string>({
      query: (url) => ({
        url: `/admin/system/update_frontend_url`,
        method: "POST",
        headers: {
          "content-type": "text/plain",
        },
        body: url,
      }),
    }),
    getLicense: builder.query<LicenseResponse, void>({
      query: () => ({
        url: `/license`,
      }),
      async onQueryStarted(data, { dispatch, queryFulfilled, getState }) {
        // vocechat 官方 demo 则忽略
        if (IS_OFFICIAL_DEMO) return;
        const rootStore = getState() as RootState;
        const { upgraded: prevValue } = rootStore.server;
        try {
          const {
            data: { user_limit },
          } = await queryFulfilled;
          const currValue = user_limit > 20;
          if (prevValue !== currValue) {
            dispatch(updateInfo({ upgraded: currValue }));
          }
        } catch {
          console.error("get license failed ");
        }
      },
    }),

    getLicensePaymentUrl: builder.mutation<RenewLicenseResponse, RenewLicense>({
      query: (data) => ({
        url: `${PAYMENT_URL_PREFIX}/vocechat/payment/create`,
        method: "POST",
        body: data,
      }),
    }),
    getGeneratedLicense: builder.query<{ license: string }, string>({
      query: (session_id) => ({
        url: `${PAYMENT_URL_PREFIX}/vocechat/licenses/${session_id}`,
      }),
    }),
    checkLicense: builder.mutation<LicenseResponse, string>({
      query: (license) => ({
        url: "/license/check",
        method: "POST",
        body: { license },
      }),
    }),
    upsertLicense: builder.mutation<boolean, string>({
      query: (license) => ({
        url: "/license",
        method: "PUT",
        body: { license },
      }),
    }),
    clearAllMessages: builder.query<void, void>({
      queryFn: async () => ({ data: undefined }),
    }),
    clearAllFiles: builder.query<void, void>({
      queryFn: async () => ({ data: undefined }),
    }),
    getWidgetExtCSS: builder.query<string, void>({
      queryFn: async () => ({ data: "" }),
    }),
    updateWidgetExtCSS: builder.mutation<boolean, string>({
      queryFn: async () => ({ data: true }),
    }),
    getBotRelatedChannels: builder.query<Channel[], { api_key: string; public_only?: boolean }>({
      query: ({ api_key, public_only = false }) => ({
        url: public_only ? `/bot?public_only=${public_only}` : `/bot`,
        headers: {
          "x-api-key": api_key,
        },
      }),
    }),
    sendMessageByBot: builder.mutation<
      number,
      {
        uid?: number;
        cid?: number;
        api_key: string;
        content: string;
        type?: ContentTypeKey;
        properties?: object;
      }
    >({
      query: ({ uid, cid, api_key, type = "text", properties, content }) => ({
        headers: {
          "x-api-key": api_key,
          "content-type": ContentTypes[type],
          "X-Properties": properties ? encodeBase64(JSON.stringify(properties)) : "",
        },
        url: cid ? `/bot/send_to_group/${cid}` : `/bot/send_to_user/${uid}`,
        method: "POST",
        body: content,
      }),
    }),
    getGroupAnnouncement: builder.query<{ announcement: GroupAnnouncement | null }, number>({
      queryFn: async () => ({ data: FORK_NO_GROUP_ANNOUNCEMENT }),
      providesTags: (result, error, gid) => [{ type: "GroupAnnouncements", id: gid }],
    }),
    createOrUpdateGroupAnnouncement: builder.mutation<
      GroupAnnouncement,
      { gid: number; content: string }
    >({
      queryFn: async ({ gid, content }) => {
        const now = Math.floor(Date.now() / 1000);
        return {
          data: {
            gid,
            content,
            created_by: 0,
            created_at: now,
            updated_at: now
          }
        };
      },
      invalidatesTags: (result, error, { gid }) => [{ type: "GroupAnnouncements", id: gid }],
    }),
    deleteGroupAnnouncement: builder.mutation<void, number>({
      queryFn: async () => ({ data: undefined }),
      invalidatesTags: (result, error, gid) => [{ type: "GroupAnnouncements", id: gid }],
    }),
  }),
});

export const {
  useGetWidgetExtCSSQuery,
  useUpdateWidgetExtCSSMutation,
  useLazyGetServerVersionQuery,
  useGetServerVersionQuery,
  useGetGithubAuthConfigQuery,
  useGetGithubAuthPublicConfigQuery,
  useUpdateGithubAuthConfigMutation,
  useGetGoogleAuthConfigQuery,
  useGetGoogleAuthPublicConfigQuery,
  useUpdateGoogleAuthConfigMutation,
  useGetSMTPStatusQuery,
  useSendTestEmailMutation,
  useUpdateFirebaseConfigMutation,
  useGetFirebaseConfigQuery,
  useLazyGetFirebaseConfigQuery,
  useLazyGetAgoraConfigQuery,
  useLazyGetSMTPConfigQuery,
  useLazyGetLoginConfigQuery,
  useGetLoginConfigQuery,
  useUpdateLoginConfigMutation,
  useGetSMTPConfigQuery,
  useUpdateSMTPConfigMutation,
  useUpdateAgoraConfigMutation,
  useGetServerQuery,
  useLazyGetServerQuery,
  useUpdateServerMutation,
  useUpdateLogoMutation,
  useGetThirdPartySecretQuery,
  useUpdateThirdPartySecretMutation,
  useUpsertLicenseMutation,
  useCheckLicenseMutation,
  useGetLicenseQuery,
  useGetLicensePaymentUrlMutation,
  useLazyGetGeneratedLicenseQuery,
  useLazyGetBotRelatedChannelsQuery,
  useSendMessageByBotMutation,
  useUpdateFrontendUrlMutation,
  useGetFrontendUrlQuery,
  useGetAgoraConfigQuery,
  useGetAgoraStatusQuery,
  useGetAgoraChannelsQuery,
  useUpdateSystemCommonMutation,
  useLazyGetSystemCommonQuery,
  useGetSystemCommonQuery,
  useGenerateAgoraTokenMutation,
  useLazyGetAgoraUsersByChannelQuery,
  useLazyClearAllFilesQuery,
  useLazyClearAllMessagesQuery,
  useLazyGetFilesQuery,
  useGetVocespaceConfigQuery,
  useLazyGetVocespaceConfigQuery,
  useUpdateVocespaceConfigMutation,
  useHealthCheckVocespaceMutation,
  useGetGroupAnnouncementQuery,
  useCreateOrUpdateGroupAnnouncementMutation,
  useDeleteGroupAnnouncementMutation,
} = serverApi;
