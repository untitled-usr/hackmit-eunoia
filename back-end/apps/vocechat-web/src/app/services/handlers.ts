import toast from "react-hot-toast";
import { batch } from "react-redux";

import { ContentTypes } from "../config";
import type { ContentType, ContentTypeKey } from "@/types/message";
import { addMessage, removeMessage, type MessagePayload } from "../slices/message";
import { addChannelMsg, removeChannelMsg } from "../slices/message.channel";
import { addUserMsg, removeUserMsg } from "../slices/message.user";

/** 各 send / reply mutation 传入字段略有差异，在此统一归一化 */
export type OnMessageSendStartedArg = {
  ignoreLocal?: boolean;
  id: number;
  content: string | { path: string };
  type?: string;
  from_uid?: number;
  reply_mid?: number | null;
  properties?: Partial<{ local_id: number; content_type: string; size: number }>;
};

export const onMessageSendStarted = async (
  {
    ignoreLocal = false,
    id,
    content,
    type = "text",
    from_uid,
    reply_mid = null,
    properties: propertiesIn,
  }: OnMessageSendStartedArg,
  { dispatch, queryFulfilled }: { dispatch: any; queryFulfilled: Promise<{ data: number }> },
  from: "channel" | "user" = "channel"
) => {
  const properties = {
    local_id: propertiesIn?.local_id ?? +new Date(),
    content_type: propertiesIn?.content_type ?? "",
    size: propertiesIn?.size ?? 0,
  };
  // 忽略 archive 类型的消息 以及没有 from_uid
  if (type == "archive" || !from_uid) return;
  // id: who send to ,from_uid: who sent
  // console.log("handlers data", content, type, properties, ignoreLocal, id);
  const isMedia = properties.content_type
    ? ["image", "video", "audio"].includes(properties.content_type.toLowerCase().split("/")[0])
    : false;
  // const isImage = properties.content_type?.startsWith("image");
  const ts = properties.local_id || +new Date();
  const tmpMsg = {
    content:
      isMedia && typeof content === "object" && content !== null && "path" in content
        ? content.path
        : typeof content === "string"
          ? content
          : "",
    content_type: ContentTypes[type as ContentTypeKey] as ContentType,
    created_at: ts,
    properties,
    from_uid,
    reply_mid,
    sending: true,
  };
  const addContextMessage = from == "channel" ? addChannelMsg : addUserMsg;
  const removeContextMessage = from == "channel" ? removeChannelMsg : removeUserMsg;
  if (!ignoreLocal) {
    batch(() => {
      dispatch(addMessage({ mid: ts, ...tmpMsg } as MessagePayload));
      dispatch(addContextMessage({ id, mid: ts }));
    });
  }

  try {
    const { data: server_mid } = await queryFulfilled;
    // throw new Error();
    // console.log("message server mid", server_mid);
    batch(() => {
      dispatch(removeContextMessage({ id, mid: ts }));
      dispatch(
        addMessage({ mid: server_mid, ...tmpMsg, sending: false } as MessagePayload)
      );
      dispatch(addContextMessage({ id, mid: server_mid }));
    });
    setTimeout(() => {
      dispatch(removeMessage(ts));
    }, 300);
    // dispatch(removePendingMessage({ id, mid:ts, type: from }));
  } catch (error: unknown) {
    const err = error as { error?: { status?: number } };
    if (err?.error?.status == 403) {
      toast.error(
        from === "user"
          ? "对方已将你屏蔽或未接受好友请求，无法发送消息"
          : "发送失败，可能没有权限"
      );
      // dispatch(updateMessage({ mid: ts, failed: true }));
    } else {
      toast.error(`Send Message Failed ${JSON.stringify(error)}`);
    }
    dispatch(removeContextMessage({ id, mid: ts }));
    dispatch(removeMessage(ts));
    // patchResult.undo();
  }
};
