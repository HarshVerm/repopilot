"use client";

import type { ReactNode } from "react";
import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { Footer } from "./footer";
import { Sidebar } from "./sidebar";
import { getCurrentUser, logout } from "@/lib/api/auth";
import { queryKeys } from "@/lib/query-client";
import { isApiError } from "@/lib/api/client";
import { ErrorState } from "@/components/shared/error-state";
import { LoadingState } from "@/components/shared/loading-state";

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const isPublicRoute = pathname === "/login";
  const userQuery = useQuery({
    queryKey: queryKeys.currentUser,
    queryFn: ({ signal }) => getCurrentUser(signal),
    enabled: !isPublicRoute,
    retry: false,
    staleTime: 60_000,
  });
  const logoutMutation = useMutation({
    mutationFn: logout,
    onSuccess: () => {
      queryClient.clear();
      router.replace("/login");
    },
  });

  useEffect(() => {
    if (
      !isPublicRoute &&
      userQuery.isError &&
      isApiError(userQuery.error) &&
      userQuery.error.status === 401
    ) {
      router.replace("/login");
    }
  }, [isPublicRoute, router, userQuery.error, userQuery.isError]);

  if (isPublicRoute) {
    return children;
  }

  if (userQuery.isPending) {
    return (
      <div className="min-h-screen bg-[#0D1117] p-8 text-[#dae3ee]">
        <LoadingState title="Loading RepoPilot session" rows={3} />
      </div>
    );
  }

  if (userQuery.isError) {
    if (isApiError(userQuery.error) && userQuery.error.status === 401) {
      return null;
    }
    return (
      <div className="min-h-screen bg-[#0D1117] p-8 text-[#dae3ee]">
        <ErrorState error={userQuery.error} onRetry={() => userQuery.refetch()} />
      </div>
    );
  }

  return (
    <div className="h-screen w-screen overflow-hidden bg-[#0D1117] text-[#dae3ee]">
      <Sidebar
        user={userQuery.data}
        onOpenCreateTask={() => router.push("/tasks/new")}
        onLogout={() => logoutMutation.mutate()}
        isLoggingOut={logoutMutation.isPending}
      />
      <div className="flex h-full flex-col overflow-hidden pl-16 lg:pl-64">
        {logoutMutation.isError ? (
          <div
            role="alert"
            className="fixed right-4 top-4 z-[80] rounded-lg border border-rose-400/30 bg-rose-950 px-4 py-3 text-sm text-rose-100 shadow-xl"
          >
            Sign out failed. Please try again.
          </div>
        ) : null}
        <main className="flex min-h-0 flex-1 flex-col overflow-hidden pb-8">{children}</main>
        <Footer />
      </div>
    </div>
  );
}
