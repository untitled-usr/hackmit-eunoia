package v1

import (
	"context"
	"fmt"
	"math/rand"
	"os"
	"strconv"
	"regexp"
	"sort"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/timestamppb"

	v1pb "github.com/usememos/memos/proto/gen/api/v1"
	storepb "github.com/usememos/memos/proto/gen/store"
	"github.com/usememos/memos/store"
)

const (
	defaultDriftDailyLimit   = int32(5)
	unlimitedRemainingPicks  = int32(-1)
	driftCandidateExpireSecs = int64(24 * 60 * 60)
	maxDriftBottleTags       = 8
	maxDriftBottleTagLength  = 32
	defaultSearchPageSize    = 20
	maxSearchPageSize        = 100
)

var wordMatcher = regexp.MustCompile(`[a-zA-Z0-9\p{Han}]+`)

type weightedDriftCandidate struct {
	pool  *store.DriftCandidatePool
	drift *store.DriftBottle
}

func (s *APIV1Service) CreateDriftBottle(ctx context.Context, request *v1pb.CreateDriftBottleRequest) (*v1pb.DriftBottle, error) {
	user, err := s.fetchCurrentUser(ctx)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get user")
	}
	if user == nil {
		return nil, status.Errorf(codes.Unauthenticated, "user not authenticated")
	}
	if strings.TrimSpace(request.Content) == "" {
		return nil, status.Errorf(codes.InvalidArgument, "content is required")
	}

	memoMessage, err := s.CreateMemo(ctx, &v1pb.CreateMemoRequest{
		Memo: &v1pb.Memo{
			Content:    request.Content,
			Visibility: v1pb.Visibility_PRIVATE,
		},
	})
	if err != nil {
		return nil, err
	}
	memoUID, err := ExtractMemoUIDFromName(memoMessage.Name)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to parse memo uid: %v", err)
	}
	memo, err := s.Store.GetMemo(ctx, &store.FindMemo{UID: &memoUID})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get created memo")
	}
	if memo == nil {
		return nil, status.Errorf(codes.Internal, "created memo not found")
	}

	// Inline attachments are created first, then attached in batch to keep order deterministic.
	finalAttachments := make([]*v1pb.Attachment, 0, len(request.Attachments))
	for _, attachment := range request.Attachments {
		if attachment == nil {
			continue
		}
		if attachment.Name != "" && len(attachment.Content) == 0 {
			finalAttachments = append(finalAttachments, &v1pb.Attachment{Name: attachment.Name})
			continue
		}
		if attachment.Filename == "" {
			return nil, status.Errorf(codes.InvalidArgument, "attachment filename is required for inline content")
		}
		memoName := memoMessage.Name
		createdAttachment, err := s.CreateAttachment(ctx, &v1pb.CreateAttachmentRequest{
			Attachment: &v1pb.Attachment{
				Filename:     attachment.Filename,
				Content:      attachment.Content,
				Type:         attachment.Type,
				ExternalLink: attachment.ExternalLink,
				Memo:         &memoName,
			},
		})
		if err != nil {
			return nil, err
		}
		finalAttachments = append(finalAttachments, &v1pb.Attachment{Name: createdAttachment.Name})
	}
	if len(finalAttachments) > 0 {
		if _, err := s.SetMemoAttachments(ctx, &v1pb.SetMemoAttachmentsRequest{
			Name:        memoMessage.Name,
			Attachments: finalAttachments,
		}); err != nil {
			return nil, err
		}
	}

	driftUID, err := ValidateAndGenerateUID(request.DriftBottleId)
	if err != nil {
		return nil, err
	}
	now := time.Now().Unix()
	driftBottle, err := s.Store.CreateDriftBottle(ctx, &store.DriftBottle{
		UID:       driftUID,
		MemoID:    memo.ID,
		CreatorID: user.ID,
		Status:    store.DriftBottleStatusActive,
		CreatedTs: now,
		UpdatedTs: now,
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to create drift bottle: %v", err)
	}
	normalizedTags, err := normalizeDriftTags(request.Tags)
	if err != nil {
		return nil, err
	}
	if err := s.Store.DeleteDriftBottleTag(ctx, &store.DeleteDriftBottleTag{DriftBottleID: &driftBottle.ID}); err != nil {
		return nil, status.Errorf(codes.Internal, "failed to clear drift bottle tags")
	}
	nowTagTs := time.Now().Unix()
	for _, tag := range normalizedTags {
		if _, err := s.Store.UpsertDriftBottleTag(ctx, &store.DriftBottleTag{
			DriftBottleID: driftBottle.ID,
			Tag:           tag,
			NormalizedTag: strings.ToLower(tag),
			CreatedTs:     nowTagTs,
		}); err != nil {
			return nil, status.Errorf(codes.Internal, "failed to save drift bottle tags")
		}
	}

	if _, err := s.refreshMyCandidatePool(ctx, user.ID); err != nil {
		return nil, status.Errorf(codes.Internal, "failed to refresh candidate pool: %v", err)
	}
	return s.buildDriftBottleMessage(ctx, driftBottle, 0)
}

func (s *APIV1Service) GetDriftBottle(ctx context.Context, request *v1pb.GetDriftBottleRequest) (*v1pb.DriftBottle, error) {
	user, err := s.fetchCurrentUser(ctx)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get user")
	}
	if user == nil {
		return nil, status.Errorf(codes.Unauthenticated, "user not authenticated")
	}
	driftBottle, err := s.getAccessibleDriftBottle(ctx, request.Name, user)
	if err != nil {
		return nil, err
	}

	return s.buildDriftBottleMessage(ctx, driftBottle, 0)
}

func (s *APIV1Service) ReplyDriftBottle(ctx context.Context, request *v1pb.ReplyDriftBottleRequest) (*v1pb.Memo, error) {
	user, err := s.fetchCurrentUser(ctx)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get user")
	}
	if user == nil {
		return nil, status.Errorf(codes.Unauthenticated, "user not authenticated")
	}
	if strings.TrimSpace(request.Content) == "" {
		return nil, status.Errorf(codes.InvalidArgument, "content is required")
	}
	driftBottle, err := s.getAccessibleDriftBottle(ctx, request.Name, user)
	if err != nil {
		return nil, err
	}
	memo, err := s.Store.GetMemo(ctx, &store.FindMemo{ID: &driftBottle.MemoID})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get backing memo")
	}
	if memo == nil {
		return nil, status.Errorf(codes.NotFound, "backing memo not found")
	}
	commentMemo, err := s.CreateMemo(ctx, &v1pb.CreateMemoRequest{
		Memo: &v1pb.Memo{
			Content:    request.Content,
			Visibility: v1pb.Visibility_PRIVATE,
		},
		MemoId: request.CommentId,
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to create reply memo")
	}
	commentUID, err := ExtractMemoUIDFromName(commentMemo.Name)
	if err != nil {
		return nil, status.Errorf(codes.InvalidArgument, "invalid comment memo name: %v", err)
	}
	commentMemoModel, err := s.Store.GetMemo(ctx, &store.FindMemo{UID: &commentUID})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get reply memo")
	}
	if commentMemoModel == nil {
		return nil, status.Errorf(codes.Internal, "reply memo not found")
	}
	if _, err := s.Store.UpsertMemoRelation(ctx, &store.MemoRelation{
		MemoID:        commentMemoModel.ID,
		RelatedMemoID: memo.ID,
		Type:          store.MemoRelationComment,
	}); err != nil {
		return nil, status.Errorf(codes.Internal, "failed to create reply relation")
	}
	commentCreatorID, err := ExtractUserIDFromName(commentMemo.Creator)
	if err != nil {
		return nil, status.Errorf(codes.InvalidArgument, "invalid comment creator")
	}
	if commentCreatorID != memo.CreatorID {
		activity, err := s.Store.CreateActivity(ctx, &store.Activity{
			CreatorID: commentCreatorID,
			Type:      store.ActivityTypeMemoComment,
			Level:     store.ActivityLevelInfo,
			Payload: &storepb.ActivityPayload{
				MemoComment: &storepb.ActivityMemoCommentPayload{
					MemoId:        commentMemoModel.ID,
					RelatedMemoId: memo.ID,
				},
			},
		})
		if err != nil {
			return nil, status.Errorf(codes.Internal, "failed to create reply activity")
		}
		if _, err := s.Store.CreateInbox(ctx, &store.Inbox{
			SenderID:   commentCreatorID,
			ReceiverID: memo.CreatorID,
			Status:     store.UNREAD,
			Message: &storepb.InboxMessage{
				Type:       storepb.InboxMessage_MEMO_COMMENT,
				ActivityId: &activity.ID,
			},
		}); err != nil {
			return nil, status.Errorf(codes.Internal, "failed to create reply inbox")
		}
	}
	s.SSEHub.Broadcast(&SSEEvent{
		Type: SSEEventMemoCommentCreated,
		Name: fmt.Sprintf("%s%s", MemoNamePrefix, memo.UID),
	})
	return commentMemo, nil
}

func (s *APIV1Service) PickDriftBottle(ctx context.Context, _ *v1pb.PickDriftBottleRequest) (*v1pb.PickDriftBottleResponse, error) {
	user, err := s.fetchCurrentUser(ctx)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get user")
	}
	if user == nil {
		return nil, status.Errorf(codes.Unauthenticated, "user not authenticated")
	}

	day := time.Now().UTC().Format("2006-01-02")
	dailyLimit := getDriftDailyLimitFromEnv()
	quota, err := s.Store.GetDriftDailyQuota(ctx, &store.FindDriftDailyQuota{
		UserID: &user.ID,
		Day:    &day,
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get daily quota")
	}
	if quota == nil {
		quota = &store.DriftDailyQuota{
			UserID:      user.ID,
			Day:         day,
			PickedCount: 0,
			LimitCount:  dailyLimit,
			UpdatedTs:   time.Now().Unix(),
		}
	}
	if quota.LimitCount != 0 && quota.PickedCount >= quota.LimitCount {
		return nil, status.Errorf(codes.ResourceExhausted, "daily drift pick limit reached")
	}

	candidates, err := s.Store.ListDriftCandidatePools(ctx, &store.FindDriftCandidatePool{
		UserID: &user.ID,
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to list candidates")
	}
	if len(candidates) == 0 {
		if _, err := s.refreshMyCandidatePool(ctx, user.ID); err != nil {
			return nil, status.Errorf(codes.Internal, "failed to refresh candidates")
		}
		candidates, err = s.Store.ListDriftCandidatePools(ctx, &store.FindDriftCandidatePool{
			UserID: &user.ID,
		})
		if err != nil {
			return nil, status.Errorf(codes.Internal, "failed to list candidates after refresh")
		}
	}
	if len(candidates) == 0 {
		return nil, status.Errorf(codes.NotFound, "no candidate drift bottles available")
	}

	pickedLogs, err := s.Store.ListDriftPickLogs(ctx, &store.FindDriftPickLog{
		UserID: &user.ID,
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to list pick logs")
	}
	pickedMemoSet := make(map[int32]bool, len(pickedLogs))
	for _, log := range pickedLogs {
		pickedMemoSet[log.MemoID] = true
	}

	eligible := make([]weightedDriftCandidate, 0, len(candidates))
	nowTs := time.Now().Unix()
	for _, candidate := range candidates {
		if candidate.ExpiresTs > 0 && candidate.ExpiresTs < nowTs {
			continue
		}
		if pickedMemoSet[candidate.CandidateMemoID] {
			continue
		}
		driftBottle, err := s.Store.GetDriftBottle(ctx, &store.FindDriftBottle{MemoID: &candidate.CandidateMemoID})
		if err != nil || driftBottle == nil {
			continue
		}
		if driftBottle.CreatorID == user.ID || driftBottle.Status != store.DriftBottleStatusActive {
			continue
		}
		eligible = append(eligible, weightedDriftCandidate{pool: candidate, drift: driftBottle})
	}
	if len(eligible) == 0 {
		return nil, status.Errorf(codes.NotFound, "no eligible drift bottles")
	}

	selected := chooseWeightedCandidate(eligible)
	candidatePoolID := selected.pool.ID
	if _, err := s.Store.CreateDriftPickLog(ctx, &store.DriftPickLog{
		UserID:          user.ID,
		MemoID:          selected.drift.MemoID,
		CandidatePoolID: &candidatePoolID,
		PickedTs:        time.Now().Unix(),
	}); err != nil {
		return nil, status.Errorf(codes.Internal, "failed to create pick log")
	}

	quota.PickedCount++
	quota.UpdatedTs = time.Now().Unix()
	if _, err := s.Store.UpsertDriftDailyQuota(ctx, quota); err != nil {
		return nil, status.Errorf(codes.Internal, "failed to update daily quota")
	}

	driftMessage, err := s.buildDriftBottleMessage(ctx, selected.drift, selected.pool.Score)
	if err != nil {
		return nil, err
	}
	remainingPicks := maxInt32(0, quota.LimitCount-quota.PickedCount)
	if quota.LimitCount == 0 {
		remainingPicks = unlimitedRemainingPicks
	}
	return &v1pb.PickDriftBottleResponse{
		DriftBottle:    driftMessage,
		RemainingPicks: remainingPicks,
	}, nil
}

func (s *APIV1Service) RefreshMyDriftBottleCandidates(ctx context.Context, _ *v1pb.RefreshMyDriftBottleCandidatesRequest) (*v1pb.RefreshMyDriftBottleCandidatesResponse, error) {
	user, err := s.fetchCurrentUser(ctx)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get user")
	}
	if user == nil {
		return nil, status.Errorf(codes.Unauthenticated, "user not authenticated")
	}

	count, err := s.refreshMyCandidatePool(ctx, user.ID)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to refresh candidate pool: %v", err)
	}
	return &v1pb.RefreshMyDriftBottleCandidatesResponse{RefreshedCount: int32(count)}, nil
}

func (s *APIV1Service) getAccessibleDriftBottle(ctx context.Context, name string, user *store.User) (*store.DriftBottle, error) {
	uid, err := ExtractDriftBottleUIDFromName(name)
	if err != nil {
		return nil, status.Errorf(codes.InvalidArgument, "invalid drift bottle name: %v", err)
	}
	driftBottle, err := s.Store.GetDriftBottle(ctx, &store.FindDriftBottle{UID: &uid})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get drift bottle")
	}
	if driftBottle == nil {
		return nil, status.Errorf(codes.NotFound, "drift bottle not found")
	}
	if driftBottle.CreatorID != user.ID && !isSuperUser(user) {
		limit := 1
		pickLogs, err := s.Store.ListDriftPickLogs(ctx, &store.FindDriftPickLog{
			UserID: &user.ID,
			MemoID: &driftBottle.MemoID,
			Limit:  &limit,
		})
		if err != nil {
			return nil, status.Errorf(codes.Internal, "failed to check pick logs")
		}
		if len(pickLogs) == 0 {
			return nil, status.Errorf(codes.PermissionDenied, "permission denied")
		}
	}
	return driftBottle, nil
}

func (s *APIV1Service) SearchDriftBottles(ctx context.Context, request *v1pb.SearchDriftBottlesRequest) (*v1pb.SearchDriftBottlesResponse, error) {
	user, err := s.fetchCurrentUser(ctx)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get user")
	}
	if user == nil {
		return nil, status.Errorf(codes.Unauthenticated, "user not authenticated")
	}
	searchTag, err := normalizeSearchTag(request.Tag)
	if err != nil {
		return nil, err
	}
	pageSize := int(request.PageSize)
	if pageSize <= 0 {
		pageSize = defaultSearchPageSize
	}
	if pageSize > maxSearchPageSize {
		pageSize = maxSearchPageSize
	}
	offset := 0
	if request.PageToken != "" {
		offset, err = strconv.Atoi(request.PageToken)
		if err != nil || offset < 0 {
			return nil, status.Errorf(codes.InvalidArgument, "invalid page token")
		}
	}
	tags, err := s.Store.ListDriftBottleTags(ctx, &store.FindDriftBottleTag{
		NormalizedTag: &searchTag,
		Limit:         &pageSize,
		Offset:        &offset,
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to search tags")
	}
	if len(tags) == 0 {
		return &v1pb.SearchDriftBottlesResponse{DriftBottles: []*v1pb.DriftBottle{}}, nil
	}
	bottleIDs := make([]int32, 0, len(tags))
	for _, item := range tags {
		bottleIDs = append(bottleIDs, item.DriftBottleID)
	}
	activeStatus := store.DriftBottleStatusActive
	bottles, err := s.Store.ListDriftBottles(ctx, &store.FindDriftBottle{
		IDList:  bottleIDs,
		Status:  &activeStatus,
		Limit:   &pageSize,
		Offset:  intPtr(offset),
	})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to list drift bottles")
	}
	result := make([]*v1pb.DriftBottle, 0, len(bottles))
	for _, bottle := range bottles {
		msg, err := s.buildDriftBottleMessage(ctx, bottle, 0)
		if err != nil {
			continue
		}
		result = append(result, msg)
	}
	nextPageToken := ""
	if len(tags) == pageSize {
		nextPageToken = strconv.Itoa(offset + len(tags))
	}
	return &v1pb.SearchDriftBottlesResponse{
		DriftBottles:  result,
		NextPageToken: nextPageToken,
	}, nil
}

func (s *APIV1Service) refreshMyCandidatePool(ctx context.Context, userID int32) (int, error) {
	if err := s.Store.DeleteDriftCandidatePool(ctx, &store.DeleteDriftCandidatePool{UserID: &userID}); err != nil {
		return 0, err
	}

	activeState := store.Normal
	sourceLimit := 5
	sourceMemos, err := s.Store.ListMemos(ctx, &store.FindMemo{
		CreatorID:       &userID,
		RowStatus:       &activeState,
		ExcludeComments: true,
		Limit:           &sourceLimit,
	})
	if err != nil {
		return 0, err
	}
	if len(sourceMemos) == 0 {
		return 0, nil
	}

	driftStatus := store.DriftBottleStatusActive
	allBottles, err := s.Store.ListDriftBottles(ctx, &store.FindDriftBottle{Status: &driftStatus})
	if err != nil {
		return 0, err
	}
	if len(allBottles) == 0 {
		return 0, nil
	}

	memoIDs := make([]int32, 0, len(allBottles))
	for _, b := range allBottles {
		memoIDs = append(memoIDs, b.MemoID)
	}
	candidateMemos, err := s.Store.ListMemos(ctx, &store.FindMemo{
		IDList:          memoIDs,
		RowStatus:       &activeState,
		ExcludeComments: true,
	})
	if err != nil {
		return 0, err
	}
	candidateMemoMap := make(map[int32]*store.Memo, len(candidateMemos))
	for _, memo := range candidateMemos {
		candidateMemoMap[memo.ID] = memo
	}

	pickedLogs, err := s.Store.ListDriftPickLogs(ctx, &store.FindDriftPickLog{UserID: &userID})
	if err != nil {
		return 0, err
	}
	pickedMemoSet := map[int32]bool{}
	for _, log := range pickedLogs {
		pickedMemoSet[log.MemoID] = true
	}

	totalUpserted := 0
	for idx, source := range sourceMemos {
		topN := 5 - idx
		if topN <= 0 {
			break
		}
		candidateMemoIDs := make([]int32, 0, len(allBottles))
		for _, bottle := range allBottles {
			candidateMemo := candidateMemoMap[bottle.MemoID]
			if candidateMemo == nil {
				continue
			}
			if candidateMemo.CreatorID == userID || candidateMemo.ID == source.ID {
				continue
			}
			if pickedMemoSet[candidateMemo.ID] {
				continue
			}
			candidateMemoIDs = append(candidateMemoIDs, candidateMemo.ID)
		}
		rand.Shuffle(len(candidateMemoIDs), func(i, j int) {
			candidateMemoIDs[i], candidateMemoIDs[j] = candidateMemoIDs[j], candidateMemoIDs[i]
		})
		seen := map[int32]bool{}
		nowTs := time.Now().Unix()
		for _, memoID := range candidateMemoIDs {
			if len(seen) >= topN {
				break
			}
			if seen[memoID] {
				continue
			}
			seen[memoID] = true
			_, err := s.Store.UpsertDriftCandidatePool(ctx, &store.DriftCandidatePool{
				UserID:          userID,
				SourceMemoID:    source.ID,
				CandidateMemoID: memoID,
				Score:           1,
				Tier:            int32(topN),
				RefreshedTs:     nowTs,
				ExpiresTs:       nowTs + driftCandidateExpireSecs,
			})
			if err != nil {
				return totalUpserted, err
			}
			totalUpserted++
		}
	}
	return totalUpserted, nil
}

func (s *APIV1Service) buildDriftBottleMessage(ctx context.Context, driftBottle *store.DriftBottle, score float64) (*v1pb.DriftBottle, error) {
	memo, err := s.Store.GetMemo(ctx, &store.FindMemo{ID: &driftBottle.MemoID})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to get memo")
	}
	if memo == nil {
		return nil, status.Errorf(codes.NotFound, "backing memo not found")
	}
	attachments, err := s.Store.ListAttachments(ctx, &store.FindAttachment{MemoID: &memo.ID})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to list attachments")
	}
	contentID := fmt.Sprintf("%s%s", MemoNamePrefix, memo.UID)
	reactions, err := s.Store.ListReactions(ctx, &store.FindReaction{ContentID: &contentID})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to list reactions")
	}
	relations, err := s.loadMemoRelations(ctx, memo)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to load relations")
	}
	memoInfo, err := s.convertMemoFromStore(ctx, memo, reactions, attachments, relations)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to convert memo")
	}
	tags, err := s.Store.ListDriftBottleTags(ctx, &store.FindDriftBottleTag{DriftBottleID: &driftBottle.ID})
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to list drift bottle tags")
	}
	tagValues := make([]string, 0, len(tags))
	for _, tag := range tags {
		tagValues = append(tagValues, tag.Tag)
	}
	sort.Strings(tagValues)

	return &v1pb.DriftBottle{
		Name:       fmt.Sprintf("%s%s", DriftBottleNamePrefix, driftBottle.UID),
		Memo:       fmt.Sprintf("%s%s", MemoNamePrefix, memo.UID),
		Creator:    fmt.Sprintf("%s%d", UserNamePrefix, driftBottle.CreatorID),
		State:      convertDriftBottleStateFromStore(driftBottle.Status),
		Score:      score,
		MemoInfo:   memoInfo,
		Tags:       tagValues,
		CreateTime: timestamppb.New(time.Unix(driftBottle.CreatedTs, 0)),
		UpdateTime: timestamppb.New(time.Unix(driftBottle.UpdatedTs, 0)),
	}, nil
}

func convertDriftBottleStateFromStore(state store.DriftBottleStatus) v1pb.DriftBottle_State {
	switch state {
	case store.DriftBottleStatusArchived:
		return v1pb.DriftBottle_ARCHIVED
	default:
		return v1pb.DriftBottle_ACTIVE
	}
}

func chooseWeightedCandidate(items []weightedDriftCandidate) weightedDriftCandidate {
	return items[rand.Intn(len(items))]
}

func computeMemoSimilarityScore(source, candidate *store.Memo) float64 {
	if source == nil || candidate == nil {
		return 0
	}
	sourceTokens := tokenize(source.Content)
	candidateTokens := tokenize(candidate.Content)
	if len(sourceTokens) == 0 || len(candidateTokens) == 0 {
		return 0
	}
	intersection := 0
	unionMap := map[string]bool{}
	for token := range sourceTokens {
		unionMap[token] = true
		if candidateTokens[token] {
			intersection++
		}
	}
	for token := range candidateTokens {
		unionMap[token] = true
	}
	if len(unionMap) == 0 {
		return 0
	}
	jaccard := float64(intersection) / float64(len(unionMap))
	return jaccard*100 + float64(intersection)
}

func tokenize(content string) map[string]bool {
	result := map[string]bool{}
	for _, token := range wordMatcher.FindAllString(strings.ToLower(content), -1) {
		if len(token) <= 1 {
			continue
		}
		result[token] = true
	}
	return result
}

func maxInt32(a, b int32) int32 {
	if a > b {
		return a
	}
	return b
}

func intPtr(v int) *int {
	return &v
}

func normalizeSearchTag(raw string) (string, error) {
	tag := strings.TrimSpace(strings.ToLower(raw))
	if tag == "" {
		return "", status.Errorf(codes.InvalidArgument, "tag is required")
	}
	if utf8.RuneCountInString(tag) > maxDriftBottleTagLength {
		return "", status.Errorf(codes.InvalidArgument, "tag is too long")
	}
	for _, r := range tag {
		if unicode.IsControl(r) {
			return "", status.Errorf(codes.InvalidArgument, "tag contains invalid control characters")
		}
	}
	return tag, nil
}

func normalizeDriftTags(tags []string) ([]string, error) {
	if len(tags) == 0 {
		return nil, nil
	}
	normalized := make([]string, 0, len(tags))
	seen := make(map[string]bool, len(tags))
	for _, raw := range tags {
		tag, err := normalizeSearchTag(raw)
		if err != nil {
			return nil, err
		}
		if seen[tag] {
			continue
		}
		seen[tag] = true
		normalized = append(normalized, tag)
		if len(normalized) > maxDriftBottleTags {
			return nil, status.Errorf(codes.InvalidArgument, "too many tags")
		}
	}
	return normalized, nil
}

func getDriftDailyLimitFromEnv() int32 {
	raw, ok := os.LookupEnv("DRIFT_BOTTLE_DAILY_LIMIT")
	if !ok || strings.TrimSpace(raw) == "" {
		return defaultDriftDailyLimit
	}
	value, err := strconv.ParseInt(strings.TrimSpace(raw), 10, 32)
	if err != nil || value < 0 {
		return defaultDriftDailyLimit
	}
	return int32(value)
}

