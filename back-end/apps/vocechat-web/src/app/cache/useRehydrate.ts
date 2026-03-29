import { useState } from "react";
import { useDispatch } from "react-redux";

import { fillChannels } from "../slices/channels";
import { fillFootprint } from "../slices/footprint";
import { fillMessage } from "../slices/message";
import { fillChannelMsg } from "../slices/message.channel";
import { fillFileMessage } from "../slices/message.file";
import { fillReactionMessage } from "../slices/message.reaction";
import { fillUserMsg } from "../slices/message.user";
import { fillServer, type StoredServer } from "../slices/server";
import { fillUI } from "../slices/ui";
import { fillUsers } from "../slices/users";
import type { State as MessageState } from "../slices/message";

type StringKeyed<T> = Record<string, T>;

const useRehydrate = () => {
  const [iterated, setIterated] = useState(false);
  const dispatch = useDispatch();
  const rehydrate = async () => {
    const rehydrateData: {
      channels: unknown[];
      users: unknown[];
      fileMessage: StringKeyed<unknown>;
      channelMessage: StringKeyed<unknown>;
      userMessage: StringKeyed<unknown>;
      reactionMessage: StringKeyed<unknown>;
      message: StringKeyed<unknown> & { replying: Record<string, unknown> };
      footprint: StringKeyed<unknown>;
      ui: StringKeyed<unknown>;
      server: StringKeyed<unknown>;
    } = {
      channels: [],
      users: [],
      fileMessage: {},
      channelMessage: {},
      userMessage: {},
      reactionMessage: {},
      message: { replying: {} },
      footprint: {},
      ui: {},
      server: {}
    };
    if (!window.CACHE) {
      setIterated(true);
      return;
    }
    const tables = Object.keys(window.CACHE);
    await Promise.all(
      tables.map((_key) => {
        return window.CACHE[_key]?.iterate((data: unknown, key: string) => {
          switch (_key) {
            case "channels":
              if (data) {
                rehydrateData.channels.push(data);
              }
              break;
            case "users":
              if (data) {
                rehydrateData.users.push(data);
              }
              break;
            case "footprint":
              rehydrateData.footprint[key] = data;
              break;
            case "ui":
              rehydrateData.ui[key] = data;
              break;
            case "messageChannel":
              rehydrateData.channelMessage[key] = data;
              break;
            case "messageFile":
              rehydrateData.fileMessage[key] = data || [];
              break;
            case "messageDM":
              rehydrateData.userMessage[key] = data;
              break;
            case "messageReaction":
              rehydrateData.reactionMessage[key] = data;
              break;
            case "message":
              rehydrateData.message[key] = data;
              break;
            case "server":
              rehydrateData.server[key] = data;
              break;

            default:
              break;
          }
        });
      })
    );
    /* 缓存结构随版本变化，此处仅做恢复与类型断言，避免 `never` 与空对象推断 */
    dispatch(fillUsers(rehydrateData.users as any));
    dispatch(fillServer(rehydrateData.server as unknown as StoredServer));
    dispatch(fillChannels(rehydrateData.channels as any));
    const fileMids = Object.values(rehydrateData.fileMessage).flatMap((v) =>
      Array.isArray(v) ? (v as number[]) : []
    );
    dispatch(fillFileMessage(fileMids));
    dispatch(fillChannelMsg(rehydrateData.channelMessage as any));
    dispatch(fillUserMsg(rehydrateData.userMessage as any));
    dispatch(fillMessage(rehydrateData.message as unknown as MessageState));
    dispatch(fillFootprint(rehydrateData.footprint as any));
    dispatch(fillUI(rehydrateData.ui as any));
    dispatch(fillReactionMessage(rehydrateData.reactionMessage as any));

    setIterated(true);
  };
  return { rehydrate, rehydrated: iterated };
};

export default useRehydrate;
