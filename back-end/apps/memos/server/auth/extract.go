package auth

import (
	"net/http"
)

// ExtractRefreshTokenFromCookie extracts the refresh token from cookie header.
func ExtractRefreshTokenFromCookie(cookieHeader string) string {
	if cookieHeader == "" {
		return ""
	}
	req := &http.Request{Header: http.Header{"Cookie": []string{cookieHeader}}}
	cookie, err := req.Cookie(RefreshTokenCookieName)
	if err != nil {
		return ""
	}
	return cookie.Value
}
