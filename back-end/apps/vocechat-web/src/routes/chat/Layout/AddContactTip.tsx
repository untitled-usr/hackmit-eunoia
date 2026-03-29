import { useState } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";

import IconAdd from "@/assets/icons/add.person.svg";
import IconBlock from "@/assets/icons/block.svg";
import {
  useSendFriendRequestMutation,
  useUpdateContactStatusMutation,
} from "../../../app/services/user";
import { useAppSelector } from "../../../app/store";
import { ContactAction } from "../../../types/user";
import { shallowEqual } from "react-redux";

// 勿用 `contact_verification_enable` 控制本组件：该字段来自 `/admin/system/common`，
// 自建部署常 404，默认 false 会导致陌生人加好友条永远不显示，好友流程看似「未生效」。
import Modal from "@/components/Modal";
import StyledButton from "@/components/styled/Button";
import Input from "@/components/styled/Input";

type Props = {
  uid: number;
};

const MAX_REASON = 200;

const AddContactTip = (props: Props) => {
  const { t } = useTranslation("chat");
  const [updateContactStatus] = useUpdateContactStatusMutation();
  const [sendFriendRequest, { isLoading: sending }] = useSendFriendRequestMutation();
  const [modalOpen, setModalOpen] = useState(false);
  const [reason, setReason] = useState("");
  const targetUser = useAppSelector((store) => store.users.byId[props.uid], shallowEqual);
  const outgoing = useAppSelector((store) => store.social.outgoingFriendRequests, shallowEqual);
  const pendingOut = outgoing.some((r) => r.receiver_uid === props.uid && r.status === "pending");

  const handleContactStatus = (action: ContactAction) => {
    updateContactStatus({ target_uid: props.uid, action });
  };

  const submitRequest = async () => {
    try {
      await sendFriendRequest({
        receiver_uid: props.uid,
        message: reason.trim().slice(0, MAX_REASON),
      }).unwrap();
      toast.success(t("friend_request_sent", { defaultValue: "好友申请已发送" }));
      setModalOpen(false);
      setReason("");
    } catch (err: any) {
      const status = err?.status;
      if (status === 409) {
        toast.error(
          t("friend_request_exists", {
            defaultValue: "申请已存在，请到“新的好友”中查看处理进度",
          })
        );
        return;
      }
      if (status === 403) {
        toast.error(t("friend_request_blocked", { defaultValue: "发送失败，对方可能已屏蔽你" }));
        return;
      }
      toast.error(t("friend_request_failed", { defaultValue: "发送失败，请稍后重试" }));
    }
  };

  const itemClass = `cursor-pointer flex flex-col items-center gap-1 rounded-lg w-32 text-primary-400 bg-gray-50 dark:bg-gray-800 text-sm pt-3.5 pb-3`;
  if (!targetUser) return null;
  if (targetUser.status == "added") return null;
  const blocked = targetUser.status == "blocked";
  return (
    <>
      {modalOpen && (
        <Modal>
          <div className="flex flex-col gap-3 w-96 max-w-[90vw] p-4 rounded-lg bg-gray-100 dark:bg-gray-900">
            <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">
              {t("friend_request_title", { defaultValue: "添加好友" })}
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {t("friend_request_hint", { defaultValue: "可选：填写简短验证消息（对方可见）" })}
            </p>
            <Input
              value={reason}
              onChange={(e) => setReason(e.target.value.slice(0, MAX_REASON))}
              placeholder={t("friend_request_placeholder", { defaultValue: "例如：我是…" })}
              className="w-full"
            />
            <div className="flex justify-end gap-2">
              <StyledButton className="mini ghost" onClick={() => setModalOpen(false)}>
                {t("cancel", { defaultValue: "取消" })}
              </StyledButton>
              <StyledButton className="mini" disabled={sending} onClick={submitRequest}>
                {t("send", { defaultValue: "发送" })}
              </StyledButton>
            </div>
          </div>
        </Modal>
      )}
      <div className="py-4 px-10 flex flex-col items-center gap-3 bg-slate-100 dark:bg-slate-600">
        <h3 className="text-gray-700 dark:text-gray-300 text-sm font-semibold">
          {blocked ? t("contact_block_tip") : t("contact_tip")}
        </h3>
        <ul className="flex gap-4">
          {!blocked && !pendingOut && (
            <li className={itemClass} onClick={() => setModalOpen(true)}>
              <IconAdd className="fill-primary-400" />
              <span>{t("add_contact")}</span>
            </li>
          )}
          {!blocked && pendingOut && (
            <li className={`${itemClass} opacity-80 cursor-default`}>
              <IconAdd className="fill-primary-400" />
              <span>{t("friend_request_pending", { defaultValue: "申请已发送" })}</span>
            </li>
          )}
          <li
            className={itemClass}
            onClick={
              blocked
                ? handleContactStatus.bind(null, "unblock")
                : handleContactStatus.bind(null, "block")
            }
          >
            <IconBlock className="stroke-primary-400" />
            <span>{blocked ? t("unblock") : t("block")}</span>
          </li>
        </ul>
      </div>
    </>
  );
};

export default AddContactTip;
