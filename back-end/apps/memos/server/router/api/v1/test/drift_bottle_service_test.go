package test

import (
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	apiv1 "github.com/usememos/memos/proto/gen/api/v1"
	"github.com/usememos/memos/store"
)

func TestCreateDriftBottleRequiresAuth(t *testing.T) {
	ctx := context.Background()
	ts := NewTestService(t)
	defer ts.Cleanup()

	_, err := ts.Service.CreateDriftBottle(ctx, &apiv1.CreateDriftBottleRequest{
		Content: "hello drift bottle",
	})
	require.Error(t, err)
	require.Equal(t, codes.Unauthenticated, status.Code(err))
}

func TestDriftBottleAccessAndPickQuota(t *testing.T) {
	ctx := context.Background()
	ts := NewTestService(t)
	defer ts.Cleanup()

	owner, err := ts.CreateRegularUser(ctx, "owner")
	require.NoError(t, err)
	viewer, err := ts.CreateRegularUser(ctx, "viewer")
	require.NoError(t, err)

	ownerCtx := ts.CreateUserContext(ctx, owner.ID)
	viewerCtx := ts.CreateUserContext(ctx, viewer.ID)

	created, err := ts.Service.CreateDriftBottle(ownerCtx, &apiv1.CreateDriftBottleRequest{
		Content: "hello world drift bottle content",
	})
	require.NoError(t, err)
	require.NotNil(t, created)

	_, err = ts.Service.GetDriftBottle(viewerCtx, &apiv1.GetDriftBottleRequest{Name: created.Name})
	require.Error(t, err)
	require.Equal(t, codes.PermissionDenied, status.Code(err))

	// Create one source memo for viewer so refresh has profile input.
	_, err = ts.Service.CreateMemo(viewerCtx, &apiv1.CreateMemoRequest{
		Memo: &apiv1.Memo{
			Content:    "hello world from viewer profile",
			Visibility: apiv1.Visibility_PRIVATE,
		},
	})
	require.NoError(t, err)

	picked, err := ts.Service.PickDriftBottle(viewerCtx, &apiv1.PickDriftBottleRequest{})
	require.NoError(t, err)
	require.NotNil(t, picked.GetDriftBottle())
	require.Equal(t, created.Name, picked.GetDriftBottle().GetName())

	accessible, err := ts.Service.GetDriftBottle(viewerCtx, &apiv1.GetDriftBottleRequest{Name: created.Name})
	require.NoError(t, err)
	require.Equal(t, created.Name, accessible.GetName())

	day := time.Now().UTC().Format("2006-01-02")
	_, err = ts.Store.UpsertDriftDailyQuota(viewerCtx, &store.DriftDailyQuota{
		UserID:      viewer.ID,
		Day:         day,
		PickedCount: 1,
		LimitCount:  1,
		UpdatedTs:   time.Now().Unix(),
	})
	require.NoError(t, err)

	_, err = ts.Service.PickDriftBottle(viewerCtx, &apiv1.PickDriftBottleRequest{})
	require.Error(t, err)
	require.Equal(t, codes.ResourceExhausted, status.Code(err))
}

func TestPickDriftBottleUnlimitedQuotaFromEnv(t *testing.T) {
	t.Setenv("DRIFT_BOTTLE_DAILY_LIMIT", "0")

	ctx := context.Background()
	ts := NewTestService(t)
	defer ts.Cleanup()

	owner, err := ts.CreateRegularUser(ctx, "owner-unlimited")
	require.NoError(t, err)
	viewer, err := ts.CreateRegularUser(ctx, "viewer-unlimited")
	require.NoError(t, err)

	ownerCtx := ts.CreateUserContext(ctx, owner.ID)
	viewerCtx := ts.CreateUserContext(ctx, viewer.ID)

	_, err = ts.Service.CreateDriftBottle(ownerCtx, &apiv1.CreateDriftBottleRequest{
		Content: "shared topic sunset sea wind",
	})
	require.NoError(t, err)
	_, err = ts.Service.CreateDriftBottle(ownerCtx, &apiv1.CreateDriftBottleRequest{
		Content: "shared topic sunset mountain wind",
	})
	require.NoError(t, err)

	_, err = ts.Service.CreateMemo(viewerCtx, &apiv1.CreateMemoRequest{
		Memo: &apiv1.Memo{
			Content:    "I like sunset sea and mountain with wind",
			Visibility: apiv1.Visibility_PRIVATE,
		},
	})
	require.NoError(t, err)

	_, err = ts.Service.RefreshMyDriftBottleCandidates(viewerCtx, &apiv1.RefreshMyDriftBottleCandidatesRequest{})
	require.NoError(t, err)

	firstPick, err := ts.Service.PickDriftBottle(viewerCtx, &apiv1.PickDriftBottleRequest{})
	require.NoError(t, err)
	require.Equal(t, int32(-1), firstPick.GetRemainingPicks())

	secondPick, err := ts.Service.PickDriftBottle(viewerCtx, &apiv1.PickDriftBottleRequest{})
	require.NoError(t, err)
	require.Equal(t, int32(-1), secondPick.GetRemainingPicks())
}

func TestCreateAndSearchDriftBottleTags(t *testing.T) {
	ctx := context.Background()
	ts := NewTestService(t)
	defer ts.Cleanup()

	owner, err := ts.CreateRegularUser(ctx, "owner-tags")
	require.NoError(t, err)
	viewer, err := ts.CreateRegularUser(ctx, "viewer-tags")
	require.NoError(t, err)

	ownerCtx := ts.CreateUserContext(ctx, owner.ID)
	viewerCtx := ts.CreateUserContext(ctx, viewer.ID)

	created, err := ts.Service.CreateDriftBottle(ownerCtx, &apiv1.CreateDriftBottleRequest{
		Content: "Tagged drift bottle content",
		Tags:    []string{"Stress", "Calm", "stress"},
	})
	require.NoError(t, err)
	require.NotNil(t, created)
	require.ElementsMatch(t, []string{"calm", "stress"}, created.GetTags())

	resp, err := ts.Service.SearchDriftBottles(viewerCtx, &apiv1.SearchDriftBottlesRequest{
		Tag: "stress",
	})
	require.NoError(t, err)
	require.Len(t, resp.GetDriftBottles(), 1)
	require.Equal(t, created.GetName(), resp.GetDriftBottles()[0].GetName())
}

func TestReplyDriftBottleRequiresAccess(t *testing.T) {
	ctx := context.Background()
	ts := NewTestService(t)
	defer ts.Cleanup()

	owner, err := ts.CreateRegularUser(ctx, "owner-reply")
	require.NoError(t, err)
	viewer, err := ts.CreateRegularUser(ctx, "viewer-reply")
	require.NoError(t, err)

	ownerCtx := ts.CreateUserContext(ctx, owner.ID)
	viewerCtx := ts.CreateUserContext(ctx, viewer.ID)

	created, err := ts.Service.CreateDriftBottle(ownerCtx, &apiv1.CreateDriftBottleRequest{
		Content: "A bottle waiting for a reply",
	})
	require.NoError(t, err)

	_, err = ts.Service.ReplyDriftBottle(viewerCtx, &apiv1.ReplyDriftBottleRequest{
		Name:    created.GetName(),
		Content: "before pick",
	})
	require.Error(t, err)
	require.Equal(t, codes.PermissionDenied, status.Code(err))

	_, err = ts.Service.CreateMemo(viewerCtx, &apiv1.CreateMemoRequest{
		Memo: &apiv1.Memo{
			Content:    "viewer profile for candidate generation",
			Visibility: apiv1.Visibility_PRIVATE,
		},
	})
	require.NoError(t, err)

	_, err = ts.Service.PickDriftBottle(viewerCtx, &apiv1.PickDriftBottleRequest{})
	require.NoError(t, err)

	reply, err := ts.Service.ReplyDriftBottle(viewerCtx, &apiv1.ReplyDriftBottleRequest{
		Name:    created.GetName(),
		Content: "I hear you",
	})
	require.NoError(t, err)
	require.Equal(t, "I hear you", reply.GetContent())
}

func TestReplyDriftBottleCreatesOwnerNotification(t *testing.T) {
	ctx := context.Background()
	ts := NewTestService(t)
	defer ts.Cleanup()

	owner, err := ts.CreateRegularUser(ctx, "owner-reply-notify")
	require.NoError(t, err)
	viewer, err := ts.CreateRegularUser(ctx, "viewer-reply-notify")
	require.NoError(t, err)

	ownerCtx := ts.CreateUserContext(ctx, owner.ID)
	viewerCtx := ts.CreateUserContext(ctx, viewer.ID)

	created, err := ts.Service.CreateDriftBottle(ownerCtx, &apiv1.CreateDriftBottleRequest{
		Content: "A bottle waiting for a reply notification",
	})
	require.NoError(t, err)

	_, err = ts.Service.CreateMemo(viewerCtx, &apiv1.CreateMemoRequest{
		Memo: &apiv1.Memo{
			Content:    "viewer profile for candidate generation",
			Visibility: apiv1.Visibility_PRIVATE,
		},
	})
	require.NoError(t, err)

	_, err = ts.Service.PickDriftBottle(viewerCtx, &apiv1.PickDriftBottleRequest{})
	require.NoError(t, err)

	reply, err := ts.Service.ReplyDriftBottle(viewerCtx, &apiv1.ReplyDriftBottleRequest{
		Name:    created.GetName(),
		Content: "I hear you",
	})
	require.NoError(t, err)

	resp, err := ts.Service.ListUserNotifications(ownerCtx, &apiv1.ListUserNotificationsRequest{
		Parent: fmt.Sprintf("users/%d", owner.ID),
	})
	require.NoError(t, err)
	require.Len(t, resp.GetNotifications(), 1)
	require.Equal(t, apiv1.UserNotification_MEMO_COMMENT, resp.GetNotifications()[0].GetType())
	require.NotNil(t, resp.GetNotifications()[0].GetMemoComment())
	require.Equal(t, reply.GetName(), resp.GetNotifications()[0].GetMemoComment().GetMemo())
	require.Equal(t, created.GetMemo(), resp.GetNotifications()[0].GetMemoComment().GetRelatedMemo())
}
