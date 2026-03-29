import { FormEvent, useState } from "react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { useRegisterMutation } from "@/app/services/auth";
import Button from "@/components/styled/Button";
import Input from "@/components/styled/Input";

/** Public registration: server assigns uid; display name becomes uid string. */
export default function Register() {
  const { t: ct } = useTranslation();
  const navigateTo = useNavigate();
  const [register, { isLoading }] = useRegisterMutation();
  const [password, setPassword] = useState("");

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await register({
        password: password || undefined,
        gender: 0,
        language: "en-US"
      }).unwrap();
      toast.success(ct("tip.reg"));
      navigateTo("/");
    } catch {
      toast.error("Registration failed");
    }
  };

  return (
    <div className="flex flex-col gap-6 w-full max-w-md">
      <h1 className="text-xl font-semibold dark:text-gray-100">{ct("reg.title", "Register")}</h1>
      <p className="text-sm text-gray-500 dark:text-gray-400">
        {ct("reg.id_only_hint", "No signup fields required — the server creates your account and returns your user ID.")}
      </p>
      <form className="flex flex-col gap-4" onSubmit={onSubmit}>
        <Input
          type="password"
          placeholder={ct("password", "Password (optional)")}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <Button type="submit" disabled={isLoading}>
          {isLoading ? "…" : ct("reg.btn", "Create account")}
        </Button>
      </form>
      <p className="text-sm text-gray-500">
        <Link to="/login" className="underline">
          {ct("sign_in", "Sign in")}
        </Link>
      </p>
    </div>
  );
}
