"use client";

import { useParams, usePathname, useRouter } from "next/navigation";
import { createContext, type ReactNode, useContext, useEffect, useState } from "react";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { AppShell } from "./app-shell";
import { BareHeader } from "./bare-header";
import { ServicesChip } from "./services-chip";

type Project = components["schemas"]["ProjectOut"];
type Loaded = { scope: string; email: string; projects: Project[] };

const SessionContext = createContext<{ email: string; projects: Project[]; loading: boolean } | null>(null);

/** The signed-in account and its projects, from the one load the (app) layout makes. */
export function useAppSession() {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useAppSession needs the (app) layout");
  return session;
}

/**
 * The (app) layout's client half: loads the session once, draws the shell around every page in
 * the group, and shares the result with them. It reloads exactly where the pages it replaces
 * did: when the projects list is entered, and when a project is entered from outside one.
 * Moving between a project's own pages, or between projects, reuses the load.
 */
export function AppFrame({ children }: { children: ReactNode }) {
  const { projectId } = useParams<{ projectId?: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const [state, setState] = useState<Loaded | "error" | null>(null);
  const scope = projectId ? "project" : pathname;

  useEffect(() => {
    let cancelled = false;
    // A 401 that a refresh can't fix never resolves here: the client redirects to /login.
    Promise.all([api.GET("/auth/me"), api.GET("/projects")])
      .then(([me, projects]) => {
        if (!cancelled) setState(me.data && projects.data ? { scope, email: me.data.email, projects: projects.data } : "error");
      })
      .catch(() => {
        if (!cancelled) setState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [scope]);

  if (state === null) {
    return (
      <div className="flex flex-1 flex-col">
        {/* The chip is here so a cold start shows "Waking" in the place it will stay. */}
        <div className="flex h-56 items-center justify-between gap-12 border-b border-hairline-strong px-16 tablet:px-24">
          <Skeleton className="h-24 w-160" />
          <ServicesChip />
        </div>
        <div className="p-16 tablet:p-32">
          <Skeleton className="h-32 w-160" />
          <Skeleton className="mt-20 h-120" />
        </div>
      </div>
    );
  }

  if (state === "error") {
    return (
      <main className="flex flex-1 flex-col">
        <BareHeader />
        <EmptyState title="Couldn't load your projects" description="Check your connection and reload the page." />
      </main>
    );
  }

  async function signOut() {
    await api.POST("/auth/logout");
    // A full load, not router.push: nothing from the old session survives in memory.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/login");
  }

  return (
    <SessionContext value={{ email: state.email, projects: state.projects, loading: state.scope !== scope }}>
      <AppShell
        projects={state.projects}
        projectId={projectId}
        email={state.email}
        pathname={pathname}
        onProjectChange={(id) => router.push(`/projects/${id}`)}
        onSignOut={signOut}
      >
        {children}
      </AppShell>
    </SessionContext>
  );
}
