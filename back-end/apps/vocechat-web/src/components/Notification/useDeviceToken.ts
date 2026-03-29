import { useEffect, useState } from "react";
import { getApp, getApps, initializeApp } from "firebase/app";
import { getMessaging, getToken } from "firebase/messaging";

import { firebaseConfig, KEY_DEVICE_TOKEN } from "@/app/config";

let requesting = false;
let error = false;
const useDeviceToken = (vapidKey: string) => {
  const [token, setToken] = useState<string>(localStorage.getItem(KEY_DEVICE_TOKEN) || "");
  useEffect(() => {
    if (token) {
      localStorage.setItem(KEY_DEVICE_TOKEN, token);
    }
  }, [token]);

  useEffect(() => {
    // https only
    if (!navigator.serviceWorker || requesting || error || token) return;
    requesting = true;
    const app = getApps().length > 0 ? getApp() : initializeApp(firebaseConfig);
    const messaging = getMessaging(app);
    getToken(messaging, {
      vapidKey
    })
      .then((currentToken) => {
        if (currentToken) {
          setToken((prev) => (prev === currentToken ? prev : currentToken));
        } else {
          // Show permission request UI
          console.info("No registration token available. Request permission to generate one.");
        }
        requesting = false;
      })
      .catch((err) => {
        requesting = false;
        error = true;
        console.info("An error occurred while retrieving token. ", err);
      });
  }, [token, vapidKey]);
  return token;
};

export default useDeviceToken;
