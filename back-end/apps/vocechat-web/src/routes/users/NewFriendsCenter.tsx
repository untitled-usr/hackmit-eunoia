import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import dayjs from "dayjs";
import toast from "react-hot-toast";

import StyledButton from "@/components/styled/Button";
import {
  useAcceptFriendRequestMutation,
  useCancelFriendRequestMutation,
  useDeleteFriendRequestRecordMutation,
  useLazyGetFriendRequestRecordsQuery,
  useRejectFriendRequestMutation,
} from "@/app/services/user";
import { useAppSelector } from "@/app/store";
import { FriendRequestRecordDTO } from "@/types/user";
import { shallowEqual } from "react-redux";

type Tab = "incoming" | "outgoing";

const statusText: Record<string, string> = {
  pending: "待处理",
  accepted: "已同意",
  rejected: "已拒绝",
  canceled: "已撤销",
  expired: "已失效",
};

export default function NewFriendsCenter() {
  const { t } = useTranslation("member");
  const [tab, setTab] = useState<Tab>("incoming");
  const loginUid = useAppSelector((s) => s.authData.user?.uid, shallowEqual);
  const usersById = useAppSelector((s) => s.users.byId, shallowEqual);
  const [fetchRecords, { data, isFetching }] = useLazyGetFriendRequestRecordsQuery();
  const [acceptReq] = useAcceptFriendRequestMutation();
  const [rejectReq] = useRejectFriendRequestMutation();
  const [cancelReq] = useCancelFriendRequestMutation();
  const [deleteRecord] = useDeleteFriendRequestRecordMutation();

  const refresh = () => {
    fetchRecords(undefined, true);
  };

  useEffect(() => {
    if (!loginUid) return;
    refresh();
  }, [loginUid]);

  const records = data ?? [];
  const list = useMemo(() => {
    if (!loginUid) return [];
    return records.filter((r) =>
      tab === "incoming" ? r.receiver_uid === loginUid : r.requester_uid === loginUid
    );
  }, [records, loginUid, tab]);

  const peerUid = (r: FriendRequestRecordDTO) =>
    tab === "incoming" ? r.requester_uid : r.receiver_uid;
  const peerName = (uid: number) => usersById[uid]?.name ?? `#${uid}`;

  const onAccept = async (id: number) => {
    try {
      await acceptReq(id).unwrap();
      toast.success(t("friend_accepted", { defaultValue: "已同意好友申请" }));
      refresh();
    } catch {
      toast.error(t("action_failed", { defaultValue: "操作失败" }));
    }
  };

  const onReject = async (id: number) => {
    try {
      await rejectReq(id).unwrap();
      toast.success(t("friend_rejected", { defaultValue: "已拒绝好友申请" }));
      refresh();
    } catch {
      toast.error(t("action_failed", { defaultValue: "操作失败" }));
    }
  };

  const onCancel = async (id: number) => {
    try {
      await cancelReq(id).unwrap();
      toast.success(t("friend_canceled", { defaultValue: "已撤销申请" }));
      refresh();
    } catch {
      toast.error(t("action_failed", { defaultValue: "操作失败" }));
    }
  };

  const onDelete = async (id: number) => {
    try {
      await deleteRecord(id).unwrap();
      toast.success(t("deleted", { defaultValue: "已删除记录" }));
      refresh();
    } catch {
      toast.error(t("action_failed", { defaultValue: "操作失败" }));
    }
  };

  return (
    <div className="w-full h-full px-4 md:px-6 py-4 md:py-6 overflow-y-auto">
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100">
          {t("new_friends", { defaultValue: "新的好友" })}
        </h2>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
          {t("new_friends_desc", {
            defaultValue:
              "收到的申请可同意/拒绝；发出的申请可撤销。已处理记录保留3天，超时申请7天失效并在3天后清除。",
          })}
        </p>
      </div>

      <div className="flex gap-2 mb-4">
        <button
          className={`px-3 py-1.5 rounded-md text-sm ${
            tab === "incoming"
              ? "bg-primary-500 text-white"
              : "bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-200"
          }`}
          onClick={() => setTab("incoming")}
        >
          {t("incoming_friend_requests", { defaultValue: "收到的好友申请" })}
        </button>
        <button
          className={`px-3 py-1.5 rounded-md text-sm ${
            tab === "outgoing"
              ? "bg-primary-500 text-white"
              : "bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-200"
          }`}
          onClick={() => setTab("outgoing")}
        >
          {t("outgoing_friend_requests", { defaultValue: "发出的好友申请" })}
        </button>
      </div>

      {isFetching ? (
        <div className="text-sm text-gray-500 dark:text-gray-400">
          {t("loading", { defaultValue: "加载中..." })}
        </div>
      ) : list.length === 0 ? (
        <div className="text-sm text-gray-500 dark:text-gray-400">
          {t("empty", { defaultValue: "暂无记录" })}
        </div>
      ) : (
        <ul className="space-y-2">
          {list.map((r) => (
            <li
              key={r.id}
              className="rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 p-3"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="font-medium text-gray-800 dark:text-gray-100">
                  {peerName(peerUid(r))}
                </div>
                <span className="text-xs px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-700">
                  {statusText[r.status] ?? r.status}
                </span>
              </div>
              <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                {tab === "incoming"
                  ? t("request_message_from_peer", { defaultValue: "对方留言" })
                  : t("request_message_self", { defaultValue: "我的申请留言" })}
                ：{r.message || t("empty_message", { defaultValue: "（无）" })}
              </div>
              <div className="text-[11px] text-gray-400 dark:text-gray-500 mt-1">
                {t("created_at", { defaultValue: "发起时间" })}：
                {dayjs(r.created_at).format("YYYY-MM-DD HH:mm")}
                {r.responded_at ? (
                  <>
                    {" · "}
                    {t("handled_at", { defaultValue: "处理时间" })}：
                    {dayjs(r.responded_at).format("YYYY-MM-DD HH:mm")}
                  </>
                ) : null}
              </div>
              <div className="flex gap-2 mt-3">
                {tab === "incoming" && r.status === "pending" ? (
                  <>
                    <StyledButton className="mini" onClick={() => onAccept(r.id)}>
                      {t("accept", { defaultValue: "同意" })}
                    </StyledButton>
                    <StyledButton className="mini ghost" onClick={() => onReject(r.id)}>
                      {t("reject", { defaultValue: "拒绝" })}
                    </StyledButton>
                  </>
                ) : null}
                {tab === "outgoing" && r.status === "pending" ? (
                  <StyledButton className="mini ghost" onClick={() => onCancel(r.id)}>
                    {t("withdraw", { defaultValue: "撤销" })}
                  </StyledButton>
                ) : null}
                {r.can_delete && r.status !== "pending" ? (
                  <StyledButton className="mini ghost" onClick={() => onDelete(r.id)}>
                    {t("delete_record", { defaultValue: "删除记录" })}
                  </StyledButton>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
