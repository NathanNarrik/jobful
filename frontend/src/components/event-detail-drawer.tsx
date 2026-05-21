"use client";

import { CalendarDays, ExternalLink, MapPin, RefreshCw, Sparkles, Users, X } from "lucide-react";
import { Badge } from "@/components/badge";
import { companyInitials, plainTextDescription, shortDate, titleCase } from "@/lib/format";
import { useEventsStore } from "@/stores/events-store";

export function EventDetailDrawer() {
  const { activeEvent, detailLoading, closeEvent } = useEventsStore();

  if (!activeEvent && !detailLoading) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/25 backdrop-blur-[1px]" onClick={closeEvent}>
      <aside
        className="ml-auto flex h-full w-full max-w-3xl flex-col bg-[var(--surface)] shadow-2xl ring-1 ring-white/10"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="border-b border-[var(--line)] bg-[var(--surface-soft)] p-5">
          <div className="flex items-start justify-between gap-4">
            <div className="flex min-w-0 items-start gap-3">
              {activeEvent ? (
                <div className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-[var(--accent-soft)] text-sm font-bold text-[var(--accent-strong)] shadow-sm ring-1 ring-teal-300/20">
                  {companyInitials(activeEvent.firm_name)}
                </div>
              ) : null}
              <div className="min-w-0">
                <p className="text-sm font-semibold text-[var(--accent)]">{activeEvent?.firm_name ?? "Loading"}</p>
                <h2 className="mt-1 text-2xl font-semibold leading-8 tracking-tight">{activeEvent?.event_title ?? "Opening event"}</h2>
                {activeEvent ? (
                  <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-sm text-[var(--muted)]">
                    <Meta icon={<CalendarDays size={15} />} value={dateTimeLabel(activeEvent.starts_at)} />
                    <Meta icon={<MapPin size={15} />} value={activeEvent.location.slice(0, 2).join("; ")} />
                    <Meta icon={<Users size={15} />} value={titleCase(activeEvent.firm_kind)} />
                  </div>
                ) : null}
              </div>
            </div>
            <button className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-transparent hover:border-[var(--line)] hover:bg-[var(--surface-strong)]" onClick={closeEvent}>
              <X size={18} />
            </button>
          </div>
        </div>

        {activeEvent ? (
          <>
            <div className="flex flex-wrap gap-2 border-b border-[var(--line)] px-5 py-3">
              <Badge tone="teal">{titleCase(activeEvent.event_type)}</Badge>
              <Badge>{titleCase(activeEvent.location_type)}</Badge>
              <Badge>{titleCase(activeEvent.source_provider)}</Badge>
              {activeEvent.audience_tags.map((tag) => (
                <Badge key={tag}>{titleCase(tag)}</Badge>
              ))}
            </div>
            <div className="flex-1 overflow-y-auto bg-[var(--background)] px-5 py-5">
              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <Field icon={<CalendarDays size={16} />} label="Starts" value={dateTimeLabel(activeEvent.starts_at)} />
                <Field icon={<CalendarDays size={16} />} label="Ends" value={activeEvent.ends_at ? dateTimeLabel(activeEvent.ends_at) : "Not specified"} />
                <Field icon={<MapPin size={16} />} label="Location" value={activeEvent.location.join("; ")} />
                <Field icon={<RefreshCw size={16} />} label="Seen by Jobful" value={`First ${shortDate(activeEvent.first_seen_at)} | latest ${shortDate(activeEvent.last_seen_at)}`} />
                <Field icon={<Sparkles size={16} />} label="Audience" value={activeEvent.audience_tags.map(titleCase).join(", ") || "Not specified"} wide />
                <Field icon={<Users size={16} />} label="Source" value={activeEvent.source_event_id ?? activeEvent.source_provider} />
              </dl>
              <section className="mt-5 rounded-xl border border-[var(--line)] bg-[var(--surface)] shadow-sm">
                <div className="border-b border-[var(--line)] px-4 py-3">
                  <h3 className="text-sm font-semibold">Details</h3>
                </div>
                <p className="max-h-[48vh] overflow-y-auto whitespace-pre-line px-4 py-4 text-sm leading-6 text-[var(--muted)]">
                  {plainTextDescription(activeEvent.description).slice(0, 7000)}
                </p>
              </section>
            </div>
            <div className="flex flex-col gap-2 border-t border-[var(--line)] bg-[var(--surface)] p-4 shadow-[0_-10px_30px_rgba(25,35,40,0.04)] sm:flex-row">
              <a
                href={activeEvent.event_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-[var(--line)] px-4 text-sm font-semibold hover:bg-[var(--surface-strong)]"
              >
                <ExternalLink size={16} />
                Open event
              </a>
              <a
                href={activeEvent.registration_url || activeEvent.event_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-lg bg-[var(--accent)] px-4 text-sm font-semibold text-[#061018] shadow-sm hover:bg-[var(--accent-strong)]"
              >
                <ExternalLink size={16} />
                Register
              </a>
            </div>
          </>
        ) : (
          <div className="p-4 text-sm text-[var(--muted)]">Loading event detail...</div>
        )}
      </aside>
    </div>
  );
}

function Meta({ icon, value }: { icon: React.ReactNode; value: string }) {
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      <span className="shrink-0 text-[var(--muted)]">{icon}</span>
      <span className="truncate">{value}</span>
    </span>
  );
}

function Field({ icon, label, value, wide = false }: { icon: React.ReactNode; label: string; value: string; wide?: boolean }) {
  return (
    <div className={`rounded-xl border border-[var(--line)] bg-[var(--surface)] p-3 shadow-sm ${wide ? "sm:col-span-2" : ""}`}>
      <dt className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
        {icon}
        {label}
      </dt>
      <dd className="mt-2 text-sm font-medium leading-5">{value}</dd>
    </div>
  );
}

function dateTimeLabel(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}
