/**
 * The ONLY module that talks to the backend.
 *
 * Every function below is currently backed by an in-memory mock store
 * (src/lib/mock-db.ts). When the real REST API exists, replace each body with
 * the fetch call noted in its comment and delete mock-db.ts — no UI changes.
 */
import { db } from "./mock-db";
import type {
  ActivityEvent,
  Expense,
  Group,
  GroupBalances,
  NewExpenseInput,
  Payment,
  User,
} from "./types";

const LATENCY_MS = 260;
const delay = <T>(value: T): Promise<T> =>
  new Promise((resolve) => setTimeout(() => resolve(value), LATENCY_MS));

export const api = {
  // ---- auth -------------------------------------------------------------
  /** GET /api/me */
  getCurrentUser: (): Promise<User | null> => delay(db.currentUser()),
  /** POST /api/auth/login */
  signIn: (email: string, _password: string): Promise<User> => delay(db.signIn(email)),
  /** POST /api/auth/signup */
  signUp: (name: string, email: string, _password: string): Promise<User> =>
    delay(db.signUp(name, email)),
  /** POST /api/auth/logout */
  signOut: (): Promise<void> => delay(db.signOut()),
  /** PATCH /api/me */
  updateProfile: (patch: { name?: string; email?: string }): Promise<User> =>
    delay(db.updateProfile(patch)),

  // ---- groups -----------------------------------------------------------
  /** GET /api/groups */
  listGroups: (): Promise<Group[]> => delay(db.groupsForCurrentUser()),
  /** GET /api/groups/:id */
  getGroup: (groupId: string): Promise<Group | null> => delay(db.group(groupId)),
  /** POST /api/groups */
  createGroup: (name: string, description: string): Promise<Group> =>
    delay(db.createGroup(name, description)),
  /** PATCH /api/groups/:id */
  renameGroup: (groupId: string, name: string): Promise<Group> =>
    delay(db.renameGroup(groupId, name)),
  /** POST /api/groups/:id/members */
  addMember: (groupId: string, email: string): Promise<Group> => delay(db.addMember(groupId, email)),

  // ---- expenses ---------------------------------------------------------
  /** GET /api/groups/:id/expenses */
  listExpenses: (groupId: string): Promise<Expense[]> => delay(db.expenses(groupId)),
  /** POST /api/groups/:id/expenses */
  addExpense: (input: NewExpenseInput): Promise<Expense> => delay(db.addExpense(input)),
  /** DELETE /api/expenses/:id */
  deleteExpense: (expenseId: string): Promise<void> => delay(db.deleteExpense(expenseId)),

  // ---- balances & settlement -------------------------------------------
  /** GET /api/groups/:id/balances (server recomputes; mirrors src/lib/money.ts) */
  getBalances: (groupId: string): Promise<GroupBalances> => delay(db.balances(groupId)),
  /** GET /api/groups/:id/payments */
  listPayments: (groupId: string): Promise<Payment[]> => delay(db.payments(groupId)),
  /** POST /api/groups/:id/payments */
  recordPayment: (input: Omit<Payment, "id">): Promise<Payment> => delay(db.recordPayment(input)),

  // ---- activity ---------------------------------------------------------
  /** GET /api/groups/:id/activity */
  listActivity: (groupId: string): Promise<ActivityEvent[]> => delay(db.activity(groupId)),
};
