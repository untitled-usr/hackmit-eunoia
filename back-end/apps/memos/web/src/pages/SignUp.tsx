import copy from "copy-to-clipboard";
import { LoaderIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "react-hot-toast";
import { Link } from "react-router-dom";
import { setActingUid } from "@/auth-state";
import AuthFooter from "@/components/AuthFooter";
import { Button } from "@/components/ui/button";
import { userServiceClient } from "@/connect";
import { useAuth } from "@/contexts/AuthContext";
import { useInstance } from "@/contexts/InstanceContext";
import useLoading from "@/hooks/useLoading";
import useNavigateTo from "@/hooks/useNavigateTo";
import { handleError } from "@/lib/error";
import { useTranslate } from "@/utils/i18n";

function actingUidFromUserName(name: string): string | null {
  const prefix = "users/";
  if (!name.startsWith(prefix)) {
    return null;
  }
  return name.slice(prefix.length) || null;
}

const SignUp = () => {
  const t = useTranslate();
  const navigateTo = useNavigateTo();
  const actionBtnLoadingState = useLoading(false);
  const { initialize: initAuth } = useAuth();
  const { generalSetting: instanceGeneralSetting, profile, initialize: initInstance } = useInstance();
  const [registeredUid, setRegisteredUid] = useState<string | null>(null);

  const handleSignUpButtonClick = async () => {
    if (actionBtnLoadingState.isLoading) {
      return;
    }

    try {
      actionBtnLoadingState.setLoading();
      const created = await userServiceClient.createUser({});
      const uid = actingUidFromUserName(created.name);
      if (!uid) {
        throw new Error("invalid user name in create response");
      }
      setActingUid(uid);
      await initAuth();
      await initInstance();
      setRegisteredUid(uid);
      toast.success(`注册成功，您的用户 ID：${uid}`);
    } catch (error: unknown) {
      handleError(error, toast.error, {
        fallbackMessage: "Sign up failed",
      });
    }
    actionBtnLoadingState.setFinish();
  };

  const copyUid = async () => {
    if (!registeredUid) return;
    const text = registeredUid;
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        toast.success("已复制用户 ID");
        return;
      }
    } catch {
      /* fall through */
    }
    if (copy(text)) {
      toast.success("已复制用户 ID");
      return;
    }
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      ta.style.top = "0";
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      ta.setSelectionRange(0, text.length);
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      if (ok) {
        toast.success("已复制用户 ID");
        return;
      }
    } catch {
      /* ignore */
    }
    toast.error("复制失败，请手动选择复制");
  };

  const goHome = () => {
    navigateTo("/");
  };

  return (
    <div className="py-4 sm:py-8 w-80 max-w-full min-h-svh mx-auto flex flex-col justify-start items-center">
      <div className="w-full py-4 grow flex flex-col justify-center items-center">
        <div className="w-full flex flex-row justify-center items-center mb-6">
          <img className="h-14 w-auto rounded-full shadow" src={instanceGeneralSetting.customProfile?.logoUrl || "/logo.webp"} alt="" />
          <p className="ml-2 text-5xl text-foreground opacity-80">{instanceGeneralSetting.customProfile?.title || "Memos"}</p>
        </div>
        {!instanceGeneralSetting.disallowUserRegistration ? (
          <>
            <p className="w-full text-2xl mt-2 text-muted-foreground">{t("auth.create-your-account")}</p>
            <p className="w-full text-sm text-muted-foreground mt-1">一键注册，无需填写信息；登录时使用用户 UID。</p>
            {!registeredUid ? (
              <div className="flex flex-row justify-end items-center w-full mt-6">
                <Button type="button" className="w-full h-10" disabled={actionBtnLoadingState.isLoading} onClick={handleSignUpButtonClick}>
                  {t("common.sign-up")}
                  {actionBtnLoadingState.isLoading && <LoaderIcon className="w-5 h-auto ml-2 animate-spin opacity-60" />}
                </Button>
              </div>
            ) : (
              <div className="w-full mt-6 space-y-3 rounded-xl border border-emerald-200 dark:border-emerald-900 bg-emerald-50/80 dark:bg-emerald-950/40 p-4">
                <p className="text-sm font-medium text-emerald-900 dark:text-emerald-100">您的用户 ID（请保存，用于登录）</p>
                <code className="block w-full break-all rounded-lg bg-background border border-emerald-100 dark:border-emerald-900 px-3 py-2 text-xs">
                  {registeredUid}
                </code>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <Button type="button" variant="outline" className="flex-1" onClick={copyUid}>
                    复制用户 ID
                  </Button>
                  <Button type="button" className="flex-1" onClick={goHome}>
                    进入首页
                  </Button>
                </div>
              </div>
            )}
          </>
        ) : (
          <p className="w-full text-2xl mt-2 text-muted-foreground">Sign up is not allowed.</p>
        )}
        {!profile.admin ? (
          <p className="w-full mt-4 text-sm font-medium text-muted-foreground">{t("auth.host-tip")}</p>
        ) : (
          <p className="w-full mt-4 text-sm">
            <span className="text-muted-foreground">{t("auth.sign-in-tip")}</span>
            <Link to="/auth" className="cursor-pointer ml-2 text-primary hover:underline" viewTransition>
              {t("common.sign-in")}
            </Link>
          </p>
        )}
      </div>
      <AuthFooter />
    </div>
  );
};

export default SignUp;
