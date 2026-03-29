#![allow(clippy::large_enum_variant)]
#![allow(clippy::uninlined_format_args)]

mod api;
mod api_key;
mod bootstrap_admin;
mod config;
mod create_user;
mod license;
mod middleware;
mod self_signed;
mod server;
mod state;
#[cfg(test)]
mod test_harness;

use std::{
    fs::File,
    path::{Path, PathBuf},
    sync::Arc,
    time::Duration,
};

use clap::Parser;
use poem::{
    listener::{Listener, TcpListener},
    EndpointExt, RouteScheme, Server,
};
use serde::Deserialize;
use sqlx::SqlitePool;
use tokio::runtime::Runtime;
use tracing_subscriber::{fmt::Subscriber, util::SubscriberInitExt, EnvFilter};

use crate::{
    config::{Config, TlsConfig},
    state::State,
};

#[derive(Debug, Default, Deserialize)]
struct EnvironmentVars {
    data_dir: Option<PathBuf>,

    fcm_project_id: String,
    fcm_private_key: String,
    fcm_client_email: String,
    token_uri: String,
}

impl EnvironmentVars {
    fn merge_to_config(self, mut config: Config) -> Config {
        if let Some(data_dir) = self.data_dir {
            config.system.data_dir = data_dir;
        }

        config.offical_fcm_config.project_id = self.fcm_project_id;
        config.offical_fcm_config.private_key = self.fcm_private_key;
        config.offical_fcm_config.client_email = self.fcm_client_email;
        config.offical_fcm_config.token_uri = self.token_uri;

        config
    }
}

#[derive(Debug, Parser)]
#[clap(name = "vocechat", author, version, about)]
struct Options {
    /// Path of the config file
    #[clap(default_value = "config/config.toml")]
    pub config: PathBuf,
    /// Start a daemon in the background
    #[cfg(not(windows))]
    #[clap(long = "daemon")]
    pub daemon: bool,
    /// Create pid file, lock it exclusive and write daemon pid.
    #[cfg(not(windows))]
    #[clap(long = "pid.file")]
    pub pid_file: Option<PathBuf>,
    /// Standard output file of the daemon
    #[clap(long = "stdout")]
    pub stdout: Option<PathBuf>,
    /// Server domain
    #[clap(long = "network.domain")]
    network_domain: Vec<String>,
    /// Listener bind address
    #[clap(long = "network.bind")]
    network_bind: Option<String>,
    /// Tls type (none, self_signed, certificate, acme_http_01,
    /// acme_tls_alpn_01)
    #[clap(long = "network.tls.type")]
    network_tls_type: Option<String>,
    /// Certificate file path
    #[clap(long = "network.tls.cert")]
    network_tls_cert_path: Option<String>,
    /// Certificate key path
    #[clap(long = "network.tls.key")]
    network_tls_key_path: Option<String>,
    /// Listener bind address for AcmeHTTP_01
    #[clap(long = "network.tls.acme.http_bind")]
    network_tls_acme_http_bind: Option<String>,
    /// Frontend url
    #[clap(long = "network.frontend_url")]
    frontend_url: Option<String>,
    /// Acme directory url
    #[clap(
        long = "network.tls.acme.directory_url",
        default_value = "https://acme-v02.api.letsencrypt.org/directory"
    )]
    network_tls_acme_directory_url: String,
    /// Cache path for certificates
    #[clap(long = "network.tls.acme.cache_path")]
    network_tls_acme_cache_path: Option<String>,
}

impl Options {
    fn merge_to_config(self, mut config: Config) -> Config {
        config.network.domain.extend(self.network_domain);
        if let Some(network_bind) = self.network_bind {
            config.network.bind = network_bind;
        }

        if let Some(network_tls_type) = self.network_tls_type {
            match network_tls_type.as_str() {
                "none" => config.network.tls = None,
                "self_signed" => config.network.tls = Some(TlsConfig::SelfSigned),
                "certificate" => match (self.network_tls_cert_path, self.network_tls_key_path) {
                    (Some(cert_path), Some(key_path)) => {
                        config.network.tls = Some(TlsConfig::Certificate {
                            cert: None,
                            cert_path: Some(cert_path),
                            key: None,
                            key_path: Some(key_path),
                        });
                    }
                    (None, _) => {
                        tracing::warn!("`network.tls.cert` is required");
                    }
                    (_, None) => {
                        tracing::warn!("`network.tls.key` is required");
                    }
                },
                "acme_http_01" => match self.network_tls_acme_http_bind {
                    Some(http_bind) => {
                        config.network.tls = Some(TlsConfig::AcmeHttp01 {
                            http_bind,
                            directory_url: Some(self.network_tls_acme_directory_url),
                            cache_path: self.network_tls_acme_cache_path,
                        });
                    }
                    None => {
                        tracing::warn!("`network.tls.acme.http_bind` is required");
                    }
                },
                "acme_tls_alpn_01" => {
                    config.network.tls = Some(TlsConfig::AcmeTlsAlpn01 {
                        directory_url: Some(self.network_tls_acme_directory_url),
                        cache_path: self.network_tls_acme_cache_path,
                    });
                }
                _ => {
                    tracing::warn!(
                        r#type = network_tls_type.as_str(),
                        "unknown `network.tls.type`"
                    );
                }
            }
        }

        if let Some(frontend_url) = self.frontend_url {
            config.network.frontend_url = frontend_url;
        }

        config
    }
}

fn init_tracing(with_ansi: bool) {
    if std::env::var_os("RUST_LOG").is_none() {
        std::env::set_var("RUST_LOG", "vocechat=debug,poem=debug");
    }

    let subscriber = Subscriber::builder()
        .with_env_filter(EnvFilter::from_default_env())
        .with_ansi(with_ansi)
        .finish();
    subscriber.try_init().unwrap();
}

fn load_config(path: &Path) -> anyhow::Result<Config> {
    let data = std::fs::read(path)?;
    Ok(toml::from_slice(&data)?)
}

fn main() {
    let options: Options = Options::parse();

    #[cfg(not(windows))]
    if options.daemon {
        use daemonize::Daemonize;

        let mut daemon = Daemonize::new().working_directory(std::env::current_dir().unwrap());

        if let Some(stdout_file) = &options.stdout {
            match File::create(stdout_file) {
                Ok(file) => {
                    daemon = daemon.stdout(file);
                }
                Err(err) => {
                    tracing::error!(
                        path = %stdout_file.display(),
                        error = %err,
                        "failed to create file"
                    );
                }
            }
        }

        if let Some(pid_file) = &options.pid_file {
            daemon = daemon.pid_file(pid_file);
        }

        if let Err(err) = daemon.start() {
            tracing::error!(error = %err, "failed to create daemon");
            return;
        }

        init_tracing(false);
    } else {
        init_tracing(true);
    }

    #[cfg(windows)]
    init_tracing(true);

    Runtime::new().unwrap().block_on(async move {
        // load config
        tracing::info!(
            current_dir = %std::env::current_dir().unwrap().display(),
            path = %options.config.display(),
            "load configuration file.",
        );
        let config_path = options.config.clone();
        let config = Arc::new(match load_config(&config_path) {
            Ok(config) => envy::prefixed("VOCECHAT_")
                .from_env::<EnvironmentVars>()
                .unwrap_or_default()
                .merge_to_config(options.merge_to_config(config)),
            Err(err) => {
                tracing::error!(
                    path = %config_path.display(),
                    error = %err,
                    "failed to load configuration file."
                );
                return;
            }
        });

        let state = match server::create_state(config_path.parent().unwrap(), config.clone()).await
        {
            Ok(state) => state,
            Err(err) => {
                tracing::error!(
                    error = %err,
                    "failed to create server."
                );
                return;
            }
        };

        let auto_cert = match &config.network.tls {
            Some(tls) => match tls.create_auto_cert(&config.network.domain) {
                Ok(auto_cert) => auto_cert,
                Err(err) => {
                    tracing::error!(
                        error = %err,
                        "failed to create auto certificate manager"
                    );
                    return;
                }
            },
            None => None,
        };

        crate::license::init_license(&state).await.unwrap();

        let app = match &config.network.tls {
            Some(TlsConfig::AcmeHttp01 { .. }) => RouteScheme::new()
                .https(server::create_endpoint(state.clone()).await)
                .http(auto_cert.as_ref().unwrap().http_01_endpoint())
                .boxed(),
            _ => server::create_endpoint(state.clone()).await
                .map_to_response()
                .boxed(),
        };

        tokio::spawn({
            let state = state.clone();
            async move {
                loop {
                    tokio::time::sleep(Duration::from_secs(30)).await;
                    state.clean_mute().await;
                    state.sync_bot_key_last_used().await;

                    tokio::task::spawn_blocking({
                        let state = state.clone();
                        move || {
                            state.clean_temp_files();
                            state.clean_files();
                        }
                    });
                }
            }
        });

        let mut listener = TcpListener::bind(config.network.bind.to_string()).boxed();
        if let Some(tls_config) = &config.network.tls {
            listener = match tls_config.transform_listener(listener, auto_cert) {
                Ok(listener) => listener,
                Err(err) => {
                    tracing::error!(error = %err, "failed to create listener");
                    return;
                }
            };
            if let TlsConfig::AcmeHttp01 { http_bind, .. } = &tls_config {
                listener = listener
                    .combine(TcpListener::bind(http_bind.clone()))
                    .boxed();
            }
        }

        Server::new(listener).run(app).await.unwrap();
    });
}

