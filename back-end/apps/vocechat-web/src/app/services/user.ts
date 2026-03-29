import { createApi } from "@reduxjs/toolkit/query/react";

import { ContentTypeKey, MuteDTO } from "@/types/message";
import {
  AutoDeleteMsgDTO,
  BotAPIKey,
  ContactAction,
  ContactResponse,
  ContactStatus,
  FriendRequestDTO,
  FriendRequestRecordDTO,
  User,
  UserCreateDTO,
  UserDTO,
  UserForAdmin,
  UserForAdminDTO,
  UserRemarkDTO,
} from "@/types/user";
import { ContentTypes } from "../config";
import { updateAutoDeleteSetting, updateMute } from "../slices/footprint";
import { fillUsers, updateContactStatus as updateStatus } from "../slices/users";
import { RootState } from "../store";
// import toast from "react-hot-toast";
import baseQuery from "./base.query";
import { onMessageSendStarted } from "./handlers";
import { encodeBase64 } from "@/utils";
import { updateLoginUser } from "../slices/auth.data";

export const userApi = createApi({
  reducerPath: "userApi",
  baseQuery,
  tagTypes: ["UserContacts", "FriendRequests", "Blacklist"],
  endpoints: (builder) => ({
    getUsers: builder.query<User[], void>({
      query: () => ({ url: `/user` }),
      transformResponse: (data: User[]) => {
        return data.map((user) => ({
          ...user,
          avatar: "",
        }));
      },
      async onQueryStarted(data, { dispatch, queryFulfilled, getState }) {
        try {
          const { data: users } = await queryFulfilled;
          const {
            authData: { user: loginUser },
          } = getState() as RootState;
          dispatch(
            fillUsers(
              users.map((u) => {
                const status = loginUser?.uid == u.uid ? "added" : "";
                return {
                  ...u,
                  status,
                };
              })
            )
          );
        } catch {
          console.log("get user list error");
        }
      },
    }),
    getContacts: builder.query<ContactResponse[], void>({
      query: () => ({ url: `/user/contacts` }),
      providesTags: ["UserContacts"],
      async onQueryStarted(data, { dispatch, queryFulfilled }) {
        try {
          const { data: users } = await queryFulfilled;
          const payloads = users.map((c) => {
            const uid = c.target_uid;
            const status = c.contact_info.status as ContactStatus;
            return {
              uid,
              status,
              removed_by_peer: Boolean(c.contact_info.removed_by_peer)
            };
          });
          dispatch(updateStatus(payloads));
        } catch {
          console.log("get contact list error");
        }
      },
    }),
    deleteUser: builder.query<void, number>({
      query: (uid) => ({ url: `/admin/user/${uid}`, method: "DELETE" }),
    }),
    createUser: builder.mutation<UserForAdmin, UserCreateDTO>({
      query: (data) => ({
        url: `/admin/user`,
        body: data,
        method: "POST",
      }),
    }),
    searchUser: builder.mutation<User, { search_type: "id" | "name"; keyword: string }>({
      query: (input) => ({
        url: `/user/search`,
        body: input,
        method: "POST",
      }),
      transformResponse: (user: User) => ({
        ...user,
        avatar: "",
      }),
    }),
    getBlacklist: builder.query<User[], void>({
      query: () => ({ url: `/user/blacklist` }),
      providesTags: ["Blacklist"],
      transformResponse: (data: User[]) =>
        data.map((user) => ({
          ...user,
          avatar: "",
        }))
    }),
    sendFriendRequest: builder.mutation<
      number,
      { receiver_uid: number; message?: string }
    >({
      query: (body) => ({
        url: `/user/friend_requests`,
        method: "POST",
        body: { receiver_uid: body.receiver_uid, message: body.message ?? "" },
      }),
      invalidatesTags: ["UserContacts", "FriendRequests"],
    }),
    acceptFriendRequest: builder.mutation<void, number>({
      query: (id) => ({
        url: `/user/friend_requests/${id}/accept`,
        method: "POST",
      }),
      invalidatesTags: ["UserContacts", "FriendRequests"],
    }),
    rejectFriendRequest: builder.mutation<void, number>({
      query: (id) => ({
        url: `/user/friend_requests/${id}/reject`,
        method: "POST",
      }),
      invalidatesTags: ["FriendRequests"],
    }),
    cancelFriendRequest: builder.mutation<void, number>({
      query: (id) => ({
        url: `/user/friend_requests/${id}/cancel`,
        method: "POST",
      }),
      invalidatesTags: ["FriendRequests"],
    }),
    removeFriend: builder.mutation<void, number>({
      query: (uid) => ({
        url: `/user/friends/${uid}`,
        method: "DELETE",
      }),
      invalidatesTags: ["UserContacts"],
      async onQueryStarted(uid, { dispatch, queryFulfilled }) {
        try {
          await queryFulfilled;
          dispatch(
            updateStatus({
              uid,
              status: "",
              removed_by_peer: false,
            })
          );
        } catch {
          /* fallback handled by caller */
        }
      },
    }),
    addToBlacklist: builder.mutation<void, number>({
      query: (uid) => ({
        url: `/user/blacklist/${uid}`,
        method: "POST",
      }),
      invalidatesTags: ["UserContacts", "Blacklist"],
    }),
    removeFromBlacklist: builder.mutation<void, number>({
      query: (uid) => ({
        url: `/user/blacklist/${uid}`,
        method: "DELETE",
      }),
      invalidatesTags: ["Blacklist", "UserContacts"],
    }),
    getFriendRequestsIncoming: builder.query<FriendRequestDTO[], void>({
      query: () => ({ url: `/user/friend_requests/incoming` }),
      providesTags: ["FriendRequests"],
    }),
    getFriendRequestsOutgoing: builder.query<FriendRequestDTO[], void>({
      query: () => ({ url: `/user/friend_requests/outgoing` }),
      providesTags: ["FriendRequests"],
    }),
    getFriendRequestRecords: builder.query<FriendRequestRecordDTO[], void>({
      query: () => ({ url: `/user/friend_requests/records` }),
      providesTags: ["FriendRequests"],
    }),
    deleteFriendRequestRecord: builder.mutation<void, number>({
      query: (id) => ({
        url: `/user/friend_requests/${id}`,
        method: "DELETE",
      }),
      invalidatesTags: ["FriendRequests"],
    }),
    pinChat: builder.mutation<void, { uid: number } | { gid: number }>({
      query: (data) => ({
        url: `/user/pin_chat`,
        method: "POST",
        body: { target: data },
      }),
    }),
    unpinChat: builder.mutation<void, { uid: number } | { gid: number }>({
      query: (data) => ({
        url: `/user/unpin_chat`,
        method: "POST",
        body: { target: data },
      }),
    }),
    updateUser: builder.mutation<UserForAdmin, UserForAdminDTO>({
      query: ({ id, ...rest }) => ({
        url: `/admin/user/${id}`,
        body: rest,
        method: "PUT",
      }),
    }),
    updateRemark: builder.mutation<void, UserRemarkDTO>({
      query: (data) => ({
        url: `/user/contact_remark`,
        body: data,
        method: "PUT",
      }),
    }),

    updateAutoDeleteMsg: builder.mutation<void, AutoDeleteMsgDTO>({
      query: (data) => ({
        url: `/user/burn-after-reading`,
        body: data,
        method: "POST",
      }),
      async onQueryStarted(data, { dispatch, queryFulfilled }) {
        try {
          await queryFulfilled;
          if (data.users) {
            // users
            dispatch(updateAutoDeleteSetting({ burn_after_reading_users: data.users }));
          }
          if (data.groups) {
            // channel
            dispatch(updateAutoDeleteSetting({ burn_after_reading_groups: data.groups }));
          }
        } catch {
          console.log("update auto delete message setting error");
        }
      },
    }),

    updateContactStatus: builder.mutation<void, { action: ContactAction; target_uid: number }>({
      query: (payload) => ({
        url: `/user/update_contact_status`,
        method: "POST",
        body: payload,
      }),
      async onQueryStarted(data, { dispatch, queryFulfilled }) {
        const map = {
          add: "added",
          block: "blocked",
          remove: "",
          unblock: "",
        };
        try {
          await queryFulfilled;
          const status = map[data.action] as ContactStatus;
          dispatch(
            updateStatus({
              uid: data.target_uid,
              status,
              removed_by_peer: false,
            })
          );
        } catch (error) {
          console.log("update mute failed", error);
        }
      },
    }),
    updateMuteSetting: builder.mutation<void, MuteDTO>({
      query: (data) => ({
        url: `/user/mute`,
        method: "POST",
        body: data,
      }),
      async onQueryStarted(data, { dispatch, queryFulfilled }) {
        try {
          await queryFulfilled;
          dispatch(updateMute(data));
        } catch (error) {
          console.log("update mute failed", error);
        }
      },
    }),
    getUserByAdmin: builder.query<UserForAdmin, number>({
      query: (uid) => ({ url: `/admin/user/${uid}` }),
    }),
    // bot operations
    createBotAPIKey: builder.mutation<void, { uid: number; name: string }>({
      query: ({ uid, name }) => ({
        url: `/admin/user/bot-api-key/${uid}`,
        method: "POST",
        body: { name },
      }),
    }),
    getBotAPIKeys: builder.query<BotAPIKey[], number>({
      query: (uid) => ({ url: `/admin/user/bot-api-key/${uid}` }),
    }),
    deleteBotAPIKey: builder.query<void, { uid: number; kid: number }>({
      query: ({ uid, kid }) => ({ url: `/admin/user/bot-api-key/${uid}/${kid}`, method: "DELETE" }),
    }),
    // bot operations end
    updateInfo: builder.mutation<User, UserDTO>({
      query: (data) => ({
        url: `/user`,
        method: "PUT",
        body: data,
      }),
      async onQueryStarted(params, { dispatch, queryFulfilled }) {
        try {
          const { data } = await queryFulfilled;
          dispatch(updateLoginUser({ ...data, avatar: "" }));
        } catch (error) {
          console.log("update login user failed", error);
        }
      },
    }),
    sendMsg: builder.mutation<
      number,
      {
        id: number;
        content: string | { path: string };
        type: ContentTypeKey;
        properties?: object;
        from_uid?: number;
        ignoreLocal?: boolean;
        reply_mid?: number | null;
      }
    >({
      query: ({ id, content, type = "text", properties = "" }) => ({
        headers: {
          "content-type": ContentTypes[type],
          "X-Properties": properties ? encodeBase64(JSON.stringify(properties)) : "",
        },
        url: `/user/${id}/send`,
        method: "POST",
        body: type == "file" ? JSON.stringify(content) : content,
      }),
      async onQueryStarted(param1, param2) {
        await onMessageSendStarted.call(this, param1, param2, "user");
      },
    }),
  }),
});

export const {
  useUpdateRemarkMutation,
  useLazyGetUsersQuery,
  useLazyGetBlacklistQuery,
  useGetBlacklistQuery,
  useGetUserByAdminQuery,
  useUpdateAutoDeleteMsgMutation,
  useCreateUserMutation,
  useUpdateUserMutation,
  useUpdateMuteSettingMutation,
  useLazyDeleteUserQuery,
  useUpdateInfoMutation,
  useLazyGetContactsQuery,
  useSendMsgMutation,
  useCreateBotAPIKeyMutation,
  useLazyDeleteBotAPIKeyQuery,
  useGetBotAPIKeysQuery,
  useSearchUserMutation,
  useUpdateContactStatusMutation,
  usePinChatMutation,
  useUnpinChatMutation,
  useSendFriendRequestMutation,
  useAcceptFriendRequestMutation,
  useRejectFriendRequestMutation,
  useCancelFriendRequestMutation,
  useRemoveFriendMutation,
  useAddToBlacklistMutation,
  useRemoveFromBlacklistMutation,
  useLazyGetFriendRequestsIncomingQuery,
  useLazyGetFriendRequestsOutgoingQuery,
  useLazyGetFriendRequestRecordsQuery,
  useDeleteFriendRequestRecordMutation,
} = userApi;
