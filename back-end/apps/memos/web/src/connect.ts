import { Code, ConnectError, createClient, type Interceptor } from "@connectrpc/connect";
import { createConnectTransport } from "@connectrpc/connect-web";
import { getActingUid } from "./auth-state";
import { AttachmentService } from "./types/proto/api/v1/attachment_service_pb";
import { IdentityProviderService } from "./types/proto/api/v1/idp_service_pb";
import { InstanceService } from "./types/proto/api/v1/instance_service_pb";
import { MemoService } from "./types/proto/api/v1/memo_service_pb";
import { ShortcutService } from "./types/proto/api/v1/shortcut_service_pb";
import { UserService } from "./types/proto/api/v1/user_service_pb";
import { redirectOnAuthFailure } from "./utils/auth-redirect";

interface RequestWithHeader {
  header: Headers;
}

const actingUidInterceptor: Interceptor = (next) => async (req) => {
  const uid = getActingUid();
  if (uid) {
    (req as unknown as RequestWithHeader).header.set("X-Acting-Uid", uid);
  }
  try {
    return await next(req);
  } catch (error) {
    if (error instanceof ConnectError && error.code === Code.Unauthenticated) {
      redirectOnAuthFailure();
    }
    throw error;
  }
};

const transport = createConnectTransport({
  baseUrl: window.location.origin,
  useBinaryFormat: true,
  interceptors: [actingUidInterceptor],
});

export const instanceServiceClient = createClient(InstanceService, transport);
export const userServiceClient = createClient(UserService, transport);
export const memoServiceClient = createClient(MemoService, transport);
export const attachmentServiceClient = createClient(AttachmentService, transport);
export const shortcutServiceClient = createClient(ShortcutService, transport);
export const identityProviderServiceClient = createClient(IdentityProviderService, transport);
