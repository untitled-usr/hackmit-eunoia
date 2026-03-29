package auth

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestGenerateAccessTokenV2(t *testing.T) {
	secret := []byte("test-secret")

	t.Run("generates valid access token", func(t *testing.T) {
		token, expiresAt, err := GenerateAccessTokenV2(1, "testuser", "USER", "ACTIVE", secret)
		require.NoError(t, err)
		assert.NotEmpty(t, token)
		assert.True(t, expiresAt.After(time.Now()))
		assert.True(t, expiresAt.Before(time.Now().Add(AccessTokenDuration+time.Minute)))
	})

	t.Run("generates different tokens for same user", func(t *testing.T) {
		token1, _, err := GenerateAccessTokenV2(1, "testuser", "USER", "ACTIVE", secret)
		require.NoError(t, err)

		time.Sleep(2 * time.Second) // Ensure different timestamps (tokens have 1s precision)

		token2, _, err := GenerateAccessTokenV2(1, "testuser", "USER", "ACTIVE", secret)
		require.NoError(t, err)

		assert.NotEqual(t, token1, token2, "tokens should be different due to different timestamps")
	})
}

func TestParseAccessTokenV2(t *testing.T) {
	secret := []byte("test-secret")

	t.Run("parses valid access token", func(t *testing.T) {
		token, _, err := GenerateAccessTokenV2(1, "testuser", "USER", "ACTIVE", secret)
		require.NoError(t, err)

		claims, err := ParseAccessTokenV2(token, secret)
		require.NoError(t, err)
		assert.Equal(t, "1", claims.Subject)
		assert.Equal(t, "testuser", claims.Username)
		assert.Equal(t, "USER", claims.Role)
		assert.Equal(t, "ACTIVE", claims.Status)
		assert.Equal(t, "access", claims.Type)
	})

	t.Run("fails with wrong secret", func(t *testing.T) {
		token, _, err := GenerateAccessTokenV2(1, "testuser", "USER", "ACTIVE", secret)
		require.NoError(t, err)

		wrongSecret := []byte("wrong-secret")
		_, err = ParseAccessTokenV2(token, wrongSecret)
		assert.Error(t, err)
	})

	t.Run("fails with invalid token", func(t *testing.T) {
		_, err := ParseAccessTokenV2("invalid-token", secret)
		assert.Error(t, err)
	})

	t.Run("fails with refresh token", func(t *testing.T) {
		// Generate a refresh token and try to parse it as access token
		// Should fail because audience mismatch is caught before type check
		refreshToken, _, err := GenerateRefreshToken(1, "token-id", secret)
		require.NoError(t, err)

		_, err = ParseAccessTokenV2(refreshToken, secret)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "invalid audience")
	})

	t.Run("parses token with different roles", func(t *testing.T) {
		roles := []string{"USER", "ADMIN"}
		for _, role := range roles {
			token, _, err := GenerateAccessTokenV2(1, "testuser", role, "ACTIVE", secret)
			require.NoError(t, err)

			claims, err := ParseAccessTokenV2(token, secret)
			require.NoError(t, err)
			assert.Equal(t, role, claims.Role)
		}
	})
}

func TestGenerateRefreshToken(t *testing.T) {
	secret := []byte("test-secret")

	t.Run("generates valid refresh token", func(t *testing.T) {
		token, expiresAt, err := GenerateRefreshToken(1, "token-id-123", secret)
		require.NoError(t, err)
		assert.NotEmpty(t, token)
		assert.True(t, expiresAt.After(time.Now().Add(29*24*time.Hour)))
	})

	t.Run("generates different tokens for different token IDs", func(t *testing.T) {
		token1, _, err := GenerateRefreshToken(1, "token-id-1", secret)
		require.NoError(t, err)

		token2, _, err := GenerateRefreshToken(1, "token-id-2", secret)
		require.NoError(t, err)

		assert.NotEqual(t, token1, token2)
	})
}

func TestParseRefreshToken(t *testing.T) {
	secret := []byte("test-secret")

	t.Run("parses valid refresh token", func(t *testing.T) {
		token, _, err := GenerateRefreshToken(1, "token-id-123", secret)
		require.NoError(t, err)

		claims, err := ParseRefreshToken(token, secret)
		require.NoError(t, err)
		assert.Equal(t, "1", claims.Subject)
		assert.Equal(t, "token-id-123", claims.TokenID)
		assert.Equal(t, "refresh", claims.Type)
	})

	t.Run("fails with wrong secret", func(t *testing.T) {
		token, _, err := GenerateRefreshToken(1, "token-id-123", secret)
		require.NoError(t, err)

		wrongSecret := []byte("wrong-secret")
		_, err = ParseRefreshToken(token, wrongSecret)
		assert.Error(t, err)
	})

	t.Run("fails with invalid token", func(t *testing.T) {
		_, err := ParseRefreshToken("invalid-token", secret)
		assert.Error(t, err)
	})

	t.Run("fails with access token", func(t *testing.T) {
		// Generate an access token and try to parse it as refresh token
		// Should fail because audience mismatch is caught before type check
		accessToken, _, err := GenerateAccessTokenV2(1, "testuser", "USER", "ACTIVE", secret)
		require.NoError(t, err)

		_, err = ParseRefreshToken(accessToken, secret)
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "invalid audience")
	})
}

func TestAccessTokenV2Integration(t *testing.T) {
	secret := []byte("test-secret")

	t.Run("full lifecycle: generate, parse, validate", func(t *testing.T) {
		userID := int32(42)
		username := "john_doe"
		role := "ADMIN"
		status := "ACTIVE"

		// Generate token
		token, expiresAt, err := GenerateAccessTokenV2(userID, username, role, status, secret)
		require.NoError(t, err)
		assert.NotEmpty(t, token)

		// Parse token
		claims, err := ParseAccessTokenV2(token, secret)
		require.NoError(t, err)

		// Validate claims
		assert.Equal(t, "42", claims.Subject)
		assert.Equal(t, username, claims.Username)
		assert.Equal(t, role, claims.Role)
		assert.Equal(t, status, claims.Status)
		assert.Equal(t, "access", claims.Type)
		assert.Equal(t, Issuer, claims.Issuer)
		assert.NotNil(t, claims.IssuedAt)
		assert.NotNil(t, claims.ExpiresAt)

		// Validate expiration
		assert.True(t, claims.ExpiresAt.Equal(expiresAt) || claims.ExpiresAt.Before(expiresAt))
	})
}

func TestRefreshTokenIntegration(t *testing.T) {
	secret := []byte("test-secret")

	t.Run("full lifecycle: generate, parse, validate", func(t *testing.T) {
		userID := int32(42)
		tokenID := "unique-token-id-456"

		// Generate token
		token, expiresAt, err := GenerateRefreshToken(userID, tokenID, secret)
		require.NoError(t, err)
		assert.NotEmpty(t, token)

		// Parse token
		claims, err := ParseRefreshToken(token, secret)
		require.NoError(t, err)

		// Validate claims
		assert.Equal(t, "42", claims.Subject)
		assert.Equal(t, tokenID, claims.TokenID)
		assert.Equal(t, "refresh", claims.Type)
		assert.Equal(t, Issuer, claims.Issuer)
		assert.NotNil(t, claims.IssuedAt)
		assert.NotNil(t, claims.ExpiresAt)

		// Validate expiration
		assert.True(t, claims.ExpiresAt.Equal(expiresAt) || claims.ExpiresAt.Before(expiresAt))
	})
}

func TestTokenExpiration(t *testing.T) {
	secret := []byte("test-secret")

	t.Run("access token expires after AccessTokenDuration", func(t *testing.T) {
		_, expiresAt, err := GenerateAccessTokenV2(1, "testuser", "USER", "ACTIVE", secret)
		require.NoError(t, err)

		expectedExpiry := time.Now().Add(AccessTokenDuration)
		delta := expiresAt.Sub(expectedExpiry)
		assert.True(t, delta < time.Second, "expiration should be within 1 second of expected")
	})

	t.Run("refresh token expires after RefreshTokenDuration", func(t *testing.T) {
		_, expiresAt, err := GenerateRefreshToken(1, "token-id", secret)
		require.NoError(t, err)

		expectedExpiry := time.Now().Add(RefreshTokenDuration)
		delta := expiresAt.Sub(expectedExpiry)
		assert.True(t, delta < time.Second, "expiration should be within 1 second of expected")
	})
}
