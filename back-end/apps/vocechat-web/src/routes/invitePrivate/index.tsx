import { useEffect } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { shallowEqual } from "react-redux";

import { useJoinPrivateChannelMutation, useLazyGetChannelQuery } from "../../app/services/channel";
import { useAppSelector } from "../../app/store";
import StyledButton from "../../components/styled/Button";

const InvitePrivate = () => {
  const { channel_id } = useParams();
  const server = useAppSelector((store) => store.server, shallowEqual);
  const navigateTo = useNavigate();
  const [joinChannel, { isLoading, data, isSuccess }] = useJoinPrivateChannelMutation();
  const [fetchChannelInfo, { data: channel, isSuccess: fetchChannelSuccess }] =
    useLazyGetChannelQuery();
  const [searchParams] = useSearchParams(new URLSearchParams(location.search));
  const magic_token = searchParams.get("magic_token") ?? "";
  const isTokenValid = Boolean(magic_token);

  useEffect(() => {
    if (channel_id) {
      fetchChannelInfo(+channel_id);
    }
  }, [channel_id]);
  useEffect(() => {
    if (data && isSuccess) {
      navigateTo(`/chat/channel/${data.gid}`);
      location.reload();
    }
  }, [isSuccess, data, navigateTo]);
  const handleJoin = async () => {
    const resp = await joinChannel({ magic_token });
    console.log({ resp });

    if (resp && "error" in resp && resp.error) {
      const err = resp.error as { status?: number | string };
      const key = typeof err.status === "number" ? err.status : 0;
      switch (key) {
        case 409:
          alert("The invite link is invalid or expired");
          break;
        case 412:
          alert("You are already in this channel");
          break;
        default:
          break;
      }
    }
  };
  if (!fetchChannelSuccess) return null;
  return (
    <div className="flex-center flex-col gap-4 h-screen overflow-x-hidden overflow-y-auto dark:bg-gray-700 dark:text-slate-100">
      <div className="flex flex-col gap-4 items-center py-8 px-10 rounded-lg shadow-md bg-slate-100/30 dark:bg-gray-800 text-center">
        <div className="flex flex-col items-center gap-4">
          <img src={server.logo} className="w-20 h-20" alt="server logo" />
          <h2 className="text-2xl font-bold">{server.name}</h2>
        </div>
        <span>
          {isTokenValid ? (
            <>
              You are invited to join private channel{" "}
              <strong className="text-primary-400">#{channel?.name}</strong>
            </>
          ) : (
            "Missing invite token in link"
          )}
        </span>
        <StyledButton disabled={isLoading || !isTokenValid} onClick={handleJoin}>
          Join
        </StyledButton>
      </div>
    </div>
  );
};

export default InvitePrivate;
