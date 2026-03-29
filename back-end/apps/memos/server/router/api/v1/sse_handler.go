package v1

import (
	"fmt"
	"log/slog"
	"net/http"
	"time"

	"github.com/labstack/echo/v5"

	"github.com/usememos/memos/server/auth"
	"github.com/usememos/memos/store"
)

const (
	// sseHeartbeatInterval is the interval between heartbeat pings to keep the connection alive.
	sseHeartbeatInterval = 30 * time.Second
)

// RegisterSSERoutes registers the SSE endpoint on the given Echo instance.
func RegisterSSERoutes(echoServer *echo.Echo, hub *SSEHub, storeInstance *store.Store, secret string) {
	authenticator := auth.NewAuthenticator(storeInstance, secret)
	echoServer.GET("/api/v1/sse", func(c *echo.Context) error {
		return handleSSE(c, hub, authenticator)
	})
}

// handleSSE handles the SSE connection for live memo refresh.
// The optional X-Acting-Uid header can be provided to act as a specific user.
func handleSSE(c *echo.Context, hub *SSEHub, authenticator *auth.Authenticator) error {
	result, err := authenticator.AuthenticateByActingUIDHeader(c.Request().Context(), c.Request().Header.Get("X-Acting-Uid"))
	if err != nil {
		return c.JSON(http.StatusUnauthorized, map[string]string{"error": "invalid X-Acting-Uid"})
	}
	authCtx := auth.ApplyToContext(c.Request().Context(), result)
	c.SetRequest(c.Request().WithContext(authCtx))

	// Set SSE headers.
	w := c.Response()
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("X-Accel-Buffering", "no") // Disable nginx buffering
	w.WriteHeader(http.StatusOK)

	// Flush headers immediately.
	if f, ok := w.(http.Flusher); ok {
		f.Flush()
	}

	// Subscribe to the hub.
	client := hub.Subscribe()
	defer hub.Unsubscribe(client)

	// Create a ticker for heartbeat pings.
	heartbeat := time.NewTicker(sseHeartbeatInterval)
	defer heartbeat.Stop()

	ctx := c.Request().Context()

	slog.Debug("SSE client connected")

	for {
		select {
		case <-ctx.Done():
			// Client disconnected.
			slog.Debug("SSE client disconnected")
			return nil

		case data, ok := <-client.events:
			if !ok {
				// Channel closed, client was unsubscribed.
				return nil
			}
			// Write SSE event.
			if _, err := fmt.Fprintf(w, "data: %s\n\n", data); err != nil {
				return nil
			}
			if f, ok := w.(http.Flusher); ok {
				f.Flush()
			}

		case <-heartbeat.C:
			// Send a heartbeat comment to keep the connection alive.
			if _, err := fmt.Fprint(w, ": heartbeat\n\n"); err != nil {
				return nil
			}
			if f, ok := w.(http.Flusher); ok {
				f.Flush()
			}
		}
	}
}
