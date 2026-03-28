# systemd --user Units

These units manage backend processes while frontends remain manual dev servers.

Available units:

- `open-webui-backend.service`
- `memos-backend.service`
- `vocechat-backend.service`
- `mid-auth.service`

## Install

```bash
mkdir -p ~/.config/systemd/user
cp /root/devstack/workspace/infra/systemd-user/*.service ~/.config/systemd/user/
systemctl --user daemon-reload
```

## Start Example

```bash
systemctl --user enable --now open-webui-backend.service
systemctl --user enable --now memos-backend.service
systemctl --user enable --now vocechat-backend.service
```
