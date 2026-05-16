"use client";

import { Search, SlidersHorizontal } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useDiscoveryStore } from "@/stores/discovery-store";

const programTypes = ["internship", "new_grad", "experienced", "other"];
const remoteTypes = ["remote", "hybrid", "onsite", "unknown"];
const visaStatuses = ["sponsors", "opt_cpt_allowed", "requires_authorization", "does_not_sponsor", "not_mentioned"];
const gradYears = ["2026", "2027", "2028", "2029", "2030"];

export function FilterBar() {
  const { filters, setFilter, loadJobs, popularSkills } = useDiscoveryStore();
  const [searchDraft, setSearchDraft] = useState(filters.search);
  const skillOptions = useMemo(() => popularSkills.map((skill) => skill.skill), [popularSkills]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setFilter("search", searchDraft);
      void loadJobs(0);
    }, 300);
    return () => window.clearTimeout(timeout);
  }, [loadJobs, searchDraft, setFilter]);

  function updateFilter(key: keyof typeof filters, value: string) {
    setFilter(key, value);
    void loadJobs(0);
  }

  return (
    <div className="sticky top-14 z-30 border-b border-[var(--line)] bg-[var(--background)]/95 px-4 py-3 backdrop-blur sm:px-6">
      <div className="mx-auto grid max-w-7xl gap-3 lg:grid-cols-[minmax(220px,1fr)_auto]">
        <label className="relative block">
          <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted)]" size={17} />
          <input
            value={searchDraft}
            onChange={(event) => setSearchDraft(event.target.value)}
            placeholder="Search title or company"
            className="h-10 w-full rounded-md border border-[var(--line)] bg-white pl-9 pr-3 text-sm outline-none focus:border-[var(--accent)]"
          />
        </label>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
          <Select label="Program" value={filters.program_type} options={programTypes} onChange={(value) => updateFilter("program_type", value)} />
          <Select label="Grad year" value={filters.grad_year} options={gradYears} onChange={(value) => updateFilter("grad_year", value)} />
          <Select label="Remote" value={filters.remote_type} options={remoteTypes} onChange={(value) => updateFilter("remote_type", value)} />
          <Select label="Visa" value={filters.visa_status} options={visaStatuses} onChange={(value) => updateFilter("visa_status", value)} />
          <Select label="Skill" value={filters.skill} options={skillOptions} onChange={(value) => updateFilter("skill", value)} />
        </div>
      </div>
      <div className="mx-auto mt-2 flex max-w-7xl items-center gap-2 text-xs text-[var(--muted)]">
        <SlidersHorizontal size={14} />
        <span>Instant filters refetch the feed. Search is debounced.</span>
      </div>
    </div>
  );
}

function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex h-10 items-center gap-2 rounded-md border border-[var(--line)] bg-white px-2 text-sm">
      <span className="hidden text-xs font-medium text-[var(--muted)] sm:inline">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="min-w-0 flex-1 bg-transparent text-sm outline-none"
        aria-label={label}
      >
        <option value="">All</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option.replaceAll("_", " ")}
          </option>
        ))}
      </select>
    </label>
  );
}
