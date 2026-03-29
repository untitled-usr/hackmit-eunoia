import { FC, ReactElement } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useGetInitializedQuery } from "@/app/services/auth";
import { useAppSelector } from "@/app/store";
import Loading from "./Loading";
import { shallowEqual } from "react-redux";

interface Props {
  children: ReactElement;
  redirectTo?: string;
}

/** Memos 式：空库时仍允许进入登录/注册，由公开 register 创建首用户；不走强制 onboarding */
function allowLoginWhenUninitialized(pathname: string) {
  return (
    pathname === "/login" ||
    pathname.startsWith("/register") ||
    pathname.startsWith("/invite_mobile")
  );
}

const RequireNoAuth: FC<Props> = ({ children, redirectTo = "/" }) => {
  const { pathname } = useLocation();
  const { isLoading } = useGetInitializedQuery();
  const { token, initialized, guest } = useAppSelector((store) => store.authData, shallowEqual);
  // Show loading instead of blank screen while initialization probe is pending.
  if (isLoading && !initialized) return <Loading fullscreen context="no-auth-init" />;
  if (!initialized && !allowLoginWhenUninitialized(pathname)) {
    return <Navigate to={`/onboarding`} replace />;
  }
  return token && !guest ? <Navigate to={redirectTo} replace /> : children;
};

export default RequireNoAuth;
