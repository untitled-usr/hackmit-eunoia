import { FC } from "react";
import { useTranslation } from "react-i18next";

interface Props {
  cid?: number;
}

/** Magic-link invites removed in acting-uid mode. */
const InviteByEmail: FC<Props> = () => {
  const { t } = useTranslation("chat");
  return (
    <div className="pt-4 text-sm text-gray-500 dark:text-gray-400">
      {t("invite_by_email")} — unavailable (use shareable invite link instead).
    </div>
  );
};

export default InviteByEmail;
