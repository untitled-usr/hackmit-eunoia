import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../context/useAuth'
import { MidAuthHttpError } from '../lib/midAuth'
import { HomeSignInPrompt } from '../components/HomeSignInPrompt'
import {
  acceptFriendRequest,
  cancelFriendRequest,
  listFriendRequestRecords,
  listIncomingFriendRequests,
  listOutgoingFriendRequests,
  rejectFriendRequest,
  type FriendRequestItem,
  type FriendRequestRecordItem,
  type SocialUserIdentity,
} from '../lib/midAuthSocialChat'

function formatIdentityLabel(identity?: SocialUserIdentity, fallbackVoceUid?: string): string {
  if (identity) {
    const displayName = identity.displayName?.trim() || ''
    const username = identity.username?.trim() || ''
    if (displayName && username) {
      return displayName === username ? username : `${displayName} (@${username})`
    }
    return displayName || username || identity.publicId || fallbackVoceUid || 'Unknown user'
  }
  return fallbackVoceUid || 'Unknown user'
}

export function MessageNotificationsPanel() {
  const { user, loading } = useAuth()
  const [incoming, setIncoming] = useState<FriendRequestItem[]>([])
  const [outgoing, setOutgoing] = useState<FriendRequestItem[]>([])
  const [records, setRecords] = useState<FriendRequestRecordItem[]>([])
  const [loadingEvents, setLoadingEvents] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hint, setHint] = useState<string | null>(null)

  const toErrorMessage = useCallback((err: unknown, fallback = 'Request failed'): string => {
    if (err instanceof MidAuthHttpError) {
      if (err.status === 401 || err.status === 403) return 'Session expired. Please sign in again.'
      if (err.status === 404) return 'Social notifications are not enabled on the server.'
      if (err.status === 503) return 'Social service is temporarily unavailable (503). Please try again later.'
      return err.message
    }
    return err instanceof Error ? err.message : fallback
  }, [])

  const loadEvents = useCallback(async () => {
    if (!user) return
    setLoadingEvents(true)
    setError(null)
    try {
      const [incomingRows, outgoingRows, recordRows] = await Promise.all([
        listIncomingFriendRequests(),
        listOutgoingFriendRequests(),
        listFriendRequestRecords(),
      ])
      setIncoming(incomingRows)
      setOutgoing(outgoingRows)
      setRecords(recordRows)
    } catch (e) {
      setError(toErrorMessage(e, 'Failed to load notifications.'))
    } finally {
      setLoadingEvents(false)
    }
  }, [toErrorMessage, user])

  useEffect(() => {
    if (!user || loading) {
      setIncoming([])
      setOutgoing([])
      setRecords([])
      setError(null)
      return
    }
    void loadEvents()
  }, [user, loading, loadEvents])

  const onAccept = useCallback(
    async (requestId: string) => {
      try {
        await acceptFriendRequest(requestId)
        setHint('Friend request accepted.')
        await loadEvents()
      } catch (e) {
        setHint(toErrorMessage(e, 'Action failed.'))
      }
    },
    [loadEvents, toErrorMessage],
  )

  const onReject = useCallback(
    async (requestId: string) => {
      try {
        await rejectFriendRequest(requestId)
        setHint('Friend request rejected.')
        await loadEvents()
      } catch (e) {
        setHint(toErrorMessage(e, 'Action failed.'))
      }
    },
    [loadEvents, toErrorMessage],
  )

  const onCancel = useCallback(
    async (requestId: string) => {
      try {
        await cancelFriendRequest(requestId)
        setHint('Request cancelled.')
        await loadEvents()
      } catch (e) {
        setHint(toErrorMessage(e, 'Action failed.'))
      }
    },
    [loadEvents, toErrorMessage],
  )

  if (!loading && !user) {
    return <HomeSignInPrompt title="Ocean Whispers" description="Sign in to view friend requests and social events." />
  }

  return (
    <div
      id="message-notifications"
      className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden"
    >
      <div className="flex min-h-0 min-w-0 flex-1 flex-col px-6 pb-6 pt-2 md:px-8 md:pb-8">
        <div className="mx-auto min-h-0 w-full max-w-3xl flex-1 overflow-y-auto overscroll-contain">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-700">Friend requests & social events</h3>
            <button
              type="button"
              onClick={() => void loadEvents()}
              className="rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-700 hover:bg-white"
            >
              Refresh
            </button>
          </div>
          {error ? <p className="mb-3 text-xs text-red-600">{error}</p> : null}
          {hint ? <p className="mb-3 text-xs text-slate-600">{hint}</p> : null}
          {loadingEvents ? <p className="mb-3 text-xs text-slate-500">Loading…</p> : null}

          <div className="space-y-3">
            {incoming.map((item) => (
              <div
                key={`incoming-${item.id}`}
                className="glass flex items-center justify-between rounded-xl p-4"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm text-slate-800">
                    📥 Incoming friend request #{item.id}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    From {formatIdentityLabel(item.requester, item.requesterVoceUid)}
                    {' · '}
                    {item.createdAt || 'Unknown time'}
                  </div>
                  {item.requester ? (
                    <div className="mt-1 text-[11px] text-slate-500">
                      {item.requester.email} · {item.requester.publicId}
                    </div>
                  ) : null}
                  {item.message ? <div className="mt-1 text-xs text-slate-600">Message: {item.message}</div> : null}
                </div>
                <div className="ml-3 flex shrink-0 gap-2">
                  <button
                    type="button"
                    onClick={() => void onAccept(item.id)}
                    className="rounded-md border border-slate-200 px-2 py-1 text-xs text-sky-700 hover:bg-white"
                  >
                    Accept
                  </button>
                  <button
                    type="button"
                    onClick={() => void onReject(item.id)}
                    className="rounded-md border border-slate-200 px-2 py-1 text-xs hover:bg-white"
                  >
                    Reject
                  </button>
                </div>
              </div>
            ))}

            {outgoing.map((item) => (
              <div
                key={`outgoing-${item.id}`}
                className="glass flex items-center justify-between rounded-xl p-4"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm text-slate-800">
                    📤 Outgoing friend request #{item.id}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    To {formatIdentityLabel(item.receiver, item.receiverVoceUid)}
                    {' · '}
                    {item.createdAt || 'Unknown time'}
                  </div>
                  {item.receiver ? (
                    <div className="mt-1 text-[11px] text-slate-500">
                      {item.receiver.email} · {item.receiver.publicId}
                    </div>
                  ) : null}
                  {item.message ? <div className="mt-1 text-xs text-slate-600">Message: {item.message}</div> : null}
                </div>
                <div className="ml-3 shrink-0">
                  <button
                    type="button"
                    onClick={() => void onCancel(item.id)}
                    className="rounded-md border border-slate-200 px-2 py-1 text-xs hover:bg-white"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ))}

            {records.map((item) => (
              <div
                key={`record-${item.id}`}
                className="glass flex items-center justify-between rounded-xl p-4"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm text-slate-800">
                    🗂 Request record #{item.id} · {item.status}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    Requester {formatIdentityLabel(item.requester, item.requesterVoceUid)}
                    {' → '}
                    Receiver {formatIdentityLabel(item.receiver, item.receiverVoceUid)}
                  </div>
                  {item.requester && item.receiver ? (
                    <div className="mt-1 text-[11px] text-slate-500">
                      Requester: {item.requester.email} · Receiver: {item.receiver.email}
                    </div>
                  ) : null}
                  <div className="mt-1 text-xs text-slate-500">
                    Created {item.createdAt || 'Unknown'} · Responded {item.respondedAt || 'Unknown'}
                  </div>
                </div>
              </div>
            ))}

            {!loadingEvents &&
            incoming.length === 0 &&
            outgoing.length === 0 &&
            records.length === 0 ? (
              <div className="glass rounded-xl p-4 text-sm text-slate-500">
                No notifications yet.
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}
