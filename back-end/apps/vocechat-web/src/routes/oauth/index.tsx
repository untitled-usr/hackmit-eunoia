import { FC, useEffect } from "react";

const OAuthPage: FC = () => {
  useEffect(() => {
    window.location.replace("/#/login");
  }, []);
  return null;
};

export default OAuthPage;
