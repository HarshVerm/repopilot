import { LoadingState } from "@/components/shared/loading-state";

export default function SettingsLoading() {
  return (
    <div className="p-6">
      <LoadingState title="Loading settings" rows={3} />
    </div>
  );
}
