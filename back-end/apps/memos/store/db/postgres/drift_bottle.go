package postgres

import (
	"context"
	"database/sql"
	"fmt"
	"strings"

	"github.com/usememos/memos/store"
)

func (d *DB) CreateDriftBottle(ctx context.Context, create *store.DriftBottle) (*store.DriftBottle, error) {
	stmt := `INSERT INTO drift_bottle (uid, memo_id, creator_id, status) VALUES ($1, $2, $3, $4) RETURNING id, created_ts, updated_ts`
	if err := d.db.QueryRowContext(ctx, stmt, create.UID, create.MemoID, create.CreatorID, create.Status).Scan(&create.ID, &create.CreatedTs, &create.UpdatedTs); err != nil {
		return nil, err
	}
	return create, nil
}

func (d *DB) ListDriftBottles(ctx context.Context, find *store.FindDriftBottle) ([]*store.DriftBottle, error) {
	where, args := []string{"1 = 1"}, []any{}
	if v := find.ID; v != nil {
		where, args = append(where, "id = "+placeholder(len(args)+1)), append(args, *v)
	}
	if v := find.UID; v != nil {
		where, args = append(where, "uid = "+placeholder(len(args)+1)), append(args, *v)
	}
	if v := find.MemoID; v != nil {
		where, args = append(where, "memo_id = "+placeholder(len(args)+1)), append(args, *v)
	}
	if v := find.CreatorID; v != nil {
		where, args = append(where, "creator_id = "+placeholder(len(args)+1)), append(args, *v)
	}
	if v := find.Status; v != nil {
		where, args = append(where, "status = "+placeholder(len(args)+1)), append(args, *v)
	}
	if len(find.IDList) > 0 {
		holders := make([]string, 0, len(find.IDList))
		for _, id := range find.IDList {
			holders = append(holders, placeholder(len(args)+1))
			args = append(args, id)
		}
		where = append(where, "id IN ("+strings.Join(holders, ", ")+")")
	}
	query := `SELECT id, uid, memo_id, creator_id, status, created_ts, updated_ts FROM drift_bottle WHERE ` + strings.Join(where, " AND ") + ` ORDER BY created_ts DESC, id DESC`
	if find.Limit != nil {
		query = fmt.Sprintf("%s LIMIT %d", query, *find.Limit)
		if find.Offset != nil {
			query = fmt.Sprintf("%s OFFSET %d", query, *find.Offset)
		}
	}
	rows, err := d.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	list := make([]*store.DriftBottle, 0)
	for rows.Next() {
		item := &store.DriftBottle{}
		if err := rows.Scan(&item.ID, &item.UID, &item.MemoID, &item.CreatorID, &item.Status, &item.CreatedTs, &item.UpdatedTs); err != nil {
			return nil, err
		}
		list = append(list, item)
	}
	return list, rows.Err()
}

func (d *DB) UpdateDriftBottle(ctx context.Context, update *store.UpdateDriftBottle) error {
	set, args := []string{}, []any{}
	if v := update.UpdatedTs; v != nil {
		set, args = append(set, "updated_ts = "+placeholder(len(args)+1)), append(args, *v)
	}
	if v := update.Status; v != nil {
		set, args = append(set, "status = "+placeholder(len(args)+1)), append(args, *v)
	}
	if len(set) == 0 {
		return nil
	}
	args = append(args, update.ID)
	_, err := d.db.ExecContext(ctx, "UPDATE drift_bottle SET "+strings.Join(set, ", ")+" WHERE id = "+placeholder(len(args)), args...)
	return err
}

func (d *DB) UpsertDriftBottleTag(ctx context.Context, upsert *store.DriftBottleTag) (*store.DriftBottleTag, error) {
	stmt := `
		INSERT INTO drift_bottle_tag (drift_bottle_id, tag, normalized_tag, created_ts)
		VALUES ($1, $2, $3, $4)
		ON CONFLICT (drift_bottle_id, normalized_tag)
		DO UPDATE SET tag=EXCLUDED.tag
		RETURNING id, drift_bottle_id, tag, normalized_tag, created_ts
	`
	item := &store.DriftBottleTag{}
	if err := d.db.QueryRowContext(ctx, stmt, upsert.DriftBottleID, upsert.Tag, upsert.NormalizedTag, upsert.CreatedTs).
		Scan(&item.ID, &item.DriftBottleID, &item.Tag, &item.NormalizedTag, &item.CreatedTs); err != nil {
		return nil, err
	}
	return item, nil
}

func (d *DB) ListDriftBottleTags(ctx context.Context, find *store.FindDriftBottleTag) ([]*store.DriftBottleTag, error) {
	where, args := []string{"1 = 1"}, []any{}
	if v := find.ID; v != nil {
		where, args = append(where, "id = "+placeholder(len(args)+1)), append(args, *v)
	}
	if v := find.DriftBottleID; v != nil {
		where, args = append(where, "drift_bottle_id = "+placeholder(len(args)+1)), append(args, *v)
	}
	if v := find.NormalizedTag; v != nil {
		where, args = append(where, "normalized_tag = "+placeholder(len(args)+1)), append(args, *v)
	}
	if len(find.DriftBottleIDList) > 0 {
		holders := make([]string, 0, len(find.DriftBottleIDList))
		for _, id := range find.DriftBottleIDList {
			holders = append(holders, placeholder(len(args)+1))
			args = append(args, id)
		}
		where = append(where, "drift_bottle_id IN ("+strings.Join(holders, ", ")+")")
	}
	query := `SELECT id, drift_bottle_id, tag, normalized_tag, created_ts FROM drift_bottle_tag WHERE ` + strings.Join(where, " AND ") + ` ORDER BY id DESC`
	if find.Limit != nil {
		query = fmt.Sprintf("%s LIMIT %d", query, *find.Limit)
		if find.Offset != nil {
			query = fmt.Sprintf("%s OFFSET %d", query, *find.Offset)
		}
	}
	rows, err := d.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	list := make([]*store.DriftBottleTag, 0)
	for rows.Next() {
		item := &store.DriftBottleTag{}
		if err := rows.Scan(&item.ID, &item.DriftBottleID, &item.Tag, &item.NormalizedTag, &item.CreatedTs); err != nil {
			return nil, err
		}
		list = append(list, item)
	}
	return list, rows.Err()
}

func (d *DB) DeleteDriftBottleTag(ctx context.Context, delete *store.DeleteDriftBottleTag) error {
	where, args := []string{"1 = 1"}, []any{}
	if v := delete.ID; v != nil {
		where, args = append(where, "id = "+placeholder(len(args)+1)), append(args, *v)
	}
	if v := delete.DriftBottleID; v != nil {
		where, args = append(where, "drift_bottle_id = "+placeholder(len(args)+1)), append(args, *v)
	}
	_, err := d.db.ExecContext(ctx, "DELETE FROM drift_bottle_tag WHERE "+strings.Join(where, " AND "), args...)
	return err
}

func (d *DB) UpsertDriftCandidatePool(ctx context.Context, upsert *store.DriftCandidatePool) (*store.DriftCandidatePool, error) {
	stmt := `
		INSERT INTO drift_candidate_pool (user_id, source_memo_id, candidate_memo_id, score, tier, refreshed_ts, expires_ts)
		VALUES ($1, $2, $3, $4, $5, $6, $7)
		ON CONFLICT (user_id, source_memo_id, candidate_memo_id)
		DO UPDATE SET score=EXCLUDED.score, tier=EXCLUDED.tier, refreshed_ts=EXCLUDED.refreshed_ts, expires_ts=EXCLUDED.expires_ts
		RETURNING id, user_id, source_memo_id, candidate_memo_id, score, tier, refreshed_ts, expires_ts
	`
	item := &store.DriftCandidatePool{}
	if err := d.db.QueryRowContext(ctx, stmt, upsert.UserID, upsert.SourceMemoID, upsert.CandidateMemoID, upsert.Score, upsert.Tier, upsert.RefreshedTs, upsert.ExpiresTs).
		Scan(&item.ID, &item.UserID, &item.SourceMemoID, &item.CandidateMemoID, &item.Score, &item.Tier, &item.RefreshedTs, &item.ExpiresTs); err != nil {
		return nil, err
	}
	return item, nil
}

func (d *DB) ListDriftCandidatePools(ctx context.Context, find *store.FindDriftCandidatePool) ([]*store.DriftCandidatePool, error) {
	where, args := []string{"1 = 1"}, []any{}
	if v := find.ID; v != nil {
		where, args = append(where, "id = "+placeholder(len(args)+1)), append(args, *v)
	}
	if v := find.UserID; v != nil {
		where, args = append(where, "user_id = "+placeholder(len(args)+1)), append(args, *v)
	}
	if v := find.SourceMemoID; v != nil {
		where, args = append(where, "source_memo_id = "+placeholder(len(args)+1)), append(args, *v)
	}
	if v := find.CandidateMemoID; v != nil {
		where, args = append(where, "candidate_memo_id = "+placeholder(len(args)+1)), append(args, *v)
	}
	query := `SELECT id, user_id, source_memo_id, candidate_memo_id, score, tier, refreshed_ts, expires_ts FROM drift_candidate_pool WHERE ` + strings.Join(where, " AND ") + ` ORDER BY score DESC, id DESC`
	if find.Limit != nil {
		query = fmt.Sprintf("%s LIMIT %d", query, *find.Limit)
		if find.Offset != nil {
			query = fmt.Sprintf("%s OFFSET %d", query, *find.Offset)
		}
	}
	rows, err := d.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	list := make([]*store.DriftCandidatePool, 0)
	for rows.Next() {
		item := &store.DriftCandidatePool{}
		if err := rows.Scan(&item.ID, &item.UserID, &item.SourceMemoID, &item.CandidateMemoID, &item.Score, &item.Tier, &item.RefreshedTs, &item.ExpiresTs); err != nil {
			return nil, err
		}
		list = append(list, item)
	}
	return list, rows.Err()
}

func (d *DB) DeleteDriftCandidatePool(ctx context.Context, delete *store.DeleteDriftCandidatePool) error {
	where, args := []string{"1 = 1"}, []any{}
	if v := delete.ID; v != nil {
		where, args = append(where, "id = "+placeholder(len(args)+1)), append(args, *v)
	}
	if v := delete.UserID; v != nil {
		where, args = append(where, "user_id = "+placeholder(len(args)+1)), append(args, *v)
	}
	if v := delete.SourceMemoID; v != nil {
		where, args = append(where, "source_memo_id = "+placeholder(len(args)+1)), append(args, *v)
	}
	if v := delete.CandidateMemoID; v != nil {
		where, args = append(where, "candidate_memo_id = "+placeholder(len(args)+1)), append(args, *v)
	}
	_, err := d.db.ExecContext(ctx, "DELETE FROM drift_candidate_pool WHERE "+strings.Join(where, " AND "), args...)
	return err
}

func (d *DB) CreateDriftPickLog(ctx context.Context, create *store.DriftPickLog) (*store.DriftPickLog, error) {
	stmt := `INSERT INTO drift_pick_log (user_id, memo_id, candidate_pool_id, picked_ts) VALUES ($1, $2, $3, $4) RETURNING id`
	if err := d.db.QueryRowContext(ctx, stmt, create.UserID, create.MemoID, create.CandidatePoolID, create.PickedTs).Scan(&create.ID); err != nil {
		return nil, err
	}
	return create, nil
}

func (d *DB) ListDriftPickLogs(ctx context.Context, find *store.FindDriftPickLog) ([]*store.DriftPickLog, error) {
	where, args := []string{"1 = 1"}, []any{}
	if v := find.ID; v != nil {
		where, args = append(where, "id = "+placeholder(len(args)+1)), append(args, *v)
	}
	if v := find.UserID; v != nil {
		where, args = append(where, "user_id = "+placeholder(len(args)+1)), append(args, *v)
	}
	if v := find.MemoID; v != nil {
		where, args = append(where, "memo_id = "+placeholder(len(args)+1)), append(args, *v)
	}
	if len(find.UserIDIn) > 0 {
		holders := make([]string, 0, len(find.UserIDIn))
		for _, id := range find.UserIDIn {
			holders = append(holders, placeholder(len(args)+1))
			args = append(args, id)
		}
		where = append(where, "user_id IN ("+strings.Join(holders, ", ")+")")
	}
	query := `SELECT id, user_id, memo_id, candidate_pool_id, picked_ts FROM drift_pick_log WHERE ` + strings.Join(where, " AND ") + ` ORDER BY picked_ts DESC, id DESC`
	if find.Limit != nil {
		query = fmt.Sprintf("%s LIMIT %d", query, *find.Limit)
		if find.Offset != nil {
			query = fmt.Sprintf("%s OFFSET %d", query, *find.Offset)
		}
	}
	rows, err := d.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	list := make([]*store.DriftPickLog, 0)
	for rows.Next() {
		item := &store.DriftPickLog{}
		if err := rows.Scan(&item.ID, &item.UserID, &item.MemoID, &item.CandidatePoolID, &item.PickedTs); err != nil {
			return nil, err
		}
		list = append(list, item)
	}
	return list, rows.Err()
}

func (d *DB) UpsertDriftDailyQuota(ctx context.Context, upsert *store.DriftDailyQuota) (*store.DriftDailyQuota, error) {
	stmt := `
		INSERT INTO drift_daily_quota (user_id, day, picked_count, limit_count, updated_ts)
		VALUES ($1, $2, $3, $4, $5)
		ON CONFLICT (user_id, day)
		DO UPDATE SET picked_count=EXCLUDED.picked_count, limit_count=EXCLUDED.limit_count, updated_ts=EXCLUDED.updated_ts
		RETURNING user_id, day, picked_count, limit_count, updated_ts
	`
	item := &store.DriftDailyQuota{}
	if err := d.db.QueryRowContext(ctx, stmt, upsert.UserID, upsert.Day, upsert.PickedCount, upsert.LimitCount, upsert.UpdatedTs).
		Scan(&item.UserID, &item.Day, &item.PickedCount, &item.LimitCount, &item.UpdatedTs); err != nil {
		return nil, err
	}
	return item, nil
}

func (d *DB) GetDriftDailyQuota(ctx context.Context, find *store.FindDriftDailyQuota) (*store.DriftDailyQuota, error) {
	where, args := []string{"1 = 1"}, []any{}
	if find.UserID != nil {
		where, args = append(where, "user_id = "+placeholder(len(args)+1)), append(args, *find.UserID)
	}
	if find.Day != nil {
		where, args = append(where, "day = "+placeholder(len(args)+1)), append(args, *find.Day)
	}
	query := `SELECT user_id, day, picked_count, limit_count, updated_ts FROM drift_daily_quota WHERE ` + strings.Join(where, " AND ") + ` LIMIT 1`
	item := &store.DriftDailyQuota{}
	if err := d.db.QueryRowContext(ctx, query, args...).Scan(&item.UserID, &item.Day, &item.PickedCount, &item.LimitCount, &item.UpdatedTs); err != nil {
		if err == sql.ErrNoRows {
			return nil, nil
		}
		return nil, err
	}
	return item, nil
}
