"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { useToast } from "@/components/toast";
import { Button, Empty, ErrorBlock, PageTitle, Spinner, Tabs } from "@/components/ui";
import { errorMessage, get, patch, post, put } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cx, timeAgo } from "@/lib/format";

type Tab = "reports" | "flagged" | "paused" | "flags" | "models" | "metrics" | "audit";

function useAct() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (body: { action: string; target_id: string; reason?: string; amount?: number }) => post("/admin/actions", body),
    onSuccess: () => {
      toast("Done.", "success");
      void qc.invalidateQueries({ queryKey: ["admin"] });
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
}

interface Report { id: string; target_type: string; target_id: string; reason: string; details: string | null; created_at: string; preview: Record<string, string> | null }

function Reports() {
  const act = useAct();
  const q = useQuery({ queryKey: ["admin", "reports"], queryFn: () => get<{ items: Report[] }>("/admin/reports?status=open") });
  if (q.isLoading) return <Spinner className="size-6" />;
  if (q.isError) return <ErrorBlock message={errorMessage(q.error)} />;
  if (!q.data?.items.length) return <Empty title="Queue is clear." />;
  return (
    <ul className="flex flex-col gap-3">
      {q.data.items.map((r) => (
        <li key={r.id} className="rounded-2xl border border-line bg-surface p-4">
          <div className="mb-2 flex flex-wrap items-center gap-2 text-[12px]">
            <span className="rounded-md bg-danger/15 px-2 py-0.5 font-mono font-bold text-danger">{r.reason}</span>
            <span className="font-mono text-faint">{r.target_type}</span>
            <span className="ml-auto text-faint">{timeAgo(r.created_at)}</span>
          </div>
          {r.preview && <p className="whitespace-pre-wrap text-sm">{r.preview.content ?? r.preview.question ?? `@${r.preview.username} (${r.preview.status})`}</p>}
          {r.details && <p className="mt-2 text-[13px] italic text-dim">“{r.details}”</p>}
          <div className="mt-3 flex flex-wrap gap-2">
            {r.target_type === "turn" && <Button size="sm" variant="danger" onClick={() => act.mutate({ action: "hide_turn", target_id: r.target_id })}>Hide turn</Button>}
            {r.target_type === "debate" && <Button size="sm" variant="danger" onClick={() => act.mutate({ action: "hide_debate", target_id: r.target_id })}>Hide debate</Button>}
            {r.target_type === "user" && <Button size="sm" variant="danger" onClick={() => act.mutate({ action: "ban_user", target_id: r.target_id })}>Ban user</Button>}
            {r.preview?.debate_id && <Button size="sm" variant="outline" href={`/d/${r.preview.debate_id}`}>Open debate</Button>}
            <Button size="sm" variant="outline" onClick={() => act.mutate({ action: "resolve_report", target_id: r.id })}>Resolve</Button>
            <Button size="sm" variant="ghost" onClick={() => act.mutate({ action: "dismiss_report", target_id: r.id })}>Dismiss</Button>
          </div>
        </li>
      ))}
    </ul>
  );
}

function Flagged() {
  const act = useAct();
  const q = useQuery({ queryKey: ["admin", "flagged"], queryFn: () => get<{ items: { id: string; debate_id: string; content: string; reason: string | null; injection_flag: boolean; created_at: string }[] }>("/admin/flagged-turns") });
  if (q.isLoading) return <Spinner className="size-6" />;
  if (!q.data?.items.length) return <Empty title="No flagged turns." />;
  return (
    <ul className="flex flex-col gap-3">
      {q.data.items.map((t) => (
        <li key={t.id} className="rounded-2xl border border-line bg-surface p-4">
          <p className="mb-2 font-mono text-[12px] text-danger">{t.reason}{t.injection_flag && " · injection"}</p>
          <p className="whitespace-pre-wrap text-sm">{t.content}</p>
          <div className="mt-3 flex gap-2">
            <Button size="sm" variant="outline" onClick={() => act.mutate({ action: "approve_turn", target_id: t.id })}>Approve</Button>
            <Button size="sm" variant="danger" onClick={() => act.mutate({ action: "hide_turn", target_id: t.id })}>Hide</Button>
            <Link href={`/d/${t.debate_id}`} className="self-center text-[13px] underline">Debate</Link>
          </div>
        </li>
      ))}
    </ul>
  );
}

function Paused() {
  const act = useAct();
  const q = useQuery({ queryKey: ["admin", "paused"], queryFn: () => get<{ items: { id: string; question: string; reason: string; paused_from: string; updated_at: string }[] }>("/admin/paused-debates") });
  if (q.isLoading) return <Spinner className="size-6" />;
  if (!q.data?.items.length) return <Empty title="Nothing paused." body="Debates pause when an AI model or the judge fails twice." />;
  return (
    <ul className="flex flex-col gap-3">
      {q.data.items.map((d) => (
        <li key={d.id} className="flex flex-col gap-2 rounded-2xl border border-line bg-surface p-4 sm:flex-row sm:items-center">
          <div className="flex-1"><Link href={`/d/${d.id}`} className="font-semibold hover:underline">{d.question}</Link>
            <p className="text-[12px] text-faint">{d.reason} · paused during {d.paused_from} · {timeAgo(d.updated_at)}</p></div>
          <Button size="sm" onClick={() => act.mutate({ action: "resume_debate", target_id: d.id })}>Resume</Button>
          <Button size="sm" variant="danger" onClick={() => act.mutate({ action: "cancel_debate", target_id: d.id })}>Cancel & refund</Button>
        </li>
      ))}
    </ul>
  );
}

function Flags() {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["admin", "flags"], queryFn: () => get<{ items: { key: string; enabled: boolean; reason: string | null }[] }>("/admin/flags") });
  return (
    <ul className="flex flex-col gap-2">
      {q.data?.items.map((f) => (
        <li key={f.key} className="flex items-center gap-4 rounded-2xl border border-line bg-surface px-4 py-3">
          <span className="flex-1"><span className="font-mono font-semibold">{f.key}</span>{f.reason && <span className="block text-[12px] text-faint">{f.reason}</span>}</span>
          <Button size="sm" variant={f.enabled ? "outline" : "for"} onClick={async () => {
            const reason = f.enabled ? window.prompt("Reason for disabling?") ?? "" : "";
            try {
              await put(`/admin/flags/${f.key}`, { enabled: !f.enabled, reason: reason || null });
              await qc.invalidateQueries({ queryKey: ["admin", "flags"] });
            } catch (e) {
              toast(errorMessage(e), "error");
            }
          }}>{f.enabled ? "Disable" : "Enable"}</Button>
        </li>
      ))}
    </ul>
  );
}

function Models() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin", "models"], queryFn: () => get<{ items: { key: string; litellm_id: string; display_name: string; provider: string; tier: string; enabled: boolean; selectable: boolean; rating: number }[] }>("/admin/models") });
  const toggle = async (key: string, body: Record<string, unknown>) => {
    await patch(`/admin/models/${key}`, body);
    await qc.invalidateQueries({ queryKey: ["admin", "models"] });
  };
  return (
    <div className="overflow-x-auto rounded-2xl border border-line">
      <table className="w-full min-w-[640px] text-sm">
        <thead className="bg-surface-2 text-left font-mono text-[11px] text-faint"><tr><th className="p-3">KEY</th><th>LITELLM ID</th><th>TIER</th><th>ELO</th><th>ENABLED</th><th>PICKER</th></tr></thead>
        <tbody>
          {q.data?.items.map((m) => (
            <tr key={m.key} className="border-t border-line">
              <td className="p-3 font-semibold">{m.display_name}<span className="block font-mono text-[11px] text-faint">{m.key}</span></td>
              <td className="font-mono text-[12px]">{m.litellm_id}</td>
              <td>{m.tier}</td>
              <td className="font-mono">{m.rating}</td>
              <td><input type="checkbox" checked={m.enabled} onChange={() => toggle(m.key, { enabled: !m.enabled })} aria-label={`Enable ${m.key}`} /></td>
              <td><input type="checkbox" checked={m.selectable} onChange={() => toggle(m.key, { selectable: !m.selectable })} aria-label={`Show ${m.key} in picker`} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface Metrics {
  completion_by_mode: { mode: string; timing: string; started: number; completed: number; completion_rate: number }[];
  avg_votes_per_completed_debate: number;
  second_debate_within_7d: { cohort: number; returned: number; rate: number };
  cost_per_completed_debate: { mode: string; debates: number; total_usd: number; per_debate_usd: number }[];
  free_to_paid: { exhausted_free: number; paid: number; rate: number };
  llm_spend_today_usd: number;
  users_total: number;
  active_last_24h: number;
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-2xl border border-line bg-surface p-4">
      <p className="font-mono text-[10.5px] font-bold tracking-[0.14em] text-faint">{label}</p>
      <p className="font-display mt-1 text-3xl font-extrabold tabular">{value}</p>
      {sub && <p className="text-[12px] text-dim">{sub}</p>}
    </div>
  );
}

function MetricsView() {
  const [days, setDays] = useState(30);
  const q = useQuery({ queryKey: ["admin", "metrics", days], queryFn: () => get<Metrics>(`/admin/metrics?days=${days}`) });
  const m = q.data;
  const pct = (n: number) => `${Math.round(n * 100)}%`;
  return (
    <div className="flex flex-col gap-5">
      <Tabs value={String(days)} onChange={(v) => setDays(Number(v))} items={[{ value: "7", label: "7d" }, { value: "30", label: "30d" }, { value: "90", label: "90d" }]} className="w-fit" />
      {!m ? <Spinner className="size-6" /> : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="USERS" value={String(m.users_total)} sub={`${m.active_last_24h} active in 24h`} />
            <Stat label="2ND DEBATE ≤7D" value={pct(m.second_debate_within_7d.rate)} sub={`${m.second_debate_within_7d.returned}/${m.second_debate_within_7d.cohort} new creators`} />
            <Stat label="VOTES / DEBATE" value={m.avg_votes_per_completed_debate.toFixed(1)} sub="completed debates" />
            <Stat label="FREE → PAID" value={pct(m.free_to_paid.rate)} sub={`${m.free_to_paid.paid}/${m.free_to_paid.exhausted_free} used up free`} />
            <Stat label="LLM SPEND TODAY" value={`$${m.llm_spend_today_usd.toFixed(2)}`} />
          </div>
          <div className="overflow-x-auto rounded-2xl border border-line">
            <table className="w-full min-w-[520px] text-sm">
              <thead className="bg-surface-2 text-left font-mono text-[11px] text-faint"><tr><th className="p-3">MODE</th><th>TIMING</th><th>STARTED</th><th>COMPLETED</th><th>RATE</th></tr></thead>
              <tbody>
                {m.completion_by_mode.map((r) => (
                  <tr key={`${r.mode}${r.timing}`} className="border-t border-line"><td className="p-3">{r.mode}</td><td>{r.timing}</td><td className="font-mono">{r.started}</td><td className="font-mono">{r.completed}</td><td className="font-mono">{pct(r.completion_rate)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            {m.cost_per_completed_debate.map((c) => <Stat key={c.mode} label={`COST / ${c.mode.toUpperCase()}`} value={`$${c.per_debate_usd.toFixed(3)}`} sub={`${c.debates} debates · $${c.total_usd.toFixed(2)}`} />)}
          </div>
        </>
      )}
    </div>
  );
}

function Audit() {
  const q = useQuery({ queryKey: ["admin", "audit"], queryFn: () => get<{ items: { actor_id: string | null; action: string; target_type: string | null; target_id: string | null; details: Record<string, unknown> | null; created_at: string }[] }>("/admin/audit") });
  return (
    <ul className="divide-y divide-line rounded-2xl border border-line bg-surface text-sm">
      {q.data?.items.map((a, i) => (
        <li key={i} className="flex flex-wrap gap-3 px-4 py-2.5">
          <span className="font-mono font-semibold">{a.action}</span>
          <span className="font-mono text-[12px] text-faint">{a.target_type}:{a.target_id?.slice(0, 8)}</span>
          {a.details?.reason ? <span className="text-dim">“{String(a.details.reason)}”</span> : null}
          <span className="ml-auto text-faint">{timeAgo(a.created_at)}</span>
        </li>
      ))}
    </ul>
  );
}

export function AdminView() {
  const { user, status } = useAuth();
  const [tab, setTab] = useState<Tab>("reports");
  if (status === "loading") return <div className="grid min-h-[50dvh] place-items-center"><Spinner className="size-6" /></div>;
  if (user?.role !== "admin") return <div className="mx-auto max-w-xl px-4 py-16"><Empty title="Admins only." /></div>;
  const tabs: { value: Tab; label: string }[] = [
    { value: "reports", label: "Reports" }, { value: "flagged", label: "Flagged" }, { value: "paused", label: "Paused" },
    { value: "metrics", label: "Metrics" }, { value: "flags", label: "Kill switches" }, { value: "models", label: "Models" }, { value: "audit", label: "Audit" },
  ];
  return (
    <div className="mx-auto max-w-5xl px-4 pb-20 pt-8 sm:px-6">
      <PageTitle eyebrow="CONTROL ROOM" title="Admin" />
      <Tabs value={tab} onChange={setTab} items={tabs} className="mb-6 w-fit max-w-full" />
      <div className={cx(tab === "metrics" ? "" : "max-w-4xl")}>
        {tab === "reports" && <Reports />}
        {tab === "flagged" && <Flagged />}
        {tab === "paused" && <Paused />}
        {tab === "flags" && <Flags />}
        {tab === "models" && <Models />}
        {tab === "metrics" && <MetricsView />}
        {tab === "audit" && <Audit />}
      </div>
    </div>
  );
}
