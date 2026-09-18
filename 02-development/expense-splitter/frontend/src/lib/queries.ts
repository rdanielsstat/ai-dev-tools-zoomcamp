import { queryOptions } from "@tanstack/react-query";
import { api } from "./api";

export const meQuery = queryOptions({
  queryKey: ["me"],
  queryFn: () => api.getCurrentUser(),
});

export const groupsQuery = queryOptions({
  queryKey: ["groups"],
  queryFn: () => api.listGroups(),
});

export const groupQuery = (groupId: string) =>
  queryOptions({
    queryKey: ["group", groupId],
    queryFn: () => api.getGroup(groupId),
  });

export const expensesQuery = (groupId: string) =>
  queryOptions({
    queryKey: ["expenses", groupId],
    queryFn: () => api.listExpenses(groupId),
  });

export const balancesQuery = (groupId: string) =>
  queryOptions({
    queryKey: ["balances", groupId],
    queryFn: () => api.getBalances(groupId),
  });

export const activityQuery = (groupId: string) =>
  queryOptions({
    queryKey: ["activity", groupId],
    queryFn: () => api.listActivity(groupId),
  });
