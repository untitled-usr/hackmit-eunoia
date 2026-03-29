package mcp

import (
	"net/http"

	"github.com/labstack/echo/v5"
	"github.com/labstack/echo/v5/middleware"
	mcpserver "github.com/mark3labs/mcp-go/server"

	"github.com/usememos/memos/internal/profile"
	"github.com/usememos/memos/server/auth"
	"github.com/usememos/memos/server/friendship"
	"github.com/usememos/memos/store"
)

type MCPService struct {
	profile        *profile.Profile
	store          *store.Store
	authenticator  *auth.Authenticator
	friendResolver friendship.Resolver
}

func NewMCPService(profile *profile.Profile, store *store.Store, secret string, friendResolver friendship.Resolver) *MCPService {
	return &MCPService{
		profile:        profile,
		store:          store,
		authenticator:  auth.NewAuthenticator(store, secret),
		friendResolver: friendResolver,
	}
}

func (s *MCPService) RegisterRoutes(echoServer *echo.Echo) {
	mcpSrv := mcpserver.NewMCPServer("Memos", "1.0.0",
		mcpserver.WithToolCapabilities(true),
		mcpserver.WithResourceCapabilities(true, true),
		mcpserver.WithPromptCapabilities(true),
		mcpserver.WithLogging(),
	)
	s.registerMemoTools(mcpSrv)
	s.registerTagTools(mcpSrv)
	s.registerAttachmentTools(mcpSrv)
	s.registerRelationTools(mcpSrv)
	s.registerReactionTools(mcpSrv)
	s.registerMemoResources(mcpSrv)
	s.registerPrompts(mcpSrv)

	httpHandler := mcpserver.NewStreamableHTTPServer(mcpSrv)

	mcpGroup := echoServer.Group("")
	mcpGroup.Use(middleware.CORSWithConfig(middleware.CORSConfig{
		AllowOrigins: []string{"*"},
	}))
	mcpGroup.Use(func(next echo.HandlerFunc) echo.HandlerFunc {
		return func(c *echo.Context) error {
			result, err := s.authenticator.AuthenticateByActingUIDHeader(c.Request().Context(), c.Request().Header.Get("X-Acting-Uid"))
			if err != nil {
				return c.JSON(http.StatusUnauthorized, map[string]string{"message": "invalid X-Acting-Uid"})
			}
			if result == nil {
				return next(c)
			}
			ctx := auth.ApplyToContext(c.Request().Context(), result)
			c.SetRequest(c.Request().WithContext(ctx))
			return next(c)
		}
	})
	mcpGroup.Any("/mcp", echo.WrapHandler(httpHandler))
}
