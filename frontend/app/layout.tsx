import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DirectIndex",
  description: "Simulation-only direct indexing and tax-loss harvesting dashboard"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

