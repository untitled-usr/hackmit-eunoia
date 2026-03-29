import { LoaderIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "react-hot-toast";
import { Link } from "react-router-dom";
import { setActingUid } from "@/auth-state";
import AuthFooter from "@/components/AuthFooter";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/contexts/AuthContext";
import { useInstance } from "@/contexts/InstanceContext";
import useCurrentUser from "@/hooks/useCurrentUser";
import useLoading from "@/hooks/useLoading";
import useNavigateTo from "@/hooks/useNavigateTo";
import { Routes } from "@/router";
import { useTranslate } from "@/utils/i18n";

const SignIn = () => {
  const t = useTranslate();
  const navigateTo = useNavigateTo();
  const currentUser = useCurrentUser();
  const { initialize: initAuth } = useAuth();
  const { generalSetting: instanceGeneralSetting } = useInstance();
  const actionBtnLoadingState = useLoading(false);
  const [uidInput, setUidInput] = useState("");

  useEffect(() => {
    if (currentUser?.name) {
      window.location.href = Routes.ROOT;
    }
  }, [currentUser]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const uid = uidInput.trim();
    if (!uid) {
      toast.error("请输入用户 UID（数字）");
      return;
    }
    if (!/^\d+$/.test(uid)) {
      toast.error("UID 必须为数字");
      return;
    }
    if (actionBtnLoadingState.isLoading) return;

    try {
      actionBtnLoadingState.setLoading();
      setActingUid(uid);
      await initAuth();
      navigateTo("/");
    } catch (error: unknown) {
      console.error(error);
      toast.error("无效 UID 或用户不存在");
      setActingUid(null);
    } finally {
      actionBtnLoadingState.setFinish();
    }
  };

  return (
    <div className="py-4 sm:py-8 w-80 max-w-full min-h-svh mx-auto flex flex-col justify-start items-center">
      <div className="w-full py-4 grow flex flex-col justify-center items-center">
        <div className="w-full flex flex-row justify-center items-center mb-6">
          <img className="h-14 w-auto rounded-full shadow" src={instanceGeneralSetting.customProfile?.logoUrl || "/logo.webp"} alt="" />
          <p className="ml-2 text-5xl text-foreground opacity-80">{instanceGeneralSetting.customProfile?.title || "Memos"}</p>
        </div>
        <p className="w-full text-sm text-muted-foreground mb-2">
          使用内部用户 UID 作为当前身份（请求头 <code className="text-xs">X-Acting-Uid</code>）。注册成功后请使用返回的{" "}
          <code className="text-xs">users/&#123;id&#125;</code> 中的数字。
        </p>
        <form className="w-full mt-2" onSubmit={handleSubmit}>
          <div className="w-full flex flex-col gap-2">
            <span className="leading-8 text-muted-foreground">用户 UID</span>
            <Input
              className="w-full bg-background h-10"
              type="text"
              inputMode="numeric"
              placeholder="例如 1"
              value={uidInput}
              disabled={actionBtnLoadingState.isLoading}
              autoComplete="off"
              onChange={(e) => setUidInput(e.target.value)}
            />
          </div>
          <Button type="submit" className="w-full h-10 mt-6" disabled={actionBtnLoadingState.isLoading}>
            继续
            {actionBtnLoadingState.isLoading && <LoaderIcon className="w-5 h-auto ml-2 animate-spin opacity-60" />}
          </Button>
        </form>
        {!instanceGeneralSetting.disallowUserRegistration && (
          <p className="w-full mt-4 text-sm">
            <span className="text-muted-foreground">{t("auth.sign-up-tip")}</span>
            <Link to="/auth/signup" className="cursor-pointer ml-2 text-primary hover:underline" viewTransition>
              {t("common.sign-up")}
            </Link>
          </p>
        )}
      </div>
      <AuthFooter />
    </div>
  );
};

export default SignIn;
