import { ChangeEvent, useEffect, useState } from "react";
import { toast } from "react-hot-toast";
import { useTranslation } from "react-i18next";

import { useCreateUserMutation } from "../../../app/services/user";
import Modal from "../../../components/Modal";
import Button from "../../../components/styled/Button";
import Input from "../../../components/styled/Input";
import StyledModal from "../../../components/styled/Modal";

type Props = {
  closeModal: () => void;
};
const CreateModal = ({ closeModal }: Props) => {
  const [createUser, { isSuccess, isLoading, error }] = useCreateUserMutation();
  const { t } = useTranslation("setting", { keyPrefix: "bot" });
  const [webhook_url, setWebhook_url] = useState("");
  const { t: ct } = useTranslation();

  const handleInputChange = (evt: ChangeEvent<HTMLInputElement>) => {
    setWebhook_url(evt.target.value);
  };

  const handleCreateBot = () => {
    createUser({
      is_bot: true,
      is_admin: false,
      gender: 1,
      language: "en-US",
      password: "",
      webhook_url: webhook_url.trim() === "" ? undefined : webhook_url
    });
  };

  useEffect(() => {
    if (!error || !("status" in error)) return;
    switch (error.status) {
      case 406:
        toast.error("Invalid Webhook URL!");
        break;
      case 409:
        toast.error("Could not create bot (conflict). Retry.");
        break;
      default:
        break;
    }
  }, [error]);

  useEffect(() => {
    if (isSuccess) {
      toast.success("Create Bot Successfully!");
      closeModal();
    }
  }, [isSuccess, closeModal]);

  return (
    <Modal id="modal-modal">
      <StyledModal
        title={t("create_title")}
        description={t("create_desc")}
        buttons={
          <>
            <Button className="cancel" onClick={closeModal}>
              {ct("action.cancel")}
            </Button>
            <Button onClick={handleCreateBot}>{isLoading ? "Creating" : ct("action.done")}</Button>
          </>
        }
      >
        <div className="w-full flex flex-col gap-2">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            The server assigns a numeric user id; you can rename the bot in admin after creation.
          </p>
          <div className="flex flex-col items-start gap-1 w-full">
            <label htmlFor="webhook_url" className="text-sm text-gray-500">
              Webhook URL (Optional)
            </label>
            <Input
              onChange={handleInputChange}
              value={webhook_url}
              id="webhook_url"
              type="url"
              placeholder="Please input webhook url"
            />
          </div>
        </div>
      </StyledModal>
    </Modal>
  );
};

export default CreateModal;
