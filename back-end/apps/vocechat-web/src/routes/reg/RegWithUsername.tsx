import { FC, useEffect } from "react";

/** Legacy magic-link registration; redirect to login. */
const RegWithUsername: FC = () => {
  useEffect(() => {
    window.location.replace("/#/login");
  }, []);
  return null;
};

export default RegWithUsername;
