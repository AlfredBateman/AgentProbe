"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { BareHeader } from "@/components/shell/bare-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { FieldError, Input, Label, Textarea } from "@/components/ui/field";
import { api } from "@/lib/api/client";
import { apiErrorMessage, apiFieldErrors } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { requiredError } from "@/lib/validators";

type Project = components["schemas"]["ProjectOut"];
type Session = { email: string; projects: Project[] };

export default function ProjectsPage() {
  const router = useRouter();
  const [session, setSession] = useState<Session | "error" | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const load = () =>
    Promise.all([api.GET("/auth/me"), api.GET("/projects")]).then(([me, projects]) =>
      setSession(me.data && projects.data ? { email: me.data.email, projects: projects.data } : "error"),
    );

  useEffect(() => {
    // A 401 that a refresh can't fix never resolves here: the client redirects to /login.
    load().catch(() => setSession("error"));
  }, []);

  async function signOut() {
    await api.POST("/auth/logout");
    // A full load, not router.push: nothing from the old session survives in memory.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/login");
  }

  function onCreated(project: Project) {
    setDialogOpen(false);
    router.push(`/projects/${project.id}`);
  }

  if (session === null) {
    return (
      <main className="flex flex-1 flex-col">
        <BareHeader />
        <div className="mx-auto w-full max-w-1440 flex-1 px-16 py-30 tablet:px-30">
          <Skeleton className="h-32 w-160" />
          <Skeleton className="mt-20 h-120" />
        </div>
      </main>
    );
  }

  if (session === "error") {
    return (
      <main className="flex flex-1 flex-col">
        <BareHeader />
        <EmptyState title="Couldn't load your projects" description="Check your connection and reload the page." />
      </main>
    );
  }

  return (
    <main className="flex flex-1 flex-col">
      <BareHeader
        right={
          <div className="flex items-center gap-12">
            <span className="hidden max-w-200 truncate text-ink-muted tablet:inline" title={session.email}>
              {session.email}
            </span>
            <Button variant="secondary" onClick={signOut} title={`Signed in as ${session.email}`}>
              Sign out
            </Button>
          </div>
        }
      />
      <div className="mx-auto w-full max-w-1440 flex-1 px-16 py-30 tablet:px-30">
        <div className="mb-20 flex flex-wrap items-center justify-between gap-12">
          <h1 className="font-display text-dash-title-sm tablet:text-dash-title">Projects</h1>
          {session.projects.length > 0 && <Button onClick={() => setDialogOpen(true)}>New project</Button>}
        </div>
        {session.projects.length === 0 ? (
          <EmptyState
            title="No projects yet"
            description="A project holds your agents, suites and runs."
            action={<Button onClick={() => setDialogOpen(true)}>New project</Button>}
          />
        ) : (
          <div className="grid grid-cols-1 gap-15 tablet:grid-cols-2 desktop:grid-cols-3">
            {session.projects.map((p) => (
              <Link key={p.id} href={`/projects/${p.id}`} className="rounded-xl outline-none focus-visible:shadow-focus">
                <Card className="h-full hover:bg-surface-2">
                  <h2 className="font-display text-dash-heading">{p.name}</h2>
                  {p.description && <p className="mt-6 line-clamp-2 text-body-sm text-ink-muted">{p.description}</p>}
                </Card>
              </Link>
            ))}
          </div>
        )}
      </div>
      <CreateProjectDialog open={dialogOpen} onClose={() => setDialogOpen(false)} onCreated={onCreated} />
    </main>
  );
}

function CreateProjectDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (project: Project) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [errors, setErrors] = useState<{ name?: string; form?: string }>({});
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const nameError = requiredError(name, "Name");
    if (nameError) {
      setErrors({ name: nameError });
      return;
    }
    setErrors({});
    setSubmitting(true);
    const { data, error, response } = await api.POST("/projects", {
      body: { name, description: description || null },
    });
    setSubmitting(false);
    if (data) {
      setName("");
      setDescription("");
      onCreated(data);
      return;
    }
    if (response.status === 422) {
      setErrors(apiFieldErrors(error));
      return;
    }
    setErrors({ form: apiErrorMessage(error) });
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="New project"
      actions={
        <>
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="create-project" disabled={submitting}>
            {submitting ? "Creating…" : "Create project"}
          </Button>
        </>
      }
    >
      <form id="create-project" className="flex flex-col gap-15 text-left" onSubmit={onSubmit} noValidate>
        <div className="flex flex-col gap-6">
          <Label htmlFor="project-name">Name</Label>
          <Input
            id="project-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-invalid={!!errors.name}
            aria-describedby={errors.name ? "project-name-error" : undefined}
          />
          <FieldError id="project-name-error">{errors.name}</FieldError>
        </div>
        <div className="flex flex-col gap-6">
          <Label htmlFor="project-description">Description (optional)</Label>
          <Textarea id="project-description" value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
        <FieldError id="create-project-error">{errors.form}</FieldError>
      </form>
    </Dialog>
  );
}
