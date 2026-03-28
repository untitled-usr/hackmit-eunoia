import { apiFetch } from "./client";
import type {
  UserAppMapping,
  UserAppMappingListResponse,
  User,
  UserCreatePayload,
  UserFilters,
  UserListResponse,
  UserPatchPayload
} from "../types/user";

export async function listUsers(params: {
  limit: number;
  offset: number;
  filters: UserFilters;
}): Promise<UserListResponse> {
  return await apiFetch<UserListResponse>("/admin/users", {
    method: "GET",
    query: {
      limit: params.limit,
      offset: params.offset,
      username: params.filters.username,
      email: params.filters.email,
      public_id: params.filters.public_id,
      is_active: params.filters.is_active
    }
  });
}

export async function getUser(id: string): Promise<User> {
  return await apiFetch<User>(`/admin/users/${encodeURIComponent(id)}`, { method: "GET" });
}

export async function createUser(payload: UserCreatePayload): Promise<User> {
  return await apiFetch<User>("/admin/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export async function patchUser(id: string, payload: UserPatchPayload): Promise<User> {
  return await apiFetch<User>(`/admin/users/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export async function deleteUser(id: string): Promise<void> {
  await apiFetch<void>(`/admin/users/${encodeURIComponent(id)}`, {
    method: "DELETE"
  });
}

export async function listUserMappingsByUserId(userId: string): Promise<UserAppMapping[]> {
  const response = await apiFetch<UserAppMappingListResponse>("/admin/user_app_mappings", {
    method: "GET",
    query: {
      limit: 100,
      offset: 0,
      user_id: userId
    }
  });
  return response.items;
}
