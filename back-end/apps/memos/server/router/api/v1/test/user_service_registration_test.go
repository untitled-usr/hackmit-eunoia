package test

import (
	"context"
	"fmt"
	"strconv"
	"testing"

	"github.com/stretchr/testify/require"
	"google.golang.org/protobuf/types/known/fieldmaskpb"

	apiv1 "github.com/usememos/memos/proto/gen/api/v1"
	storepb "github.com/usememos/memos/proto/gen/store"
	"github.com/usememos/memos/store"
)

func TestCreateUserRegistration(t *testing.T) {
	ctx := context.Background()

	t.Run("CreateUser success when registration enabled", func(t *testing.T) {
		ts := NewTestService(t)
		defer ts.Cleanup()

		// User registration is enabled by default, no need to set it explicitly

		// Create user without authentication - should succeed (password field is ignored)
		created, err := ts.Service.CreateUser(ctx, &apiv1.CreateUserRequest{
			User: &apiv1.User{
				Password: "password123",
			},
		})
		require.NoError(t, err)
		require.Equal(t, apiv1.User_USER, created.Role)
		userID, err := strconv.ParseInt(created.Name[len("users/"):], 10, 32)
		require.NoError(t, err)
		require.GreaterOrEqual(t, userID, int64(2))
		storedUser, err := ts.Store.GetUser(ctx, &store.FindUser{ID: ptr(int32(userID))})
		require.NoError(t, err)
		require.Equal(t, "", storedUser.PasswordHash)
	})

	t.Run("CreateUser allows empty username and password", func(t *testing.T) {
		ts := NewTestService(t)
		defer ts.Cleanup()
		_, err := ts.CreateHostUser(ctx, "admin")
		require.NoError(t, err)

		createdUser, err := ts.Service.CreateUser(ctx, &apiv1.CreateUserRequest{})
		require.NoError(t, err)
		require.NotNil(t, createdUser)

		userID, err := strconv.ParseInt(createdUser.Name[len("users/"):], 10, 32)
		require.NoError(t, err)
		storedUser, err := ts.Store.GetUser(ctx, &store.FindUser{ID: ptr(int32(userID))})
		require.NoError(t, err)
		require.NotNil(t, storedUser)
		require.Equal(t, "", storedUser.PasswordHash)
	})

	t.Run("CreateUser blocked when registration disabled", func(t *testing.T) {
		ts := NewTestService(t)
		defer ts.Cleanup()

		// Create a host user first so we're not in first-user setup mode
		_, err := ts.CreateHostUser(ctx, "admin")
		require.NoError(t, err)

		// Disable user registration
		_, err = ts.Store.UpsertInstanceSetting(ctx, &storepb.InstanceSetting{
			Key: storepb.InstanceSettingKey_GENERAL,
			Value: &storepb.InstanceSetting_GeneralSetting{
				GeneralSetting: &storepb.InstanceGeneralSetting{
					DisallowUserRegistration: true,
				},
			},
		})
		require.NoError(t, err)

		// Try to create user without authentication - should fail
		_, err = ts.Service.CreateUser(ctx, &apiv1.CreateUserRequest{})
		require.Error(t, err)
		require.Contains(t, err.Error(), "not allowed")
	})

	t.Run("CreateUser succeeds for superuser even when registration disabled", func(t *testing.T) {
		ts := NewTestService(t)
		defer ts.Cleanup()

		// Create host user
		hostUser, err := ts.CreateHostUser(ctx, "admin")
		require.NoError(t, err)
		hostCtx := ts.CreateUserContext(ctx, hostUser.ID)

		// Disable user registration
		_, err = ts.Store.UpsertInstanceSetting(ctx, &storepb.InstanceSetting{
			Key: storepb.InstanceSettingKey_GENERAL,
			Value: &storepb.InstanceSetting_GeneralSetting{
				GeneralSetting: &storepb.InstanceGeneralSetting{
					DisallowUserRegistration: true,
				},
			},
		})
		require.NoError(t, err)

		// Host user can create users even when registration is disabled - should succeed
		_, err = ts.Service.CreateUser(hostCtx, &apiv1.CreateUserRequest{})
		require.NoError(t, err)
	})

	t.Run("CreateUser regular user cannot create users when registration disabled", func(t *testing.T) {
		ts := NewTestService(t)
		defer ts.Cleanup()

		// Create regular user
		regularUser, err := ts.CreateRegularUser(ctx, "regularuser")
		require.NoError(t, err)
		regularUserCtx := ts.CreateUserContext(ctx, regularUser.ID)

		// Disable user registration
		_, err = ts.Store.UpsertInstanceSetting(ctx, &storepb.InstanceSetting{
			Key: storepb.InstanceSettingKey_GENERAL,
			Value: &storepb.InstanceSetting_GeneralSetting{
				GeneralSetting: &storepb.InstanceGeneralSetting{
					DisallowUserRegistration: true,
				},
			},
		})
		require.NoError(t, err)

		// Regular user tries to create user when registration is disabled - should fail
		_, err = ts.Service.CreateUser(regularUserCtx, &apiv1.CreateUserRequest{})
		require.Error(t, err)
		require.Contains(t, err.Error(), "not allowed")
	})

	t.Run("CreateUser ignores ADMIN role when caller is admin", func(t *testing.T) {
		ts := NewTestService(t)
		defer ts.Cleanup()

		hostUser, err := ts.CreateHostUser(ctx, "admin")
		require.NoError(t, err)
		hostCtx := ts.CreateUserContext(ctx, hostUser.ID)

		createdUser, err := ts.Service.CreateUser(hostCtx, &apiv1.CreateUserRequest{
			User: &apiv1.User{
				Role: apiv1.User_ADMIN,
			},
		})
		require.NoError(t, err)
		require.NotNil(t, createdUser)
		require.Equal(t, apiv1.User_USER, createdUser.Role)
	})

	t.Run("CreateUser unauthenticated user can only create regular user", func(t *testing.T) {
		ts := NewTestService(t)
		defer ts.Cleanup()

		// Create a host user first so we're not in first-user setup mode
		_, err := ts.CreateHostUser(ctx, "admin")
		require.NoError(t, err)

		// User registration is enabled by default

		// Unauthenticated user tries to create admin user - role should be ignored
		createdUser, err := ts.Service.CreateUser(ctx, &apiv1.CreateUserRequest{
			User: &apiv1.User{
				Role: apiv1.User_ADMIN, // This should be ignored
			},
		})
		require.NoError(t, err)
		require.NotNil(t, createdUser)
		require.Equal(t, apiv1.User_USER, createdUser.Role, "Unauthenticated users can only create USER role")
		expectedID := createdUser.Name[len("users/"):]
		require.Equal(t, expectedID, createdUser.Username, "USER username should expose id string")
		require.Empty(t, createdUser.AvatarUrl, "USER should not expose avatar")
		require.Equal(t, expectedID, createdUser.DisplayName, "USER display name should be id string")
	})

	t.Run("CreateUser with USER role ignores username and nickname", func(t *testing.T) {
		ts := NewTestService(t)
		defer ts.Cleanup()
		_, err := ts.CreateHostUser(ctx, "admin")
		require.NoError(t, err)

		createdUser, err := ts.Service.CreateUser(ctx, &apiv1.CreateUserRequest{
			User: &apiv1.User{
				Username:    "input_username_should_be_ignored",
				DisplayName: "Input Nickname",
				AvatarUrl:   "data:image/png;base64,iVBORw0KGgo=",
				Password:    "password123",
				Role:        apiv1.User_USER,
			},
		})
		require.NoError(t, err)
		require.NotNil(t, createdUser)
		expectedID := createdUser.Name[len("users/"):]
		require.Equal(t, expectedID, createdUser.Username)
		require.Empty(t, createdUser.AvatarUrl)
		require.Equal(t, expectedID, createdUser.DisplayName)
	})

	t.Run("UpdateUser rejects username, display name and avatar updates for USER", func(t *testing.T) {
		ts := NewTestService(t)
		defer ts.Cleanup()

		regularUser, err := ts.CreateRegularUser(ctx, "regularuser")
		require.NoError(t, err)
		regularUserCtx := ts.CreateUserContext(ctx, regularUser.ID)
		userName := "users/" + fmt.Sprint(regularUser.ID)

		_, err = ts.Service.UpdateUser(regularUserCtx, &apiv1.UpdateUserRequest{
			User: &apiv1.User{
				Name:        userName,
				Username:    "updated",
				DisplayName: "Updated",
				AvatarUrl:   "data:image/png;base64,iVBORw0KGgo=",
			},
			UpdateMask: &fieldmaskpb.FieldMask{
				Paths: []string{"username"},
			},
		})
		require.Error(t, err)
		require.Contains(t, err.Error(), "managed by system")

		_, err = ts.Service.UpdateUser(regularUserCtx, &apiv1.UpdateUserRequest{
			User: &apiv1.User{
				Name:        userName,
				DisplayName: "Updated",
			},
			UpdateMask: &fieldmaskpb.FieldMask{
				Paths: []string{"display_name"},
			},
		})
		require.Error(t, err)
		require.Contains(t, err.Error(), "managed by system")

		_, err = ts.Service.UpdateUser(regularUserCtx, &apiv1.UpdateUserRequest{
			User: &apiv1.User{
				Name:      userName,
				AvatarUrl: "data:image/png;base64,iVBORw0KGgo=",
			},
			UpdateMask: &fieldmaskpb.FieldMask{
				Paths: []string{"avatar_url"},
			},
		})
		require.Error(t, err)
		require.Contains(t, err.Error(), "managed by system")
	})
}

func ptr[T any](v T) *T {
	return &v
}
