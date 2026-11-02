import { request } from "./http";

export type ManagedUser = {
  id: number;
  username: string;
  role: "client" | "admin";
  is_active: boolean;
  last_seen_at: string | null;
};

export type CreateUserPayload = {
  username: string;
  password: string;
  role: "client" | "admin";
  is_active: boolean;
};

export type UpdateUserPayload = Omit<CreateUserPayload, "password"> & {
  password?: string;
};

const USERS_PATH = "/api/v1/auth/admin/users";

export async function listManagedUsers(): Promise<ManagedUser[]> {
  const response = await request<{ items: ManagedUser[] }>(USERS_PATH);
  return response.items;
}

export async function createManagedUser(payload: CreateUserPayload): Promise<ManagedUser> {
  const response = await request<{ item: ManagedUser }>(USERS_PATH, {
    method: "POST",
    body: payload,
  });
  return response.item;
}

export async function updateManagedUser(userId: number, payload: UpdateUserPayload): Promise<ManagedUser> {
  const response = await request<{ item: ManagedUser }>(`${USERS_PATH}/${userId}`, {
    method: "PATCH",
    body: payload,
  });
  return response.item;
}

export async function deleteManagedUser(userId: number): Promise<void> {
  await request<{ deleted: boolean }>(`${USERS_PATH}/${userId}`, { method: "DELETE" });
}
