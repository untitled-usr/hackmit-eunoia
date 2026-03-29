package store

import "context"

type DriftBottleStatus string

const (
	DriftBottleStatusActive   DriftBottleStatus = "ACTIVE"
	DriftBottleStatusArchived DriftBottleStatus = "ARCHIVED"
)

type DriftBottle struct {
	ID int32
	// UID is the user provided unique identifier.
	UID string

	CreatorID int32
	MemoID    int32
	Status    DriftBottleStatus
	CreatedTs int64
	UpdatedTs int64
}

type DriftBottleTag struct {
	ID             int32
	DriftBottleID  int32
	Tag            string
	NormalizedTag  string
	CreatedTs      int64
}

type FindDriftBottle struct {
	ID        *int32
	UID       *string
	MemoID    *int32
	CreatorID *int32
	Status    *DriftBottleStatus
	IDList    []int32
	Limit     *int
	Offset    *int
}

type FindDriftBottleTag struct {
	ID            *int32
	DriftBottleID *int32
	NormalizedTag *string
	DriftBottleIDList []int32
	Limit         *int
	Offset        *int
}

type DeleteDriftBottleTag struct {
	ID            *int32
	DriftBottleID *int32
}

type UpdateDriftBottle struct {
	ID        int32
	UpdatedTs *int64
	Status    *DriftBottleStatus
}

type DriftCandidatePool struct {
	ID              int32
	UserID          int32
	SourceMemoID    int32
	CandidateMemoID int32
	Score           float64
	Tier            int32
	RefreshedTs     int64
	ExpiresTs       int64
}

type FindDriftCandidatePool struct {
	ID              *int32
	UserID          *int32
	SourceMemoID    *int32
	CandidateMemoID *int32
	Limit           *int
	Offset          *int
}

type DeleteDriftCandidatePool struct {
	ID              *int32
	UserID          *int32
	SourceMemoID    *int32
	CandidateMemoID *int32
}

type DriftPickLog struct {
	ID              int32
	UserID          int32
	MemoID          int32
	CandidatePoolID *int32
	PickedTs        int64
}

type FindDriftPickLog struct {
	ID       *int32
	UserID   *int32
	MemoID   *int32
	UserIDIn []int32
	Limit    *int
	Offset   *int
}

type DriftDailyQuota struct {
	UserID     int32
	Day        string
	PickedCount int32
	LimitCount int32
	UpdatedTs  int64
}

type FindDriftDailyQuota struct {
	UserID *int32
	Day    *string
}

func (s *Store) CreateDriftBottle(ctx context.Context, create *DriftBottle) (*DriftBottle, error) {
	return s.driver.CreateDriftBottle(ctx, create)
}

func (s *Store) ListDriftBottles(ctx context.Context, find *FindDriftBottle) ([]*DriftBottle, error) {
	return s.driver.ListDriftBottles(ctx, find)
}

func (s *Store) GetDriftBottle(ctx context.Context, find *FindDriftBottle) (*DriftBottle, error) {
	list, err := s.ListDriftBottles(ctx, find)
	if err != nil {
		return nil, err
	}
	if len(list) == 0 {
		return nil, nil
	}
	return list[0], nil
}

func (s *Store) UpdateDriftBottle(ctx context.Context, update *UpdateDriftBottle) error {
	return s.driver.UpdateDriftBottle(ctx, update)
}

func (s *Store) UpsertDriftBottleTag(ctx context.Context, upsert *DriftBottleTag) (*DriftBottleTag, error) {
	return s.driver.UpsertDriftBottleTag(ctx, upsert)
}

func (s *Store) ListDriftBottleTags(ctx context.Context, find *FindDriftBottleTag) ([]*DriftBottleTag, error) {
	return s.driver.ListDriftBottleTags(ctx, find)
}

func (s *Store) DeleteDriftBottleTag(ctx context.Context, delete *DeleteDriftBottleTag) error {
	return s.driver.DeleteDriftBottleTag(ctx, delete)
}

func (s *Store) UpsertDriftCandidatePool(ctx context.Context, upsert *DriftCandidatePool) (*DriftCandidatePool, error) {
	return s.driver.UpsertDriftCandidatePool(ctx, upsert)
}

func (s *Store) ListDriftCandidatePools(ctx context.Context, find *FindDriftCandidatePool) ([]*DriftCandidatePool, error) {
	return s.driver.ListDriftCandidatePools(ctx, find)
}

func (s *Store) DeleteDriftCandidatePool(ctx context.Context, delete *DeleteDriftCandidatePool) error {
	return s.driver.DeleteDriftCandidatePool(ctx, delete)
}

func (s *Store) CreateDriftPickLog(ctx context.Context, create *DriftPickLog) (*DriftPickLog, error) {
	return s.driver.CreateDriftPickLog(ctx, create)
}

func (s *Store) ListDriftPickLogs(ctx context.Context, find *FindDriftPickLog) ([]*DriftPickLog, error) {
	return s.driver.ListDriftPickLogs(ctx, find)
}

func (s *Store) UpsertDriftDailyQuota(ctx context.Context, upsert *DriftDailyQuota) (*DriftDailyQuota, error) {
	return s.driver.UpsertDriftDailyQuota(ctx, upsert)
}

func (s *Store) GetDriftDailyQuota(ctx context.Context, find *FindDriftDailyQuota) (*DriftDailyQuota, error) {
	return s.driver.GetDriftDailyQuota(ctx, find)
}
