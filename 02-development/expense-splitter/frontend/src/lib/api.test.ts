import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "./api";

// `api` now talks to the real FastAPI backend over HTTP (see ../../../openapi.yaml
// and ../../../backend). Endpoint behavior itself is covered by the backend's
// own pytest suite; these tests cover this module's HTTP plumbing — request
// shape, auth header/token handling, and error mapping — against a mocked
// fetch, so they run fast with no server needed.

function jsonResponse(status: number, body: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const fetchMock = vi.fn<typeof fetch>();

/** Node has no DOM, so stub the bits of localStorage api.ts relies on. */
function createMemoryStorage(): Storage {
  const data = new Map<string, string>();
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => void data.set(key, value),
    removeItem: (key) => void data.delete(key),
    clear: () => data.clear(),
    key: (index) => Array.from(data.keys())[index] ?? null,
    get length() {
      return data.size;
    },
  };
}

let localStorage: Storage;

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  localStorage = createMemoryStorage();
  vi.stubGlobal("localStorage", localStorage);
  fetchMock.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("request URL and headers", () => {
  it("hits the configured API base URL with a JSON content type", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, []));
    await api.listGroups();
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("http://localhost:8000/api/groups");
    expect((init!.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });

  it("omits the Authorization header when signed out", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, []));
    await api.listGroups();
    const [, init] = fetchMock.mock.calls[0]!;
    expect((init!.headers as Record<string, string>)["Authorization"]).toBeUndefined();
  });

  it("attaches the bearer token after signing in", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        token: "tok_123",
        user: { id: "u1", name: "Mara", email: "mara@even.app", avatarInitials: "MA" },
      }),
    );
    await api.signIn("mara@even.app", "hunter22");

    fetchMock.mockResolvedValueOnce(jsonResponse(200, []));
    await api.listGroups();
    const [, init] = fetchMock.mock.calls[1]!;
    expect((init!.headers as Record<string, string>)["Authorization"]).toBe("Bearer tok_123");
  });
});

describe("auth flows", () => {
  it("signUp stores the returned token and returns the user", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(201, {
        token: "tok_abc",
        user: { id: "u1", name: "Mara", email: "mara@even.app", avatarInitials: "MA" },
      }),
    );
    const user = await api.signUp("Mara", "mara@even.app", "hunter22");
    expect(user.email).toBe("mara@even.app");
    expect(localStorage.getItem("even.token")).toBe("tok_abc");
  });

  it("getCurrentUser returns null without a stored token, making no request", async () => {
    const user = await api.getCurrentUser();
    expect(user).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("getCurrentUser clears the token and returns null on a 401", async () => {
    localStorage.setItem("even.token", "stale-token");
    fetchMock.mockResolvedValue(jsonResponse(401, { detail: "Invalid or expired token." }));
    const user = await api.getCurrentUser();
    expect(user).toBeNull();
    expect(localStorage.getItem("even.token")).toBeNull();
  });

  it("signOut clears the token even if the request fails", async () => {
    localStorage.setItem("even.token", "tok_1");
    fetchMock.mockResolvedValue(jsonResponse(500, { detail: "boom" }));
    await expect(api.signOut()).rejects.toThrow();
    expect(localStorage.getItem("even.token")).toBeNull();
  });
});

describe("error mapping", () => {
  it("surfaces the backend's detail message", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(400, { detail: "Settle up before leaving this group." }),
    );
    await expect(api.leaveGroup("g1")).rejects.toThrow("Settle up before leaving this group.");
  });

  it("throws an ApiError carrying the status code", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(403, { detail: "Only an admin can perform this action." }),
    );
    await expect(api.deleteGroup("g1")).rejects.toBeInstanceOf(ApiError);
  });

  it("getGroup maps a 404 to null instead of throwing", async () => {
    fetchMock.mockResolvedValue(jsonResponse(404, { detail: "Group not found." }));
    expect(await api.getGroup("nope")).toBeNull();
  });

  it("reports a clear error when the server is unreachable", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(api.listGroups()).rejects.toThrow(/reach the server/i);
  });

  it("treats a 204 response as a void success", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(api.leaveGroup("g1")).resolves.toBeUndefined();
  });
});

describe("request bodies", () => {
  it("addExpense posts to the group's expenses endpoint with the input as the body", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(201, {
        id: "e1",
        groupId: "g1",
        description: "Coffee",
        amountCents: 500,
        date: "2026-01-01",
        category: null,
        splitType: "equal",
        payers: [{ userId: "u1", amountCents: 500 }],
        shares: { u1: 500 },
        createdBy: "u1",
      }),
    );
    const input = {
      groupId: "g1",
      description: "Coffee",
      amountCents: 500,
      date: "2026-01-01",
      category: null,
      splitType: "equal" as const,
      payers: [{ userId: "u1", amountCents: 500 }],
      participantIds: ["u1"],
    };
    await api.addExpense(input);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(String(url)).toBe("http://localhost:8000/api/groups/g1/expenses");
    expect(init!.method).toBe("POST");
    expect(JSON.parse(init!.body as string)).toEqual(input);
  });
});
