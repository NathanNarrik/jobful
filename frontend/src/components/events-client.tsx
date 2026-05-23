"use client";

import { CalendarDays, ChevronLeft, ChevronRight, Database, Sparkles, Zap } from "lucide-react";
import { useEffect } from "react";
import { Badge } from "@/components/badge";
import { EventDetailDrawer } from "@/components/event-detail-drawer";
import { EventFilterBar } from "@/components/event-filter-bar";
import { EventRow } from "@/components/event-row";
import { useEventsStore } from "@/stores/events-store";

export function EventsClient() {
  const { events, sources, total, limit, offset, loading, error, setFilter, loadEvents, loadSources } = useEventsStore();

  useEffect(() => {
    const firmSearch = new URLSearchParams(window.location.search).get("firm") ?? "";
    if (firmSearch) {
      setFilter("firm", firmSearch);
    }
    void loadSources();
    void loadEvents(0);
  }, [loadEvents, loadSources, setFilter]);

  const nextOffset = offset + limit;
  const canGoBack = offset > 0;
  const canGoNext = nextOffset < total;
  const sourceCount = sources.length;
  const sourceStatusCounts = sources.reduce<Record<string, number>>((counts, source) => {
    counts[source.source_status] = (counts[source.source_status] ?? 0) + 1;
    return counts;
  }, {});

  return (
    <main>
      <div className="mx-auto max-w-7xl px-4 py-5 sm:px-6">
        <div className="mb-4 grid gap-4 lg:grid-cols-[1fr_auto] lg:items-end">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[var(--accent)]">Recruiting calendar</p>
            <h1 className="mt-1 text-3xl font-semibold tracking-tight">Events</h1>
            <p className="mt-1 text-sm text-[var(--muted)]">Company-hosted recruiting sessions, fairs, webinars, and early-career events.</p>
          </div>
          <div className="grid gap-2 sm:grid-cols-3">
            <Stat icon={<CalendarDays size={15} />} label="Events" value={total.toLocaleString()} />
            <Stat icon={<Zap size={15} />} label="Page" value={`${offset + 1}-${Math.min(offset + limit, total)}`} />
            <Stat icon={<Database size={15} />} label="Sources" value={sourceCount.toLocaleString()} />
          </div>
        </div>
        <div className="mb-4">
          <EventFilterBar />
        </div>
        {sources.length ? (
          <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-[var(--muted)]">
            <span className="font-semibold text-[var(--muted-strong)]">Source health</span>
            {Object.entries(sourceStatusCounts).map(([status, count]) => (
              <Badge key={status} tone={sourceStatusTone(status)}>
                {statusLabel(status)} {count}
              </Badge>
            ))}
          </div>
        ) : null}
        <div className="mb-3 flex items-center justify-end gap-2">
          <button
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--line)] bg-[var(--surface)] shadow-sm transition hover:bg-[var(--surface-soft)] disabled:opacity-45"
            disabled={!canGoBack || loading}
            onClick={() => void loadEvents(Math.max(0, offset - limit))}
            title="Previous page"
          >
            <ChevronLeft size={16} />
          </button>
          <button
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--line)] bg-[var(--surface)] shadow-sm transition hover:bg-[var(--surface-soft)] disabled:opacity-45"
            disabled={!canGoNext || loading}
            onClick={() => void loadEvents(nextOffset)}
            title="Next page"
          >
            <ChevronRight size={16} />
          </button>
        </div>
        {error ? <div className="mb-4 rounded-md border border-rose-300/30 bg-rose-400/10 p-3 text-sm text-rose-100">{error}</div> : null}
        <section className="overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--surface)] shadow-[0_10px_30px_rgba(25,35,40,0.06)]">
          <div className="hidden grid-cols-[minmax(260px,1.35fr)_minmax(190px,0.9fr)_minmax(220px,1fr)_auto] border-b border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2.5 text-xs font-bold uppercase tracking-wide text-[var(--muted)] md:grid">
            <span>Event</span>
            <span>When</span>
            <span>Signals</span>
            <span className="text-right">Action</span>
          </div>
          {loading && !events.length ? (
            Array.from({ length: 10 }).map((_, index) => <div key={index} className="h-20 animate-pulse border-b border-[var(--line)] bg-[var(--surface)]" />)
          ) : events.length ? (
            events.map((event) => <EventRow key={event.id} event={event} />)
          ) : (
            <div className="flex min-h-48 flex-col items-center justify-center gap-2 px-4 py-10 text-center">
              <Sparkles className="text-[var(--muted)]" size={24} />
              <p className="font-semibold">No events match that view.</p>
              <p className="text-sm text-[var(--muted)]">Try a broader filter or import fresh event sources.</p>
            </div>
          )}
        </section>
      </div>
      <EventDetailDrawer />
    </main>
  );
}

function statusLabel(status: string) {
  return status.replace(/[-_]/g, " ");
}

function sourceStatusTone(status: string): React.ComponentProps<typeof Badge>["tone"] {
  if (status === "productive") return "green";
  if (status === "empty" || status === "parser-needed") return "amber";
  if (status === "blocked" || status === "auth-required" || status === "failed") return "red";
  return "neutral";
}

function Stat({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex h-12 items-center gap-3 rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 shadow-sm">
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-[var(--accent-soft)] text-[var(--accent)]">{icon}</span>
      <span>
        <span className="block text-[11px] font-bold uppercase tracking-wide text-[var(--muted)]">{label}</span>
        <span className="block text-sm font-semibold">{value}</span>
      </span>
    </div>
  );
}
