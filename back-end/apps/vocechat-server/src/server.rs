use std::{path::Path, sync::Arc};

use anyhow::Result;
use itertools::Itertools;
use poem::{
    middleware::{Cors, TokioMetrics, Tracing},
    Endpoint, EndpointExt, Route,
};
use rc_msgdb::MsgDb;
use sqlx::migrate::{MigrateDatabase, Migrator};
use tokio::sync::{broadcast, mpsc, RwLock};

use crate::{
    api,
    api::{
        get_merged_message, AgoraConfig, FcmConfig, FrontendUrlConfig, OrganizationConfig,
        SmtpConfig,
    },
    bootstrap_admin::ensure_system_bootstrap_admin,
    config::KeyConfig,
    create_user::{CreateUser, CreateUserBy},
    middleware::ActingUidSse,
    state::{
        forward_chat_messages_to_webhook, BroadcastEvent, Cache, DynamicConfigEntry,
    },
    Config, SqlitePool, State,
};

pub static MIGRATOR: Migrator = sqlx::migrate!();

/// 用户头像功能已移除：删除遗留目录 `data/avatar`，并将库内 `avatar_updated_at` 归零（幂等）。
fn cleanup_legacy_user_avatar_artifacts(system: &crate::config::SystemConfig) {
    let legacy_dir = system.data_dir.join("avatar");
    if legacy_dir.exists() {
        match std::fs::remove_dir_all(&legacy_dir) {
            Ok(()) => tracing::info!(
                path = %legacy_dir.display(),
                "removed legacy user avatar directory"
            ),
            Err(e) => tracing::warn!(
                path = %legacy_dir.display(),
                error = %e,
                "failed to remove legacy user avatar directory"
            ),
        }
    }
}

async fn reset_legacy_user_avatar_timestamps(pool: &SqlitePool) -> anyhow::Result<()> {
    let z = api::DateTime::zero();
    let r = sqlx::query("UPDATE user SET avatar_updated_at = ? WHERE avatar_updated_at != ?")
        .bind(z)
        .bind(z)
        .execute(pool)
        .await?;
    if r.rows_affected() > 0 {
        tracing::info!(
            rows = r.rows_affected(),
            "cleared legacy user avatar_updated_at in database"
        );
    }
    Ok(())
}

pub fn create_random_str(len: usize) -> String {
    String::from_utf8(
        (0..len)
            .map(|_| fastrand::alphanumeric() as u8)
            .collect_vec(),
    )
    .unwrap()
}

pub async fn create_state(config_path: &Path, config: Arc<Config>) -> Result<State> {
    // load key config
    let mut key_config = None;
    let key_config_path = config.system.data_dir.join("key.json");
    if key_config_path.exists() {
        if let Ok(data) = std::fs::read(&key_config_path) {
            if let Ok(cfg) = serde_json::from_slice::<KeyConfig>(&data) {
                key_config = Some(cfg);
            }
        }
    }

    std::fs::create_dir_all(&config.system.data_dir).expect("create data dir");

    if key_config.is_none() {
        let cfg = KeyConfig {
            server_id: create_random_str(32),
            server_key: create_random_str(32),
            third_party_secret: create_random_str(32),
        };
        std::fs::write(&key_config_path, serde_json::to_vec(&cfg)?)?;
        key_config = Some(cfg);
    }
    let key_config = key_config.unwrap();

    std::fs::create_dir_all(config.system.tmp_dir()).expect("create tmp dir");
    std::fs::create_dir_all(config.system.db_dir()).expect("create db dir");
    std::fs::create_dir_all(config.system.msg_dir()).expect("create message dir");
    std::fs::create_dir_all(config.system.thumbnail_dir()).expect("create thumbnails dir");
    std::fs::create_dir_all(config.system.file_dir()).expect("create file dir");
    std::fs::create_dir_all(config.system.group_avatar_dir()).expect("create group avatars dir");

    // open sqlite db
    let dsn = format!("sqlite:{}", config.system.sqlite_filename().display());
    if !config.system.sqlite_filename().exists() {
        tracing::info!(dsn = dsn.as_str(), "create sqlite db.");
        sqlx::Sqlite::create_database(&dsn).await?;
    }

    tracing::info!(dsn = dsn.as_str(), "open sqlite db.");
    let db_pool = SqlitePool::connect(&dsn).await?;
    MIGRATOR.run(&db_pool).await?;

    cleanup_legacy_user_avatar_artifacts(&config.system);
    reset_legacy_user_avatar_timestamps(&db_pool).await?;

    // open message db
    tracing::info!(
        path = config.system.msg_dir().display().to_string().as_str(),
        "open message db."
    );
    let msg_db = MsgDb::open(config.system.msg_dir())?;

    let (groups, users) = futures_util::try_join!(
        State::load_groups_cache(&msg_db, &db_pool),
        State::load_users_cache(&db_pool),
    )?;

    let (msg_updated_tx, msg_updated_rx) = mpsc::unbounded_channel();

    let state = State {
        key_config: Arc::new(RwLock::new(key_config)),
        config: config.clone(),
        config_path: config_path.to_owned(),
        db_pool,
        msg_db: Arc::new(msg_db),
        cache: Arc::new(RwLock::new(Cache {
            dynamic_config: Default::default(),
            groups,
            users,
        })),
        event_sender: Arc::new(broadcast::channel(128).0),
        msg_updated_channel: Arc::new(msg_updated_tx),
        invalid_device_tokens: Default::default(),
    };

    ensure_system_bootstrap_admin(
        &state,
        config.system.test_skip_system_admin_bootstrap,
    )
    .await?;

    // load dynamic config
    state
        .initialize_dynamic_config::<OrganizationConfig>()
        .await?;
    state
        .initialize_dynamic_config::<FrontendUrlConfig>()
        .await?;
    state.initialize_dynamic_config::<SmtpConfig>().await?;
    state
        .initialize_dynamic_config_with::<FcmConfig, _>(|| DynamicConfigEntry {
            enabled: true,
            config: FcmConfig {
                use_official: true,
                ..Default::default()
            },
        })
        .await?;
    state.initialize_dynamic_config::<AgoraConfig>().await?;

    // create users
    for user in &config.users {
        let pending_name = {
            let cache = state.cache.read().await;
            cache.pending_registration_name()
        };
        let create_user = CreateUser::new(
            pending_name.as_str(),
            CreateUserBy::Password {
                password: Some(user.password.as_str()),
            },
            false,
        )
        .gender(user.gender)
        .set_admin(false)
        .language(&user.language);
        let _ = state.create_user(create_user).await;
    }

    tokio::spawn(process_msg_updated(state.clone(), msg_updated_rx));
    tokio::spawn(forward_chat_messages_to_webhook(state.clone()));
    Ok(state)
}

async fn process_msg_updated(state: State, mut rx: mpsc::UnboundedReceiver<i64>) {
    while let Some(mid) = rx.recv().await {
        // process pinned messages
        if let Ok(merged_msg) = get_merged_message(&state.msg_db, mid) {
            let mut cache = state.cache.write().await;
            let Cache { groups, users, .. } = &mut *cache;

            for (gid, group) in groups {
                if let Some((idx, pinned_msg)) = group
                    .pinned_messages
                    .iter_mut()
                    .enumerate()
                    .find(|(_, pinned_msg)| pinned_msg.mid == mid)
                {
                    let targets = if group.ty.is_public() {
                        users.iter().map(|(uid, _)| *uid).collect()
                    } else {
                        group.members.clone()
                    };

                    match merged_msg {
                        Some(merged_msg) => {
                            // pinned message updated

                            // update cache
                            pinned_msg.content = merged_msg.content;

                            // broadcast
                            let _ = state.event_sender.send(Arc::new(
                                BroadcastEvent::PinnedMessageUpdated {
                                    targets,
                                    gid: *gid,
                                    mid,
                                    msg: Some(pinned_msg.clone()),
                                },
                            ));
                        }
                        None => {
                            // pinned message deleted

                            // update cache
                            group.pinned_messages.remove(idx);

                            // update database
                            if let Err(err) =
                                sqlx::query("delete from pinned_message where gid = ? and mid = ?")
                                    .bind(gid)
                                    .bind(mid)
                                    .execute(&state.db_pool)
                                    .await
                            {
                                tracing::error!(
                                    gid = gid,
                                    mid = mid,
                                    error = %err,
                                    "failed to delete pinned message"
                                );
                            }

                            // broadcast
                            let _ = state.event_sender.send(Arc::new(
                                BroadcastEvent::PinnedMessageUpdated {
                                    targets,
                                    gid: *gid,
                                    mid,
                                    msg: None,
                                },
                            ));
                        }
                    }
                    break;
                }
            }
        }
    }
}

pub async fn create_endpoint(state: State) -> impl Endpoint {
    let mut api_service = state.config.network.domain.iter().fold(
        api::create_api_service().server("http://localhost:3000/api"),
        |acc, domain| acc.server(format!("https://{}/api", domain)),
    );
    let frontend_url = state
        .get_dynamic_config_instance::<FrontendUrlConfig>()
        .await
        .and_then(|config| config.url.clone())
        .or_else(|| {
            if !state.config.network.frontend_url.is_empty() {
                Some(state.config.network.frontend_url.clone())
            } else {
                None
            }
        });
    if let Some(frontend_url) = frontend_url {
        api_service = api_service.server(if frontend_url.ends_with('/') {
            format!("{}api", frontend_url)
        } else {
            format!("{}/api", frontend_url)
        });
    };

    let metrics = TokioMetrics::new();

    Route::new()
        .nest(
            "/",
            poem::endpoint::StaticFilesEndpoint::new(state.config.system.wwwroot_dir())
                .index_file("index.html"),
        )
        .at("/health", poem::endpoint::make_sync(|_| ()))
        .at("/metrics", metrics.exporter())
        .nest("/api/doc", api_service.swagger_ui())
        .nest("/api/doc2", api_service.rapidoc())
        .nest("/api/swagger", api_service.swagger_ui())
        .nest("/api/doc3", api_service.redoc())
        .nest("/api/spec", api_service.spec_endpoint())
        .nest("/api", api_service)
        .with(ActingUidSse)
        .with(Tracing)
        .with(Cors::new().allow_credentials(true))
        .with(metrics)
        .inspect_err(|err: &sqlx::Error| {
            tracing::error!(error = %err, "sqlite error");
        })
        .data(state)
}

#[cfg(test)]
mod tests {
    use poem::{
        listener::{Acceptor, Listener, TcpListener},
        Server,
    };
    use reqwest::{Certificate, StatusCode};

    use super::*;
    use crate::{
        config::{NetworkConfig, SystemConfig, TlsConfig},
        self_signed::create_self_signed_config,
    };

    #[tokio::test]
    async fn test_tls_server() {
        let tempdir = tempfile::TempDir::new().unwrap();
        let config = Config {
            system: SystemConfig {
                data_dir: tempdir.path().to_path_buf(),
                upload_avatar_limit: 1024 * 1024,
                send_image_limit: 1024 * 1024,
                upload_timeout_seconds: 300,
                file_expiry_days: 30 * 3,
                max_favorite_archives: 100,
                disable_license: false,
                test_skip_system_admin_bootstrap: false,
            },
            network: NetworkConfig {
                domain: Vec::new(),
                bind: "127.0.0.1:0".to_string(),
                tls: Some(TlsConfig::SelfSigned),
                frontend_url: "https://127.0.0.1:3000".to_string(),
            },
            template: Default::default(),
            users: vec![],
            webclient_url: None,
            offical_fcm_config: Default::default(),
        };
        let state = create_state(tempdir.path(), Arc::new(config))
            .await
            .unwrap();
        let ep = create_endpoint(state).await;
        let acceptor = TcpListener::bind("127.0.0.1:0")
            .rustls(create_self_signed_config())
            .into_acceptor()
            .await
            .unwrap();
        let addr = acceptor.local_addr().remove(0);
        tokio::spawn(async move {
            Server::new_with_acceptor(acceptor).run(ep).await.unwrap();
        });
        let port = addr.as_socket_addr().unwrap().port();

        let client = reqwest::Client::builder()
            .use_rustls_tls()
            .add_root_certificate(Certificate::from_pem(include_bytes!("../cert/ca.crt")).unwrap())
            .danger_accept_invalid_certs(true)
            .no_proxy()
            .build()
            .unwrap();
        let url = format!("https://localhost:{}/health", port);
        let resp = client.get(url).send().await.unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }
}
