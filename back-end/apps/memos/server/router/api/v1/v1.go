package v1

import (
	"context"
	"net/http"

	"connectrpc.com/connect"
	"github.com/grpc-ecosystem/grpc-gateway/v2/runtime"
	"github.com/labstack/echo/v5"
	"github.com/labstack/echo/v5/middleware"
	"golang.org/x/sync/semaphore"

	"github.com/usememos/memos/internal/profile"
	"github.com/usememos/memos/plugin/markdown"
	v1pb "github.com/usememos/memos/proto/gen/api/v1"
	"github.com/usememos/memos/server/auth"
	"github.com/usememos/memos/server/friendship"
	"github.com/usememos/memos/store"
)

type APIV1Service struct {
	v1pb.UnimplementedInstanceServiceServer
	v1pb.UnimplementedUserServiceServer
	v1pb.UnimplementedMemoServiceServer
	v1pb.UnimplementedDriftBottleServiceServer
	v1pb.UnimplementedAttachmentServiceServer
	v1pb.UnimplementedShortcutServiceServer
	v1pb.UnimplementedIdentityProviderServiceServer

	Secret          string
	Profile         *profile.Profile
	Store           *store.Store
	FriendResolver  friendship.Resolver
	MarkdownService markdown.Service
	SSEHub          *SSEHub

	// thumbnailSemaphore limits concurrent thumbnail generation to prevent memory exhaustion
	thumbnailSemaphore *semaphore.Weighted
}

func NewAPIV1Service(secret string, profile *profile.Profile, store *store.Store, friendResolver friendship.Resolver) *APIV1Service {
	markdownService := markdown.NewService(
		markdown.WithTagExtension(),
	)
	if friendResolver == nil {
		friendResolver, _ = friendship.NewSQLiteResolver("")
	}
	return &APIV1Service{
		Secret:             secret,
		Profile:            profile,
		Store:              store,
		FriendResolver:     friendResolver,
		MarkdownService:    markdownService,
		SSEHub:             NewSSEHub(),
		thumbnailSemaphore: semaphore.NewWeighted(3), // Limit to 3 concurrent thumbnail generations
	}
}

// RegisterGateway registers the gRPC-Gateway and Connect handlers with the given Echo instance.
func (s *APIV1Service) RegisterGateway(ctx context.Context, echoServer *echo.Echo) error {
	// Auth middleware for gRPC-Gateway - runs after routing, has access to method name.
	// Uses the same PublicMethods config as the Connect AuthInterceptor.
	authenticator := auth.NewAuthenticator(s.Store, s.Secret)
	gatewayAuthMiddleware := func(next runtime.HandlerFunc) runtime.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request, pathParams map[string]string) {
			ctx := r.Context()
			rpcMethod, hasRPCMethod := runtime.RPCMethod(ctx)

			result, err := authenticator.AuthenticateByActingUIDHeader(ctx, r.Header.Get("X-Acting-Uid"))
			if err != nil {
				if hasRPCMethod && !IsPublicMethod(rpcMethod) {
					http.Error(w, `{"code": 16, "message": "invalid X-Acting-Uid"}`, http.StatusUnauthorized)
					return
				}
				result = nil
			}

			if result == nil && hasRPCMethod && !IsPublicMethod(rpcMethod) {
				http.Error(w, `{"code": 16, "message": "missing X-Acting-Uid"}`, http.StatusUnauthorized)
				return
			}

			ctx = auth.ApplyToContext(ctx, result)
			r = r.WithContext(ctx)

			next(w, r, pathParams)
		}
	}

	// Create gRPC-Gateway mux with auth middleware.
	gwMux := runtime.NewServeMux(
		runtime.WithMiddlewares(gatewayAuthMiddleware),
	)
	if err := v1pb.RegisterInstanceServiceHandlerServer(ctx, gwMux, s); err != nil {
		return err
	}
	if err := v1pb.RegisterUserServiceHandlerServer(ctx, gwMux, s); err != nil {
		return err
	}
	if err := v1pb.RegisterMemoServiceHandlerServer(ctx, gwMux, s); err != nil {
		return err
	}
	if err := v1pb.RegisterDriftBottleServiceHandlerServer(ctx, gwMux, s); err != nil {
		return err
	}
	if err := v1pb.RegisterAttachmentServiceHandlerServer(ctx, gwMux, s); err != nil {
		return err
	}
	if err := v1pb.RegisterShortcutServiceHandlerServer(ctx, gwMux, s); err != nil {
		return err
	}
	if err := v1pb.RegisterIdentityProviderServiceHandlerServer(ctx, gwMux, s); err != nil {
		return err
	}
	gwGroup := echoServer.Group("")
	gwGroup.Use(middleware.CORSWithConfig(middleware.CORSConfig{
		AllowOrigins: []string{"*"},
	}))
	// Register SSE endpoint with same CORS as rest of /api/v1.
	gwGroup.GET("/api/v1/sse", func(c *echo.Context) error {
		return handleSSE(c, s.SSEHub, auth.NewAuthenticator(s.Store, s.Secret))
	})
	handler := echo.WrapHandler(gwMux)

	gwGroup.Any("/api/v1/*", handler)
	gwGroup.Any("/file/*", handler)

	// Connect handlers for browser clients (replaces grpc-web).
	logStacktraces := s.Profile.Demo
	connectInterceptors := connect.WithInterceptors(
		NewMetadataInterceptor(), // Convert HTTP headers to gRPC metadata first
		NewLoggingInterceptor(logStacktraces),
		NewRecoveryInterceptor(logStacktraces),
		NewAuthInterceptor(s.Store, s.Secret),
	)
	connectMux := http.NewServeMux()
	connectHandler := NewConnectServiceHandler(s)
	connectHandler.RegisterConnectHandlers(connectMux, connectInterceptors)

	// Wrap with CORS for browser access
	corsHandler := middleware.CORSWithConfig(middleware.CORSConfig{
		UnsafeAllowOriginFunc: func(_ *echo.Context, origin string) (string, bool, error) {
			return origin, true, nil
		},
		AllowMethods:     []string{http.MethodGet, http.MethodPost, http.MethodOptions},
		AllowHeaders:     []string{"*"},
		AllowCredentials: true,
	})
	connectGroup := echoServer.Group("", corsHandler)
	connectGroup.Any("/memos.api.v1.*", echo.WrapHandler(connectMux))

	return nil
}
