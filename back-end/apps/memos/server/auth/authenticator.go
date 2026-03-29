package auth

import (
	"context"
	"strconv"
	"strings"
	"time"

	"github.com/pkg/errors"

	"github.com/usememos/memos/internal/util"
	"github.com/usememos/memos/store"
)

// Authenticator provides shared authentication and authorization logic.
// Used by gRPC interceptor, Connect interceptor, and file server to ensure
// consistent authentication behavior across all API endpoints.
//
// Authentication methods:
// - JWT access tokens: Short-lived tokens (15 minutes) for API access
//
// This struct is safe for concurrent use.
type Authenticator struct {
	store  *store.Store
	secret string
}

// UserClaims represents authenticated user info from access token.
type UserClaims struct {
	UserID   int32
	Username string
	Role     string
	Status   string
}

// NewAuthenticator creates a new Authenticator instance.
func NewAuthenticator(store *store.Store, secret string) *Authenticator {
	return &Authenticator{
		store:  store,
		secret: secret,
	}
}

// AuthenticateByAccessTokenV2 validates a short-lived access token.
// Returns claims without database query (stateless validation).
func (a *Authenticator) AuthenticateByAccessTokenV2(accessToken string) (*UserClaims, error) {
	claims, err := ParseAccessTokenV2(accessToken, []byte(a.secret))
	if err != nil {
		return nil, errors.Wrap(err, "invalid access token")
	}

	userID, err := util.ConvertStringToInt32(claims.Subject)
	if err != nil {
		return nil, errors.Wrap(err, "invalid user ID in token")
	}

	return &UserClaims{
		UserID:   userID,
		Username: claims.Username,
		Role:     claims.Role,
		Status:   claims.Status,
	}, nil
}

// AuthenticateByRefreshToken validates a refresh token against the database.
func (a *Authenticator) AuthenticateByRefreshToken(ctx context.Context, refreshToken string) (*store.User, string, error) {
	claims, err := ParseRefreshToken(refreshToken, []byte(a.secret))
	if err != nil {
		return nil, "", errors.Wrap(err, "invalid refresh token")
	}

	userID, err := util.ConvertStringToInt32(claims.Subject)
	if err != nil {
		return nil, "", errors.Wrap(err, "invalid user ID in token")
	}

	// Check token exists in database (revocation check)
	token, err := a.store.GetUserRefreshTokenByID(ctx, userID, claims.TokenID)
	if err != nil {
		return nil, "", errors.Wrap(err, "failed to get refresh token")
	}
	if token == nil {
		return nil, "", errors.New("refresh token revoked")
	}

	// Check token not expired
	if token.ExpiresAt != nil && token.ExpiresAt.AsTime().Before(time.Now()) {
		return nil, "", errors.New("refresh token expired")
	}

	// Get user
	user, err := a.store.GetUser(ctx, &store.FindUser{ID: &userID})
	if err != nil {
		return nil, "", errors.Wrap(err, "failed to get user")
	}
	if user == nil {
		return nil, "", errors.New("user not found")
	}
	if user.RowStatus == store.Archived {
		return nil, "", errors.New("user is archived")
	}

	return user, claims.TokenID, nil
}

// AuthResult contains the result of an authentication attempt.
type AuthResult struct {
	User *store.User
}

// AuthenticateByActingUIDHeader resolves user identity from the X-Acting-Uid header.
// Returns (nil, nil) when the header is empty.
func (a *Authenticator) AuthenticateByActingUIDHeader(ctx context.Context, headerValue string) (*AuthResult, error) {
	value := strings.TrimSpace(headerValue)
	if value == "" {
		return nil, nil
	}

	uid, err := strconv.ParseInt(value, 10, 32)
	if err != nil || uid <= 0 {
		return nil, errors.New("invalid X-Acting-Uid header")
	}
	userID := int32(uid)

	user, err := a.store.GetUser(ctx, &store.FindUser{ID: &userID})
	if err != nil {
		return nil, errors.Wrap(err, "failed to get acting user")
	}
	if user == nil {
		return nil, errors.New("acting user not found")
	}
	if user.RowStatus == store.Archived {
		return nil, errors.New("acting user is archived")
	}
	return &AuthResult{User: user}, nil
}
