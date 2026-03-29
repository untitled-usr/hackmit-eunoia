import { FC, ReactElement } from "react";
import { Navigate } from "react-router-dom";

import { useAppSelector } from "@/app/store";
import { shallowEqual } from "react-redux";

interface Props {
  children: ReactElement;
}
/** Guest login removed (Memos-style acting uid only). */
const GuestOnly: FC<Props> = ({ children }) => {
  const { token } = useAppSelector((store) => store.authData, shallowEqual);
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return children;
};

export default GuestOnly;
