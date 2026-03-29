import { useEffect } from "react";

import useStreaming from "@/hooks/useStreaming";
import { useAppSelector } from "../app/store";
import { shallowEqual } from "react-redux";

export default function useSSE() {
  const loginUid = useAppSelector((store) => store.authData.user?.uid, shallowEqual);
  const { startStreaming } = useStreaming();

  const canStreaming = !!loginUid;

  useEffect(() => {
    if (canStreaming) {
      startStreaming();
    }
  }, [canStreaming]);

  return null;
}
