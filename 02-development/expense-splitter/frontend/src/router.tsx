import { QueryClient } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";
import { ApiError } from "./lib/api";
import { routeTree } from "./routeTree.gen";

export const getRouter = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        // A 401 means "not signed in" or "session expired" — retrying
        // won't fix that, and it turns one redirect into a burst of
        // requests. Other failures still get the default 3 retries.
        retry: (failureCount, error) =>
          error instanceof ApiError && error.status === 401 ? false : failureCount < 3,
      },
    },
  });

  const router = createRouter({
    routeTree,
    context: { queryClient },
    scrollRestoration: true,
    defaultPreloadStaleTime: 0,
  });

  return router;
};
