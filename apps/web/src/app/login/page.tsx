"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";
import { AuthFrame } from "@/components/shell/auth-frame";
import { Button } from "@/components/ui/button";
import { FieldError, FormError, Input, Label } from "@/components/ui/field";
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
      <div aria-hidden>
        <Skeleton className="h-40" />
        <Skeleton className="mt-16 h-40" />
        <Skeleton className="mt-16 h-40" />
      </div>
    );
  }

  return (
    <>
      <form className="flex flex-col gap-16" onSubmit={onSubmit} noValidate>
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
        <FormError id="form-error">{errors.form}</FormError>
        <Button type="submit" disabled={submitting}>
          {submitting ? "Signing in…" : "Sign in"}
        </Button>
      </form>
      <p className="mt-24 border-t border-hairline pt-16 type-body-sm text-ink-muted">
        No account?{" "}
        <Link href={next === "/projects" ? "/register" : `/register?next=${encodeURIComponent(next)}`} className="tap underline underline-offset-4">
          Register
        </Link>
      </p>
    </>
  );
}

export default function LoginPage() {
  return (
    <AuthFrame
      eyebrow="[ Access ]"
      headline={
        <>
          Sign <span className="text-outline">in</span>
        </>
      }
      lede="Use the account you registered with. It opens your projects, suites and runs."
      panelTitle="Credentials"
    >
      <Suspense fallback={<Skeleton className="h-160" />}>
        <LoginForm />
      </Suspense>
    </AuthFrame>
  );
}
