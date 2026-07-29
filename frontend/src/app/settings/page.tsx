import { Suspense } from "react";
import { SettingsView } from "@/components/settings/settings-view";

export default function SettingsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex-1 bg-[#0D1117] p-6 text-sm text-zinc-400">
          Loading GitHub settings…
        </div>
      }
    >
      <SettingsView />
    </Suspense>
  );
}
