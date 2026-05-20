"use client";

import { ArrowUpRight, CalendarDays, ExternalLink, MapPin, Users } from "lucide-react";
import { Badge } from "@/components/badge";
import { companyInitials, compactLocation, titleCase } from "@/lib/format";
import { useEventsStore } from "@/stores/events-store";
import type { EventListItem } from "@/types";

export function EventRow({ event }: { event: EventListItem }) {
  const { openEvent } = useEventsStore();
  const registerUrl = event.registration_url || event.event_url;

  return (
    <article
      className="grid cursor-pointer gap-3 border-b border-[var(--line)] bg-[var(--surface)] px-4 py-3 transition hover:bg-[var(--surface-soft)] hover:shadow-[inset_3px_0_0_var(--accent)] md:grid-cols-[minmax(260px,1.35fr)_minmax(190px,0.9fr)_minmax(220px,1fr)_auto] md:items-center"
      onClick={() => void openEvent(event.id)}
    >
      <div className="flex min-w-0 items-start gap-3">
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-[var(--accent-soft)] text-xs font-bold text-[var(--accent-strong)] ring-1 ring-inset ring-teal-300/20">
          {companyInitials(event.firm_name)}
        </div>
        <div className="min-w-0">
          <p className="truncate text-xs font-bold uppercase tracking-wide text-[var(--accent)]">{event.firm_name}</p>
          <h2 className="mt-0.5 line-clamp-2 text-[15px] font-semibold leading-5 text-[var(--foreground)]">{event.event_title}</h2>
        </div>
      </div>

      <div className="grid gap-1 text-xs text-[var(--muted)] sm:grid-cols-3 md:block md:space-y-1">
        <span className="flex min-w-0 items-center gap-1.5">
          <CalendarDays size={14} />
          <span className="truncate">{dateTimeLabel(event.starts_at)}</span>
        </span>
        <span className="flex min-w-0 items-center gap-1.5">
          <MapPin size={14} />
          <span className="truncate">{compactLocation(event.location)}</span>
        </span>
        <span className="flex items-center gap-1.5">
          <Users size={14} />
          <span>{event.audience_tags.slice(0, 2).join(", ") || titleCase(event.firm_kind)}</span>
        </span>
      </div>

      <div className="flex flex-wrap gap-1.5">
        <Badge tone="teal">{titleCase(event.event_type)}</Badge>
        <Badge>{titleCase(event.location_type)}</Badge>
        <Badge>{titleCase(event.firm_kind)}</Badge>
        {event.audience_tags.slice(0, 2).map((tag) => (
          <Badge key={tag}>{titleCase(tag)}</Badge>
        ))}
      </div>

      <div className="flex items-center gap-2 md:justify-end">
        <button
          type="button"
          className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[var(--line)] text-[var(--muted)] hover:bg-[var(--surface-strong)]"
          title="View event"
          onClick={(clickEvent) => {
            clickEvent.stopPropagation();
            void openEvent(event.id);
          }}
        >
          <ArrowUpRight size={15} />
        </button>
        <a
          href={registerUrl}
          target="_blank"
          rel="noreferrer"
          onClick={(clickEvent) => clickEvent.stopPropagation()}
          className="inline-flex h-8 items-center gap-1 rounded-md bg-[var(--accent)] px-2.5 text-xs font-semibold text-[#061018] hover:bg-[var(--accent-strong)]"
        >
          <ExternalLink size={14} />
          Register
        </a>
      </div>
    </article>
  );
}

function dateTimeLabel(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}
