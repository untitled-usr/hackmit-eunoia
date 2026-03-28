import type { User, UserAppMapping } from "../types/user";

type Props = {
  users: User[];
  userMappings: Record<string, UserAppMapping[]>;
  selectedIds: Set<string>;
  loading: boolean;
  onToggleSelect: (id: string) => void;
  onToggleSelectAll: (checked: boolean) => void;
  onView: (user: User) => void;
  onEdit: (user: User) => void;
  onDelete: (user: User) => void;
};

function formatDate(value: string | null): string {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

export default function UserTable(props: Props) {
  const allChecked = props.users.length > 0 && props.users.every((u) => props.selectedIds.has(u.id));
  const someChecked = props.users.some((u) => props.selectedIds.has(u.id));

  return (
    <div className="card">
      <table className="table">
        <thead>
          <tr>
            <th>
              <input
                type="checkbox"
                checked={allChecked}
                ref={(el) => {
                  if (el) el.indeterminate = !allChecked && someChecked;
                }}
                onChange={(e) => props.onToggleSelectAll(e.target.checked)}
              />
            </th>
            <th>ID</th>
            <th>用户名</th>
            <th>Email</th>
            <th>展示名</th>
            <th>状态</th>
            <th>下游唯一ID映射</th>
            <th>更新时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {props.users.map((u) => (
            <tr key={u.id}>
              <td>
                <input
                  type="checkbox"
                  checked={props.selectedIds.has(u.id)}
                  onChange={() => props.onToggleSelect(u.id)}
                />
              </td>
              <td className="mono">{u.id}</td>
              <td>{u.username}</td>
              <td>{u.email}</td>
              <td>{u.display_name}</td>
              <td>{u.is_active ? "active" : "inactive"}</td>
              <td>
                {(props.userMappings[u.id] ?? []).length > 0
                  ? (props.userMappings[u.id] ?? [])
                      .map((m) => `${m.app_name}:${m.app_uid}`)
                      .join(", ")
                  : "-"}
              </td>
              <td>{formatDate(u.updated_at)}</td>
              <td className="actions">
                <button onClick={() => props.onView(u)}>详情</button>
                <button onClick={() => props.onEdit(u)}>编辑</button>
                <button className="danger" onClick={() => props.onDelete(u)}>
                  删除
                </button>
              </td>
            </tr>
          ))}
          {!props.loading && props.users.length === 0 && (
            <tr>
              <td colSpan={9} className="empty">
                暂无数据
              </td>
            </tr>
          )}
          {props.loading && (
            <tr>
              <td colSpan={9} className="empty">
                加载中...
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
