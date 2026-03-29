import { createSlice, PayloadAction } from "@reduxjs/toolkit";

import { FriendRequestDTO } from "@/types/user";

export interface SocialState {
  blockedUserIds: number[];
  incomingFriendRequests: FriendRequestDTO[];
  outgoingFriendRequests: FriendRequestDTO[];
}

const initialState: SocialState = {
  blockedUserIds: [],
  incomingFriendRequests: [],
  outgoingFriendRequests: []
};

export function mergeFriendRequestEventsForUser(
  state: SocialState,
  loginUid: number,
  events: FriendRequestDTO[]
) {
  for (const e of events) {
    const drop = (arr: FriendRequestDTO[]) => {
      const i = arr.findIndex((x) => x.id === e.id);
      if (i >= 0) arr.splice(i, 1);
    };
    drop(state.incomingFriendRequests);
    drop(state.outgoingFriendRequests);
    if (e.status === "pending") {
      if (e.receiver_uid === loginUid) {
        state.incomingFriendRequests.push(e);
      }
      if (e.requester_uid === loginUid) {
        state.outgoingFriendRequests.push(e);
      }
    }
  }
}

const socialSlice = createSlice({
  name: "social",
  initialState,
  reducers: {
    resetSocial() {
      return initialState;
    },
    setSocialFromUserSettings(
      state,
      action: PayloadAction<{
        blocked_users?: number[];
        incoming_friend_requests?: FriendRequestDTO[];
        outgoing_friend_requests?: FriendRequestDTO[];
      }>
    ) {
      const p = action.payload;
      if (p.blocked_users) {
        state.blockedUserIds = p.blocked_users;
      }
      if (p.incoming_friend_requests) {
        state.incomingFriendRequests = p.incoming_friend_requests;
      }
      if (p.outgoing_friend_requests) {
        state.outgoingFriendRequests = p.outgoing_friend_requests;
      }
    },
    mergeFriendRequests(
      state,
      action: PayloadAction<{ loginUid: number; events: FriendRequestDTO[] }>
    ) {
      mergeFriendRequestEventsForUser(state, action.payload.loginUid, action.payload.events);
    },
    addBlockedUsers(state, action: PayloadAction<number[]>) {
      for (const id of action.payload) {
        if (!state.blockedUserIds.includes(id)) {
          state.blockedUserIds.push(id);
        }
      }
    },
    removeBlockedUsers(state, action: PayloadAction<number[]>) {
      const s = new Set(action.payload);
      state.blockedUserIds = state.blockedUserIds.filter((id) => !s.has(id));
    }
  }
});

export const {
  resetSocial,
  setSocialFromUserSettings,
  mergeFriendRequests,
  addBlockedUsers,
  removeBlockedUsers
} = socialSlice.actions;

export default socialSlice.reducer;
