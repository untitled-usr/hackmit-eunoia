import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";
import { getActingUid } from "@/auth-state";
import { useAuth } from "@/contexts/AuthContext";
import { memoKeys } from "@/hooks/useMemoQueries";
import { userKeys } from "@/hooks/useUserQueries";

const INITIAL_RETRY_DELAY_MS = 1000;
const MAX_RETRY_DELAY_MS = 30000;
const RETRY_BACKOFF_MULTIPLIER = 2;

export type SSEConnectionStatus = "connected" | "disconnected" | "connecting";

type Listener = () => void;

let _status: SSEConnectionStatus = "disconnected";
const _listeners = new Set<Listener>();

function getSSEStatus(): SSEConnectionStatus {
  return _status;
}

function setSSEStatus(s: SSEConnectionStatus) {
  if (_status !== s) {
    _status = s;
    _listeners.forEach((l) => l());
  }
}

function subscribeSSEStatus(listener: Listener): () => void {
  _listeners.add(listener);
  return () => _listeners.delete(listener);
}

export function useSSEConnectionStatus(): SSEConnectionStatus {
  return useSyncExternalStore(subscribeSSEStatus, getSSEStatus, getSSEStatus);
}

export function useLiveMemoRefresh() {
  const queryClient = useQueryClient();
  const { currentUser } = useAuth();
  const retryDelayRef = useRef(INITIAL_RETRY_DELAY_MS);
  const abortControllerRef = useRef<AbortController | null>(null);

  const currentUserName = currentUser?.name;
  const handleEvent = useCallback((event: SSEChangeEvent) => handleSSEEvent(event, queryClient), [queryClient]);

  useEffect(() => {
    let mounted = true;
    let retryTimeout: ReturnType<typeof setTimeout> | null = null;

    const connect = async () => {
      if (!mounted) return;

      const uid = getActingUid();
      if (!uid) {
        setSSEStatus("disconnected");
        return;
      }

      setSSEStatus("connecting");
      const abortController = new AbortController();
      abortControllerRef.current = abortController;

      try {
        const response = await fetch("/api/v1/sse", {
          headers: {
            "X-Acting-Uid": uid,
          },
          signal: abortController.signal,
          credentials: "include",
        });

        if (!response.ok || !response.body) {
          throw new Error(`SSE connection failed: ${response.status}`);
        }

        retryDelayRef.current = INITIAL_RETRY_DELAY_MS;
        setSSEStatus("connected");

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (mounted) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          const messages = buffer.split("\n\n");
          buffer = messages.pop() || "";

          for (const message of messages) {
            if (!message.trim()) continue;

            for (const line of message.split("\n")) {
              if (line.startsWith("data: ")) {
                const jsonStr = line.slice(6);
                try {
                  const event = JSON.parse(jsonStr) as SSEChangeEvent;
                  handleEvent(event);
                } catch {
                  // Ignore malformed JSON.
                }
              }
            }
          }
        }
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === "AbortError") {
          setSSEStatus("disconnected");
          return;
        }
      }

      setSSEStatus("disconnected");

      if (mounted) {
        const delay = retryDelayRef.current;
        retryDelayRef.current = Math.min(delay * RETRY_BACKOFF_MULTIPLIER, MAX_RETRY_DELAY_MS);
        retryTimeout = setTimeout(connect, delay);
      }
    };

    connect();

    return () => {
      mounted = false;
      setSSEStatus("disconnected");
      retryDelayRef.current = INITIAL_RETRY_DELAY_MS;
      if (retryTimeout) {
        clearTimeout(retryTimeout);
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [handleEvent, currentUserName]);
}

interface SSEChangeEvent {
  type: string;
  name: string;
}

function handleSSEEvent(event: SSEChangeEvent, queryClient: ReturnType<typeof useQueryClient>) {
  switch (event.type) {
    case "memo.created":
      queryClient.invalidateQueries({ queryKey: memoKeys.lists() });
      queryClient.invalidateQueries({ queryKey: userKeys.stats() });
      break;

    case "memo.updated":
      queryClient.invalidateQueries({ queryKey: memoKeys.detail(event.name) });
      queryClient.invalidateQueries({ queryKey: memoKeys.lists() });
      break;

    case "memo.deleted":
      queryClient.removeQueries({ queryKey: memoKeys.detail(event.name) });
      queryClient.invalidateQueries({ queryKey: memoKeys.lists() });
      queryClient.invalidateQueries({ queryKey: userKeys.stats() });
      break;

    case "memo.comment.created":
      queryClient.invalidateQueries({ queryKey: memoKeys.comments(event.name) });
      queryClient.invalidateQueries({ queryKey: memoKeys.detail(event.name) });
      break;

    case "reaction.upserted":
    case "reaction.deleted":
      queryClient.invalidateQueries({ queryKey: memoKeys.detail(event.name) });
      queryClient.invalidateQueries({ queryKey: memoKeys.lists() });
      break;
  }
}
