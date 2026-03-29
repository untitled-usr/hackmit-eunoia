import { useEffect } from "react";

export default function GuestPage() {
  useEffect(() => {
    window.location.replace("/#/login");
  }, []);
  return null;
}
