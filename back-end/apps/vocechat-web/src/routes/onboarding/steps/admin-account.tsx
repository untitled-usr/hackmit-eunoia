import { FC, useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { useDispatch } from "react-redux";
import { useWizard } from "react-use-wizard";

import { KEY_UID } from "@/app/config";
import { useLazyGetMeQuery } from "@/app/services/auth";
import { useUpdateServerMutation } from "@/app/services/server";
import { useUpdateUserMutation } from "@/app/services/user";
import { setAuthData, updateInitialized } from "@/app/slices/auth.data";
import StyledButton from "@/components/styled/Button";
import StyledInput from "@/components/styled/Input";

type Props = {
  serverName: string;
};
const AdminAccount: FC<Props> = ({ serverName }) => {
  const { t } = useTranslation("welcome", { keyPrefix: "onboarding" });
  const { nextStep } = useWizard();
  const formRef = useRef<HTMLFormElement>(null);
  const dispatch = useDispatch();
  const [getMe, { isLoading: loadingMe, isError: meError }] = useLazyGetMeQuery();
  const [updateUser, { isLoading: updatingPw }] = useUpdateUserMutation();
  const [updateServer, { isLoading: isUpdatingServer }] = useUpdateServerMutation();

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");

  useEffect(() => {
    if (meError) {
      toast.error(`Failed to connect as system admin`);
    }
  }, [meError]);

  return (
    <div className="h-full flex-center flex-col text-center w-[360px] m-auto dark:text-gray-100">
      <span className="text-2xl mb-2 font-bold">{t("admin_title")}</span>
      <span className="text-sm mb-6">{t("admin_desc")}</span>
      <form ref={formRef} action="/" className="flex flex-col gap-2 w-full">
        <StyledInput
          className="large"
          type="password"
          placeholder={t("admin_password_placeholder") as string}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <StyledInput
          className="large"
          type="password"
          placeholder={t("admin_password_confirm_placeholder") as string}
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
      </form>
      <p className="text-xs text-gray-500 dark:text-gray-400 mt-2 mb-2">{t("admin_uid_hint")}</p>
      <StyledButton
        className="mt-6 w-full"
        onClick={async () => {
          const wantsPassword = password.length > 0 || confirm.length > 0;
          if (wantsPassword) {
            if (password.length < 6 || confirm.length < 6) {
              toast.error("Password must be at least 6 characters");
              return;
            }
            if (password !== confirm) {
              toast.error("Passwords do not match");
              return;
            }
          }
          localStorage.setItem(KEY_UID, "1");
          try {
            const me = await getMe().unwrap();
            const user = {
              uid: me.uid,
              name: me.name,
              gender: me.gender as 0 | 1,
              language: me.language,
              is_admin: me.is_admin,
              avatar_updated_at: me.avatar_updated_at,
              create_by: me.create_by,
              is_bot: me.is_bot
            };
            dispatch(setAuthData({ user }));
            if (wantsPassword) {
              await updateUser({ id: 1, password }).unwrap();
            }
            dispatch(updateInitialized(true));
            await updateServer({
              name: serverName
            }).unwrap();
            nextStep();
          } catch {
            toast.error("Continue failed — check server is running and uid 1 exists");
          }
        }}
      >
        {!(loadingMe || updatingPw || isUpdatingServer) ? t("sign") : "..."}
      </StyledButton>
    </div>
  );
};
export default AdminAccount;
