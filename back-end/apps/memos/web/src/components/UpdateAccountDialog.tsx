import { isEqual } from "lodash-es";
import { XIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "react-hot-toast";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useInstance } from "@/contexts/InstanceContext";
import { convertFileToBase64 } from "@/helpers/utils";
import useCurrentUser from "@/hooks/useCurrentUser";
import { useUpdateUser } from "@/hooks/useUserQueries";
import { handleError } from "@/lib/error";
import { User_Role } from "@/types/proto/api/v1/user_service_pb";
import { useTranslate } from "@/utils/i18n";
import UserAvatar from "./UserAvatar";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
}

interface State {
  avatarUrl: string;
  username: string;
  displayName: string;
  description: string;
  gender: string;
  age: number;
}

function UpdateAccountDialog({ open, onOpenChange, onSuccess }: Props) {
  const t = useTranslate();
  const currentUser = useCurrentUser();
  const { generalSetting: instanceGeneralSetting } = useInstance();
  const { mutateAsync: updateUser } = useUpdateUser();
  const isNormalUser = currentUser?.role === User_Role.USER;
  const [state, setState] = useState<State>({
    avatarUrl: currentUser?.avatarUrl ?? "",
    username: currentUser?.username ?? "",
    displayName: currentUser?.displayName ?? "",
    description: currentUser?.description ?? "",
    gender: currentUser?.gender ?? "",
    age: currentUser?.age ?? 0,
  });

  const handleCloseBtnClick = () => {
    onOpenChange(false);
  };

  const setPartialState = (partialState: Partial<State>) => {
    setState((state) => {
      return {
        ...state,
        ...partialState,
      };
    });
  };

  const handleAvatarChanged = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      const image = files[0];
      if (image.size > 2 * 1024 * 1024) {
        toast.error("Max file size is 2MB");
        return;
      }
      try {
        const base64 = await convertFileToBase64(image);
        setPartialState({
          avatarUrl: base64,
        });
      } catch (error) {
        console.error(error);
        toast.error(`Failed to convert image to base64`);
      }
    }
  };

  const handleDisplayNameChanged = (e: React.ChangeEvent<HTMLInputElement>) => {
    setPartialState({
      displayName: e.target.value as string,
    });
  };

  const handleUsernameChanged = (e: React.ChangeEvent<HTMLInputElement>) => {
    setPartialState({
      username: e.target.value as string,
    });
  };

  const handleDescriptionChanged = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setState((state) => {
      return {
        ...state,
        description: e.target.value as string,
      };
    });
  };

  const handleGenderChanged = (e: React.ChangeEvent<HTMLInputElement>) => {
    setState((state) => {
      return {
        ...state,
        gender: e.target.value as string,
      };
    });
  };

  const handleAgeChanged = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value.trim();
    setState((state) => {
      return {
        ...state,
        age: value === "" ? 0 : Number.parseInt(value, 10) || 0,
      };
    });
  };

  const handleSaveBtnClick = async () => {
    if (!isNormalUser && state.username === "") {
      toast.error(t("message.fill-all"));
      return;
    }

    try {
      const updateMask = [];
      if (!isNormalUser && !isEqual(currentUser?.username, state.username)) {
        updateMask.push("username");
      }
      if (!isNormalUser && !isEqual(currentUser?.displayName, state.displayName)) {
        updateMask.push("display_name");
      }
      if (!isNormalUser && !isEqual(currentUser?.avatarUrl, state.avatarUrl)) {
        updateMask.push("avatar_url");
      }
      if (!isEqual(currentUser?.description, state.description)) {
        updateMask.push("description");
      }
      if (!isEqual(currentUser?.gender, state.gender)) {
        updateMask.push("gender");
      }
      if (!isEqual(currentUser?.age ?? 0, state.age)) {
        updateMask.push("age");
      }
      await updateUser({
        user: {
          name: currentUser?.name,
          username: state.username,
          displayName: state.displayName,
          avatarUrl: state.avatarUrl,
          description: state.description,
          gender: state.gender,
          age: state.age,
        },
        updateMask,
      });
      toast.success(t("message.update-succeed"));
      onSuccess?.();
      onOpenChange(false);
    } catch (error: unknown) {
      await handleError(error, toast.error, {
        context: "Update account",
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t("setting.account-section.update-information")}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          {!isNormalUser && (
            <div className="flex flex-row items-center gap-2">
              <Label>{t("common.avatar")}</Label>
              <label className="relative cursor-pointer hover:opacity-80">
                <UserAvatar className="w-10 h-10" avatarUrl={state.avatarUrl} />
                <input type="file" accept="image/*" className="absolute invisible w-full h-full inset-0" onChange={handleAvatarChanged} />
              </label>
              {state.avatarUrl && (
                <XIcon
                  className="w-4 h-auto cursor-pointer opacity-60 hover:opacity-80"
                  onClick={() =>
                    setPartialState({
                      avatarUrl: "",
                    })
                  }
                />
              )}
            </div>
          )}
          {!isNormalUser && (
            <div className="grid gap-2">
              <Label htmlFor="username">
                {t("common.username")}
                <span className="text-sm text-muted-foreground ml-1">({t("setting.account-section.username-note")})</span>
              </Label>
              <Input
                id="username"
                value={state.username}
                onChange={handleUsernameChanged}
                disabled={instanceGeneralSetting.disallowChangeUsername}
              />
            </div>
          )}
          {!isNormalUser && (
            <div className="grid gap-2">
              <Label htmlFor="displayName">
                {t("common.nickname")}
                <span className="text-sm text-muted-foreground ml-1">({t("setting.account-section.nickname-note")})</span>
              </Label>
              <Input
                id="displayName"
                value={state.displayName}
                onChange={handleDisplayNameChanged}
                disabled={instanceGeneralSetting.disallowChangeNickname}
              />
            </div>
          )}
          <div className="grid gap-2">
            <Label htmlFor="description">{t("common.description")}</Label>
            <Textarea id="description" rows={2} value={state.description} onChange={handleDescriptionChanged} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="gender">Gender</Label>
            <Input id="gender" value={state.gender} onChange={handleGenderChanged} placeholder="Gender" maxLength={64} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="age">Age</Label>
            <Input
              id="age"
              type="number"
              min={0}
              max={200}
              value={state.age > 0 ? state.age : ""}
              onChange={handleAgeChanged}
              placeholder="Age"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={handleCloseBtnClick}>
            {t("common.cancel")}
          </Button>
          <Button onClick={handleSaveBtnClick}>{t("common.save")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default UpdateAccountDialog;
