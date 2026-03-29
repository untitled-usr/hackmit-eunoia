import toast from "react-hot-toast";
import { fetchBaseQuery, type FetchBaseQueryError } from "@reduxjs/toolkit/query";

import { getLocalAuthData } from "@/utils";
import BASE_URL, { DEV_DIRECT_BASE_URL, actingUidHeader, IS_OFFICIAL_DEMO } from "../config";
import { resetAuthData } from "../slices/auth.data";

const whiteList = [
  "register",
  "getSMTPStatus",
  "getLoginConfig",
  "getServerVersion",
  "getServer",
  "getInitialized",
  "getBotRelatedChannels",
  "sendMessageByBot",
  "getAgoraVoicingList",
  "preCheckFileFromUrl"
];
const whiteList401 = [
  "getAgoraVoicingList",
  "getAgoraChannels",
  "getGoogleAuthConfig",
  "getGithubAuthConfig"
];
const errorWhiteList = [
  "preCheckFileFromUrl",
  "getFavoriteDetails",
  "getOGInfo",
  "getArchiveMessage",
  "getGoogleAuthPublicConfig",
  "getGithubAuthPublicConfig",
  "getGoogleAuthConfig",
  "getGithubAuthConfig"
];
const whiteList404 = [
  "getArchiveMessage",
  "preCheckFileFromUrl",
  "deleteMessage",
  "deleteMessages",
  "getWidgetExtCSS",
  "getSystemCommon",
  "getAgoraStatus",
  // vocechat-server has no `/admin/notification/*` or `/user/notification/*` (queries stubbed; keep for mutations).
  "getEnabledChannelTypes",
  "getAvailableChannelTypes",
  "getUserChannels"
];

const prepareHeaders = (headers: Headers, { endpoint }: { endpoint: string }) => {
  const { actingUid } = getLocalAuthData();
  if (IS_OFFICIAL_DEMO && "crypto" in window) {
    const uuid = window.crypto.randomUUID();
    headers.set("request_uuid", uuid);
  }
  if (actingUid && !whiteList.includes(endpoint)) {
    headers.set(actingUidHeader, actingUid);
  }
  return headers;
};

const baseQuery = fetchBaseQuery({
  baseUrl: BASE_URL,
  prepareHeaders,
});

const directBaseQuery = fetchBaseQuery({
  baseUrl: DEV_DIRECT_BASE_URL,
  prepareHeaders,
});

function errorStatusCode(err: FetchBaseQueryError): number | "FETCH_ERROR" | undefined {
  if (err.status === "FETCH_ERROR") return "FETCH_ERROR";
  if (err.status === "PARSING_ERROR") return err.originalStatus;
  if (typeof err.status === "number") return err.status;
  return undefined;
}

function errorMessageData(data: unknown): string {
  if (typeof data === "string") return data;
  if (data && typeof data === "object" && "message" in data && typeof (data as { message: unknown }).message === "string") {
    return (data as { message: string }).message;
  }
  return "";
}

const baseQueryWithActingUid = async (args: any, api: any, extraOptions: any) => {
  let result = await baseQuery(args, api, extraOptions);
  // Dev fallback: if same-origin `/api` cannot be reached in current access path,
  // retry once with direct backend origin (e.g. http://<host>:7922/api).
  if (
    process.env.NODE_ENV === "development" &&
    result?.error?.status === "FETCH_ERROR" &&
    DEV_DIRECT_BASE_URL !== BASE_URL
  ) {
    const directResult = await directBaseQuery(args, api, extraOptions);
    if (!directResult?.error) {
      return directResult;
    }
    result = directResult;
  }
  if (result?.error) {
    console.error("api error", result.error, args, api.endpoint);
    if (errorWhiteList.includes(api.endpoint)) return result;
    const err = result.error as FetchBaseQueryError;
    const code = errorStatusCode(err);
    switch (code) {
      case "FETCH_ERROR":
        toast.error(`${api.endpoint}: Failed to fetch`);
        break;
      case 400:
        toast.error("Bad Request");
        break;
      case 401:
        if (whiteList401.includes(api.endpoint)) {
          return result;
        }
        if (api.endpoint !== "getMe") {
          api.dispatch(resetAuthData());
          location.href = "/#/login";
        }
        break;
      case 403: {
        const whiteList403 = ["sendMsg"];
        if (!whiteList403.includes(api.endpoint)) {
          toast.error("Request Not Allowed");
        }
        break;
      }
      case 404:
        if (!whiteList404.includes(api.endpoint)) {
          toast.error("Request Not Found");
        }
        break;
      case 413:
        toast.error("File size too large");
        break;
      case 415:
        toast.error("Unsupported Media Type");
        break;
      case 451:
        // Register must not trigger logout loop when license/referer check fails
        if (api.endpoint !== "getMe" && api.endpoint !== "register") {
          api.dispatch(resetAuthData());
          location.href = "/#/login";
        }
        toast.error(errorMessageData(err.data) || "License Error");
        break;
      case 500:
      case 503:
        toast.error(errorMessageData(err.data) || "Server Error");
        break;
      default:
        break;
    }
  }
  return result;
};

export default baseQueryWithActingUid;
