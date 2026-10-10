import { Button } from "@/components/ui";

export default function NotFound() {
  return (
    <div className="stage-duel grain flex min-h-[70dvh] flex-col items-center justify-center gap-4 px-6 text-center">
      <p className="font-mono text-[12px] font-bold tracking-[0.2em] text-faint">404 · NO CONTEST</p>
      <h1 className="font-display text-[clamp(2.4rem,8vw,4.5rem)] font-extrabold leading-[0.9]">This corner is empty.</h1>
      <p className="max-w-md text-dim">The page you&apos;re looking for doesn&apos;t exist, or the debate was removed.</p>
      <div className="mt-2 flex gap-3">
        <Button href="/" variant="primary">Back to the arena</Button>
        <Button href="/new" variant="for">Start a debate</Button>
      </div>
    </div>
  );
}
