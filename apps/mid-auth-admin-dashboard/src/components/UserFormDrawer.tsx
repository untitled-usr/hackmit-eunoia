import { useEffect, useMemo, useState } from "react";
import type { User, UserCreatePayload, UserPatchPayload } from "../types/user";

type Props = {
  open: boolean;
  mode: "create" | "edit";
  user: User | null;
  saving: boolean;
  onClose: () => void;
  onSubmit: (payload: UserCreatePayload | UserPatchPayload) => Promise<void>;
};

type FormState = {
  id: string;
  public_id: string;
  username: string;
  email: string;
  password_hash: string;
  display_name: string;
  is_active: boolean;
  avatar_mime_type: string;
  avatar_data: string;
};

const emptyForm: FormState = {
  id: "",
  public_id: "",
  username: "",
  email: "",
  password_hash: "",
  display_name: "",
  is_active: true,
  avatar_mime_type: "",
  avatar_data: ""
};

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("读取文件失败"));
    reader.onload = () => {
      const value = String(reader.result ?? "");
      const idx = value.indexOf("base64,");
      resolve(idx >= 0 ? value.slice(idx + 7) : value);
    };
    reader.readAsDataURL(file);
  });
}

export default function UserFormDrawer(props: Props) {
  const [form, setForm] = useState<FormState>(emptyForm);
  const [clearAvatar, setClearAvatar] = useState(false);

  useEffect(() => {
    if (!props.open) return;
    if (props.mode === "edit" && props.user) {
      setForm({
        id: props.user.id,
        public_id: props.user.public_id,
        username: props.user.username,
        email: props.user.email,
        password_hash: props.user.password_hash,
        display_name: props.user.display_name,
        is_active: props.user.is_active,
        avatar_mime_type: props.user.avatar_mime_type ?? "",
        avatar_data: props.user.avatar_data ?? ""
      });
    } else {
      setForm(emptyForm);
    }
    setClearAvatar(false);
  }, [props.open, props.mode, props.user]);

  const previewUrl = useMemo(() => {
    if (clearAvatar || !form.avatar_data) return "";
    const mime = form.avatar_mime_type || "image/png";
    return `data:${mime};base64,${form.avatar_data}`;
  }, [form.avatar_data, form.avatar_mime_type, clearAvatar]);

  if (!props.open) return null;

  async function handlePickAvatar(file: File | undefined): Promise<void> {
    if (!file) return;
    const base64 = await fileToBase64(file);
    setForm((prev) => ({
      ...prev,
      avatar_data: base64,
      avatar_mime_type: file.type || prev.avatar_mime_type || "image/png"
    }));
    setClearAvatar(false);
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    if (props.mode === "create") {
      const payload: UserCreatePayload = {
        id: form.id.trim(),
        public_id: form.public_id.trim(),
        username: form.username.trim(),
        email: form.email.trim(),
        password_hash: form.password_hash.trim(),
        display_name: form.display_name.trim(),
        is_active: form.is_active,
        avatar_data: clearAvatar ? null : form.avatar_data || null,
        avatar_mime_type: clearAvatar ? null : form.avatar_mime_type || null
      };
      await props.onSubmit(payload);
      return;
    }

    const payload: UserPatchPayload = {
      public_id: form.public_id.trim(),
      username: form.username.trim(),
      email: form.email.trim(),
      display_name: form.display_name.trim(),
      is_active: form.is_active
    };
    if (form.password_hash.trim()) payload.password_hash = form.password_hash.trim();
    if (clearAvatar) {
      payload.avatar_data = null;
      payload.avatar_mime_type = null;
    } else if (form.avatar_data) {
      payload.avatar_data = form.avatar_data;
      payload.avatar_mime_type = form.avatar_mime_type || "image/png";
    }
    await props.onSubmit(payload);
  }

  return (
    <div className="drawer-backdrop">
      <aside className="drawer">
        <div className="drawer-header">
          <h3>{props.mode === "create" ? "新建用户" : "编辑用户"}</h3>
          <button onClick={props.onClose}>关闭</button>
        </div>
        <form className="form-grid" onSubmit={handleSubmit}>
          <label>
            ID
            <input
              value={form.id}
              disabled={props.mode === "edit"}
              required
              onChange={(e) => setForm((p) => ({ ...p, id: e.target.value }))}
            />
          </label>
          <label>
            public_id
            <input
              value={form.public_id}
              required
              onChange={(e) => setForm((p) => ({ ...p, public_id: e.target.value }))}
            />
          </label>
          <label>
            username
            <input
              value={form.username}
              required
              onChange={(e) => setForm((p) => ({ ...p, username: e.target.value }))}
            />
          </label>
          <label>
            email
            <input
              type="email"
              value={form.email}
              required
              onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))}
            />
          </label>
          <label>
            display_name
            <input
              value={form.display_name}
              required
              onChange={(e) => setForm((p) => ({ ...p, display_name: e.target.value }))}
            />
          </label>
          <label>
            password_hash {props.mode === "edit" ? "(留空不修改)" : ""}
            <input
              value={form.password_hash}
              required={props.mode === "create"}
              onChange={(e) => setForm((p) => ({ ...p, password_hash: e.target.value }))}
            />
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm((p) => ({ ...p, is_active: e.target.checked }))}
            />
            is_active
          </label>
          <label>
            avatar (图片文件)
            <input
              type="file"
              accept="image/png,image/jpeg"
              onChange={(e) => void handlePickAvatar(e.target.files?.[0])}
            />
          </label>
          <label className="checkbox">
            <input type="checkbox" checked={clearAvatar} onChange={(e) => setClearAvatar(e.target.checked)} />
            清空头像
          </label>
          {previewUrl && (
            <div className="avatar-preview">
              <img src={previewUrl} alt="avatar-preview" />
            </div>
          )}
          <div className="drawer-actions">
            <button type="button" onClick={props.onClose}>
              取消
            </button>
            <button type="submit" disabled={props.saving}>
              {props.saving ? "保存中..." : "保存"}
            </button>
          </div>
        </form>
      </aside>
    </div>
  );
}
