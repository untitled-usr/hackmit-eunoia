import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { createUser, deleteUser, listUserMappingsByUserId, listUsers, patchUser } from "./api/users";
import { toErrorText } from "./api/client";
import { login, logout, me } from "./api/auth";
import UserFormDrawer from "./components/UserFormDrawer";
import UserTable from "./components/UserTable";
import UserDetailPanel from "./components/UserDetailPanel";
import type {
  User,
  UserAppMapping,
  UserCreatePayload,
  UserFilters,
  UserPatchPayload
} from "./types/user";

const PAGE_SIZE = 20;

export default function App() {
  const [activeTab, setActiveTab] = useState<"users" | "embed">("users");
  const [embedPlatform, setEmbedPlatform] = useState<"openwebui" | "vocechat" | "memos">("openwebui");
  const [authLoading, setAuthLoading] = useState(true);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [adminUser, setAdminUser] = useState<string | null>(null);

  const [users, setUsers] = useState<User[]>([]);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [filters, setFilters] = useState<UserFilters>({});
  const [filterInputs, setFilterInputs] = useState<UserFilters>({});
  const [detailUser, setDetailUser] = useState<User | null>(null);
  const [userMappings, setUserMappings] = useState<Record<string, UserAppMapping[]>>({});
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [drawerMode, setDrawerMode] = useState<"create" | "edit">("create");
  const [drawerOpen, setDrawerOpen] = useState(false);

  const canPrev = offset > 0;
  const canNext = users.length === PAGE_SIZE;
  const selectedCount = selectedIds.size;

  const selectedUsers = useMemo(
    () => users.filter((u) => selectedIds.has(u.id)).map((u) => u.id),
    [users, selectedIds]
  );

  const isAuthed = !!adminUser;

  const bootstrapAuth = useCallback(async () => {
    setAuthLoading(true);
    try {
      const res = await me();
      if (res.authenticated && res.username) {
        setAdminUser(res.username);
      } else {
        setAdminUser(null);
      }
    } catch {
      setAdminUser(null);
    } finally {
      setAuthLoading(false);
    }
  }, []);

  useEffect(() => {
    void bootstrapAuth();
  }, [bootstrapAuth]);

  const reload = useCallback(async () => {
    if (!isAuthed) return;
    setLoading(true);
    setError("");
    try {
      const response = await listUsers({
        limit: PAGE_SIZE,
        offset,
        filters
      });
      setUsers(response.items);
      const mappingPairs = await Promise.all(
        response.items.map(async (u) => {
          try {
            const items = await listUserMappingsByUserId(u.id);
            return [u.id, items] as const;
          } catch {
            return [u.id, []] as const;
          }
        })
      );
      setUserMappings(Object.fromEntries(mappingPairs));
      setSelectedIds(new Set());
      if (detailUser) {
        const found = response.items.find((u) => u.id === detailUser.id) ?? null;
        setDetailUser(found);
      }
    } catch (e) {
      setError(toErrorText(e));
    } finally {
      setLoading(false);
    }
  }, [detailUser, filters, isAuthed, offset]);

  useEffect(() => {
    if (!isAuthed) return;
    void reload();
  }, [isAuthed, reload]);

  async function submitLogin(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError("");
    setNotice("");
    try {
      const res = await login({ username, password });
      setAdminUser(res.username);
      setPassword("");
      setNotice(`登录成功：${res.username}`);
    } catch (e) {
      setError(toErrorText(e));
    }
  }

  async function handleLogout(): Promise<void> {
    setError("");
    setNotice("");
    try {
      await logout();
      setAdminUser(null);
      setUsers([]);
      setSelectedIds(new Set());
      setDetailUser(null);
      setNotice("已退出登录");
    } catch (e) {
      setError(toErrorText(e));
    }
  }

  function openCreate(): void {
    setDrawerMode("create");
    setEditingUser(null);
    setDrawerOpen(true);
  }

  function openEdit(user: User): void {
    setDrawerMode("edit");
    setEditingUser(user);
    setDrawerOpen(true);
  }

  async function submitDrawer(payload: UserCreatePayload | UserPatchPayload): Promise<void> {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      if (drawerMode === "create") {
        await createUser(payload as UserCreatePayload);
        setNotice("创建用户成功");
      } else if (editingUser) {
        await patchUser(editingUser.id, payload as UserPatchPayload);
        setNotice("更新用户成功");
      }
      setDrawerOpen(false);
      await reload();
    } catch (e) {
      setError(toErrorText(e));
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteOne(user: User): Promise<void> {
    if (!window.confirm(`确认删除用户 ${user.username} (${user.id}) 吗？`)) return;
    setError("");
    setNotice("");
    try {
      await deleteUser(user.id);
      setNotice(`删除成功: ${user.id}`);
      if (detailUser?.id === user.id) setDetailUser(null);
      await reload();
    } catch (e) {
      setError(toErrorText(e));
    }
  }

  async function handleBatchDelete(): Promise<void> {
    if (selectedUsers.length === 0) return;
    if (!window.confirm(`确认批量删除 ${selectedUsers.length} 个用户吗？`)) return;
    setError("");
    setNotice("");
    const results = await Promise.allSettled(selectedUsers.map((id) => deleteUser(id)));
    let ok = 0;
    const failed: string[] = [];
    results.forEach((r, idx) => {
      if (r.status === "fulfilled") ok += 1;
      else failed.push(`${selectedUsers[idx]} => ${toErrorText(r.reason)}`);
    });
    setNotice(`批量删除完成：成功 ${ok}，失败 ${failed.length}`);
    if (failed.length) setError(failed.join("\n"));
    await reload();
  }

  if (authLoading) {
    return (
      <main className="page">
        <section className="card">
          <h2>检查登录状态...</h2>
        </section>
      </main>
    );
  }

  if (!isAuthed) {
    return (
      <main className="page">
        <section className="card login-card">
          <h1>Mid-Auth-Admin 登录</h1>
          {error && <pre className="notice err">{error}</pre>}
          <form className="form-grid" onSubmit={(e) => void submitLogin(e)}>
            <label>
              用户名
              <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="admin" />
            </label>
            <label>
              密码
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="输入密码"
              />
            </label>
            <div className="drawer-actions">
              <button type="submit">登录</button>
            </div>
          </form>
        </section>
      </main>
    );
  }

  return (
    <main className="page">
      <header className="header">
        <h1>Mid-Auth 用户管理 Dashboard</h1>
        <div className="header-actions">
          <span className="login-hint">当前管理员：{adminUser}</span>
          <button onClick={() => void handleLogout()}>退出</button>
          <button onClick={openCreate}>新建用户</button>
          <button className="danger" disabled={selectedCount === 0} onClick={() => void handleBatchDelete()}>
            批量删除 ({selectedCount})
          </button>
        </div>
      </header>

      <section className="card tab-strip">
        <button className={activeTab === "users" ? "tab active" : "tab"} onClick={() => setActiveTab("users")}>
          用户管理
        </button>
        <button className={activeTab === "embed" ? "tab active" : "tab"} onClick={() => setActiveTab("embed")}>
          三前端嵌入
        </button>
      </section>

      {activeTab === "embed" ? (
        <section className="card embed-card">
          <div className="embed-toolbar">
            <button
              className={embedPlatform === "openwebui" ? "tab active" : "tab"}
              onClick={() => setEmbedPlatform("openwebui")}
            >
              OpenWebUI
            </button>
            <button className={embedPlatform === "vocechat" ? "tab active" : "tab"} onClick={() => setEmbedPlatform("vocechat")}>
              VoceChat
            </button>
            <button className={embedPlatform === "memos" ? "tab active" : "tab"} onClick={() => setEmbedPlatform("memos")}>
              Memos
            </button>
          </div>
          <iframe
            className="embed-frame"
            src={`/embed/${embedPlatform}/`}
            title={`embed-${embedPlatform}`}
            referrerPolicy="same-origin"
          />
        </section>
      ) : (
        <>
          <section className="card filters">
            <h3>过滤</h3>
            <div className="filter-grid">
              <input
                placeholder="username"
                value={filterInputs.username ?? ""}
                onChange={(e) => setFilterInputs((p) => ({ ...p, username: e.target.value }))}
              />
              <input
                placeholder="email"
                value={filterInputs.email ?? ""}
                onChange={(e) => setFilterInputs((p) => ({ ...p, email: e.target.value }))}
              />
              <input
                placeholder="public_id"
                value={filterInputs.public_id ?? ""}
                onChange={(e) => setFilterInputs((p) => ({ ...p, public_id: e.target.value }))}
              />
              <select
                value={filterInputs.is_active ?? ""}
                onChange={(e) => setFilterInputs((p) => ({ ...p, is_active: e.target.value }))}
              >
                <option value="">is_active(全部)</option>
                <option value="true">true</option>
                <option value="false">false</option>
              </select>
              <button
                onClick={() => {
                  setOffset(0);
                  setFilters(filterInputs);
                }}
              >
                应用过滤
              </button>
              <button
                onClick={() => {
                  setOffset(0);
                  setFilterInputs({});
                  setFilters({});
                }}
              >
                重置
              </button>
            </div>
          </section>

          {notice && <pre className="notice ok">{notice}</pre>}
          {error && <pre className="notice err">{error}</pre>}

          <section className="layout">
            <div>
              <UserTable
                users={users}
                userMappings={userMappings}
                selectedIds={selectedIds}
                loading={loading}
                onToggleSelect={(id) =>
                  setSelectedIds((prev) => {
                    const next = new Set(prev);
                    if (next.has(id)) next.delete(id);
                    else next.add(id);
                    return next;
                  })
                }
                onToggleSelectAll={(checked) =>
                  setSelectedIds(checked ? new Set(users.map((u) => u.id)) : new Set())
                }
                onView={setDetailUser}
                onEdit={openEdit}
                onDelete={(user) => void handleDeleteOne(user)}
              />
              <div className="pager">
                <button disabled={!canPrev || loading} onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}>
                  上一页
                </button>
                <span>
                  offset: {offset}, size: {PAGE_SIZE}
                </span>
                <button disabled={!canNext || loading} onClick={() => setOffset((o) => o + PAGE_SIZE)}>
                  下一页
                </button>
              </div>
            </div>
            <UserDetailPanel user={detailUser} mappings={detailUser ? userMappings[detailUser.id] ?? [] : []} />
          </section>

          <UserFormDrawer
            open={drawerOpen}
            mode={drawerMode}
            user={editingUser}
            saving={saving}
            onClose={() => setDrawerOpen(false)}
            onSubmit={submitDrawer}
          />
        </>
      )}
    </main>
  );
}
