import { FC } from "react";

/** Passkeys removed in acting-uid mode. */
const PasskeyManagement: FC = () => {
  return <p className="text-sm text-gray-500">Passkeys are not available in this deployment.</p>;
};

export default PasskeyManagement;
