"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { AuthFrame } from "@/components/shell/auth-frame";
import { Button } from "@/components/ui/button";
import { FieldError, FormError, Input, Label } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/feedback";
import { api } from "@/lib/api/client";
import { apiErrorMessage, apiFieldErrors } from "@/lib/api/errors";
import { safeNext } from "@/lib/safe-next";
import { emailError, newPasswordError } from "@/lib/validators";

type Errors = { email?: string; password?: string; form?: string };

function RegisterForm() {
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<Errors>({});
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const fieldErrors: Errors = {
      email: emailError(email) ?? undefined,
      password: newPasswordError(password) ?? undefined,
    };
    if (fieldErrors.email || fieldErrors.password) {
      setErrors(fieldErrors);
      return;
    }
    setErrors({});
    setSubmitting(true);
    const { error, response } = await api.POST("/auth/register", { body: { email, password } });
    setSubmitting(false);
    if (!error) {
      // Registering also starts a session (agentprobe_api.auth.register), so there's nowhere
      // to sign in to afterward — go straight to the destination.
      router.replace(next);
      return;
    }
    if (response.status === 422) {
      setErrors(apiFieldErrors(error));
      return;
    }
    setErrors({ form: apiErrorMessage(error) });
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
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={!!errors.password}
            aria-describedby={errors.password ? "password-error" : "password-hint"}
          />
          {!errors.password && (
            <p id="password-hint" className="type-micro text-ink-muted">
              At least 12 characters.
            </p>
          )}
          <FieldError id="password-error">{errors.password}</FieldError>
        </div>
        <FormError id="form-error">{errors.form}</FormError>
        <Button type="submit" disabled={submitting}>
          {submitting ? "Creating account…" : "Create account"}
        </Button>
      </form>
      <p className="mt-24 border-t border-hairline pt-16 type-body-sm text-ink-muted">
        Already have an account?{" "}
        <Link href={next === "/projects" ? "/login" : `/login?next=${encodeURIComponent(next)}`}>Sign in</Link>
      </p>
    </>
  );
}

export default function RegisterPage() {
  return (
    <AuthFrame
      eyebrow="[ New account ]"
      headline={
        <>
          Create <span className="text-outline">account</span>
        </>
      }
      lede="Registering also signs you in, so you go straight to your projects."
      panelTitle="New account"
    >
      <Suspense fallback={<Skeleton className="h-240" />}>
        <RegisterForm />
      </Suspense>
    </AuthFrame>
  );
}
