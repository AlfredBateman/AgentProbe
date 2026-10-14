"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import { useAppSession } from "@/components/shell/app-frame";
import { Button } from "@/components/ui/button";
import { type Column, DataTable } from "@/components/ui/data-table";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { FieldError, FormError, Input, Label, Textarea } from "@/components/ui/field";
import { api } from "@/lib/api/client";
import { apiErrorMessage, apiFieldErrors } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { useReveal, useStagger } from "@/lib/motion/hooks";
import { requiredError } from "@/lib/validators";

type Project = components["schemas"]["ProjectOut"];

const COLUMNS: Column<Project>[] = [
  {
    key: "name",
    header: "Name",
    value: (p) => p.name,
    render: (p) => (
      <Link href={`/projects/${p.id}`} className="text-ink underline decoration-hairline-strong underline-offset-4 hover:decoration-accent">
        {p.name}
      </Link>
    ),
  },
  {
    key: "description",
    header: "Description",
    value: (p) => p.description,
    render: (p) => <span className="block max-w-[36ch] truncate text-ink-muted">{p.description ?? "—"}</span>,
    className: "hidden tablet:table-cell",
  },
  // The first segment of the uuid: enough to tell two projects with one name apart.
  {
    key: "id",
    header: "Id",
    render: (p) => <span className="text-ink-muted">{p.id.slice(0, 8)}</span>,
    className: "hidden desktop:table-cell",
  },
];

export default function ProjectsPage() {
  const router = useRouter();
  const { projects, loading } = useAppSession();
  const [dialogOpen, setDialogOpen] = useState(false);
  const headerRef = useRef<HTMLElement>(null);
  useReveal(headerRef);

  return (
    <>
      <header ref={headerRef} className="flex flex-wrap items-end justify-between gap-16 border-b border-hairline-strong pb-16">
        <div>
          <p className="type-micro text-ink-muted">
            [ Workspace ] <span aria-hidden>{"///"}</span> {loading ? "Loading" : `${projects.length} ${projects.length === 1 ? "project" : "projects"}`}
          </p>
          <h1 className="mt-8 type-display-md">Projects</h1>
        </div>
        {!loading && projects.length > 0 && <Button onClick={() => setDialogOpen(true)}>New project</Button>}
      </header>

      <div className="mt-24">
        {loading ? (
          <Skeleton className="h-160" />
        ) : projects.length === 0 ? (
          <div className="border border-hairline-strong">
            <EmptyState
              title="No projects yet"
              description="A project holds your agents, suites and runs."
              action={<Button onClick={() => setDialogOpen(true)}>New project</Button>}
            />
          </div>
        ) : (
          <ProjectsTable projects={projects} />
        )}
      </div>

      <CreateProjectDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onCreated={(project) => {
          setDialogOpen(false);
          router.push(`/projects/${project.id}`);
        }}
      />
    </>
  );
}

function ProjectsTable({ projects }: { projects: Project[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useStagger(ref, "tbody tr");
  return (
    <div ref={ref} className="border border-hairline-strong">
      <DataTable columns={COLUMNS} rows={projects} rowKey={(p) => p.id} caption="Projects" initialSort={{ key: "name", direction: "ascending" }} />
    </div>
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
      <form id="create-project" className="flex flex-col gap-16 text-left" onSubmit={onSubmit} noValidate>
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
          <Label htmlFor="project-description" caption="Optional">
            Description
          </Label>
          <Textarea id="project-description" value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
        <FormError id="create-project-error">{errors.form}</FormError>
      </form>
    </Dialog>
  );
}
