import { API_V1_URL } from "./config";

export type AuthUser = {
  id: number;
  username: string;
  role: "client" | "admin";
};

export type AuthResponse = {
  user: AuthUser;
  /**
   * Giữ optional để tương thích response cũ.
   * Trình duyệt dùng session cookie HttpOnly, không dùng access token.
   */
  access_token?: string;
  token_type?: "bearer";
  expires_in?: number;
};

let restoringSession: Promise<AuthResponse> | null = null;

async function parseResponse<T>(response: Response): Promise<T> {
  const body = await response.json();

  if (!response.ok) {
    throw new Error(body.detail ?? "Không thể thực hiện yêu cầu.");
  }

  return body as T;
}

export async function login(
  username: string,
  password: string,
): Promise<AuthResponse> {
  const body = new URLSearchParams({ username, password });

  const response = await fetch(`${API_V1_URL}/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body,
  });

  return parseResponse<AuthResponse>(response);
}

export async function register(
  username: string,
  password: string,
): Promise<AuthResponse> {
  const response = await fetch(`${API_V1_URL}/auth/register`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ username, password }),
  });

  return parseResponse<AuthResponse>(response);
}

async function fetchCurrentUser(): Promise<AuthResponse> {
  const response = await fetch(`${API_V1_URL}/auth/me`, {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error("Chưa đăng nhập.");
  }

  const user = (await response.json()) as AuthUser;
  return { user };
}

/** Khôi phục phiên từ cookie `session_id` HttpOnly sau khi tải lại trang. */
export function restoreSession(): Promise<AuthResponse> {
  restoringSession ??= fetchCurrentUser().finally(() => {
    restoringSession = null;
  });
  return restoringSession;
}

export async function logout(): Promise<void> {
  await fetch(`${API_V1_URL}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
}
