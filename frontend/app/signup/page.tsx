"use client";

import { ArrowRight, UserPlus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { apiFetch } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      await apiFetch("/auth/signup", {
        method: "POST",
        body: JSON.stringify({ email, password })
      });
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <Link href="/" className="brand">
          <span className="brand-mark">D</span>
          <span>DirectIndex</span>
        </Link>
        <h1>Create account</h1>
        <p>Passwords are hashed in the backend and never stored in the browser.</p>
        <form className="form-stack" onSubmit={submit}>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input id="email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={12}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="12+ characters with letters and numbers"
            />
          </div>
          {error ? <div className="error">{error}</div> : null}
          <div className="form-actions">
            <button className="primary-button" disabled={loading} type="submit"><UserPlus size={16} /> {loading ? "Creating" : "Create account"}</button>
            <Link className="ghost-button" href="/login">Log in <ArrowRight size={16} /></Link>
          </div>
        </form>
        <p className="fine-print">Use a local development password. Rotate secrets before deploying.</p>
      </section>
    </main>
  );
}

