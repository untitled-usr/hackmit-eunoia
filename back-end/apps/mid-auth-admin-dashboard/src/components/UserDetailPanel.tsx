import type { User, UserAppMapping } from "../types/user";

type Props = {
  user: User | null;
  mappings: UserAppMapping[];
};

function row(label: string, value: string) {
  return (
    <div className="detail-row">
      <span className="label">{label}</span>
      <span className="value">{value || "-"}</span>
    </div>
  );
}

export default function UserDetailPanel({ user, mappings }: Props) {
  if (!user) {
    return (
      <div className="card detail-panel">
        <h3>用户详情</h3>
        <div className="empty">请选择一条用户记录查看详情</div>
      </div>
    );
  }

  const avatarUrl =
    user.avatar_data && user.avatar_mime_type
      ? `data:${user.avatar_mime_type};base64,${user.avatar_data}`
      : "";

  return (
    <div className="card detail-panel">
      <h3>用户详情</h3>
      {avatarUrl ? (
        <img src={avatarUrl} alt="avatar" className="avatar" />
      ) : (
        <div className="empty">无头像</div>
      )}
      {row("id", user.id)}
      {row("public_id", user.public_id)}
      {row("username", user.username)}
      {row("email", user.email)}
      {row("display_name", user.display_name)}
      {row("is_active", String(user.is_active))}
      {row("created_at", user.created_at)}
      {row("updated_at", user.updated_at)}
      {row("last_login_at", user.last_login_at ?? "-")}
      {row("avatar_updated_at", user.avatar_updated_at ?? "-")}
      <div className="mapping-block">
        <div className="label">下游唯一ID映射</div>
        {mappings.length === 0 ? (
          <div className="empty">暂无映射</div>
        ) : (
          <ul className="mapping-list">
            {mappings.map((m) => (
              <li key={m.id}>
                <span className="mono">{m.app_name}</span>
                {" -> "}
                <span className="mono">{m.app_uid}</span>
                {m.app_username ? ` (${m.app_username})` : ""}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
