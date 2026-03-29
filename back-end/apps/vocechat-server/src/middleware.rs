use poem::{
    http::{
        header::{HeaderName, HeaderValue},
        StatusCode,
    },
    Endpoint, EndpointExt, Error, Request, Response,
};
use poem_openapi::{ApiExtractor, ExtractParamOptions};

use crate::api::Token;

/// Browser EventSource cannot set `X-Acting-Uid`; allow `?acting_uid=` on `/user/events` only.
#[derive(Clone)]
pub struct ActingUidSse;

impl<E: Endpoint<Output = Response>> poem::Middleware<E> for ActingUidSse {
    type Output = ActingUidSseEndpoint<E>;

    fn transform(&self, inner: E) -> Self::Output {
        ActingUidSseEndpoint(inner)
    }
}

pub struct ActingUidSseEndpoint<E>(E);

#[poem::async_trait]
impl<E: Endpoint<Output = Response>> Endpoint for ActingUidSseEndpoint<E> {
    type Output = Response;

    async fn call(&self, mut req: Request) -> poem::Result<Response> {
        let path = req.uri().path();
        if path.contains("/user/events") {
            if let Some(q) = req.uri().query() {
                for (k, v) in url::form_urlencoded::parse(q.as_bytes()) {
                    if k == "acting_uid" {
                        let name = HeaderName::from_static("x-acting-uid");
                        if !req.headers().contains_key(&name) {
                            if let Ok(val) = HeaderValue::try_from(v.as_ref()) {
                                req.headers_mut().insert(name, val);
                            }
                        }
                        break;
                    }
                }
            }
        }
        self.0.call(req).await
    }
}

pub fn guest_forbidden(ep: impl Endpoint) -> impl Endpoint {
    ep.before(|req| async move {
        let token = Token::from_request(
            &req,
            &mut Default::default(),
            ExtractParamOptions {
                name: "",
                default_value: None,
                explode: false,
            },
        )
        .await?;
        if token.is_guest {
            return Err(Error::from_status(StatusCode::FORBIDDEN));
        }
        Ok(req)
    })
}
