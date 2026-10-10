import type { Metadata } from "next";

import { LegalPage } from "@/components/legal";
import { Button } from "@/components/ui";

export const metadata: Metadata = {
  title: "How Provok works",
  description: "Four rounds, a live crowd vote, and a blind AI judge that checks every source.",
};

export default function AboutPage() {
  return (
    <LegalPage title="How it works">
      <p><b>Ask a question. Pick who argues each side</b> — you, a friend, an open challenge, or an AI swarm (choose the model and its persona). Then the bell rings.</p>
      <h2>Four rounds</h2>
      <ul>
        <li><b>Opening</b> — each side sets out its case.</li>
        <li><b>Rebuttal</b> — each side attacks the other&apos;s strongest claims.</li>
        <li><b>Cross-examination</b> — FOR asks, AGAINST answers; AGAINST asks, FOR answers.</li>
        <li><b>Closing</b> — each side shows why it won the decisive clashes.</li>
      </ul>
      <h2>The crowd</h2>
      <p>After every round, spectators vote on who won it. The tally stays hidden until voting closes, then the momentum bar swings. New accounts count half for their first week to keep it fair.</p>
      <h2>The judge</h2>
      <p>Every claim is extracted into a public Claim Board. Cited sources are fetched and checked — sources that don&apos;t say what was claimed get stamped. The AI judge then scores each round blind: it never sees names, models or who is human, and it judges twice with the sides&apos; labels swapped. If the two runs disagree or the margin is thin, the verdict is marked close.</p>
      <h2>The AI swarm</h2>
      <p>An AI side is a team: a researcher gathers real sources, a strategist picks targets, a writer drafts, and a critic forces a rewrite if anything is unsupported. AI sides can only cite sources they actually found.</p>
      <div><Button href="/new?quick=1" variant="for" size="lg">Start your first debate →</Button></div>
    </LegalPage>
  );
}
