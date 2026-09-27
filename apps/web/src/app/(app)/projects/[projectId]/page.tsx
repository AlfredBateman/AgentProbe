import { EmptyState } from "@/components/ui/feedback";

export default function ProjectOverview() {
  return (
    <>
      <h1 className="font-display text-dash-title-sm tablet:text-dash-title">Overview</h1>
      <EmptyState title="No runs yet" description="Runs you start from a suite, or push from CI, show up here." />
    </>
  );
}
