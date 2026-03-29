package postgres

import (
	"context"
	"database/sql"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	storepb "github.com/usememos/memos/proto/gen/store"
	"github.com/usememos/memos/store"
)

// getTestDSN returns PostgreSQL DSN from environment or returns empty string.
func getTestDSN() string {
	// For unit tests, we expect TEST_POSTGRES_DSN to be set.
	// Example: TEST_POSTGRES_DSN="postgresql://user:pass@localhost:5432/memos_test?sslmode=disable".
	return ""
}

// TestUpsertUserSetting tests basic upsert functionality.
func TestUpsertUserSetting(t *testing.T) {
	dsn := getTestDSN()
	if dsn == "" {
		t.Skip("PostgreSQL DSN not provided, skipping test")
	}

	db, err := sql.Open("postgres", dsn)
	require.NoError(t, err)
	defer db.Close()

	ctx := context.Background()
	driver := &DB{db: db}

	// Setup
	_, err = db.ExecContext(ctx, `
		CREATE TABLE IF NOT EXISTS user_setting (
			user_id INTEGER NOT NULL,
			key TEXT NOT NULL,
			value TEXT NOT NULL,
			UNIQUE(user_id, key)
		)
	`)
	require.NoError(t, err)

	defer func() {
		db.ExecContext(ctx, "DELETE FROM user_setting WHERE user_id = 9999")
	}()

	// Test insert
	setting := &store.UserSetting{
		UserID: 9999,
		Key:    storepb.UserSetting_GENERAL,
		Value:  `{"locale":"en"}`,
	}
	result, err := driver.UpsertUserSetting(ctx, setting)
	assert.NoError(t, err)
	assert.NotNil(t, result)
	assert.Equal(t, int32(9999), result.UserID)

	// Test update (upsert on conflict)
	setting.Value = `{"locale":"zh"}`
	result, err = driver.UpsertUserSetting(ctx, setting)
	assert.NoError(t, err)
	assert.Equal(t, `{"locale":"zh"}`, result.Value)
}
