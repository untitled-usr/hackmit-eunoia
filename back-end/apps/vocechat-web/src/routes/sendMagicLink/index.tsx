import { useEffect } from "react";

export default function SendMagicLinkPage() {
  useEffect(() => {
    window.location.replace("/#/login");
  }, []);
  return null;
}
