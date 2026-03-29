import { useEffect } from "react";
import initCache, { useRehydrate } from "@/app/cache";
import { useLazyGetFavoritesQuery, useLazyLoadMoreMessagesQuery } from "@/app/services/message";
import { useLazyGetServerVersionQuery, useLazyGetSystemCommonQuery } from "@/app/services/server";
import { useLazyGetContactsQuery, useLazyGetUsersQuery } from "@/app/services/user";
import { useAppSelector } from "@/app/store";
import useLicense from "./useLicense";
import useStreaming from "./useStreaming";
import { shallowEqual } from "react-redux";

let preloadChannelMsgs = false;
export default function usePreload() {
  const { isLoading: loadingLicense } = useLicense(false);
  const [preloadChannelMessages] = useLazyLoadMoreMessagesQuery();
  const { rehydrate, rehydrated } = useRehydrate();
  const ready = useAppSelector((store) => store.ui.ready, shallowEqual);
  const loginUid = useAppSelector((store) => store.authData.user?.uid, shallowEqual);
  const enableContacts = useAppSelector(
    (store) => store.server.contact_verification_enable,
    shallowEqual
  );
  const channelIds = useAppSelector((store) => store.channels.ids, shallowEqual);
  const isGuest = useAppSelector((store) => store.authData.guest, shallowEqual);
  const channelMessageData = useAppSelector((store) => store.channelMessage, shallowEqual);
  const { startStreaming, stopStreaming } = useStreaming();
  const [
    getFavorites,
    {
      isLoading: favoritesLoading,
      isSuccess: favoritesSuccess,
      isError: favoritesError,
      data: favorites
    }
  ] = useLazyGetFavoritesQuery();
  const [
    getUsers,
    { isLoading: usersLoading, isSuccess: usersSuccess, isError: usersError, data: users }
  ] = useLazyGetUsersQuery();
  const [getContacts, { data: contacts }] = useLazyGetContactsQuery();

  const [
    getServerVersion,
    {
      data: serverVersion,
      isSuccess: serverVersionSuccess,
      isError: serverVersionError,
      isLoading: loadingServerVersion,
    }
  ] = useLazyGetServerVersionQuery();
  const [getSystemCommon] = useLazyGetSystemCommonQuery();
  useEffect(() => {
    initCache();
    rehydrate();
    getServerVersion();
    // return ()=>{
    //   stopStreaming()
    // }
  }, []);
  // 在 guest 的时候 预取 channel 数据
  useEffect(() => {
    if (isGuest && channelIds.length > 0 && !preloadChannelMsgs) {
      const tmps = channelIds.filter((cid) => !channelMessageData[cid]);
      tmps.forEach((id) => {
        if (id) {
          preloadChannelMessages({ id, limit: 50 });
        }
      });
      preloadChannelMsgs = true;
    }
  }, [channelIds, channelMessageData, isGuest]);
  useEffect(() => {
    if (rehydrated && serverVersion) {
      getUsers().then(() => {
        if (!isGuest) {
          getContacts();
        }
      });
      getFavorites();
      getSystemCommon();
    }
  }, [rehydrated, serverVersion, isGuest]);
  const canStreaming = !!loginUid && rehydrated && !ready;

  useEffect(() => {
    if (canStreaming) {
      // 先停掉，再连接
      stopStreaming();
      setTimeout(() => {
        startStreaming();
      }, 100);
    }
  }, [canStreaming]);
  return {
    loading:
      usersLoading || favoritesLoading || !rehydrated || loadingLicense || loadingServerVersion,
    error: usersError || favoritesError || serverVersionError,
    // Avoid deadlock on home loading screen when any optional preload request fails once.
    success:
      (usersSuccess || usersError) &&
      (favoritesSuccess || favoritesError) &&
      (serverVersionSuccess || serverVersionError),
    data: {
      users: enableContacts ? contacts : users,
      favorites
    }
  };
}
