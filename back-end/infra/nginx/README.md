# Nginx Reverse Proxy

This folder contains a multi-domain reverse proxy for local development:

- `owui.dev.local` -> Open WebUI frontend (`127.0.0.1:7923`)
- `memos.dev.local` -> Memos frontend (`127.0.0.1:7924`)
- `chat.dev.local` -> VoceChat backend (`127.0.0.1:7922`)
- `api.dev.local` -> future FastAPI middle layer (`127.0.0.1:19000`)

## Enable Config

```bash
sudo cp /root/devstack/workspace/infra/nginx/devstack.conf /etc/nginx/conf.d/devstack.conf
sudo nginx -t
sudo systemctl reload nginx
```

## Hosts Entries

Add to `/etc/hosts`:

```text
127.0.0.1 owui.dev.local memos.dev.local chat.dev.local api.dev.local
```
