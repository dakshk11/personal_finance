"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { BrandLink } from "@/components/AppHeader";

export default function SignupPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/dashboard");
  }, [router]);

  return (
    <main className="auth-page">
      <section className="auth-card">
        <BrandLink />
        <h1>Signup disabled</h1>
        <p>The app is using the local demo workspace for now.</p>
        <Link className="primary-button" href="/dashboard">Open dashboard <ArrowRight size={16} /></Link>
      </section>
    </main>
  );
}
