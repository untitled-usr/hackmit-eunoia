import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import clsx from "clsx";
import { NavLink } from "react-router-dom";

import { useGetBlacklistQuery, useRemoveFromBlacklistMutation } from "@/app/services/user";
import Avatar from "@/components/Avatar";
import GoBackNav from "@/components/GoBackNav";
import StyledButton from "@/components/styled/Button";

export default function BlockedUsersPage() {
  const { t } = useTranslation("member");
  const { data: list = [], isLoading, refetch } = useGetBlacklistQuery();
  const [unblock, { isLoading: ub }] = useRemoveFromBlacklistMutation();

  const handleUnblock = async (uid: number) => {
    try {
      await unblock(uid).unwrap();
      toast.success(t("unblocked", { defaultValue: "已取消屏蔽" }));
      refetch();
    } catch {
      toast.error(t("action_failed", { defaultValue: "操作失败" }));
    }
  };

  return (
    <div className={clsx("flex flex-col h-screen md:h-full md:pt-2 md:pb-2 md:pr-12")}>
      <div className="md:rounded-2xl bg-white dark:bg-gray-800 shadow flex flex-col flex-1 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-600 flex items-center gap-3">
          <NavLink to="/users" className="text-primary-500 text-sm md:hidden">
            ←
          </NavLink>
          <h1 className="text-base font-semibold text-gray-800 dark:text-gray-100">
            {t("blocked_users", { defaultValue: "屏蔽列表" })}
          </h1>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {isLoading ? (
            <p className="text-sm text-gray-500">…</p>
          ) : list.length === 0 ? (
            <p className="text-sm text-gray-500">{t("empty_blocked", { defaultValue: "暂无屏蔽用户" })}</p>
          ) : (
            <ul className="space-y-2">
              {list.map((u) => (
                <li
                  key={u.uid}
                  className="flex items-center justify-between gap-3 p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700/50"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <Avatar src={u.avatar} name={u.name} width={40} height={40} />
                    <div className="min-w-0">
                      <div className="font-medium text-gray-800 dark:text-gray-100 truncate">{u.name}</div>
                      <div className="text-xs text-gray-500 truncate">UID {u.uid}</div>
                    </div>
                  </div>
                  <StyledButton className="mini" disabled={ub} onClick={() => handleUnblock(u.uid)}>
                    {t("unblock", { defaultValue: "取消屏蔽" })}
                  </StyledButton>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <GoBackNav />
    </div>
  );
}
