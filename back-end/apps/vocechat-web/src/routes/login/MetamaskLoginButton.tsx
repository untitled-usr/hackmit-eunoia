import { LoginCredential } from "@/types/auth";
import { AuthType } from "@/types/common";

/** MetaMask login removed in acting-uid mode. */
export default function MetamaskLoginButton(_props: {
  login: (params: LoginCredential) => void;
  type?: AuthType;
}) {
  return null;
}
