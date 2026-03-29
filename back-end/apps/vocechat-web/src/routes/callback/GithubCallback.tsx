import { FC, useEffect } from "react";

export type GithubLoginSource = string;

/** GitHub OAuth removed; redirect to login. */
const GithubCallback: FC<{ code?: string; from?: GithubLoginSource }> = () => {
  useEffect(() => {
    window.location.replace("/#/login");
  }, []);
  return null;
};

export default GithubCallback;
