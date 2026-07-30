"use client";

// Module purpose: Render and coordinate the login view interface.

import { AlertTriangle, Github, Terminal } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { githubLoginUrl } from "@/lib/api/auth";

/** Purpose: Render the login view interface. */
export function LoginView() {
  const searchParams = useSearchParams();
  const authNotConfigured =
    searchParams.get("error") === "github-auth-not-configured";

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#0D1117] px-6 text-[#dae3ee]">
      <section className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-blue-400/30 bg-blue-500/10">
            <Terminal className="h-4 w-4 text-blue-300" />
          </div>
          <span className="text-lg font-bold tracking-tight">RepoPilot</span>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight text-white">
          Engineering work starts with an issue.
        </h1>
        <p className="mt-3 text-sm leading-6 text-zinc-400">
          Sign in to select an authorized repository, run the coding agent, and
          review the exact verified diff before RepoPilot opens a pull request.
        </p>
        {authNotConfigured ? (
          <div
            role="alert"
            className="mt-6 flex gap-3 rounded-lg border border-amber-400/25 bg-amber-500/10 p-4 text-amber-100"
          >
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
            <div>
              <p className="text-sm font-semibold">
                GitHub sign-in is not configured
              </p>
              <p className="mt-1 text-xs leading-5 text-amber-100/70">
                Add the GitHub App client ID and client secret to the root
                .env file, then restart the backend.
              </p>
            </div>
          </div>
        ) : null}
        <a
          href={githubLoginUrl()}
          className="mt-6 flex w-full items-center justify-center gap-2 rounded-lg border border-[#3F3F46] bg-[#FAFAFA] px-4 py-2.5 text-sm font-semibold text-[#18181B] transition-colors hover:bg-zinc-200 focus:outline-none focus:ring-2 focus:ring-blue-400"
        >
          <Github className="h-4 w-4" />
          Continue with GitHub
        </a>
        <p className="mt-4 text-xs leading-5 text-zinc-500">
          Repository access is granted separately through the RepoPilot GitHub
          App. Tokens and App credentials are never stored in browser storage.
        </p>
      </section>
    </main>
  );
}
