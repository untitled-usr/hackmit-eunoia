package v1

import (
	"context"

	"github.com/pkg/errors"

	"github.com/usememos/memos/server/auth"
	"github.com/usememos/memos/store"
)

// fetchCurrentUser returns the acting user from context (set by X-Acting-Uid at the gateway).
func (s *APIV1Service) fetchCurrentUser(ctx context.Context) (*store.User, error) {
	userID := auth.GetUserID(ctx)
	if userID == 0 {
		return nil, nil
	}
	user, err := s.Store.GetUser(ctx, &store.FindUser{
		ID: &userID,
	})
	if err != nil {
		return nil, err
	}
	if user == nil {
		return nil, errors.Errorf("user %d not found", userID)
	}
	return user, nil
}
