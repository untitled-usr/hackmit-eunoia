import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import clsx from "clsx";

import {
  useAcceptFriendRequestMutation,
  useCancelFriendRequestMutation,
  useLazyGetFriendRequestsIncomingQuery,
  useLazyGetFriendRequestsOutgoingQuery,
  useRejectFriendRequestMutation,
} from "@/app/services/user";
import { mergeFriendRequests, setSocialFromUserSettings } from "@/app/slices/social";
import { useAppDispatch, useAppSelector } from "@/app/store";
import { FriendRequestDTO } from "@/types/user";
import StyledButton from "@/components/styled/Button";
import { shallowEqual } from "react-redux";

export default function FriendRequestsPanel() {
  const { t } = useTranslation("member");
  const dispatch = useAppDispatch();
  const loginUid = useAppSelector((s) => s.authData.user?.uid, shallowEqual);
  const incoming = useAppSelector((s) => s.social.incomingFriendRequests, shallowEqual);
  const outgoing = useAppSelector((s) => s.social.outgoingFriendRequests, shallowEqual);
  const usersById = useAppSelector((s) => s.users.byId, shallowEqual);

  const [fetchIn] = useLazyGetFriendRequestsIncomingQuery();
  const [fetchOut] = useLazyGetFriendRequestsOutgoingQuery();
  const [accept] = useAcceptFriendRequestMutation();
  const [reject] = useRejectFriendRequestMutation();
  const [cancel] = useCancelFriendRequestMutation();

  useEffect(() => {
    if (!loginUid) return;
    (async () => {
      try {
        const [inR, outR] = await Promise.all([fetchIn().unwrap(), fetchOut().unwrap()]);
        dispatch(
          setSocialFromUserSettings({
            incoming_friend_requests: inR,
            outgoing_friend_requests: outR,
          })
        );
      } catch {
        /* SSE may already populate */
      }
    })();
  }, [loginUid, dispatch, fetchIn, fetchOut]);

  const nameOf = (uid: number) => usersById[uid]?.name ?? `#${uid}`;

  const onAccept = async (r: FriendRequestDTO) => {
    try {
      await accept(r.id).unwrap();
      dispatch(mergeFriendRequests({ loginUid: loginUid!, events: [{ ...r, status: "accepted" }] }));
      toast.success(t("friend_accepted", { defaultValue: "已接受好友申请" }));
    } catch {
      toast.error(t("action_failed", { defaultValue: "操作失败" }));
    }
  };

  const onReject = async (r: FriendRequestDTO) => {
    try {
      await reject(r.id).unwrap();
      dispatch(mergeFriendRequests({ loginUid: loginUid!, events: [{ ...r, status: "rejected" }] }));
    } catch {
      toast.error(t("action_failed", { defaultValue: "操作失败" }));
    }
  };

  const onCancel = async (r: FriendRequestDTO) => {
    try {
      await cancel(r.id).unwrap();
      dispatch(mergeFriendRequests({ loginUid: loginUid!, events: [{ ...r, status: "canceled" }] }));
    } catch {
      toast.error(t("action_failed", { defaultValue: "操作失败" }));
    }
  };

  const pendingIn = incoming.filter((r) => r.status === "pending");
  const pendingOut = outgoing.filter((r) => r.status === "pending");

  if (pendingIn.length === 0 && pendingOut.length === 0) return null;

  return (
    <div className="mx-2 mb-2 p-3 rounded-lg bg-gray-100 dark:bg-gray-700/80 text-sm space-y-3">
      {pendingIn.length > 0 && (
        <div>
          <div className="font-semibold text-gray-700 dark:text-gray-200 mb-2">
            {t("incoming_friend_requests", { defaultValue: "收到的好友申请" })}
          </div>
          <ul className="space-y-2">
            {pendingIn.map((r) => (
              <li
                key={r.id}
                className="flex flex-col gap-1 border border-gray-200 dark:border-gray-600 rounded-md p-2"
              >
                <span className="text-gray-800 dark:text-gray-100">{nameOf(r.requester_uid)}</span>
                {r.message ? (
                  <span className="text-xs text-gray-500 dark:text-gray-400">{r.message}</span>
                ) : null}
                <div className="flex gap-2">
                  <StyledButton className="mini" onClick={() => onAccept(r)}>
                    {t("accept", { defaultValue: "接受" })}
                  </StyledButton>
                  <StyledButton className="mini ghost" onClick={() => onReject(r)}>
                    {t("reject", { defaultValue: "拒绝" })}
                  </StyledButton>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
      {pendingOut.length > 0 && (
        <div>
          <div className="font-semibold text-gray-700 dark:text-gray-200 mb-2">
            {t("outgoing_friend_requests", { defaultValue: "待对方确认" })}
          </div>
          <ul className="space-y-2">
            {pendingOut.map((r) => (
              <li
                key={r.id}
                className={clsx(
                  "flex items-center justify-between gap-2",
                  "border border-gray-200 dark:border-gray-600 rounded-md p-2"
                )}
              >
                <span>{nameOf(r.receiver_uid)}</span>
                <StyledButton className="mini ghost" onClick={() => onCancel(r)}>
                  {t("withdraw", { defaultValue: "撤回" })}
                </StyledButton>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
