"use client";

import { CalendarDays, ChevronDown, History, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useEventsStore } from "@/stores/events-store";

const firmKinds = ["technology", "finance", "consulting", "healthcare", "government", "startup", "industrial", "retail", "other"];
const eventTypes = ["recruiting", "info_session", "career_fair", "webinar", "workshop", "networking", "conference"];
const locationTypes = ["virtual", "in_person", "hybrid", "unknown"];

export function EventFilterBar() {
  const { filters, sources, setFilter, loadEvents } = useEventsStore();
  const [openFilter, setOpenFilter] = useState<string | null>(null);
  const searchInput = useRef<HTMLInputElement | null>(null);
  const firms = useMemo(() => Array.from(new Set(sources.map((source) => source.firm_name))).sort(), [sources]);

  useEffect(() => {
    function closeDropdown() {
      setOpenFilter(null);
    }
    window.addEventListener("click", closeDropdown);
    return () => window.removeEventListener("click", closeDropdown);
  }, []);

  function commitSearch() {
    const value = searchInput.current?.value.trim() ?? "";
    if (value !== filters.search) {
      setFilter("search", value);
      void loadEvents(0);
    }
  }

  function updateFilter(key: keyof typeof filters, value: string) {
    setFilter(key, value);
    void loadEvents(0);
  }

  function clearFilters() {
    if (searchInput.current) {
      searchInput.current.value = "";
    }
    for (const key of Object.keys(filters) as (keyof typeof filters)[]) {
      setFilter(key, "");
    }
    void loadEvents(0);
  }

  const activeFilterCount = Object.values(filters).filter(Boolean).length;

  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-2.5 shadow-[0_8px_24px_rgba(25,35,40,0.045)]">
      <div className="flex flex-wrap items-center gap-2">
        <label className="relative h-10 min-w-[260px] flex-[1_1_320px] lg:max-w-[420px]">
          <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted)]" size={16} />
          <input
            key={filters.search}
            ref={searchInput}
            defaultValue={filters.search}
            onBlur={commitSearch}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.currentTarget.blur();
                commitSearch();
              }
            }}
            placeholder="Search event or firm"
            className="focus-ring h-10 w-full rounded-lg border border-[var(--line)] bg-[var(--surface)] pl-9 pr-12 text-sm shadow-sm outline-none focus:border-[var(--accent)]"
          />
          <button
            type="button"
            className="absolute right-1.5 top-1/2 inline-flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-md text-[var(--muted)] transition hover:bg-[var(--surface-soft)] hover:text-[var(--foreground)]"
            aria-label="Search"
            onMouseDown={(event) => event.preventDefault()}
            onClick={commitSearch}
          >
            <Search size={14} />
          </button>
        </label>
        <div className="grid min-w-0 flex-1 grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
          <Dropdown id="firm" label="Firm" value={filters.firm} options={firms} openFilter={openFilter} setOpenFilter={setOpenFilter} onChange={(value) => updateFilter("firm", value)} />
          <Dropdown id="kind" label="Kind" value={filters.firm_kind} options={firmKinds} openFilter={openFilter} setOpenFilter={setOpenFilter} onChange={(value) => updateFilter("firm_kind", value)} />
          <Dropdown id="type" label="Type" value={filters.event_type} options={eventTypes} openFilter={openFilter} setOpenFilter={setOpenFilter} onChange={(value) => updateFilter("event_type", value)} />
          <Dropdown id="location" label="Location" value={filters.location_type} options={locationTypes} openFilter={openFilter} setOpenFilter={setOpenFilter} onChange={(value) => updateFilter("location_type", value)} />
          <button
            type="button"
            className="flex h-10 min-w-0 items-center gap-2 rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 text-sm font-semibold text-[var(--muted-strong)] hover:bg-[var(--surface-strong)]"
            onClick={() => updateFilter("starts_after", filters.starts_after ? "" : new Date().toISOString())}
          >
            <CalendarDays size={15} />
            <span className="truncate">{filters.starts_after ? "All dates" : "Upcoming"}</span>
          </button>
          <button
            type="button"
            className={`flex h-10 min-w-0 items-center gap-2 rounded-lg border px-3 text-sm font-semibold hover:bg-[var(--surface-strong)] ${
              filters.active_only === "false"
                ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                : "border-[var(--line)] bg-[var(--surface-soft)] text-[var(--muted-strong)]"
            }`}
            onClick={() => updateFilter("active_only", filters.active_only === "false" ? "true" : "false")}
          >
            <History size={15} />
            <span className="truncate">{filters.active_only === "false" ? "Past shown" : "Active only"}</span>
          </button>
        </div>
        <button
          type="button"
          className="ml-auto inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 text-sm font-semibold text-[var(--muted-strong)] shadow-sm hover:bg-[var(--surface-soft)]"
          onClick={clearFilters}
        >
          <X size={15} />
          Clear
        </button>
      </div>
      <div className="mt-2 px-0.5 text-xs text-[var(--muted)]">{activeFilterCount} active filters</div>
    </div>
  );
}

function Dropdown({
  id,
  label,
  value,
  options,
  openFilter,
  setOpenFilter,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  options: string[];
  openFilter: string | null;
  setOpenFilter: (id: string | null) => void;
  onChange: (value: string) => void;
}) {
  const isOpen = openFilter === id;
  const displayValue = value ? formatOption(value) : "All";

  return (
    <div className="relative min-w-0" onClick={(event) => event.stopPropagation()}>
      <button
        type="button"
        className={`relative flex h-10 w-full flex-col justify-center rounded-lg border px-2.5 pr-7 text-left shadow-sm transition ${
          isOpen ? "border-[var(--accent)] bg-[var(--surface)]" : "border-[var(--line)] bg-[var(--surface-soft)] hover:bg-[var(--surface-strong)]"
        }`}
        aria-label={`${label}: ${displayValue}`}
        aria-expanded={isOpen}
        onClick={() => setOpenFilter(isOpen ? null : id)}
      >
        <span className="truncate text-[10px] font-bold uppercase leading-none tracking-wide text-[var(--muted)]">{label}</span>
        <span className="truncate text-sm font-medium text-[var(--foreground)]">{displayValue}</span>
        <ChevronDown className={`absolute right-2 top-1/2 -translate-y-1/2 text-[var(--muted)] transition ${isOpen ? "rotate-180" : ""}`} size={14} />
      </button>
      {isOpen ? (
        <div className="absolute left-0 top-11 z-30 max-h-72 w-full overflow-auto rounded-lg border border-[var(--line)] bg-[var(--surface)] p-1 shadow-[0_14px_32px_rgba(25,35,40,0.14)]">
          <OptionButton label="All" active={!value} onClick={() => onChangeAndClose("", onChange, setOpenFilter)} />
          {options.map((option) => (
            <OptionButton key={option} label={formatOption(option)} active={value === option} onClick={() => onChangeAndClose(option, onChange, setOpenFilter)} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function OptionButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      className={`block w-full rounded-md px-2.5 py-2 text-left text-sm transition ${
        active ? "bg-[var(--accent-soft)] font-semibold text-[var(--accent)]" : "text-[var(--muted-strong)] hover:bg-[var(--surface-soft)]"
      }`}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

function onChangeAndClose(value: string, onChange: (value: string) => void, setOpenFilter: (id: string | null) => void) {
  onChange(value);
  setOpenFilter(null);
}

function formatOption(option: string) {
  return option.replaceAll("_", " ");
}
