package test

import (
	"context"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
	colorpb "google.golang.org/genproto/googleapis/type/color"

	storepb "github.com/usememos/memos/proto/gen/store"
	"github.com/usememos/memos/store"
)

func TestUserSettingStore(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	ts := NewTestingStore(ctx, t)
	user, err := createTestingHostUser(ctx, ts)
	require.NoError(t, err)
	_, err = ts.UpsertUserSetting(ctx, &storepb.UserSetting{
		UserId: user.ID,
		Key:    storepb.UserSetting_GENERAL,
		Value:  &storepb.UserSetting_General{General: &storepb.GeneralUserSetting{Locale: "en"}},
	})
	require.NoError(t, err)
	list, err := ts.ListUserSettings(ctx, &store.FindUserSetting{})
	require.NoError(t, err)
	require.Equal(t, 1, len(list))
	ts.Close()
}

func TestUserSettingGetByUserID(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	ts := NewTestingStore(ctx, t)
	user, err := createTestingHostUser(ctx, ts)
	require.NoError(t, err)

	// Create setting
	_, err = ts.UpsertUserSetting(ctx, &storepb.UserSetting{
		UserId: user.ID,
		Key:    storepb.UserSetting_GENERAL,
		Value:  &storepb.UserSetting_General{General: &storepb.GeneralUserSetting{Locale: "zh"}},
	})
	require.NoError(t, err)

	// Get by user ID
	setting, err := ts.GetUserSetting(ctx, &store.FindUserSetting{
		UserID: &user.ID,
		Key:    storepb.UserSetting_GENERAL,
	})
	require.NoError(t, err)
	require.NotNil(t, setting)
	require.Equal(t, "zh", setting.GetGeneral().Locale)

	// Get non-existent key
	nonExistentSetting, err := ts.GetUserSetting(ctx, &store.FindUserSetting{
		UserID: &user.ID,
		Key:    storepb.UserSetting_SHORTCUTS,
	})
	require.NoError(t, err)
	require.Nil(t, nonExistentSetting)

	ts.Close()
}

func TestUserSettingUpsertUpdate(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	ts := NewTestingStore(ctx, t)
	user, err := createTestingHostUser(ctx, ts)
	require.NoError(t, err)

	// Create initial setting
	_, err = ts.UpsertUserSetting(ctx, &storepb.UserSetting{
		UserId: user.ID,
		Key:    storepb.UserSetting_GENERAL,
		Value:  &storepb.UserSetting_General{General: &storepb.GeneralUserSetting{Locale: "en"}},
	})
	require.NoError(t, err)

	// Update setting
	_, err = ts.UpsertUserSetting(ctx, &storepb.UserSetting{
		UserId: user.ID,
		Key:    storepb.UserSetting_GENERAL,
		Value:  &storepb.UserSetting_General{General: &storepb.GeneralUserSetting{Locale: "fr"}},
	})
	require.NoError(t, err)

	// Verify update
	setting, err := ts.GetUserSetting(ctx, &store.FindUserSetting{
		UserID: &user.ID,
		Key:    storepb.UserSetting_GENERAL,
	})
	require.NoError(t, err)
	require.Equal(t, "fr", setting.GetGeneral().Locale)

	// Verify only one setting exists
	list, err := ts.ListUserSettings(ctx, &store.FindUserSetting{UserID: &user.ID})
	require.NoError(t, err)
	require.Equal(t, 1, len(list))

	ts.Close()
}

func TestUserSettingTags(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	ts := NewTestingStore(ctx, t)
	user, err := createTestingHostUser(ctx, ts)
	require.NoError(t, err)

	_, err = ts.UpsertUserSetting(ctx, &storepb.UserSetting{
		UserId: user.ID,
		Key:    storepb.UserSetting_TAGS,
		Value: &storepb.UserSetting_Tags{
			Tags: &storepb.TagsUserSetting{
				Tags: map[string]*storepb.TagMetadata{
					"bug": {
						BackgroundColor: &colorpb.Color{
							Red:   0.1,
							Green: 0.2,
							Blue:  0.3,
						},
					},
				},
			},
		},
	})
	require.NoError(t, err)

	setting, err := ts.GetUserSetting(ctx, &store.FindUserSetting{
		UserID: &user.ID,
		Key:    storepb.UserSetting_TAGS,
	})
	require.NoError(t, err)
	require.NotNil(t, setting)
	require.Contains(t, setting.GetTags().Tags, "bug")
	require.InDelta(t, 0.1, setting.GetTags().Tags["bug"].GetBackgroundColor().GetRed(), 0.0001)

	list, err := ts.ListUserSettings(ctx, &store.FindUserSetting{UserID: &user.ID})
	require.NoError(t, err)
	require.Len(t, list, 1)

	ts.Close()
}

func TestUserSettingRefreshTokens(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	ts := NewTestingStore(ctx, t)
	user, err := createTestingHostUser(ctx, ts)
	require.NoError(t, err)

	// Initially no tokens
	tokens, err := ts.GetUserRefreshTokens(ctx, user.ID)
	require.NoError(t, err)
	require.Empty(t, tokens)

	// Add a refresh token
	token1 := &storepb.RefreshTokensUserSetting_RefreshToken{
		TokenId:     "token-1",
		Description: "Chrome browser session",
	}
	err = ts.AddUserRefreshToken(ctx, user.ID, token1)
	require.NoError(t, err)

	// Verify token was added
	tokens, err = ts.GetUserRefreshTokens(ctx, user.ID)
	require.NoError(t, err)
	require.Len(t, tokens, 1)
	require.Equal(t, "token-1", tokens[0].TokenId)

	// Add another token
	token2 := &storepb.RefreshTokensUserSetting_RefreshToken{
		TokenId:     "token-2",
		Description: "Firefox browser session",
	}
	err = ts.AddUserRefreshToken(ctx, user.ID, token2)
	require.NoError(t, err)

	tokens, err = ts.GetUserRefreshTokens(ctx, user.ID)
	require.NoError(t, err)
	require.Len(t, tokens, 2)

	// Get specific token by ID
	foundToken, err := ts.GetUserRefreshTokenByID(ctx, user.ID, "token-1")
	require.NoError(t, err)
	require.NotNil(t, foundToken)
	require.Equal(t, "Chrome browser session", foundToken.Description)

	// Get non-existent token
	notFound, err := ts.GetUserRefreshTokenByID(ctx, user.ID, "non-existent")
	require.NoError(t, err)
	require.Nil(t, notFound)

	// Remove token
	err = ts.RemoveUserRefreshToken(ctx, user.ID, "token-1")
	require.NoError(t, err)

	tokens, err = ts.GetUserRefreshTokens(ctx, user.ID)
	require.NoError(t, err)
	require.Len(t, tokens, 1)
	require.Equal(t, "token-2", tokens[0].TokenId)

	ts.Close()
}

func TestUserSettingWebhooks(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	ts := NewTestingStore(ctx, t)
	user, err := createTestingHostUser(ctx, ts)
	require.NoError(t, err)

	// Initially no webhooks
	webhooks, err := ts.GetUserWebhooks(ctx, user.ID)
	require.NoError(t, err)
	require.Empty(t, webhooks)

	// Add a webhook
	webhook1 := &storepb.WebhooksUserSetting_Webhook{
		Id:    "webhook-1",
		Title: "Deploy Hook",
		Url:   "https://example.com/webhook",
	}
	err = ts.AddUserWebhook(ctx, user.ID, webhook1)
	require.NoError(t, err)

	// Verify webhook was added
	webhooks, err = ts.GetUserWebhooks(ctx, user.ID)
	require.NoError(t, err)
	require.Len(t, webhooks, 1)
	require.Equal(t, "Deploy Hook", webhooks[0].Title)

	// Update webhook
	webhook1Updated := &storepb.WebhooksUserSetting_Webhook{
		Id:    "webhook-1",
		Title: "Updated Deploy Hook",
		Url:   "https://example.com/webhook/v2",
	}
	err = ts.UpdateUserWebhook(ctx, user.ID, webhook1Updated)
	require.NoError(t, err)

	webhooks, err = ts.GetUserWebhooks(ctx, user.ID)
	require.NoError(t, err)
	require.Len(t, webhooks, 1)
	require.Equal(t, "Updated Deploy Hook", webhooks[0].Title)
	require.Equal(t, "https://example.com/webhook/v2", webhooks[0].Url)

	// Add another webhook
	webhook2 := &storepb.WebhooksUserSetting_Webhook{
		Id:    "webhook-2",
		Title: "Notification Hook",
		Url:   "https://slack.example.com/webhook",
	}
	err = ts.AddUserWebhook(ctx, user.ID, webhook2)
	require.NoError(t, err)

	webhooks, err = ts.GetUserWebhooks(ctx, user.ID)
	require.NoError(t, err)
	require.Len(t, webhooks, 2)

	// Remove webhook
	err = ts.RemoveUserWebhook(ctx, user.ID, "webhook-1")
	require.NoError(t, err)

	webhooks, err = ts.GetUserWebhooks(ctx, user.ID)
	require.NoError(t, err)
	require.Len(t, webhooks, 1)
	require.Equal(t, "webhook-2", webhooks[0].Id)

	ts.Close()
}

func TestUserSettingShortcuts(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	ts := NewTestingStore(ctx, t)
	user, err := createTestingHostUser(ctx, ts)
	require.NoError(t, err)

	// Create shortcuts setting
	shortcuts := &storepb.ShortcutsUserSetting{
		Shortcuts: []*storepb.ShortcutsUserSetting_Shortcut{
			{Id: "shortcut-1", Title: "Work Notes", Filter: "tag:work"},
			{Id: "shortcut-2", Title: "Personal", Filter: "tag:personal"},
		},
	}
	_, err = ts.UpsertUserSetting(ctx, &storepb.UserSetting{
		UserId: user.ID,
		Key:    storepb.UserSetting_SHORTCUTS,
		Value:  &storepb.UserSetting_Shortcuts{Shortcuts: shortcuts},
	})
	require.NoError(t, err)

	// Retrieve and verify
	setting, err := ts.GetUserSetting(ctx, &store.FindUserSetting{
		UserID: &user.ID,
		Key:    storepb.UserSetting_SHORTCUTS,
	})
	require.NoError(t, err)
	require.NotNil(t, setting)
	require.Len(t, setting.GetShortcuts().Shortcuts, 2)
	require.Equal(t, "Work Notes", setting.GetShortcuts().Shortcuts[0].Title)

	ts.Close()
}

func TestUserSettingMultipleSettingTypes(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	ts := NewTestingStore(ctx, t)
	user, err := createTestingHostUser(ctx, ts)
	require.NoError(t, err)

	// Create GENERAL setting
	_, err = ts.UpsertUserSetting(ctx, &storepb.UserSetting{
		UserId: user.ID,
		Key:    storepb.UserSetting_GENERAL,
		Value:  &storepb.UserSetting_General{General: &storepb.GeneralUserSetting{Locale: "ja"}},
	})
	require.NoError(t, err)

	// Create SHORTCUTS setting
	_, err = ts.UpsertUserSetting(ctx, &storepb.UserSetting{
		UserId: user.ID,
		Key:    storepb.UserSetting_SHORTCUTS,
		Value: &storepb.UserSetting_Shortcuts{Shortcuts: &storepb.ShortcutsUserSetting{
			Shortcuts: []*storepb.ShortcutsUserSetting_Shortcut{
				{Id: "s1", Title: "Shortcut 1"},
			},
		}},
	})
	require.NoError(t, err)

	// List all settings for user
	settings, err := ts.ListUserSettings(ctx, &store.FindUserSetting{UserID: &user.ID})
	require.NoError(t, err)
	require.Len(t, settings, 2)

	// Verify each setting type
	generalSetting, err := ts.GetUserSetting(ctx, &store.FindUserSetting{UserID: &user.ID, Key: storepb.UserSetting_GENERAL})
	require.NoError(t, err)
	require.Equal(t, "ja", generalSetting.GetGeneral().Locale)

	shortcutsSetting, err := ts.GetUserSetting(ctx, &store.FindUserSetting{UserID: &user.ID, Key: storepb.UserSetting_SHORTCUTS})
	require.NoError(t, err)
	require.Len(t, shortcutsSetting.GetShortcuts().Shortcuts, 1)

	ts.Close()
}

func TestUserSettingShortcutsEdgeCases(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	ts := NewTestingStore(ctx, t)
	user, err := createTestingHostUser(ctx, ts)
	require.NoError(t, err)

	// Case 1: Special characters in Filter and Title
	// Includes quotes, backslashes, newlines, and other JSON-sensitive characters
	specialCharsFilter := `tag in ["work", "project"] && content.contains("urgent")`
	specialCharsTitle := `Work "Urgent" \ Notes`
	shortcuts := &storepb.ShortcutsUserSetting{
		Shortcuts: []*storepb.ShortcutsUserSetting_Shortcut{
			{Id: "s1", Title: specialCharsTitle, Filter: specialCharsFilter},
		},
	}
	_, err = ts.UpsertUserSetting(ctx, &storepb.UserSetting{
		UserId: user.ID,
		Key:    storepb.UserSetting_SHORTCUTS,
		Value:  &storepb.UserSetting_Shortcuts{Shortcuts: shortcuts},
	})
	require.NoError(t, err)

	setting, err := ts.GetUserSetting(ctx, &store.FindUserSetting{
		UserID: &user.ID,
		Key:    storepb.UserSetting_SHORTCUTS,
	})
	require.NoError(t, err)
	require.NotNil(t, setting)
	require.Len(t, setting.GetShortcuts().Shortcuts, 1)
	require.Equal(t, specialCharsTitle, setting.GetShortcuts().Shortcuts[0].Title)
	require.Equal(t, specialCharsFilter, setting.GetShortcuts().Shortcuts[0].Filter)

	// Case 2: Unicode characters
	unicodeFilter := `tag in ["你好", "世界"]`
	unicodeTitle := `My 🚀 Shortcuts`
	shortcuts = &storepb.ShortcutsUserSetting{
		Shortcuts: []*storepb.ShortcutsUserSetting_Shortcut{
			{Id: "s2", Title: unicodeTitle, Filter: unicodeFilter},
		},
	}
	_, err = ts.UpsertUserSetting(ctx, &storepb.UserSetting{
		UserId: user.ID,
		Key:    storepb.UserSetting_SHORTCUTS,
		Value:  &storepb.UserSetting_Shortcuts{Shortcuts: shortcuts},
	})
	require.NoError(t, err)

	setting, err = ts.GetUserSetting(ctx, &store.FindUserSetting{
		UserID: &user.ID,
		Key:    storepb.UserSetting_SHORTCUTS,
	})
	require.NoError(t, err)
	require.NotNil(t, setting)
	require.Len(t, setting.GetShortcuts().Shortcuts, 1)
	require.Equal(t, unicodeTitle, setting.GetShortcuts().Shortcuts[0].Title)
	require.Equal(t, unicodeFilter, setting.GetShortcuts().Shortcuts[0].Filter)

	// Case 3: Empty shortcuts list
	// Should allow saving an empty list (clearing shortcuts)
	shortcuts = &storepb.ShortcutsUserSetting{
		Shortcuts: []*storepb.ShortcutsUserSetting_Shortcut{},
	}
	_, err = ts.UpsertUserSetting(ctx, &storepb.UserSetting{
		UserId: user.ID,
		Key:    storepb.UserSetting_SHORTCUTS,
		Value:  &storepb.UserSetting_Shortcuts{Shortcuts: shortcuts},
	})
	require.NoError(t, err)

	setting, err = ts.GetUserSetting(ctx, &store.FindUserSetting{
		UserID: &user.ID,
		Key:    storepb.UserSetting_SHORTCUTS,
	})
	require.NoError(t, err)
	require.NotNil(t, setting)
	require.NotNil(t, setting.GetShortcuts())
	require.Len(t, setting.GetShortcuts().Shortcuts, 0)

	// Case 4: Large filter string
	// Test reasonable large string handling (e.g. 4KB)
	largeFilter := strings.Repeat("tag:long_tag_name ", 200)
	shortcuts = &storepb.ShortcutsUserSetting{
		Shortcuts: []*storepb.ShortcutsUserSetting_Shortcut{
			{Id: "s3", Title: "Large Filter", Filter: largeFilter},
		},
	}
	_, err = ts.UpsertUserSetting(ctx, &storepb.UserSetting{
		UserId: user.ID,
		Key:    storepb.UserSetting_SHORTCUTS,
		Value:  &storepb.UserSetting_Shortcuts{Shortcuts: shortcuts},
	})
	require.NoError(t, err)

	setting, err = ts.GetUserSetting(ctx, &store.FindUserSetting{
		UserID: &user.ID,
		Key:    storepb.UserSetting_SHORTCUTS,
	})
	require.NoError(t, err)
	require.NotNil(t, setting)
	require.Equal(t, largeFilter, setting.GetShortcuts().Shortcuts[0].Filter)

	ts.Close()
}

func TestUserSettingShortcutsPartialUpdate(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	ts := NewTestingStore(ctx, t)
	user, err := createTestingHostUser(ctx, ts)
	require.NoError(t, err)

	// Initial set
	shortcuts := &storepb.ShortcutsUserSetting{
		Shortcuts: []*storepb.ShortcutsUserSetting_Shortcut{
			{Id: "s1", Title: "Note 1", Filter: "tag:1"},
			{Id: "s2", Title: "Note 2", Filter: "tag:2"},
		},
	}
	_, err = ts.UpsertUserSetting(ctx, &storepb.UserSetting{
		UserId: user.ID,
		Key:    storepb.UserSetting_SHORTCUTS,
		Value:  &storepb.UserSetting_Shortcuts{Shortcuts: shortcuts},
	})
	require.NoError(t, err)

	// Update by replacing the whole list (Store Upsert replaces the value for the key)
	// We want to verify that we can "update" a single item by sending the modified list
	updatedShortcuts := &storepb.ShortcutsUserSetting{
		Shortcuts: []*storepb.ShortcutsUserSetting_Shortcut{
			{Id: "s1", Title: "Note 1 Updated", Filter: "tag:1_updated"},
			{Id: "s2", Title: "Note 2", Filter: "tag:2"},
			{Id: "s3", Title: "Note 3", Filter: "tag:3"}, // Add new one
		},
	}
	_, err = ts.UpsertUserSetting(ctx, &storepb.UserSetting{
		UserId: user.ID,
		Key:    storepb.UserSetting_SHORTCUTS,
		Value:  &storepb.UserSetting_Shortcuts{Shortcuts: updatedShortcuts},
	})
	require.NoError(t, err)

	setting, err := ts.GetUserSetting(ctx, &store.FindUserSetting{
		UserID: &user.ID,
		Key:    storepb.UserSetting_SHORTCUTS,
	})
	require.NoError(t, err)
	require.NotNil(t, setting)
	require.Len(t, setting.GetShortcuts().Shortcuts, 3)

	// Verify updates
	for _, s := range setting.GetShortcuts().Shortcuts {
		if s.Id == "s1" {
			require.Equal(t, "Note 1 Updated", s.Title)
			require.Equal(t, "tag:1_updated", s.Filter)
		} else if s.Id == "s2" {
			require.Equal(t, "Note 2", s.Title)
		} else if s.Id == "s3" {
			require.Equal(t, "Note 3", s.Title)
		}
	}

	ts.Close()
}

func TestUserSettingJSONFieldsEdgeCases(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	ts := NewTestingStore(ctx, t)
	user, err := createTestingHostUser(ctx, ts)
	require.NoError(t, err)

	// Case 1: Webhook with special characters and Unicode in Title and URL
	specialWebhook := &storepb.WebhooksUserSetting_Webhook{
		Id:    "wh-special",
		Title: `My "Special" & <Webhook> 🚀`,
		Url:   "https://example.com/hook?query=你好&param=\"value\"",
	}
	err = ts.AddUserWebhook(ctx, user.ID, specialWebhook)
	require.NoError(t, err)

	webhooks, err := ts.GetUserWebhooks(ctx, user.ID)
	require.NoError(t, err)
	require.Len(t, webhooks, 1)
	require.Equal(t, specialWebhook.Title, webhooks[0].Title)
	require.Equal(t, specialWebhook.Url, webhooks[0].Url)

	// Case 2: Refresh Token with special description
	specialRefreshToken := &storepb.RefreshTokensUserSetting_RefreshToken{
		TokenId:     "rt-special",
		Description: "Browser: Firefox (Nightly) / OS: Linux 🐧",
	}
	err = ts.AddUserRefreshToken(ctx, user.ID, specialRefreshToken)
	require.NoError(t, err)

	tokens, err := ts.GetUserRefreshTokens(ctx, user.ID)
	require.NoError(t, err)
	require.Len(t, tokens, 1)
	require.Equal(t, specialRefreshToken.Description, tokens[0].Description)

	ts.Close()
}
