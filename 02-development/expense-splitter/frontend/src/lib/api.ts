/**
 * The ONLY module that talks to the backend.
 *
 * Talks to the FastAPI backend in ../backend over HTTP, per ../../openapi.yaml.
 * Base URL is configurable via VITE_API_URL (see .env.example); defaults to
 * the backend's local dev address.
 */
import type {
  ActivityEvent,
  Expense,
  Group,
  GroupBalances,
  NewExpenseInput,
  Payment,
  User,
} from "./types";

const API_BASE_URL: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000/api";

const TOKEN_KEY = "even.token";

function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Privacy mode / SSR: session just won't persist across reloads.
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Can't reach the server. Is the backend running?");
  }

  if (res.status === 204) return undefined as T;

  const body: unknown = await res.json().catch(() => null);

  if (!res.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : null;
    throw new ApiError(res.status, detail ?? `Request failed (${res.status}).`);
  }
  return body as T;
}

const json = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  // ---- auth -------------------------------------------------------------
  getCurrentUser: async (): Promise<User | null> => {
    if (!getToken()) return null;
    try {
      return await request<User>("/me");
    } catch {
      setToken(null);
      return null;
    }
  },
  signIn: async (email: string, password: string): Promise<User> => {
    const { token, user } = await request<{ token: string; user: User }>(
      "/auth/login",
      json({ email, password }),
    );
    setToken(token);
    return user;
  },
  signUp: async (name: string, email: string, password: string): Promise<User> => {
    const { token, user } = await request<{ token: string; user: User }>(
      "/auth/signup",
      json({ name, email, password }),
    );
    setToken(token);
    return user;
  },
  signOut: async (): Promise<void> => {
    try {
      await request<void>("/auth/logout", { method: "POST" });
    } finally {
      setToken(null);
    }
  },
  updateProfile: (patch: { name?: string; email?: string }): Promise<User> =>
    request<User>("/me", { method: "PATCH", body: JSON.stringify(patch) }),

  // ---- groups -----------------------------------------------------------
  listGroups: (): Promise<Group[]> => request<Group[]>("/groups"),
  getGroup: async (groupId: string): Promise<Group | null> => {
    try {
      return await request<Group>(`/groups/${groupId}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) return null;
      throw err;
    }
  },
  createGroup: (name: string, description: string): Promise<Group> =>
    request<Group>("/groups", json({ name, description })),
  renameGroup: (groupId: string, name: string): Promise<Group> =>
    request<Group>(`/groups/${groupId}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  addMember: (groupId: string, email: string): Promise<Group> =>
    request<Group>(`/groups/${groupId}/members`, json({ email })),
  leaveGroup: (groupId: string): Promise<void> =>
    request<void>(`/groups/${groupId}/leave`, { method: "POST" }),
  deleteGroup: (groupId: string): Promise<void> =>
    request<void>(`/groups/${groupId}`, { method: "DELETE" }),

  // ---- expenses ---------------------------------------------------------
  listExpenses: (groupId: string): Promise<Expense[]> =>
    request<Expense[]>(`/groups/${groupId}/expenses`),
  addExpense: (input: NewExpenseInput): Promise<Expense> =>
    request<Expense>(`/groups/${input.groupId}/expenses`, json(input)),
  editExpense: (expenseId: string, input: NewExpenseInput): Promise<Expense> =>
    request<Expense>(`/expenses/${expenseId}`, { method: "PATCH", body: JSON.stringify(input) }),
  deleteExpense: (expenseId: string): Promise<void> =>
    request<void>(`/expenses/${expenseId}`, { method: "DELETE" }),

  // ---- balances & settlement -------------------------------------------
  getBalances: (groupId: string): Promise<GroupBalances> =>
    request<GroupBalances>(`/groups/${groupId}/balances`),
  listPayments: (groupId: string): Promise<Payment[]> =>
    request<Payment[]>(`/groups/${groupId}/payments`),
  recordPayment: (input: Omit<Payment, "id">): Promise<Payment> =>
    request<Payment>(`/groups/${input.groupId}/payments`, json(input)),

  // ---- activity ---------------------------------------------------------
  listActivity: (groupId: string): Promise<ActivityEvent[]> =>
    request<ActivityEvent[]>(`/groups/${groupId}/activity`),
};
