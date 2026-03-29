import { createSlice, PayloadAction } from "@reduxjs/toolkit";

import { AuthData } from "@/types/auth";
import { User } from "@/types/user";
import { KEY_LOGIN_USER, KEY_PWA_INSTALLED, KEY_UID } from "../config";
import { StoredUser } from "./users";

interface State {
  initialized: boolean;
  guest: boolean;
  user: StoredUser | undefined;
  /** Legacy field: in Memos-style mode holds the same value as acting uid (stringified). */
  token: string;
  expireTime: number;
  refreshToken: string;
  roleChanged: boolean;
  voice: boolean;
}

const loginUser = localStorage.getItem(KEY_LOGIN_USER) || "";
const uidStored = localStorage.getItem(KEY_UID) || "";

const initialState: State = {
  initialized: true,
  guest: loginUser ? JSON.parse(loginUser).create_by == "guest" : false,
  user: loginUser ? JSON.parse(loginUser) : undefined,
  token: uidStored,
  expireTime: Number.MAX_SAFE_INTEGER,
  refreshToken: "",
  roleChanged: false,
  voice: false
};

const emptyState: State = {
  initialized: true,
  guest: false,
  user: undefined,
  token: "",
  expireTime: Number.MAX_SAFE_INTEGER,
  refreshToken: "",
  roleChanged: false,
  voice: false
};

function persistSession(user: User) {
  localStorage.setItem(KEY_LOGIN_USER, JSON.stringify(user));
  localStorage.setItem(KEY_UID, `${user.uid}`);
}

const authDataSlice = createSlice({
  name: "authData",
  initialState,
  reducers: {
    /** Memos-style: persist user and uid; no JWT. */
    setAuthData(state, { payload }: PayloadAction<AuthData | { user: User }>) {
      const user = payload.user;
      const token = "token" in payload && payload.token ? payload.token : `${user.uid}`;
      state.initialized =
        "initialized" in payload && payload.initialized !== undefined ? payload.initialized : true;
      state.user = { ...state.user, ...user, status: "added" };
      state.guest = user.create_by == "guest";
      state.token = token;
      state.refreshToken = "refresh_token" in payload ? payload.refresh_token : "";
      state.expireTime = Number.MAX_SAFE_INTEGER;
      persistSession(user);
    },
    updateLoginUser(state, { payload }: PayloadAction<Partial<StoredUser>>) {
      if (!state.user) return;
      const obj = { ...state.user, ...payload };
      Object.keys(obj).forEach((key) => {
        // @ts-ignore
        if (obj[key] === undefined) {
          // @ts-ignore
          delete obj[key];
        }
      });
      state.user = obj;
      localStorage.setItem(KEY_LOGIN_USER, JSON.stringify(obj));
    },
    updateRoleChanged(state, action: PayloadAction<boolean>) {
      state.roleChanged = action.payload;
    },
    resetAuthData() {
      localStorage.removeItem(KEY_UID);
      localStorage.removeItem(KEY_LOGIN_USER);
      localStorage.removeItem("VOCECHAT_TOKEN_EXPIRE");
      localStorage.removeItem("VOCECHAT_TOKEN");
      localStorage.removeItem("VOCECHAT_REFRESH_TOKEN");
      localStorage.removeItem(KEY_PWA_INSTALLED);
      window.USERS_VERSION = 0;
      window.AFTER_MID = 0;
      return emptyState;
    },
    updateInitialized(state, action: PayloadAction<boolean>) {
      state.initialized = action.payload;
    },
    updateToken() {
      /* no-op: JWT renew removed (acting uid mode) */
    }
  }
});

export const {
  updateInitialized,
  updateLoginUser,
  setAuthData,
  resetAuthData,
  updateToken,
  updateRoleChanged
} = authDataSlice.actions;
export default authDataSlice.reducer;
