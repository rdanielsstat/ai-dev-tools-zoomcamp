# Even — Expense Splitter Specification

## 1. Overview

**Even** is a multi-user web application for splitting shared expenses. It serves
two situations: one-off events (a trip, a group dinner) that get settled once,
and ongoing shared costs (roommates, couples) tracked continuously. Users create
groups, log expenses with flexible split rules, and the app tracks who owes whom.
When it's time to settle, Even computes the smallest set of payments that clears
all debts.

The goal, and the name, is to get everyone *even*.

## 2. Goals and non-goals

### Goals
- Let people track shared spending accurately across a group.
- Support the real ways groups split costs (not just equal shares).
- Minimize the friction of settling up by simplifying debts.
- Work for both a weekend trip and a year-long roommate arrangement.

### Non-goals (v1)
- Actually moving money (no payment processing / bank integration). Even records
  that a payment happened; it does not execute it.
- Multi-currency, receipt OCR, and recurring expenses are deferred to future work.
- Social features beyond a group activity feed (no comments, reactions, chat).
- Native mobile apps. The web UI should be responsive, but native is out of scope.

## 3. Users and roles

- **User**: an authenticated account (email + password). Has a name, email, and an
  optional avatar.
- **Group member**: a user's membership in a group. All members can add and edit
  expenses and record payments.
- **Group creator / admin**: the user who created a group. Can rename it, manage
  membership, and delete the group. (A single admin role is enough for v1.)

## 4. Core concepts / data model

- **User** — account, name, email, password hash, avatar.
- **Group** — name, description, members, created-by, created-at.
- **Membership** — links a user to a group, with role (member/admin) and join date.
- **Expense** — belongs to a group. Has a description, total amount, the payer(s),
  a date, a category (optional), a split type, and the resulting per-person shares.
- **Split** — the per-person breakdown of one expense: for each participant, the
  amount they owe for that expense.
- **Payment (settlement)** — a record that one user paid another user some amount
  on a date. Reduces the balance between them.
- **Activity event** — an append-only log entry (expense added/edited/deleted,
  payment recorded, member joined, etc.) shown in the group feed.

## 5. Functional requirements

### 5.1 Accounts and auth
- Sign up with email + password; log in; log out.
- Passwords stored hashed (never plaintext).
- Session or token-based auth; protected endpoints require authentication.
- A user can view and edit their own profile.

### 5.2 Groups
- Create a group with a name.
- Invite / add other users to a group (by email or invite link).
- View all groups the user belongs to.
- Leave a group (only when the user's balance in it is zero).
- Admin can rename or delete a group.

### 5.3 Expenses
- Add an expense to a group: description, amount, date, who paid, split rule, and
  participants.
- Edit or delete an expense (recorded in the activity feed).
- Support one or multiple payers for a single expense.
- View a group's expenses, filterable by date, member, or category.

### 5.4 Split types
The app must support all of the following for any expense:
1. **Equal** — divide evenly among selected participants.
2. **Exact amounts** — each participant owes a specified amount; must sum to total.
3. **Percentages** — each participant owes a percentage; must sum to 100%.
4. **Shares** — each participant is assigned a weight (e.g. A=2, B=1); the total
   is divided in proportion to weights.
5. **Itemized** — assign specific line items to specific people; shared items can
   be split among a subset. Tax and tip distributed proportionally.

Rounding must be handled so the shares always sum exactly to the total (no lost or
extra cents).

### 5.5 Balances and debt simplification
- For any group, compute each member's net balance (positive = owed money,
  negative = owes money).
- **Debt simplification**: given all net balances, produce the minimum number of
  payments that settles the group. This is the headline feature — instead of a
  tangle of IOUs, show "Alice pays Bob $20; Carol pays Bob $15."
- Show both the raw pairwise balances and the simplified settlement plan.

### 5.6 Settling up
- Record a payment from one member to another (amount, date).
- Recording a payment updates balances and appears in the activity feed.
- Mark a suggested settlement as done, which records the corresponding payment.

### 5.7 Activity feed
- Per-group chronological feed of events: expenses added/edited/deleted, payments
  recorded, members joined/left.
- Each entry shows who did what and when.

## 6. Non-functional requirements

- **Correctness**: money math must be exact. Use integer minor units (cents) or a
  decimal type; never binary floats for currency. Splits always reconcile to the
  total.
- **Security**: hashed passwords, authenticated + authorized access (a user only
  sees groups they belong to), input validation, no secrets in the repo.
- **Usability**: responsive web UI; the main flows (add expense, see balances,
  settle up) reachable in a few clicks.
- **Testability**: business logic (splitting, simplification) covered by unit
  tests. API endpoints covered by tests.
- **Portability**: database-agnostic persistence layer (via an ORM) so the store
  can be swapped without rewriting business logic.

## 7. Architecture (intended)

- **Frontend**: single-page web app. All backend calls centralized in one module
  so they can be mocked first and pointed at the real API later.
- **Backend**: REST API defined by an OpenAPI schema. Handles auth, groups,
  expenses, splitting, simplification.
- **Database**: accessed through an ORM (SQLAlchemy) to stay database-agnostic;
  begins as a mock/in-memory store, later replaced with a real relational DB.

## 8. Key algorithms

### 8.1 Splitting with exact reconciliation
Compute each participant's share per the split type in integer minor units.
Distribute any rounding remainder deterministically (e.g. cents go to the first
N participants) so the sum of shares equals the total exactly.

### 8.2 Debt simplification
Reduce a set of net balances to a minimal set of transfers:
1. Compute each member's net balance across all expenses and payments.
2. Separate into creditors (positive) and debtors (negative).
3. Greedily match the largest debtor against the largest creditor, emitting a
   payment for the smaller of the two magnitudes, until all balances are zero.
This yields at most (n - 1) transactions for n members and is a strong, visible
demonstration of the app's value.

## 9. Primary user flows

1. **Onboard**: sign up -> create a group -> add members.
2. **Log an expense**: pick group -> enter amount/payer -> choose split type ->
   assign participants -> save. Balances update.
3. **Check standing**: open group -> see net balances and the simplified plan.
4. **Settle up**: tap a suggested payment -> confirm it happened -> balances clear.

## 10. Success criteria

- A group of several people can log mixed-type expenses and always see balances
  that reconcile to the penny.
- The settlement plan never uses more than (n - 1) payments and clears the group.
- All money-logic and API tests pass.

## 11. Future work (out of scope for v1)

- **Multi-currency** with per-expense currencies, a group base currency, live
  exchange rates, and stored historical rates.
- **Receipt upload and OCR** to auto-populate itemized splits.
- **Recurring expenses** generated on a schedule (e.g. monthly rent).
- Real payment execution (Venmo/PayPal/bank links).
- Budgets and spending analytics.
- Comments and reactions on expenses.
- Native mobile apps and offline mode.
