import { useEffect } from "react";
import { Outlet, useOutletContext, useSearchParams } from "react-router-dom";

import SelectLanguage from "../../components/Language";
import Downloads from "../../components/Downloads";

type ContextType = { token: string };

/** Magic-link registration removed; optional token kept for outlet typing only. */
export default function RegContainer() {
  const [searchParams] = useSearchParams(new URLSearchParams(location.search));
  const magic_token = searchParams.get("magic_token") ?? "";
  useEffect(() => {
    if (magic_token) {
      window.location.replace("/#/login");
    }
  }, [magic_token]);
  if (magic_token) return null;
  return (
    <>
      <div className="flex-center h-screen overflow-x-hidden overflow-y-auto dark:bg-gray-700">
        <div className="py-8 px-10 shadow-md rounded-xl max-h-[95vh] overflow-y-auto overflow-x-hidden">
          <Outlet context={{ token: "" } satisfies ContextType} />
          <Downloads />
        </div>
      </div>
      <SelectLanguage />
    </>
  );
}

export function useMagicToken() {
  return useOutletContext<ContextType>();
}
