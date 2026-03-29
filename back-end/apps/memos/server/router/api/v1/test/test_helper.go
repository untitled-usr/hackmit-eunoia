package test

import (
	"context"
	"database/sql"
	"path/filepath"
	"testing"

	"github.com/pkg/errors"

	"github.com/usememos/memos/internal/profile"
	"github.com/usememos/memos/plugin/markdown"
	"github.com/usememos/memos/server/auth"
	"github.com/usememos/memos/server/friendship"
	apiv1 "github.com/usememos/memos/server/router/api/v1"
	"github.com/usememos/memos/store"
	teststore "github.com/usememos/memos/store/test"
	_ "modernc.org/sqlite"
)

// TestService holds the test service setup for API v1 services.
type TestService struct {
	Service *apiv1.APIV1Service
	Store   *store.Store
	Profile *profile.Profile
	Secret  string
}

type FriendshipLink struct {
	UserA   int32
	UserB   int32
	Deleted bool
}

// NewTestService creates a new test service with SQLite database.
func NewTestService(t *testing.T) *TestService {
	ctx := context.Background()

	// Create a test store with SQLite
	testStore := teststore.NewTestingStore(ctx, t)

	// Create a test profile with a temp directory for file storage,
	// so tests that create attachments don't leave artifacts in the source tree.
	testProfile := &profile.Profile{
		Demo:        true,
		Version:     "test-1.0.0",
		InstanceURL: "http://localhost:8080",
		Driver:      "sqlite",
		DSN:         ":memory:",
		Data:        t.TempDir(),
	}

	// Create APIV1Service with nil grpcServer since we're testing direct calls
	secret := "test-secret"
	markdownService := markdown.NewService(
		markdown.WithTagExtension(),
	)
	service := &apiv1.APIV1Service{
		Secret:          secret,
		Profile:         testProfile,
		Store:           testStore,
		MarkdownService: markdownService,
		SSEHub:          apiv1.NewSSEHub(),
	}

	return &TestService{
		Service: service,
		Store:   testStore,
		Profile: testProfile,
		Secret:  secret,
	}
}

// Cleanup closes resources after test.
func (ts *TestService) Cleanup() {
	if ts.Service.FriendResolver != nil {
		_ = ts.Service.FriendResolver.Close()
	}
	ts.Store.Close()
}

// CreateHostUser returns the builtin admin (id=1) after Migrate/EnsureBuiltinAdmin. The username argument is ignored.
func (ts *TestService) CreateHostUser(ctx context.Context, _ string) (*store.User, error) {
	id := store.BuiltinAdminID
	u, err := ts.Store.GetUser(ctx, &store.FindUser{ID: &id})
	if err != nil {
		return nil, err
	}
	if u == nil {
		return nil, errors.New("builtin admin not found; ensure Migrate ran")
	}
	return u, nil
}

// CreateRegularUser creates a regular user for testing.
func (ts *TestService) CreateRegularUser(ctx context.Context, username string) (*store.User, error) {
	return ts.Store.CreateUser(ctx, &store.User{
		Username: username,
		Role:     store.RoleUser,
	})
}

// CreateUserContext creates a context with the given user's ID for authentication.
func (*TestService) CreateUserContext(ctx context.Context, userID int32) context.Context {
	// Use the context key from the auth package
	return context.WithValue(ctx, auth.UserIDContextKey, userID)
}

func (ts *TestService) SetupFriendshipDB(t *testing.T, links ...FriendshipLink) {
	t.Helper()

	if ts.Service.FriendResolver != nil {
		_ = ts.Service.FriendResolver.Close()
	}

	dbPath := filepath.Join(t.TempDir(), "vocechat.sqlite")
	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		t.Fatalf("failed to open sqlite db: %v", err)
	}
	defer db.Close()

	if _, err := db.Exec(`
		CREATE TABLE friendship (
			uid_low INTEGER NOT NULL,
			uid_high INTEGER NOT NULL,
			created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
			updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
			deleted_at TIMESTAMP,
			deleted_by INTEGER,
			PRIMARY KEY (uid_low, uid_high),
			CHECK (uid_low < uid_high)
		);
	`); err != nil {
		t.Fatalf("failed to create friendship table: %v", err)
	}

	for _, link := range links {
		low, high := link.UserA, link.UserB
		if low > high {
			low, high = high, low
		}
		if low == high {
			continue
		}

		var deletedAt any
		if link.Deleted {
			deletedAt = "2026-01-01 00:00:00"
		} else {
			deletedAt = nil
		}

		if _, err := db.Exec(`
			INSERT INTO friendship (uid_low, uid_high, deleted_at)
			VALUES (?, ?, ?)
		`, low, high, deletedAt); err != nil {
			t.Fatalf("failed to insert friendship row: %v", err)
		}
	}

	resolver, err := friendship.NewSQLiteResolver(dbPath)
	if err != nil {
		t.Fatalf("failed to initialize friendship resolver: %v", err)
	}
	ts.Service.FriendResolver = resolver
}
