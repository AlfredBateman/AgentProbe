export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 px-5">
      <h1 className="font-display text-[32px] leading-[1.13] font-medium tracking-[-1px]">AgentProbe</h1>
      <p className="text-ink-muted">Statistically-corrected regression detection for LLM agents, gated in CI.</p>
    </main>
  );
}
