package auth

import (
	"context"

	"github.com/usememos/memos/store"
)

// ContextKey is the key type for context values.
// Using a custom type prevents collisions with other packages.
type ContextKey int

const (
	// UserIDContextKey stores the authenticated user's ID.
	// Set for all authenticated requests.
	// Use GetUserID(ctx) to retrieve this value.
	UserIDContextKey ContextKey = iota
)

// GetUserID retrieves the authenticated user's ID from the context.
// Returns 0 if no user ID is set (unauthenticated request).
func GetUserID(ctx context.Context) int32 {
	if v, ok := ctx.Value(UserIDContextKey).(int32); ok {
		return v
	}
	return 0
}

// SetUserInContext sets the authenticated user's information in the context.
// This is a simpler alternative to AuthorizeAndSetContext for cases where
// authorization is handled separately (e.g., HTTP middleware).
func SetUserInContext(ctx context.Context, user *store.User) context.Context {
	return context.WithValue(ctx, UserIDContextKey, user.ID)
}

// ApplyToContext sets the authenticated identity from an AuthResult into the context.
// This is the canonical way to propagate auth state after a successful Authenticate call.
// Safe to call with a nil result (no-op).
func ApplyToContext(ctx context.Context, result *AuthResult) context.Context {
	if result == nil {
		return ctx
	}
	if result.User != nil {
		ctx = SetUserInContext(ctx, result.User)
	}
	return ctx
}
