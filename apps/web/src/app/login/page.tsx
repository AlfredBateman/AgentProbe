"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";
import { BareHeader } from "@/components/shell/bare-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { FieldError, Input, Label } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/feedback";
import { api } from "@/lib/api/client";
import { apiErrorMessage, apiFieldErrors } from "@/lib/api/errors";
import { safeNext } from "@/lib/safe-next";
import { emailError, loginPasswordError } from "@/lib/validators";

type Errors = { email?: string; password?: string; form?: string };

function LoginForm() {
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  const [checkingSession, setCheckingSession] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<Errors>({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // A link from another site (our main use case: a dashboard link in a GitHub PR comment)
    // arrives with no SameSite=Strict refresh cookie on that first cross-site navigation. Try
    // one refresh — same-site once this page's own script runs it — before asking to sign in
    // again (ADR 0029 known limit).
    api.POST("/auth/refresh").then(({ response }) => {
      if (cancelled) return;
      if (response.ok) router.replace(next);
      else setCheckingSession(false);
    });
    return () => {
      cancelled = true;
    };
  }, [next, router]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const fieldErrors: Errors = {
      email: emailError(email) ?? undefined,
      password: loginPasswordError(password) ?? undefined,
    };
    if (fieldErrors.email || fieldErrors.password) {
      setErrors(fieldErrors);
      return;
    }
    setErrors({});
    setSubmitting(true);
    const { error, response } = await api.POST("/auth/login", { body: { email, password } });
    setSubmitting(false);
    if (!error) {
      router.replace(next);
      return;
    }
    if (response.status === 422) {
      setErrors(apiFieldErrors(error));
      return;
    }
    if (response.status === 429) {
      const retryAfter = response.headers.get("retry-after");
      setErrors({ form: retryAfter ? `Too many attempts. Try again in ${retryAfter}s.` : apiErrorMessage(error) });
      return;
    }
    setErrors({ form: apiErrorMessage(error) });
  }

  if (checkingSession) {
    return (
      <Card className="w-full max-w-400">
        <Skeleton className="h-24 w-120" />
        <Skeleton className="mt-20 h-44" />
        <Skeleton className="mt-12 h-44" />
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-400">
      <h1 className="font-display text-dash-heading">Sign in</h1>
      <form className="mt-20 flex flex-col gap-15" onSubmit={onSubmit} noValidate>
        <div className="flex flex-col gap-6">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={!!errors.email}
            aria-describedby={errors.email ? "email-error" : undefined}
          />
          <FieldError id="email-error">{errors.email}</FieldError>
        </div>
        <div className="flex flex-col gap-6">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={!!errors.password}
            aria-describedby={errors.password ? "password-error" : undefined}
          />
          <FieldError id="password-error">{errors.password}</FieldError>
        </div>
        <FieldError id="form-error">{errors.form}</FieldError>
        <Button type="submit" disabled={submitting}>
          {submitting ? "Signing in…" : "Sign in"}
        </Button>
      </form>
      <p className="mt-20 text-body-sm text-ink-muted">
        No account?{" "}
        <Link href={next === "/projects" ? "/register" : `/register?next=${encodeURIComponent(next)}`}>Register</Link>
      </p>
    </Card>
  );
}

export default function LoginPage() {
  return (
    <main className="flex flex-1 flex-col">
      <BareHeader />
      <div className="flex flex-1 items-center justify-center px-16 py-40">
        <Suspense fallback={<Skeleton className="h-260 w-full max-w-400" />}>
          <LoginForm />
        </Suspense>
      </div>
    </main>
  );
}
