import { MouseEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { useGetLoginConfigQuery } from "@/app/services/server";
import { useAppSelector } from "@/app/store";
import Avatar from "@/components/Avatar";
import Button from "@/components/styled/Button";
import ProfileBasicEditModal from "./ProfileBasicEditModal";
import RemoveAccountConfirmModal from "./RemoveAccountConfirmModal";
import UpdatePasswordModal from "./UpdatePasswordModal";
import PasskeyManagement from "./PasskeyManagement";
import { shallowEqual } from "react-redux";
import ServerVersionChecker from "@/components/ServerVersionChecker";

type EditField = "name" | "";
export default function MyAccount() {
  const { t } = useTranslation("member");
  const { t: ct } = useTranslation();
  const [passwordModal, setPasswordModal] = useState(false);
  const [editModal, setEditModal] = useState<EditField>("");
  const [removeConfirmVisible, setRemoveConfirmVisible] = useState(false);
  const { data: loginConfig } = useGetLoginConfigQuery();
  const EditModalInfo = {
    name: {
      label: t("username"),
      title: t("change_name"),
      intro: t("change_name_desc"),
    },
  };

  const sessionUid = useAppSelector((store) => store.authData.user?.uid || 0);
  const fromContacts = useAppSelector((store) => store.users.byId[sessionUid], shallowEqual);
  const fromAuth = useAppSelector((store) => store.authData.user, shallowEqual);
  const loginUser = fromContacts ?? fromAuth;

  const handleBasicEdit = (evt: MouseEvent<HTMLButtonElement>) => {
    const { edit } = evt.currentTarget.dataset as { edit: EditField };
    setEditModal(edit);
  };

  const closeBasicEditModal = () => {
    setEditModal("");
  };

  const togglePasswordModal = () => {
    setPasswordModal((prev) => !prev);
  };
  const toggleRemoveAccountModalVisible = () => {
    setRemoveConfirmVisible((prev) => !prev);
  };

  if (!loginUser) return null;
  const { uid, avatar, name } = loginUser;
  return (
    <>
      <div className="flex flex-col items-start gap-8">
        <div className="md:p-6 flex flex-col items-center w-full md:w-[512px] md:bg-gray-100 md:dark:bg-gray-800 md:rounded-2xl">
          <Avatar className="rounded-full" src={avatar ?? ""} name={name} width={96} height={96} />
          <div className="mt-2 mb-16 font-bold text-lg text-gray-800 dark:text-white">
            {name} <span className="font-normal text-gray-500">#{uid}</span>
          </div>
          <div className="w-full flex items-start justify-between mb-6">
            <div className="flex flex-col text-gray-500 dark:text-gray-50">
              <span className="text-xs uppercase  font-semibold">{t("username")}</span>
              <span className="text-sm ">
                {name} <span className="text-gray-600 dark:text-gray-400"> #{uid}</span>
              </span>
            </div>
            <Button data-edit="name" onClick={handleBasicEdit} className="">
              {ct("action.edit")}
            </Button>
          </div>

          <div className="w-full flex items-start justify-between mb-6">
            <div className="flex flex-col text-gray-500 dark:text-gray-50">
              <span className="text-xs uppercase  font-semibold">{t("password")}</span>
              <span className="text-sm">*********</span>
            </div>
            <Button onClick={togglePasswordModal}>{ct("action.edit")}</Button>
          </div>
        </div>
        
        {loginConfig?.passkey && (
          <ServerVersionChecker empty version="0.5.5">
            <div className="w-full md:w-[512px] md:p-6 md:bg-gray-100 md:dark:bg-gray-800 md:rounded-2xl">
              <PasskeyManagement />
            </div>
          </ServerVersionChecker>
        )}

        {/* uid 1 是初始账户，不能删 */}
        {uid != 1 && (
          <Button className="danger" onClick={toggleRemoveAccountModalVisible}>
            {t("delete_account")}
          </Button>
        )}
      </div>
      {editModal && (
        <ProfileBasicEditModal
          type="text"
          valueKey="name"
          {...EditModalInfo.name}
          value={name}
          closeModal={closeBasicEditModal}
        />
      )}
      {passwordModal && <UpdatePasswordModal closeModal={togglePasswordModal} />}
      {removeConfirmVisible && (
        <RemoveAccountConfirmModal closeModal={toggleRemoveAccountModalVisible} />
      )}
    </>
  );
}
