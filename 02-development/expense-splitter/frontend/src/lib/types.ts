import type { ItemizedLine, SplitType } from "./money";

export interface User {
  id: string;
  name: string;
  email: string;
  avatarInitials: string;
}

export type Role = "admin" | "member";

export interface Member {
  userId: string;
  name: string;
  avatarInitials: string;
  role: Role;
  joinedAt: string;
}

export interface Group {
  id: string;
  name: string;
  description: string;
  createdBy: string;
  createdAt: string;
  members: Member[];
}

export interface Payer {
  userId: string;
  amountCents: number;
}

export interface Expense {
  id: string;
  groupId: string;
  description: string;
  amountCents: number;
  date: string;
  category: string | null;
  splitType: SplitType;
  payers: Payer[];
  /** userId -> cents owed for this expense. Always sums to amountCents. */
  shares: Record<string, number>;
  items?: ItemizedLine[] | undefined;
  createdBy: string;
}

export interface Payment {
  id: string;
  groupId: string;
  fromUserId: string;
  toUserId: string;
  amountCents: number;
  date: string;
  note?: string | undefined;
}

export type ActivityKind =
  | "expense_added"
  | "expense_edited"
  | "expense_deleted"
  | "payment_recorded"
  | "member_joined"
  | "member_left"
  | "group_created";

export interface ActivityEvent {
  id: string;
  groupId: string;
  kind: ActivityKind;
  actorUserId: string;
  summary: string;
  amountCents?: number | undefined;
  at: string;
}

export interface GroupBalances {
  /** userId -> net cents (positive = owed money). */
  net: Record<string, number>;
  pairwise: { fromUserId: string; toUserId: string; amountCents: number }[];
  settlement: { fromUserId: string; toUserId: string; amountCents: number }[];
}

export interface NewExpenseInput {
  groupId: string;
  description: string;
  amountCents: number;
  date: string;
  category: string | null;
  splitType: SplitType;
  payers: Payer[];
  participantIds: string[];
  values?: Record<string, number> | undefined;
  items?: ItemizedLine[] | undefined;
  extraCents?: number | undefined;
}
