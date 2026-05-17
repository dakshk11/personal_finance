"use client";

import { LogIn } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { apiFetch } from "@/lib/api";

export default function LoginPage() {
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
      await apiFetch("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password })
      });
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
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
        <h1>Log in</h1>
        <p>Access portfolio simulations, backtests, and trade recommendations.</p>
        <form className="form-stack" onSubmit={submit}>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input id="email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input id="password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} />
          </div>
          {error ? <div className="error">{error}</div> : null}
          <div className="form-actions">
            <button className="primary-button" disabled={loading} type="submit"><LogIn size={16} /> {loading ? "Logging in" : "Log in"}</button>
            <Link className="ghost-button" href="/signup">Create account</Link>
          </div>
        </form>
        <p className="fine-print">Local test account: test@gmail.com / 1234. Simulation-only. No live trading or tax advice.</p>
      </section>
    </main>
  );
}
