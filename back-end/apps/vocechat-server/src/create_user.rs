use std::sync::Arc;

use poem::error::InternalServerError;
use reqwest::StatusCode;
use tokio::sync::{RwLockMappedWriteGuard, RwLockWriteGuard};

use crate::{
    api::{DateTime, LangId, UpdateAction, UserUpdateLog},
    bootstrap_admin::SYSTEM_ADMIN_UID,
    state::{BroadcastEvent, CacheUser, UserStatus},
    State,
};

#[derive(Debug)]
pub enum CreateUserBy<'a> {
    /// Local account (registration or admin-created). Password may be absent.
    Password {
        password: Option<&'a str>,
    },
}

impl<'a> CreateUserBy<'a> {
    fn type_name(&self) -> &'static str {
        match self {
            CreateUserBy::Password { .. } => "password",
        }
    }

    fn password(&self) -> Option<&'a str> {
        match self {
            CreateUserBy::Password { password, .. } => *password,
        }
    }
}

#[derive(Debug)]
pub struct CreateUser<'a> {
    name: &'a str,
    gender: i32,
    is_admin: bool,
    language: Option<&'a LangId>,
    create_by: CreateUserBy<'a>,
    webhook_url: Option<&'a str>,
    is_bot: bool,
}

impl<'a> CreateUser<'a> {
    pub fn new(name: &'a str, create_by: CreateUserBy<'a>, is_admin: bool) -> Self {
        Self {
            name,
            gender: 0,
            is_admin,
            language: None,
            create_by,
            webhook_url: None,
            is_bot: false,
        }
    }

    pub fn gender(self, gender: i32) -> Self {
        Self { gender, ..self }
    }

    pub fn set_admin(self, is_admin: bool) -> Self {
        Self { is_admin, ..self }
    }

    pub fn set_bot(self, is_bot: bool) -> Self {
        Self { is_bot, ..self }
    }

    pub fn language(self, language: &'a LangId) -> Self {
        Self {
            language: Some(language),
            ..self
        }
    }

    pub fn webhook_url(self, webhook_url: &'a str) -> Self {
        Self {
            webhook_url: Some(webhook_url),
            ..self
        }
    }
}

#[derive(Debug)]
pub enum CreateUserError {
    NameConflict,
    PoemError(poem::Error),
}

impl From<poem::Error> for CreateUserError {
    fn from(err: poem::Error) -> Self {
        CreateUserError::PoemError(err)
    }
}

impl State {
    pub async fn create_user(
        &self,
        create_user: CreateUser<'_>,
    ) -> Result<(i64, RwLockMappedWriteGuard<'_, CacheUser>), CreateUserError> {
        let password = create_user.create_by.password();
        let language = create_user.language.cloned().unwrap_or_default();
        let mut cache = self.cache.write().await;
        let is_guest = false;

        // check license
        if !self.config.system.disable_license {
            if cache
                .users
                .iter()
                .filter(|(_, user)| !user.is_guest)
                .count()
                >= crate::license::G_LICENSE.lock().await.user_limit as usize
            {
                return Err(CreateUserError::PoemError(poem::Error::from_string(
                    "License error: Users reached limit.",
                    StatusCode::UNAVAILABLE_FOR_LEGAL_REASONS,
                )));
            }
        }

        if !cache.check_name_conflict(create_user.name) {
            return Err(CreateUserError::NameConflict);
        }

        let now = DateTime::now();

        let mut tx = self.db_pool.begin().await.map_err(InternalServerError)?;

        let avatar_updated_at = DateTime::zero();
        let sql = "insert into user (name, password, gender, language, is_admin, create_by, avatar_updated_at, status, created_at, updated_at, is_guest, webhook_url, is_bot) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)";
        let uid = sqlx::query(sql)
            .bind(create_user.name)
            .bind(password)
            .bind(create_user.gender)
            .bind(&language)
            .bind(create_user.is_admin)
            .bind(create_user.create_by.type_name())
            .bind(avatar_updated_at)
            .bind(i8::from(UserStatus::Normal))
            .bind(now)
            .bind(now)
            .bind(is_guest)
            .bind(create_user.webhook_url)
            .bind(create_user.is_bot)
            .execute(&mut tx)
            .await
            .map_err(InternalServerError)?
            .last_insert_rowid();

        if uid == SYSTEM_ADMIN_UID
            && !create_user.is_admin
            && !self.config.system.test_skip_system_admin_bootstrap
        {
            let _ = tx.rollback().await;
            return Err(CreateUserError::PoemError(poem::Error::from_string(
                "uid 1 is reserved for the system administrator",
                StatusCode::INTERNAL_SERVER_ERROR,
            )));
        }

        let final_name = uid.to_string();
        sqlx::query("update user set name = ? where uid = ?")
            .bind(&final_name)
            .bind(uid)
            .execute(&mut tx)
            .await
            .map_err(InternalServerError)?;

        let stored_name = final_name.clone();

        let log_id = {
            let sql = "insert into user_log (uid, action, name, gender, language, avatar_updated_at, is_admin, is_bot) values (?, ?, ?, ?, ?, ?, ?, ?)";
            let log_id = sqlx::query(sql)
                .bind(uid)
                .bind(UpdateAction::Create)
                .bind(&final_name)
                .bind(create_user.gender)
                .bind(&language)
                .bind(avatar_updated_at)
                .bind(create_user.is_admin)
                .bind(create_user.is_bot)
                .execute(&mut tx)
                .await
                .map_err(InternalServerError)?
                .last_insert_rowid();
            Some(log_id)
        };

        tx.commit().await.map_err(InternalServerError)?;

        cache.users.insert(
            uid,
            CacheUser {
                name: stored_name,
                password: password.map(ToString::to_string),
                gender: create_user.gender,
                is_admin: create_user.is_admin,
                language: language.clone(),
                create_by: create_user.create_by.type_name().to_string(),
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
                webhook_url: create_user.webhook_url.map(ToString::to_string),
                is_bot: create_user.is_bot,
                bot_keys: Default::default(),
                active_friends: Default::default(),
                stale_friends_display: Default::default(),
                blocked_users: Default::default(),
                blocked_by_users: Default::default(),
                incoming_friend_requests: Default::default(),
                outgoing_friend_requests: Default::default(),
            },
        );

        if let Some(log_id) = log_id {
            let _ = self
                .event_sender
                .send(Arc::new(BroadcastEvent::UserLog(UserUpdateLog {
                    log_id,
                    action: UpdateAction::Create,
                    uid,
                    name: Some(final_name),
                    gender: create_user.gender.into(),
                    language: Some(language.clone()),
                    is_admin: Some(create_user.is_admin),
                    is_bot: Some(create_user.is_bot),
                    avatar_updated_at: Some(avatar_updated_at),
                })));

            for (gid, group) in cache.groups.iter() {
                if group.ty.is_public() {
                    let _ = self
                        .event_sender
                        .send(Arc::new(BroadcastEvent::UserJoinedGroup {
                            targets: cache.users.keys().copied().collect(),
                            gid: *gid,
                            uid: vec![uid],
                        }));
                }
            }
        }

        Ok((
            uid,
            RwLockWriteGuard::map(cache, |cache| cache.users.get_mut(&uid).unwrap()),
        ))
    }
}
