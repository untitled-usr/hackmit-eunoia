use std::sync::Arc;

use chrono::Duration;
use poem::{
    error::InternalServerError,
    http::StatusCode,
    web::Data,
    Error, Result,
};
use poem_openapi::{param::Path, payload::Json, Object, OpenApi};

use crate::{
    api::{
        admin_user::User,
        message::{ContactRelationSync, FriendRequestView, UserSettingsChangedMessage},
        tags::ApiTags,
        token::Token,
        UserInfo,
    },
    middleware::guest_forbidden,
    state::{BroadcastEvent, Cache, CachedFriendRequest, State},
};

fn sort_pair(a: i64, b: i64) -> (i64, i64) {
    if a < b {
        (a, b)
    } else {
        (b, a)
    }
}

fn push_settings(state: &State, uid: i64, from_device: &str, mut msg: UserSettingsChangedMessage) {
    msg.from_device = from_device.to_string();
    let _ = state.event_sender.send(Arc::new(BroadcastEvent::UserSettingsChanged {
        uid,
        message: msg,
    }));
}

fn contact_relation(cache: &Cache, viewer: i64, target: i64) -> ContactRelationSync {
    match cache.users.get(&viewer) {
        Some(u) => {
            let (status, removed_by_peer) = if u.has_blocked(target) {
                ("blocked".to_string(), false)
            } else if u.active_friends.contains(&target) {
                ("added".to_string(), false)
            } else if u.stale_friends_display.contains(&target) {
                ("added".to_string(), true)
            } else {
                ("".to_string(), false)
            };
            ContactRelationSync {
                target_uid: target,
                status,
                removed_by_peer,
            }
        }
        None => ContactRelationSync {
            target_uid: target,
            status: "".to_string(),
            removed_by_peer: false,
        },
    }
}

fn ts_ms(t: crate::api::DateTime) -> i64 {
    t.0.timestamp_millis()
}

const FRIEND_REQUEST_PENDING_EXPIRE_DAYS: i64 = 7;
const FRIEND_REQUEST_KEEP_DAYS: i64 = 3;

fn pending_expire_cutoff(now: crate::api::DateTime) -> crate::api::DateTime {
    crate::api::DateTime(now.0 - Duration::days(FRIEND_REQUEST_PENDING_EXPIRE_DAYS))
}

fn resolved_purge_cutoff(now: crate::api::DateTime) -> crate::api::DateTime {
    crate::api::DateTime(now.0 - Duration::days(FRIEND_REQUEST_KEEP_DAYS))
}

#[derive(Debug, Object, Clone)]
pub struct ContactInfoBody {
    pub status: String,
    pub created_at: i64,
    pub updated_at: i64,
    #[oai(default)]
    pub removed_by_peer: bool,
}

#[derive(Debug, Object)]
pub struct ContactResponse {
    pub target_uid: i64,
    pub target_info: User,
    pub contact_info: ContactInfoBody,
}

#[derive(Debug, Object)]
struct SearchUserRequest {
    search_type: String,
    keyword: String,
}

#[derive(Debug, Object)]
struct UpdateContactStatusRequest {
    target_uid: i64,
    action: String,
}

#[derive(Debug, Object)]
struct CreateFriendRequestBody {
    receiver_uid: i64,
    #[oai(default)]
    message: String,
}

#[derive(Debug, Object)]
struct FriendRequestRecordView {
    id: i64,
    requester_uid: i64,
    receiver_uid: i64,
    message: String,
    status: String,
    created_at: i64,
    #[oai(default)]
    responded_at: i64,
    #[oai(default)]
    can_delete: bool,
}


pub struct ApiSocial;

#[OpenApi(prefix_path = "/user", tag = "ApiTags::User")]
impl ApiSocial {
    /// Search user by id or name (first match).
    #[oai(path = "/search", method = "post", transform = "guest_forbidden")]
    async fn search_user(
        &self,
        state: Data<&State>,
        token: Token,
        req: Json<SearchUserRequest>,
    ) -> Result<Json<User>> {
        let cache = state.cache.read().await;
        let keyword = req.keyword.trim();
        if keyword.is_empty() {
            return Err(Error::from_status(StatusCode::BAD_REQUEST));
        }
        let uid = match req.search_type.as_str() {
            "id" => keyword.parse::<i64>().map_err(|_| Error::from_status(StatusCode::BAD_REQUEST))?,
            "email" => {
                return Err(Error::from_status(StatusCode::BAD_REQUEST));
            }
            "name" => {
                let kw = keyword.to_lowercase();
                cache
                    .users
                    .iter()
                    .find(|(_, u)| !u.is_guest && u.name.to_lowercase().contains(&kw))
                    .map(|(id, _)| *id)
                    .ok_or_else(|| Error::from_status(StatusCode::NOT_FOUND))?
            }
            _ => return Err(Error::from_status(StatusCode::BAD_REQUEST)),
        };
        if uid == token.uid {
            return Err(Error::from_status(StatusCode::NOT_FOUND));
        }
        let user = cache
            .users
            .get(&uid)
            .filter(|u| !u.is_guest)
            .ok_or_else(|| Error::from_status(StatusCode::NOT_FOUND))?;
        Ok(Json(user.api_user(uid)))
    }

    /// Contacts / friends list for the current user.
    #[oai(path = "/contacts", method = "get", transform = "guest_forbidden")]
    async fn get_contacts(&self, state: Data<&State>, token: Token) -> Result<Json<Vec<ContactResponse>>> {
        let cache = state.cache.read().await;
        let me = cache
            .users
            .get(&token.uid)
            .ok_or_else(|| Error::from_status(StatusCode::UNAUTHORIZED))?;
        let mut targets: std::collections::HashSet<i64> = std::collections::HashSet::new();
        for u in me.active_friends.iter() {
            targets.insert(*u);
        }
        for u in me.stale_friends_display.iter() {
            targets.insert(*u);
        }
        for u in me.blocked_users.iter() {
            targets.insert(*u);
        }
        let mut out = Vec::new();
        for tid in targets {
            if tid == token.uid {
                continue;
            }
            let Some(tu) = cache.users.get(&tid).filter(|u| !u.is_guest) else {
                continue;
            };
            let sync = contact_relation(&cache, token.uid, tid);
            let now_ms = ts_ms(crate::api::DateTime::now());
            out.push(ContactResponse {
                target_uid: tid,
                target_info: tu.api_user(tid),
                contact_info: ContactInfoBody {
                    status: sync.status.clone(),
                    created_at: now_ms,
                    updated_at: now_ms,
                    removed_by_peer: sync.removed_by_peer,
                },
            });
        }
        out.sort_by_key(|c| c.target_uid);
        Ok(Json(out))
    }

    /// Legacy contact actions: `add` (friend request), `remove`, `block`, `unblock`.
    #[oai(
        path = "/update_contact_status",
        method = "post",
        transform = "guest_forbidden"
    )]
    async fn update_contact_status(
        &self,
        state: Data<&State>,
        token: Token,
        req: Json<UpdateContactStatusRequest>,
    ) -> Result<()> {
        let target = req.target_uid;
        if target == token.uid {
            return Err(Error::from_status(StatusCode::BAD_REQUEST));
        }
        match req.action.as_str() {
            "add" => {
                self.create_friend_request_inner(&state, &token, target, String::new())
                    .await?;
            }
            "remove" => {
                remove_friendship(&state, token.uid, target, &token.device).await?;
            }
            "block" => {
                block_user(&state, token.uid, target, None, &token.device).await?;
            }
            "unblock" => {
                unblock_user(&state, token.uid, target, &token.device).await?;
            }
            _ => return Err(Error::from_status(StatusCode::BAD_REQUEST)),
        }
        Ok(())
    }

    /// Create a friend request with optional message.
    #[oai(path = "/friend_requests", method = "post", transform = "guest_forbidden")]
    async fn create_friend_request(
        &self,
        state: Data<&State>,
        token: Token,
        req: Json<CreateFriendRequestBody>,
    ) -> Result<Json<i64>> {
        let id = self
            .create_friend_request_inner(&state, &token, req.receiver_uid, req.message.clone())
            .await?;
        Ok(Json(id))
    }

    async fn create_friend_request_inner(
        &self,
        state: &State,
        token: &Token,
        receiver_uid: i64,
        message: String,
    ) -> Result<i64> {
        refresh_friend_request_lifecycle(state).await?;
        if receiver_uid == token.uid {
            return Err(Error::from_status(StatusCode::BAD_REQUEST));
        }
        let now = crate::api::DateTime::now();
        let expire_cutoff = pending_expire_cutoff(now);
        let cache = state.cache.write().await;
        let requester = cache
            .users
            .get(&token.uid)
            .ok_or_else(|| Error::from_status(StatusCode::UNAUTHORIZED))?;
        let receiver = cache
            .users
            .get(&receiver_uid)
            .filter(|u| !u.is_guest)
            .ok_or_else(|| Error::from_status(StatusCode::NOT_FOUND))?;
        if receiver.has_blocked(token.uid) {
            return Err(Error::from_status(StatusCode::FORBIDDEN));
        }
        if requester.active_friends.contains(&receiver_uid) {
            return Err(Error::from_status(StatusCode::CONFLICT));
        }
        let auto_accept_id = requester
            .incoming_friend_requests
            .iter()
            .find(|r| r.requester_uid == receiver_uid && r.created_at > expire_cutoff)
            .map(|r| r.id);
        if let Some(req_id) = auto_accept_id {
            drop(cache);
            return accept_friend_request_by_id(state, token.uid, req_id, &token.device).await;
        }
        if requester
            .outgoing_friend_requests
            .iter()
            .any(|r| r.receiver_uid == receiver_uid && r.created_at > expire_cutoff)
        {
            return Err(Error::from_status(StatusCode::CONFLICT));
        }

        drop(cache);
        let mut tx = state.db_pool.begin().await.map_err(InternalServerError)?;
        let id = sqlx::query(
            r#"insert into friend_request (requester_uid, receiver_uid, message, status, created_at, updated_at)
               values (?, ?, ?, 'pending', ?, ?)"#,
        )
        .bind(token.uid)
        .bind(receiver_uid)
        .bind(message.as_str())
        .bind(now)
        .bind(now)
        .execute(&mut *tx)
        .await
        .map_err(|e| {
            if let sqlx::Error::Database(dbe) = &e {
                if dbe.message().contains("UNIQUE") {
                    return Error::from_status(StatusCode::CONFLICT);
                }
            }
            InternalServerError(e)
        })?
        .last_insert_rowid();

        tx.commit().await.map_err(InternalServerError)?;

        let row = CachedFriendRequest {
            id,
            requester_uid: token.uid,
            receiver_uid,
            message: message.clone(),
            created_at: now,
        };
        {
            let mut c2 = state.cache.write().await;
            if let Some(u) = c2.users.get_mut(&token.uid) {
                u.outgoing_friend_requests.push(row.clone());
            }
            if let Some(u) = c2.users.get_mut(&receiver_uid) {
                u.incoming_friend_requests.push(row);
            }
        }

        let fr = FriendRequestView {
            id,
            requester_uid: token.uid,
            receiver_uid,
            message: message.clone(),
            status: "pending".to_string(),
            created_at: now,
        };
        push_settings(
            state,
            receiver_uid,
            &token.device,
            UserSettingsChangedMessage {
                friend_requests: vec![fr],
                ..Default::default()
            },
        );
        let c = state.cache.read().await;
        push_settings(
            state,
            token.uid,
            &token.device,
            UserSettingsChangedMessage {
                contact_updates: vec![contact_relation(&c, token.uid, receiver_uid)],
                ..Default::default()
            },
        );

        Ok(id)
    }

    #[oai(
        path = "/friend_requests/incoming",
        method = "get",
        transform = "guest_forbidden"
    )]
    async fn list_incoming(&self, state: Data<&State>, token: Token) -> Result<Json<Vec<FriendRequestView>>> {
        refresh_friend_request_lifecycle(&state).await?;
        let rows = sqlx::query_as::<_, (i64, i64, i64, String, crate::api::DateTime)>(
            r#"select id, requester_uid, receiver_uid, message, created_at
               from friend_request
               where receiver_uid = ? and status = 'pending'
               order by created_at desc"#,
        )
        .bind(token.uid)
        .fetch_all(&state.db_pool)
        .await
        .map_err(InternalServerError)?;
        let v = rows
            .into_iter()
            .map(|(id, requester_uid, receiver_uid, message, created_at)| FriendRequestView {
                id,
                requester_uid,
                receiver_uid,
                message,
                status: "pending".to_string(),
                created_at,
            })
            .collect();
        Ok(Json(v))
    }

    #[oai(
        path = "/friend_requests/outgoing",
        method = "get",
        transform = "guest_forbidden"
    )]
    async fn list_outgoing(&self, state: Data<&State>, token: Token) -> Result<Json<Vec<FriendRequestView>>> {
        refresh_friend_request_lifecycle(&state).await?;
        let rows = sqlx::query_as::<_, (i64, i64, i64, String, crate::api::DateTime)>(
            r#"select id, requester_uid, receiver_uid, message, created_at
               from friend_request
               where requester_uid = ? and status = 'pending'
               order by created_at desc"#,
        )
        .bind(token.uid)
        .fetch_all(&state.db_pool)
        .await
        .map_err(InternalServerError)?;
        let v = rows
            .into_iter()
            .map(|(id, requester_uid, receiver_uid, message, created_at)| FriendRequestView {
                id,
                requester_uid,
                receiver_uid,
                message,
                status: "pending".to_string(),
                created_at,
            })
            .collect();
        Ok(Json(v))
    }

    #[oai(
        path = "/friend_requests/records",
        method = "get",
        transform = "guest_forbidden"
    )]
    async fn list_records(
        &self,
        state: Data<&State>,
        token: Token,
    ) -> Result<Json<Vec<FriendRequestRecordView>>> {
        refresh_friend_request_lifecycle(&state).await?;
        let rows = sqlx::query_as::<
            _,
            (
                i64,
                i64,
                i64,
                String,
                String,
                crate::api::DateTime,
                Option<crate::api::DateTime>,
            ),
        >(
            r#"select id, requester_uid, receiver_uid, message, status, created_at, responded_at
               from friend_request
               where requester_uid = ? or receiver_uid = ?
               order by coalesce(responded_at, updated_at, created_at) desc, id desc"#,
        )
        .bind(token.uid)
        .bind(token.uid)
        .fetch_all(&state.db_pool)
        .await
        .map_err(InternalServerError)?;

        let out = rows
            .into_iter()
            .map(
                |(id, requester_uid, receiver_uid, message, status, created_at, responded_at)| {
                    FriendRequestRecordView {
                        id,
                        requester_uid,
                        receiver_uid,
                        message,
                        status: status.clone(),
                        created_at: ts_ms(created_at),
                        responded_at: responded_at.map(ts_ms).unwrap_or_default(),
                        can_delete: status != "pending",
                    }
                },
            )
            .collect();
        Ok(Json(out))
    }

    #[oai(
        path = "/friend_requests/:id/accept",
        method = "post",
        transform = "guest_forbidden"
    )]
    async fn accept_request(
        &self,
        state: Data<&State>,
        token: Token,
        id: Path<i64>,
    ) -> Result<()> {
        refresh_friend_request_lifecycle(&state).await?;
        accept_friend_request_by_id(&state, token.uid, id.0, &token.device)
            .await
            .map(|_| ())
    }

    #[oai(
        path = "/friend_requests/:id/reject",
        method = "post",
        transform = "guest_forbidden"
    )]
    async fn reject_request(
        &self,
        state: Data<&State>,
        token: Token,
        id: Path<i64>,
    ) -> Result<()> {
        refresh_friend_request_lifecycle(&state).await?;
        finalize_request(
            &state,
            id.0,
            token.uid,
            "rejected",
            true,
            &token.device,
        )
        .await
    }

    #[oai(
        path = "/friend_requests/:id/cancel",
        method = "post",
        transform = "guest_forbidden"
    )]
    async fn cancel_request(
        &self,
        state: Data<&State>,
        token: Token,
        id: Path<i64>,
    ) -> Result<()> {
        refresh_friend_request_lifecycle(&state).await?;
        finalize_request(
            &state,
            id.0,
            token.uid,
            "canceled",
            false,
            &token.device,
        )
        .await
    }

    #[oai(path = "/friend_requests/:id", method = "delete", transform = "guest_forbidden")]
    async fn delete_request(
        &self,
        state: Data<&State>,
        token: Token,
        id: Path<i64>,
    ) -> Result<()> {
        refresh_friend_request_lifecycle(&state).await?;
        delete_friend_request_record(&state, id.0, token.uid).await
    }

    #[oai(path = "/friends/:uid", method = "delete", transform = "guest_forbidden")]
    async fn delete_friend(
        &self,
        state: Data<&State>,
        token: Token,
        uid: Path<i64>,
    ) -> Result<()> {
        remove_friendship(&state, token.uid, uid.0, &token.device).await
    }

    #[oai(path = "/blacklist", method = "get", transform = "guest_forbidden")]
    async fn get_blacklist(&self, state: Data<&State>, token: Token) -> Result<Json<Vec<UserInfo>>> {
        let cache = state.cache.read().await;
        let me = cache
            .users
            .get(&token.uid)
            .ok_or_else(|| Error::from_status(StatusCode::UNAUTHORIZED))?;
        let mut list: Vec<UserInfo> = me
            .blocked_users
            .iter()
            .filter_map(|uid| cache.users.get(uid).map(|u| u.api_user_info(*uid)))
            .collect();
        list.sort_by_key(|u| u.uid);
        Ok(Json(list))
    }

    #[oai(path = "/blacklist/:uid", method = "post", transform = "guest_forbidden")]
    async fn add_blacklist(
        &self,
        state: Data<&State>,
        token: Token,
        uid: Path<i64>,
    ) -> Result<()> {
        block_user(&state, token.uid, uid.0, None, &token.device).await
    }

    #[oai(path = "/blacklist/:uid", method = "delete", transform = "guest_forbidden")]
    async fn remove_blacklist(
        &self,
        state: Data<&State>,
        token: Token,
        uid: Path<i64>,
    ) -> Result<()> {
        unblock_user(&state, token.uid, uid.0, &token.device).await
    }

    /// No-op compatibility for pinned chats (not persisted in this build).
    #[oai(path = "/pin_chat", method = "post", transform = "guest_forbidden")]
    async fn pin_chat(&self, _state: Data<&State>, _token: Token, _req: Json<serde_json::Value>) -> Result<()> {
        Ok(())
    }

    #[oai(path = "/unpin_chat", method = "post", transform = "guest_forbidden")]
    async fn unpin_chat(&self, _state: Data<&State>, _token: Token, _req: Json<serde_json::Value>) -> Result<()> {
        Ok(())
    }

    /// No-op compatibility for contact remark.
    #[oai(path = "/contact_remark", method = "put", transform = "guest_forbidden")]
    async fn contact_remark(
        &self,
        _state: Data<&State>,
        _token: Token,
        _req: Json<serde_json::Value>,
    ) -> Result<()> {
        Ok(())
    }
}

async fn accept_friend_request_by_id(
    state: &State,
    receiver_uid: i64,
    request_id: i64,
    from_device: &str,
) -> Result<i64> {
    let now = crate::api::DateTime::now();
    let row: Option<(i64, i64, i64, String)> = sqlx::query_as(
        "select id, requester_uid, receiver_uid, message from friend_request where id = ? and status = 'pending'",
    )
    .bind(request_id)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(InternalServerError)?;
    let (id, requester_uid, recv, _msg) =
        row.ok_or_else(|| Error::from_status(StatusCode::NOT_FOUND))?;
    if recv != receiver_uid {
        return Err(Error::from_status(StatusCode::FORBIDDEN));
    }

    let (low, high) = sort_pair(requester_uid, recv);
    let mut tx = state.db_pool.begin().await.map_err(InternalServerError)?;
    sqlx::query(
        "update friend_request set status = 'accepted', updated_at = ?, responded_at = ? where id = ?",
    )
    .bind(now)
    .bind(now)
    .bind(id)
    .execute(&mut *tx)
    .await
    .map_err(InternalServerError)?;
    sqlx::query(
        r#"insert into friendship (uid_low, uid_high, created_at, updated_at, deleted_at, deleted_by)
           values (?, ?, ?, ?, null, null)
           on conflict(uid_low, uid_high) do update set
             deleted_at = null, deleted_by = null, updated_at = excluded.updated_at"#,
    )
    .bind(low)
    .bind(high)
    .bind(now)
    .bind(now)
    .execute(&mut *tx)
    .await
    .map_err(InternalServerError)?;
    tx.commit().await.map_err(InternalServerError)?;

    strip_request_from_cache(state, id, requester_uid, recv).await;
    {
        let mut cache = state.cache.write().await;
        if let Some(u) = cache.users.get_mut(&requester_uid) {
            u.active_friends.insert(recv);
            u.stale_friends_display.remove(&recv);
        }
        if let Some(u) = cache.users.get_mut(&recv) {
            u.active_friends.insert(requester_uid);
            u.stale_friends_display.remove(&requester_uid);
        }
    }

    let fr_done = FriendRequestView {
        id,
        requester_uid,
        receiver_uid: recv,
        message: String::new(),
        status: "accepted".to_string(),
        created_at: now,
    };
    let snap = state.cache.read().await;
    for (uid, other) in [(requester_uid, recv), (recv, requester_uid)] {
        push_settings(
            state,
            uid,
            from_device,
            UserSettingsChangedMessage {
                friend_requests: vec![fr_done.clone()],
                contact_updates: vec![contact_relation(&snap, uid, other)],
                ..Default::default()
            },
        );
    }

    Ok(id)
}

async fn finalize_request(
    state: &State,
    request_id: i64,
    actor_uid: i64,
    status: &'static str,
    is_receiver_action: bool,
    from_device: &str,
) -> Result<()> {
    let row: Option<(i64, i64, i64)> = sqlx::query_as(
        "select id, requester_uid, receiver_uid from friend_request where id = ? and status = 'pending'",
    )
    .bind(request_id)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(InternalServerError)?;
    let (id, requester_uid, receiver_uid) =
        row.ok_or_else(|| Error::from_status(StatusCode::NOT_FOUND))?;
    if is_receiver_action {
        if actor_uid != receiver_uid {
            return Err(Error::from_status(StatusCode::FORBIDDEN));
        }
    } else if actor_uid != requester_uid {
        return Err(Error::from_status(StatusCode::FORBIDDEN));
    }

    let now = crate::api::DateTime::now();
    sqlx::query(
        "update friend_request set status = ?, updated_at = ?, responded_at = ? where id = ?",
    )
    .bind(status)
    .bind(now)
    .bind(now)
    .bind(id)
    .execute(&state.db_pool)
    .await
    .map_err(InternalServerError)?;

    strip_request_from_cache(state, id, requester_uid, receiver_uid).await;

    let fr_done = FriendRequestView {
        id,
        requester_uid,
        receiver_uid,
        message: String::new(),
        status: status.to_string(),
        created_at: now,
    };
    push_settings(
        state,
        requester_uid,
        from_device,
        UserSettingsChangedMessage {
            friend_requests: vec![fr_done.clone()],
            ..Default::default()
        },
    );
    push_settings(
        state,
        receiver_uid,
        from_device,
        UserSettingsChangedMessage {
            friend_requests: vec![fr_done],
            ..Default::default()
        },
    );

    Ok(())
}

async fn strip_request_from_cache(state: &State, id: i64, requester_uid: i64, receiver_uid: i64) {
    let mut cache = state.cache.write().await;
    if let Some(u) = cache.users.get_mut(&requester_uid) {
        u.outgoing_friend_requests.retain(|r| r.id != id);
        u.incoming_friend_requests.retain(|r| r.id != id);
    }
    if let Some(u) = cache.users.get_mut(&receiver_uid) {
        u.outgoing_friend_requests.retain(|r| r.id != id);
        u.incoming_friend_requests.retain(|r| r.id != id);
    }
}

async fn refresh_friend_request_lifecycle(state: &State) -> Result<()> {
    let now = crate::api::DateTime::now();
    let expire_cutoff = pending_expire_cutoff(now);
    let purge_cutoff = resolved_purge_cutoff(now);

    let to_expire = sqlx::query_as::<_, (i64, i64, i64, String, crate::api::DateTime)>(
        r#"select id, requester_uid, receiver_uid, message, created_at
           from friend_request
           where status = 'pending' and created_at <= ?"#,
    )
    .bind(expire_cutoff)
    .fetch_all(&state.db_pool)
    .await
    .map_err(InternalServerError)?;

    if !to_expire.is_empty() {
        sqlx::query(
            r#"update friend_request
               set status = 'expired',
                   updated_at = ?,
                   responded_at = coalesce(responded_at, datetime(created_at, '+7 day'))
               where status = 'pending' and created_at <= ?"#,
        )
        .bind(now)
        .bind(expire_cutoff)
        .execute(&state.db_pool)
        .await
        .map_err(InternalServerError)?;

        for (id, requester_uid, receiver_uid, message, created_at) in to_expire {
            strip_request_from_cache(state, id, requester_uid, receiver_uid).await;
            let fr = FriendRequestView {
                id,
                requester_uid,
                receiver_uid,
                message,
                status: "expired".to_string(),
                created_at,
            };
            push_settings(
                state,
                requester_uid,
                "",
                UserSettingsChangedMessage {
                    friend_requests: vec![fr.clone()],
                    ..Default::default()
                },
            );
            push_settings(
                state,
                receiver_uid,
                "",
                UserSettingsChangedMessage {
                    friend_requests: vec![fr],
                    ..Default::default()
                },
            );
        }
    }

    sqlx::query(
        r#"delete from friend_request
           where status in ('accepted', 'rejected', 'canceled', 'expired')
             and coalesce(responded_at, updated_at, created_at) <= ?"#,
    )
    .bind(purge_cutoff)
    .execute(&state.db_pool)
    .await
    .map_err(InternalServerError)?;
    Ok(())
}

async fn delete_friend_request_record(state: &State, request_id: i64, actor_uid: i64) -> Result<()> {
    let row: Option<(i64, i64, i64, String)> = sqlx::query_as(
        "select id, requester_uid, receiver_uid, status from friend_request where id = ?",
    )
    .bind(request_id)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(InternalServerError)?;
    let (id, requester_uid, receiver_uid, status) =
        row.ok_or_else(|| Error::from_status(StatusCode::NOT_FOUND))?;
    if actor_uid != requester_uid && actor_uid != receiver_uid {
        return Err(Error::from_status(StatusCode::FORBIDDEN));
    }
    if status == "pending" {
        return Err(Error::from_status(StatusCode::BAD_REQUEST));
    }
    sqlx::query("delete from friend_request where id = ?")
        .bind(id)
        .execute(&state.db_pool)
        .await
        .map_err(InternalServerError)?;
    Ok(())
}

async fn remove_friendship(
    state: &State,
    actor_uid: i64,
    peer_uid: i64,
    from_device: &str,
) -> Result<()> {
    let (low, high) = sort_pair(actor_uid, peer_uid);
    let now = crate::api::DateTime::now();
    let res = sqlx::query(
        "update friendship set deleted_at = ?, deleted_by = ?, updated_at = ? where uid_low = ? and uid_high = ? and deleted_at is null",
    )
    .bind(now)
    .bind(actor_uid)
    .bind(now)
    .bind(low)
    .bind(high)
    .execute(&state.db_pool)
    .await
    .map_err(InternalServerError)?;
    let ended_active = res.rows_affected() > 0;
    if !ended_active {
        // Peer already ended the friendship: allow this user to drop the stale edge from DB.
        let res2 = sqlx::query("delete from friendship where uid_low = ? and uid_high = ?")
            .bind(low)
            .bind(high)
            .execute(&state.db_pool)
            .await
            .map_err(InternalServerError)?;
        if res2.rows_affected() == 0 {
            return Err(Error::from_status(StatusCode::NOT_FOUND));
        }
    }

    {
        let mut cache = state.cache.write().await;
        if let Some(u) = cache.users.get_mut(&actor_uid) {
            u.active_friends.remove(&peer_uid);
            u.stale_friends_display.remove(&peer_uid);
        }
        if let Some(u) = cache.users.get_mut(&peer_uid) {
            u.active_friends.remove(&actor_uid);
            if ended_active && actor_uid != peer_uid {
                u.stale_friends_display.insert(actor_uid);
            }
        }
    }

    let snap = state.cache.read().await;
    for (uid, other) in [(actor_uid, peer_uid), (peer_uid, actor_uid)] {
        push_settings(
            state,
            uid,
            from_device,
            UserSettingsChangedMessage {
                contact_updates: vec![contact_relation(&snap, uid, other)],
                ..Default::default()
            },
        );
    }
    Ok(())
}

async fn block_user(
    state: &State,
    blocker_uid: i64,
    blocked_uid: i64,
    reason: Option<String>,
    from_device: &str,
) -> Result<()> {
    if blocker_uid == blocked_uid {
        return Err(Error::from_status(StatusCode::BAD_REQUEST));
    }
    let (low, high) = sort_pair(blocker_uid, blocked_uid);
    let now = crate::api::DateTime::now();
    let mut tx = state.db_pool.begin().await.map_err(InternalServerError)?;
    sqlx::query("delete from friendship where uid_low = ? and uid_high = ?")
        .bind(low)
        .bind(high)
        .execute(&mut *tx)
        .await
        .map_err(InternalServerError)?;
    sqlx::query(
        r#"insert into user_block (blocker_uid, blocked_uid, reason, created_at, updated_at)
           values (?, ?, ?, ?, ?)
           on conflict(blocker_uid, blocked_uid) do update set updated_at = excluded.updated_at"#,
    )
    .bind(blocker_uid)
    .bind(blocked_uid)
    .bind(reason.as_deref())
    .bind(now)
    .bind(now)
    .execute(&mut *tx)
    .await
    .map_err(InternalServerError)?;
    tx.commit().await.map_err(InternalServerError)?;

    {
        let mut cache = state.cache.write().await;
        if let Some(u) = cache.users.get_mut(&blocker_uid) {
            u.blocked_users.insert(blocked_uid);
            u.active_friends.remove(&blocked_uid);
            u.stale_friends_display.remove(&blocked_uid);
            u.incoming_friend_requests
                .retain(|r| r.requester_uid != blocked_uid);
            u.outgoing_friend_requests
                .retain(|r| r.receiver_uid != blocked_uid);
        }
        if let Some(u) = cache.users.get_mut(&blocked_uid) {
            u.blocked_by_users.insert(blocker_uid);
            u.active_friends.remove(&blocker_uid);
            u.stale_friends_display.remove(&blocker_uid);
            u.incoming_friend_requests
                .retain(|r| r.requester_uid != blocker_uid);
            u.outgoing_friend_requests
                .retain(|r| r.receiver_uid != blocker_uid);
        }
    }

    let snap = state.cache.read().await;
    push_settings(
        state,
        blocker_uid,
        from_device,
        UserSettingsChangedMessage {
            add_blocked_users: vec![blocked_uid],
            contact_updates: vec![contact_relation(&snap, blocker_uid, blocked_uid)],
            ..Default::default()
        },
    );
    push_settings(
        state,
        blocked_uid,
        from_device,
        UserSettingsChangedMessage {
            contact_updates: vec![contact_relation(&snap, blocked_uid, blocker_uid)],
            ..Default::default()
        },
    );

    Ok(())
}

async fn unblock_user(state: &State, blocker_uid: i64, blocked_uid: i64, from_device: &str) -> Result<()> {
    let res = sqlx::query("delete from user_block where blocker_uid = ? and blocked_uid = ?")
        .bind(blocker_uid)
        .bind(blocked_uid)
        .execute(&state.db_pool)
        .await
        .map_err(InternalServerError)?;
    if res.rows_affected() == 0 {
        return Err(Error::from_status(StatusCode::NOT_FOUND));
    }
    {
        let mut cache = state.cache.write().await;
        if let Some(u) = cache.users.get_mut(&blocker_uid) {
            u.blocked_users.remove(&blocked_uid);
        }
        if let Some(u) = cache.users.get_mut(&blocked_uid) {
            u.blocked_by_users.remove(&blocker_uid);
        }
    }
    let snap = state.cache.read().await;
    push_settings(
        state,
        blocker_uid,
        from_device,
        UserSettingsChangedMessage {
            remove_blocked_users: vec![blocked_uid],
            contact_updates: vec![contact_relation(&snap, blocker_uid, blocked_uid)],
            ..Default::default()
        },
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use poem::http::StatusCode;
    use serde_json::json;

    use crate::test_harness::TestServer;

    #[tokio::test]
    async fn blocked_user_cannot_send_dm_to_blocker() {
        let server = TestServer::new().await;
        let admin = server.login_admin().await;
        let uid1 = server.create_user(&admin).await;
        let uid2 = server.create_user(&admin).await;
        let t1 = server.login(uid1).await;
        let t2 = server.login(uid2).await;

        let resp = server
            .post(format!("/api/user/blacklist/{uid1}"))
            .header("X-Acting-Uid", &t2)
            .send()
            .await;
        resp.assert_status_is_ok();

        let resp = server
            .post(format!("/api/user/{uid2}/send"))
            .header("X-Acting-Uid", &t1)
            .header("Referer", "http://localhost/")
            .content_type("text/plain")
            .body("hi")
            .send()
            .await;
        resp.assert_status(StatusCode::FORBIDDEN);
    }

    #[tokio::test]
    async fn friend_request_rejected_when_receiver_blocked_requester() {
        let server = TestServer::new().await;
        let admin = server.login_admin().await;
        let uid1 = server.create_user(&admin).await;
        let uid2 = server.create_user(&admin).await;
        let t1 = server.login(uid1).await;
        let t2 = server.login(uid2).await;

        let resp = server
            .post(format!("/api/user/blacklist/{uid1}"))
            .header("X-Acting-Uid", &t2)
            .send()
            .await;
        resp.assert_status_is_ok();

        let resp = server
            .post("/api/user/friend_requests")
            .header("X-Acting-Uid", &t1)
            .body_json(&json!({ "receiver_uid": uid2, "message": "hi" }))
            .send()
            .await;
        resp.assert_status(StatusCode::FORBIDDEN);
    }
}
