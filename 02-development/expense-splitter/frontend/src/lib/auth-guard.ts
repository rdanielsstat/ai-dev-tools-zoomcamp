import type { QueryClient } from "@tanstack/react-query";
import { redirect } from "@tanstack/react-router";

import { meQuery } from "./queries";
import type { User } from "./types";

/** Call from a route's `beforeLoad` to keep signed-out visitors off protected pages. */
export async function requireAuth(queryClient: QueryClient): Promise<User> {
  const me = await queryClient.ensureQueryData(meQuery);
  if (!me) throw redirect({ to: "/auth" });
  return me;
}
