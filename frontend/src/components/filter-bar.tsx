"use client";

import { ChevronDown, Search, SlidersHorizontal, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useDiscoveryStore } from "@/stores/discovery-store";

const programTypes = ["internship", "new_grad", "experienced", "other"];
const remoteTypes = ["remote", "hybrid", "onsite", "unknown"];
const visaStatuses = ["sponsors", "opt_cpt_allowed", "requires_authorization", "does_not_sponsor", "not_mentioned"];
const gradYears = ["2026", "2027", "2028", "2029", "2030"];
const countries = [
  "United States",
  "Canada",
  "India",
  "United Kingdom",
  "Ireland",
  "Germany",
  "France",
  "Netherlands",
  "Spain",
  "Singapore",
  "Australia",
  "Japan",
  "China",
  "Taiwan",
  "South Korea",
  "Israel",
];

export function FilterBar() {
  const { filters, setFilter, loadJobs, popularSkills } = useDiscoveryStore();
  const [openFilter, setOpenFilter] = useState<string | null>(null);
  const searchTimeout = useRef<number | null>(null);
  const skillOptions = useMemo(() => popularSkills.map((skill) => skill.skill), [popularSkills]);

  useEffect(() => {
    function closeDropdown() {
      setOpenFilter(null);
    }

    window.addEventListener("click", closeDropdown);
    return () => window.removeEventListener("click", closeDropdown);
  }, []);

  useEffect(() => {
    return () => {
      if (searchTimeout.current) {
        window.clearTimeout(searchTimeout.current);
      }
    };
  }, []);

  function updateSearch(value: string) {
    if (searchTimeout.current) {
      window.clearTimeout(searchTimeout.current);
    }
    searchTimeout.current = window.setTimeout(() => {
      setFilter("search", value);
      void loadJobs(0);
    }, 300);
  }

  function updateFilter(key: keyof typeof filters, value: string) {
    setFilter(key, value);
    void loadJobs(0);
  }

  function clearFilters() {
    if (searchTimeout.current) {
      window.clearTimeout(searchTimeout.current);
    }
    for (const key of Object.keys(filters) as (keyof typeof filters)[]) {
      setFilter(key, "");
    }
    void loadJobs(0);
  }

  const activeFilterCount =
    Object.entries(filters).filter(([key, value]) => key !== "search" && Boolean(value)).length +
    (filters.search ? 1 : 0);

  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-2.5 shadow-[0_8px_24px_rgba(25,35,40,0.045)]">
      <div className="flex flex-wrap items-center gap-2">
        <label className="relative h-10 min-w-[260px] flex-[1_1_330px] lg:max-w-[460px]">
          <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted)]" size={16} />
          <input
            key={filters.search}
            defaultValue={filters.search}
            onChange={(event) => updateSearch(event.target.value)}
            placeholder="Search title or company"
            className="focus-ring h-10 w-full min-w-0 rounded-lg border border-[var(--line)] bg-[var(--surface)] pl-9 pr-3 text-sm shadow-sm outline-none focus:border-[var(--accent)]"
          />
        </label>
        <div className="grid min-w-0 flex-1 grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-3 2xl:grid-cols-6">
          <Dropdown
            className="w-full"
            id="program"
            label="Program"
            value={filters.program_type}
            options={programTypes}
            openFilter={openFilter}
            setOpenFilter={setOpenFilter}
            onChange={(value) => updateFilter("program_type", value)}
          />
          <Dropdown
            className="w-full"
            id="grad-year"
            label="Grad year"
            value={filters.grad_year}
            options={gradYears}
            openFilter={openFilter}
            setOpenFilter={setOpenFilter}
            onChange={(value) => updateFilter("grad_year", value)}
          />
          <Dropdown
            className="w-full"
            id="country"
            label="Country"
            value={filters.country}
            options={countries}
            openFilter={openFilter}
            setOpenFilter={setOpenFilter}
            onChange={(value) => updateFilter("country", value)}
          />
          <Dropdown
            className="w-full"
            id="remote"
            label="Remote"
            value={filters.remote_type}
            options={remoteTypes}
            openFilter={openFilter}
            setOpenFilter={setOpenFilter}
            onChange={(value) => updateFilter("remote_type", value)}
          />
          <Dropdown
            className="w-full"
            id="visa"
            label="Visa"
            value={filters.visa_status}
            options={visaStatuses}
            openFilter={openFilter}
            setOpenFilter={setOpenFilter}
            onChange={(value) => updateFilter("visa_status", value)}
          />
          <Dropdown
            className="w-full"
            id="skill"
            label="Skill"
            value={filters.skill}
            options={skillOptions}
            openFilter={openFilter}
            setOpenFilter={setOpenFilter}
            onChange={(value) => updateFilter("skill", value)}
          />
        </div>
        <button
          type="button"
          className="ml-auto inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 text-sm font-semibold text-[var(--muted-strong)] shadow-sm transition hover:border-[var(--line-strong)] hover:bg-[var(--surface-soft)]"
          onClick={clearFilters}
        >
          <X size={15} />
          Clear
        </button>
      </div>
      <div className="mt-2 flex items-center justify-between gap-2 px-0.5 text-xs text-[var(--muted)]">
        <div className="flex items-center gap-2">
          <SlidersHorizontal size={14} />
          <span>Instant filters refetch the feed. Search is debounced.</span>
        </div>
        <span className="font-medium">{activeFilterCount} active</span>
      </div>
    </div>
  );
}

function Dropdown({
  className,
  id,
  label,
  value,
  options,
  openFilter,
  setOpenFilter,
  onChange,
}: {
  className: string;
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
    <div className={`relative min-w-0 ${className}`} onClick={(event) => event.stopPropagation()}>
      <button
        type="button"
        className={`relative flex h-10 w-full flex-col justify-center rounded-lg border px-2.5 pr-7 text-left shadow-sm transition ${
          isOpen
            ? "border-[var(--accent)] bg-[var(--surface)]"
            : "border-[var(--line)] bg-[var(--surface-soft)] hover:border-[var(--line-strong)] hover:bg-[var(--surface-strong)]"
        }`}
        aria-label={`${label}: ${displayValue}`}
        aria-expanded={isOpen}
        onClick={() => setOpenFilter(isOpen ? null : id)}
      >
        <span className="truncate text-[10px] font-bold uppercase leading-none tracking-wide text-[var(--muted)]">
          {label}
        </span>
        <span className="truncate text-sm font-medium leading-snug text-[var(--foreground)]">
          {displayValue}
        </span>
        <ChevronDown
          className={`absolute right-2 top-1/2 -translate-y-1/2 text-[var(--muted)] transition ${isOpen ? "rotate-180" : ""}`}
          size={14}
        />
      </button>
      {isOpen ? (
        <div className="absolute left-0 top-11 z-30 max-h-72 w-full overflow-auto rounded-lg border border-[var(--line)] bg-[var(--surface)] p-1 shadow-[0_14px_32px_rgba(25,35,40,0.14)]">
          <OptionButton label="All" active={!value} onClick={() => onChangeAndClose("", onChange, setOpenFilter)} />
          {options.map((option) => (
            <OptionButton
              key={option}
              label={formatOption(option)}
              active={value === option}
              onClick={() => onChangeAndClose(option, onChange, setOpenFilter)}
            />
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
  const labels: Record<string, string> = {
    new_grad: "New grad",
    opt_cpt_allowed: "OPT/CPT",
    requires_authorization: "Auth required",
    does_not_sponsor: "No sponsor",
    not_mentioned: "Not mentioned",
  };

  return labels[option] ?? option.replaceAll("_", " ");
}
