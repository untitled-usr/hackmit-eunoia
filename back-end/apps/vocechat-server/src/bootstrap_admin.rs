//! Ensures a single system administrator at uid=1 when the database has no admin yet.

use std::sync::Arc;

use crate::{
    api::{DateTime, LangId, UpdateAction, UserUpdateLog},
    state::{BroadcastEvent, CacheUser, UserStatus},
    State,
};

pub const SYSTEM_ADMIN_UID: i64 = 1;
pub const SYSTEM_ADMIN_NAME: &str = "admin";

/// When `skip` is true (tests only), does nothing.
///
/// If any user already has `is_admin`, returns Ok without changing the database.
/// If there is no admin and uid=1 is taken by a non-admin user, returns an error.
/// Otherwise inserts uid=1, `name='admin'`, `is_admin=true`.
pub async fn ensure_system_bootstrap_admin(state: &State, skip: bool) -> anyhow::Result<()> {
    if skip {
        return Ok(());
    }

    let mut cache = state.cache.write().await;

    if cache.users.values().any(|u| u.is_admin) {
        return Ok(());
    }

    if let Some(u) = cache.users.get(&SYSTEM_ADMIN_UID) {
        if !u.is_admin {
            anyhow::bail!(
                "user uid=1 exists but is not an administrator; fix or remove this row before starting the server"
            );
        }
    }

    if !cache.check_name_conflict(SYSTEM_ADMIN_NAME) {
        anyhow::bail!(
            "cannot create system admin: the name '{}' is already used by another uid",
            SYSTEM_ADMIN_NAME
        );
    }

    let now = DateTime::now();
    let language = LangId::default();
    let avatar_updated_at = DateTime::zero();
    let is_guest = false;
    let is_bot = false;
    let is_admin = true;
    let gender = 0i32;
    let create_by = "password";

    let mut tx = state
        .db_pool
        .begin()
        .await
        .map_err(|e| anyhow::anyhow!(e.to_string()))?;

    let sql = "insert into user (uid, name, password, gender, language, is_admin, create_by, avatar_updated_at, status, created_at, updated_at, is_guest, webhook_url, is_bot) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)";
    sqlx::query(sql)
        .bind(SYSTEM_ADMIN_UID)
        .bind(SYSTEM_ADMIN_NAME)
        .bind(Option::<&str>::None)
        .bind(gender)
        .bind(&language)
        .bind(is_admin)
        .bind(create_by)
        .bind(avatar_updated_at)
        .bind(i8::from(UserStatus::Normal))
        .bind(now)
        .bind(now)
        .bind(is_guest)
        .bind(Option::<&str>::None)
        .bind(is_bot)
        .execute(&mut tx)
        .await
        .map_err(|e| anyhow::anyhow!(e.to_string()))?;

    let log_id = {
        let sql = "insert into user_log (uid, action, name, gender, language, avatar_updated_at, is_admin, is_bot) values (?, ?, ?, ?, ?, ?, ?, ?)";
        sqlx::query(sql)
            .bind(SYSTEM_ADMIN_UID)
            .bind(UpdateAction::Create)
            .bind(SYSTEM_ADMIN_NAME)
            .bind(gender)
            .bind(&language)
            .bind(avatar_updated_at)
            .bind(is_admin)
            .bind(is_bot)
            .execute(&mut tx)
            .await
            .map_err(|e| anyhow::anyhow!(e.to_string()))?
            .last_insert_rowid()
    };

    tx.commit()
        .await
        .map_err(|e| anyhow::anyhow!(e.to_string()))?;

    cache.users.insert(
        SYSTEM_ADMIN_UID,
        CacheUser {
            name: SYSTEM_ADMIN_NAME.to_string(),
            password: None,
            gender,
            is_admin,
            language: language.clone(),
            create_by: create_by.to_string(),
            created_at: now,
            updated_at: now,
            avatar_updated_at,
            devices: Default::default(),
            mute_user: Default::default(),
            mute_group: Default::default(),
            burn_after_reading_user: Default::default(),
            burn_after_reading_group: Default::default(),
            read_index_user: Default::default(),
            read_index_group: Default::default(),
            status: UserStatus::Normal,
            is_guest,
            webhook_url: None,
            is_bot,
            bot_keys: Default::default(),
            active_friends: Default::default(),
            stale_friends_display: Default::default(),
            blocked_users: Default::default(),
            blocked_by_users: Default::default(),
            incoming_friend_requests: Default::default(),
            outgoing_friend_requests: Default::default(),
        },
    );

    let _ = state.event_sender.send(Arc::new(BroadcastEvent::UserLog(UserUpdateLog {
        log_id,
        action: UpdateAction::Create,
        uid: SYSTEM_ADMIN_UID,
        name: Some(SYSTEM_ADMIN_NAME.to_string()),
        gender: gender.into(),
        language: Some(language.clone()),
        is_admin: Some(is_admin),
        is_bot: Some(is_bot),
        avatar_updated_at: Some(avatar_updated_at),
    })));

    for (gid, group) in cache.groups.iter() {
        if group.ty.is_public() {
            let _ = state.event_sender.send(Arc::new(BroadcastEvent::UserJoinedGroup {
                targets: cache.users.keys().copied().collect(),
                gid: *gid,
                uid: vec![SYSTEM_ADMIN_UID],
            }));
        }
    }

    Ok(())
}
