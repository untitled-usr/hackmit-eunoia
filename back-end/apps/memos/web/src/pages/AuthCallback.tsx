import { Navigate } from "react-router-dom";
import { ROUTES } from "@/router/routes";

/** OAuth callback is no longer used; redirect to acting-user sign-in. */
const AuthCallback = () => {
  return <Navigate to={ROUTES.AUTH} replace />;
};

export default AuthCallback;
