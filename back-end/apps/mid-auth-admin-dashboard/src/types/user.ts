export type User = {
  id: string;
  public_id: string;
  username: string;
  email: string;
  password_hash: string;
  display_name: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
  avatar_mime_type: string | null;
  avatar_data: string | null;
  avatar_updated_at: string | null;
};

export type UserListResponse = {
  resource: "users";
  limit: number;
  offset: number;
  items: User[];
};

export type UserFilters = {
  username?: string;
  email?: string;
  public_id?: string;
  is_active?: string;
};

export type UserCreatePayload = {
  id: string;
  public_id: string;
  username: string;
  email: string;
  password_hash: string;
  display_name: string;
  is_active?: boolean;
  avatar_mime_type?: string | null;
  avatar_data?: string | null;
};

export type UserPatchPayload = Partial<
  Omit<UserCreatePayload, "id"> & {
    last_login_at: string | null;
  }
>;

export type UserAppMapping = {
  id: number;
  user_id: string;
  app_name: string;
  app_uid: string;
  app_username: string | null;
  created_at: string;
  updated_at: string;
};

export type UserAppMappingListResponse = {
  resource: "user_app_mappings";
  limit: number;
  offset: number;
  items: UserAppMapping[];
};
