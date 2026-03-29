package friendship

import (
	"context"
	"database/sql"
	"fmt"
	"net/url"
	"strings"

	_ "modernc.org/sqlite"
)

// Resolver provides friendship lookups backed by an external data source.
type Resolver interface {
	ListFriendIDs(ctx context.Context, userID int32) ([]int32, error)
	IsFriend(ctx context.Context, userA int32, userB int32) (bool, error)
	Close() error
	Enabled() bool
}

type sqliteResolver struct {
	db      *sql.DB
	enabled bool
}

// NewSQLiteResolver creates a friendship resolver backed by SQLite.
// When dsn is empty, it returns a disabled resolver.
func NewSQLiteResolver(dsn string) (Resolver, error) {
	dsn = strings.TrimSpace(dsn)
	if dsn == "" {
		return &sqliteResolver{enabled: false}, nil
	}

	readonlyDSN := normalizeReadonlySQLiteDSN(dsn)
	db, err := sql.Open("sqlite", readonlyDSN)
	if err != nil {
		return nil, err
	}
	if err := db.Ping(); err != nil {
		_ = db.Close()
		return nil, err
	}

	return &sqliteResolver{
		db:      db,
		enabled: true,
	}, nil
}

func (r *sqliteResolver) Enabled() bool {
	return r != nil && r.enabled
}

func (r *sqliteResolver) Close() error {
	if r == nil || r.db == nil {
		return nil
	}
	return r.db.Close()
}

func (r *sqliteResolver) ListFriendIDs(ctx context.Context, userID int32) ([]int32, error) {
	if !r.Enabled() {
		return nil, nil
	}

	rows, err := r.db.QueryContext(ctx, `
		SELECT CASE WHEN uid_low = ? THEN uid_high ELSE uid_low END AS friend_id
		FROM friendship
		WHERE deleted_at IS NULL
		  AND (uid_low = ? OR uid_high = ?)
	`, userID, userID, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	friendIDs := make([]int32, 0, 16)
	for rows.Next() {
		var id int32
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		friendIDs = append(friendIDs, id)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return friendIDs, nil
}

func (r *sqliteResolver) IsFriend(ctx context.Context, userA int32, userB int32) (bool, error) {
	if !r.Enabled() || userA == userB {
		return false, nil
	}

	low, high := userA, userB
	if low > high {
		low, high = high, low
	}

	var exists int
	err := r.db.QueryRowContext(ctx, `
		SELECT 1
		FROM friendship
		WHERE uid_low = ?
		  AND uid_high = ?
		  AND deleted_at IS NULL
		LIMIT 1
	`, low, high).Scan(&exists)
	if err == sql.ErrNoRows {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return true, nil
}

func normalizeReadonlySQLiteDSN(dsn string) string {
	if strings.HasPrefix(dsn, "file:") {
		return ensureReadOnlyMode(dsn)
	}

	escaped := (&url.URL{Path: dsn}).String()
	return ensureReadOnlyMode(fmt.Sprintf("file:%s", escaped))
}

func ensureReadOnlyMode(dsn string) string {
	if !strings.HasPrefix(dsn, "file:") {
		return dsn
	}

	raw := strings.TrimPrefix(dsn, "file:")
	parts := strings.SplitN(raw, "?", 2)
	pathPart := parts[0]

	values := url.Values{}
	if len(parts) == 2 && parts[1] != "" {
		if parsed, err := url.ParseQuery(parts[1]); err == nil {
			values = parsed
		}
	}
	if values.Get("mode") == "" {
		values.Set("mode", "ro")
	}

	encoded := values.Encode()
	if encoded == "" {
		return "file:" + pathPart
	}
	return "file:" + pathPart + "?" + encoded
}

func BuildFriendFilterExpr(userID int32, friendIDs []int32) string {
	return fmt.Sprintf(`creator_id == %d || visibility == "PUBLIC"`, userID)
}
