import { createApi } from "@reduxjs/toolkit/query/react";
import baseQuery from "./base.query";
import {
  AvailableChannelType,
  EnabledChannelType,
  ToggleChannelTypeDTO,
  UserNotificationChannel,
  CreateUserChannelDTO,
  UpdateUserChannelDTO,
} from "@/types/notification";

/**
 * vocechat-server fork has no `/admin/notification/*` or `/user/notification/*`.
 * Stub all endpoints so settings pages and hooks do not 404.
 */
export const notificationApi = createApi({
  reducerPath: "notificationApi",
  baseQuery,
  tagTypes: ["EnabledChannelTypes", "AvailableChannelTypes", "UserChannels"],
  endpoints: (builder) => ({
    getEnabledChannelTypes: builder.query<EnabledChannelType[], void>({
      queryFn: async () => ({ data: [] }),
      providesTags: ["EnabledChannelTypes"],
    }),
    toggleChannelType: builder.mutation<EnabledChannelType, ToggleChannelTypeDTO>({
      queryFn: async () => ({
        error: { status: 501, data: "notification_admin_not_supported" },
      }),
      invalidatesTags: ["EnabledChannelTypes", "AvailableChannelTypes"],
    }),
    deleteChannelType: builder.mutation<string, string>({
      queryFn: async () => ({
        error: { status: 501, data: "notification_admin_not_supported" },
      }),
      invalidatesTags: ["EnabledChannelTypes", "AvailableChannelTypes"],
    }),

    getAvailableChannelTypes: builder.query<AvailableChannelType[], void>({
      queryFn: async () => ({ data: [] }),
      providesTags: ["AvailableChannelTypes"],
    }),
    getUserChannels: builder.query<UserNotificationChannel[], void>({
      queryFn: async () => ({ data: [] }),
      providesTags: ["UserChannels"],
    }),
    createUserChannel: builder.mutation<UserNotificationChannel, CreateUserChannelDTO>({
      queryFn: async () => ({
        error: { status: 501, data: "notification_user_not_supported" },
      }),
      invalidatesTags: ["UserChannels"],
    }),
    updateUserChannel: builder.mutation<UserNotificationChannel, UpdateUserChannelDTO>({
      queryFn: async () => ({
        error: { status: 501, data: "notification_user_not_supported" },
      }),
      invalidatesTags: ["UserChannels"],
    }),
    deleteUserChannel: builder.mutation<string, number>({
      queryFn: async () => ({
        error: { status: 501, data: "notification_user_not_supported" },
      }),
      invalidatesTags: ["UserChannels"],
    }),
    testUserChannel: builder.mutation<string, number>({
      queryFn: async () => ({
        error: { status: 501, data: "notification_user_not_supported" },
      }),
    }),
  }),
});

export const {
  useGetEnabledChannelTypesQuery,
  useToggleChannelTypeMutation,
  useDeleteChannelTypeMutation,
  useGetAvailableChannelTypesQuery,
  useGetUserChannelsQuery,
  useCreateUserChannelMutation,
  useUpdateUserChannelMutation,
  useDeleteUserChannelMutation,
  useTestUserChannelMutation,
} = notificationApi;
