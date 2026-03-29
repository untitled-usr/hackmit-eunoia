import { FormEvent, useEffect, useState } from "react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";

import { useLazyGetInitializedQuery, useLazyGetMeQuery, useRegisterMutation } from "@/app/services/auth";
import { useAppSelector } from "@/app/store";
import Button from "@/components/styled/Button";
import Input from "@/components/styled/Input";
import StyledLabel from "@/components/styled/Label";
import SelectLanguage from "../../components/Language";
import Downloads from "../../components/Downloads";
import ServerVersionChecker from "@/components/ServerVersionChecker";
import { KEY_UID } from "@/app/config";
import BASE_URL from "@/app/config";
export default function LoginPage() {
  const { t } = useTranslation("auth");
  const { t: ct } = useTranslation();
  const { name: serverName, logo } = useAppSelector((store) => store.server);
  const [getInitialized] = useLazyGetInitializedQuery();
  const [getMe] = useLazyGetMeQuery();
  const [register, { isLoading: regLoading }] = useRegisterMutation();

  const [uidInput, setUidInput] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getInitialized();
    const existing = localStorage.getItem(KEY_UID);
    if (existing) setUidInput(existing);
    // Trigger once on mount; lazy trigger identity is not required as dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const continueWithUidValue = async (rawUid: string, fromRegister = false) => {
    const v = rawUid.trim();
    if (!v || !/^\d+$/.test(v)) {
      toast.error("Please enter numeric user id");
      return;
    }
    setLoading(true);
    try {
      localStorage.setItem(KEY_UID, v);
      await getMe().unwrap();
      toast.success(ct("tip.login") || "OK");
      location.href = "/#/";
    } catch (err: any) {
      const code =
        typeof err?.status === "number"
          ? err.status
          : err?.status === "PARSING_ERROR"
            ? err?.originalStatus
            : err?.status;
      if (code === "FETCH_ERROR" || typeof code === "undefined") {
        toast.error("无法连接后端(7922)。请确认使用 http:// 打开 7925 页面。");
        return;
      }
      if (!fromRegister) {
        localStorage.removeItem(KEY_UID);
        toast.error("Invalid uid or user not found");
      } else {
        toast.error(`注册成功，但自动登录失败。请手动用 UID ${v} 登录`);
      }
    } finally {
      setLoading(false);
    }
  };
  const continueWithUid = async () => {
    await continueWithUidValue(uidInput, false);
  };

  const onRegister = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const user = await register({
        password: regPassword || undefined,
        gender: 0,
        language: "en-US"
      }).unwrap();
      const newUid = `${user.uid}`;
      setUidInput(newUid);
      toast.success(`注册成功，UID: ${newUid}`);
      await continueWithUidValue(newUid, true);
    } catch (err: any) {
      const code =
        typeof err?.status === "number"
          ? err.status
          : err?.status === "PARSING_ERROR"
            ? err?.originalStatus
            : err?.status;
      const reasonRaw = err?.data?.reason;
      const reason = typeof reasonRaw === "string" ? reasonRaw.toLowerCase() : "";
      const message =
        (typeof err?.data === "string" ? err.data : undefined) || err?.data?.message;
      if (code === 409 && (reason === "name_conflict" || reason === "nameconflict")) {
        toast.error("注册冲突，请重试");
        return;
      }
      if (code === 403) {
        toast.error("当前服务器已关闭注册");
        return;
      }
      if (code === 451) {
        toast.error(message || "注册被许可证策略拦截");
        return;
      }
      if (code === "FETCH_ERROR" || typeof code === "undefined") {
        toast.error("无法连接后端(7922)。请确认使用 http:// 打开 7925 页面。");
        return;
      }
      const detail =
        message ||
        (typeof err?.error === "string" ? err.error : "") ||
        (typeof err === "string" ? err : "");
      toast.error(detail || `Registration failed (${String(code ?? "unknown")})`);
    }
  };

  return (
    <div className="flex h-screen">
      <div className="flex flex-col gap-5 items-center w-full md:w-1/2 min-h-full justify-center px-4 md:px-8">
        <ServerVersionChecker version="0.0.0">
          <>
        <div className="flex flex-col items-center mb-2">
          {logo ? <img src={logo} className="w-16 h-16 mb-3" alt="" /> : null}
          <h2 className="text-2xl font-semibold text-gray-900 dark:text-gray-100 text-center">
            {serverName || "VoceChat"}
          </h2>
          <p className="text-sm text-gray-500 mt-1 text-center max-w-sm">
            Memos-style: use numeric user id as <code className="text-xs">X-Acting-Uid</code>, or register.
          </p>
          <p className="text-xs text-gray-400 mt-1 text-center break-all">API: {BASE_URL}</p>
        </div>

        <div className="w-full max-w-sm flex flex-col gap-3">
          <StyledLabel>User UID</StyledLabel>
          <Input
            className="large"
            name="uid"
            value={uidInput}
            placeholder="e.g. 1"
            onChange={(e) => setUidInput(e.target.value)}
          />
          <Button className="small" onClick={continueWithUid} disabled={loading}>
            {loading ? "…" : t("login.title", { defaultValue: "Continue" })}
          </Button>
        </div>

        <div className="w-full max-w-sm border-t border-gray-200 dark:border-gray-700 pt-6 mt-2">
          <h3 className="text-sm font-medium mb-3">Register</h3>
          <form className="flex flex-col gap-3" onSubmit={onRegister}>
            <Input
              className="large"
              type="password"
              placeholder="Password (optional)"
              value={regPassword}
              onChange={(e) => setRegPassword(e.target.value)}
            />
            <Button type="submit" className="small" disabled={regLoading}>
              {regLoading ? "…" : "Register"}
            </Button>
          </form>
        </div>

        <div className="h-4" />
        <SelectLanguage />
          </>
        </ServerVersionChecker>
      </div>
      <Downloads />
    </div>
  );
}
