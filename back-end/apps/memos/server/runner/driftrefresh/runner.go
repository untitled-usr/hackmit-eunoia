package driftrefresh

import (
	"context"
	"log/slog"
	"regexp"
	"sort"
	"strings"
	"time"

	"github.com/usememos/memos/store"
)

const (
	runnerInterval            = 24 * time.Hour
	candidateExpirationSecond = int64(24 * 60 * 60)
)

var tokenMatcher = regexp.MustCompile(`[a-zA-Z0-9\p{Han}]+`)

type Runner struct {
	Store *store.Store
}

func NewRunner(store *store.Store) *Runner {
	return &Runner{Store: store}
}

func (r *Runner) Run(ctx context.Context) {
	ticker := time.NewTicker(runnerInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ticker.C:
			r.RunOnce(ctx)
		case <-ctx.Done():
			return
		}
	}
}

func (r *Runner) RunOnce(ctx context.Context) {
	if err := r.refreshAllActiveUsers(ctx); err != nil {
		slog.Warn("failed to refresh drift candidates", "error", err)
	}
}

func (r *Runner) refreshAllActiveUsers(ctx context.Context) error {
	status := store.DriftBottleStatusActive
	bottles, err := r.Store.ListDriftBottles(ctx, &store.FindDriftBottle{Status: &status})
	if err != nil {
		return err
	}
	userSet := map[int32]bool{}
	for _, bottle := range bottles {
		userSet[bottle.CreatorID] = true
	}
	for userID := range userSet {
		if _, err := r.refreshUserCandidates(ctx, userID); err != nil {
			slog.Warn("failed to refresh user's drift candidates", "userID", userID, "error", err)
		}
	}
	return nil
}

func (r *Runner) refreshUserCandidates(ctx context.Context, userID int32) (int, error) {
	if err := r.Store.DeleteDriftCandidatePool(ctx, &store.DeleteDriftCandidatePool{UserID: &userID}); err != nil {
		return 0, err
	}

	normal := store.Normal
	sourceLimit := 5
	sourceMemos, err := r.Store.ListMemos(ctx, &store.FindMemo{
		CreatorID:       &userID,
		RowStatus:       &normal,
		ExcludeComments: true,
		Limit:           &sourceLimit,
	})
	if err != nil || len(sourceMemos) == 0 {
		return 0, err
	}

	status := store.DriftBottleStatusActive
	allBottles, err := r.Store.ListDriftBottles(ctx, &store.FindDriftBottle{Status: &status})
	if err != nil || len(allBottles) == 0 {
		return 0, err
	}

	memoIDs := make([]int32, 0, len(allBottles))
	for _, b := range allBottles {
		memoIDs = append(memoIDs, b.MemoID)
	}
	candidateMemos, err := r.Store.ListMemos(ctx, &store.FindMemo{
		IDList:          memoIDs,
		RowStatus:       &normal,
		ExcludeComments: true,
	})
	if err != nil {
		return 0, err
	}
	candidateMemoMap := map[int32]*store.Memo{}
	for _, memo := range candidateMemos {
		candidateMemoMap[memo.ID] = memo
	}

	pickedLogs, err := r.Store.ListDriftPickLogs(ctx, &store.FindDriftPickLog{UserID: &userID})
	if err != nil {
		return 0, err
	}
	pickedMemoSet := map[int32]bool{}
	for _, log := range pickedLogs {
		pickedMemoSet[log.MemoID] = true
	}

	type candidateScore struct {
		memoID int32
		score  float64
	}
	total := 0
	for idx, source := range sourceMemos {
		topN := 5 - idx
		if topN <= 0 {
			break
		}
		scored := make([]candidateScore, 0, len(allBottles))
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
			score := computeScore(source.Content, candidateMemo.Content)
			if score <= 0 {
				continue
			}
			scored = append(scored, candidateScore{memoID: candidateMemo.ID, score: score})
		}
		sort.Slice(scored, func(i, j int) bool {
			if scored[i].score == scored[j].score {
				return scored[i].memoID > scored[j].memoID
			}
			return scored[i].score > scored[j].score
		})
		seen := map[int32]bool{}
		nowTs := time.Now().Unix()
		for _, item := range scored {
			if len(seen) >= topN {
				break
			}
			if seen[item.memoID] {
				continue
			}
			seen[item.memoID] = true
			if _, err := r.Store.UpsertDriftCandidatePool(ctx, &store.DriftCandidatePool{
				UserID:          userID,
				SourceMemoID:    source.ID,
				CandidateMemoID: item.memoID,
				Score:           item.score,
				Tier:            int32(topN),
				RefreshedTs:     nowTs,
				ExpiresTs:       nowTs + candidateExpirationSecond,
			}); err != nil {
				return total, err
			}
			total++
		}
	}
	return total, nil
}

func computeScore(sourceContent, candidateContent string) float64 {
	sourceTokens := tokenize(sourceContent)
	candidateTokens := tokenize(candidateContent)
	if len(sourceTokens) == 0 || len(candidateTokens) == 0 {
		return 0
	}
	inter := 0
	union := map[string]bool{}
	for t := range sourceTokens {
		union[t] = true
		if candidateTokens[t] {
			inter++
		}
	}
	for t := range candidateTokens {
		union[t] = true
	}
	if len(union) == 0 {
		return 0
	}
	return float64(inter)/float64(len(union))*100 + float64(inter)
}

func tokenize(content string) map[string]bool {
	result := map[string]bool{}
	for _, token := range tokenMatcher.FindAllString(strings.ToLower(content), -1) {
		if len(token) <= 1 {
			continue
		}
		result[token] = true
	}
	return result
}
