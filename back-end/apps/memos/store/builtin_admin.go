package store

import (
	"context"

	"github.com/pkg/errors"
)

// EnsureBuiltinAdmin creates the built-in admin user (id=1, username "admin") when the
// database has no user with role ADMIN. Safe to call on every Migrate.
func (s *Store) EnsureBuiltinAdmin(ctx context.Context) error {
	adminRole := RoleAdmin
	limit := 1
	admins, err := s.ListUsers(ctx, &FindUser{Role: &adminRole, Limit: &limit})
	if err != nil {
		return errors.Wrap(err, "failed to list admin users")
	}
	if len(admins) > 0 {
		return nil
	}
	if err := s.driver.InsertBuiltinAdmin(ctx); err != nil {
		return errors.Wrap(err, "failed to insert builtin admin")
	}
	id := BuiltinAdminID
	u, err := s.GetUser(ctx, &FindUser{ID: &id})
	if err != nil {
		return errors.Wrap(err, "failed to load builtin admin after insert")
	}
	if u == nil {
		return errors.Errorf("builtin admin user id=%d not found after insert", BuiltinAdminID)
	}
	return nil
}
