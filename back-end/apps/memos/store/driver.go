package store

import (
	"context"
	"database/sql"
)

// Driver is an interface for store driver.
// It contains all methods that store database driver should implement.
type Driver interface {
	GetDB() *sql.DB
	Close() error

	IsInitialized(ctx context.Context) (bool, error)

	// Activity model related methods.
	CreateActivity(ctx context.Context, create *Activity) (*Activity, error)
	ListActivities(ctx context.Context, find *FindActivity) ([]*Activity, error)

	// Attachment model related methods.
	CreateAttachment(ctx context.Context, create *Attachment) (*Attachment, error)
	ListAttachments(ctx context.Context, find *FindAttachment) ([]*Attachment, error)
	UpdateAttachment(ctx context.Context, update *UpdateAttachment) error
	DeleteAttachment(ctx context.Context, delete *DeleteAttachment) error

	// Memo model related methods.
	CreateMemo(ctx context.Context, create *Memo) (*Memo, error)
	ListMemos(ctx context.Context, find *FindMemo) ([]*Memo, error)
	UpdateMemo(ctx context.Context, update *UpdateMemo) error
	DeleteMemo(ctx context.Context, delete *DeleteMemo) error

	// MemoRelation model related methods.
	UpsertMemoRelation(ctx context.Context, create *MemoRelation) (*MemoRelation, error)
	ListMemoRelations(ctx context.Context, find *FindMemoRelation) ([]*MemoRelation, error)
	DeleteMemoRelation(ctx context.Context, delete *DeleteMemoRelation) error

	// InstanceSetting model related methods.
	UpsertInstanceSetting(ctx context.Context, upsert *InstanceSetting) (*InstanceSetting, error)
	ListInstanceSettings(ctx context.Context, find *FindInstanceSetting) ([]*InstanceSetting, error)
	DeleteInstanceSetting(ctx context.Context, delete *DeleteInstanceSetting) error

	// User model related methods.
	CreateUser(ctx context.Context, create *User) (*User, error)
	// InsertBuiltinAdmin inserts the fixed id=1 admin row when no admin exists yet (see EnsureBuiltinAdmin).
	InsertBuiltinAdmin(ctx context.Context) error
	UpdateUser(ctx context.Context, update *UpdateUser) (*User, error)
	ListUsers(ctx context.Context, find *FindUser) ([]*User, error)
	DeleteUser(ctx context.Context, delete *DeleteUser) error

	// UserSetting model related methods.
	UpsertUserSetting(ctx context.Context, upsert *UserSetting) (*UserSetting, error)
	ListUserSettings(ctx context.Context, find *FindUserSetting) ([]*UserSetting, error)

	// IdentityProvider model related methods.
	CreateIdentityProvider(ctx context.Context, create *IdentityProvider) (*IdentityProvider, error)
	ListIdentityProviders(ctx context.Context, find *FindIdentityProvider) ([]*IdentityProvider, error)
	UpdateIdentityProvider(ctx context.Context, update *UpdateIdentityProvider) (*IdentityProvider, error)
	DeleteIdentityProvider(ctx context.Context, delete *DeleteIdentityProvider) error

	// Inbox model related methods.
	CreateInbox(ctx context.Context, create *Inbox) (*Inbox, error)
	ListInboxes(ctx context.Context, find *FindInbox) ([]*Inbox, error)
	UpdateInbox(ctx context.Context, update *UpdateInbox) (*Inbox, error)
	DeleteInbox(ctx context.Context, delete *DeleteInbox) error

	// Reaction model related methods.
	UpsertReaction(ctx context.Context, create *Reaction) (*Reaction, error)
	ListReactions(ctx context.Context, find *FindReaction) ([]*Reaction, error)
	GetReaction(ctx context.Context, find *FindReaction) (*Reaction, error)
	DeleteReaction(ctx context.Context, delete *DeleteReaction) error

	// DriftBottle model related methods.
	CreateDriftBottle(ctx context.Context, create *DriftBottle) (*DriftBottle, error)
	ListDriftBottles(ctx context.Context, find *FindDriftBottle) ([]*DriftBottle, error)
	UpdateDriftBottle(ctx context.Context, update *UpdateDriftBottle) error
	UpsertDriftBottleTag(ctx context.Context, upsert *DriftBottleTag) (*DriftBottleTag, error)
	ListDriftBottleTags(ctx context.Context, find *FindDriftBottleTag) ([]*DriftBottleTag, error)
	DeleteDriftBottleTag(ctx context.Context, delete *DeleteDriftBottleTag) error

	// DriftCandidatePool model related methods.
	UpsertDriftCandidatePool(ctx context.Context, upsert *DriftCandidatePool) (*DriftCandidatePool, error)
	ListDriftCandidatePools(ctx context.Context, find *FindDriftCandidatePool) ([]*DriftCandidatePool, error)
	DeleteDriftCandidatePool(ctx context.Context, delete *DeleteDriftCandidatePool) error

	// DriftPickLog model related methods.
	CreateDriftPickLog(ctx context.Context, create *DriftPickLog) (*DriftPickLog, error)
	ListDriftPickLogs(ctx context.Context, find *FindDriftPickLog) ([]*DriftPickLog, error)

	// DriftDailyQuota model related methods.
	UpsertDriftDailyQuota(ctx context.Context, upsert *DriftDailyQuota) (*DriftDailyQuota, error)
	GetDriftDailyQuota(ctx context.Context, find *FindDriftDailyQuota) (*DriftDailyQuota, error)
}
