"use client";

import { useParams, usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { AppShell, type ShellProject } from "@/components/shell/app-shell";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { api } from "@/lib/api/client";

type Session = { email: string; projects: ShellProject[] };

export default function ProjectLayout({ children }: { children: ReactNode }) {
  const { projectId } = useParams<{ projectId: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const [session, setSession] = useState<Session | "error" | null>(null);

  useEffect(() => {
    // A 401 that a refresh can't fix never resolves here: the client redirects to /login.
    Promise.all([api.GET("/auth/me"), api.GET("/projects")])
      .then(([me, projects]) =>
        setSession(me.data && projects.data ? { email: me.data.email, projects: projects.data } : "error"),
      )
      .catch(() => setSession("error"));
  }, []);

  if (session === null) return <Skeleton className="m-16 h-56" />;
  if (session === "error") return <EmptyState title="Couldn't load your projects" description="Check your connection and reload the page." />;

  async function signOut() {
    await api.POST("/auth/logout");
    // A full load, not router.push: nothing from the old session survives in memory.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/login");
  }

  return (
    <AppShell
      projects={session.projects}
      projectId={projectId}
      email={session.email}
      pathname={pathname}
      onProjectChange={(id) => router.push(`/projects/${id}`)}
      onSignOut={signOut}
    >
      {children}
    </AppShell>
  );
}
