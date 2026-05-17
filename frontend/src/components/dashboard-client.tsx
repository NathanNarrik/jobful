"use client";

import { DndContext, DragEndEvent, PointerSensor, useDroppable, useSensor, useSensors } from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical, MoveRight, Rows3 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/badge";
import { Toast } from "@/components/toast";
import { compactLocation, statusLabels, statusOrder, titleCase } from "@/lib/format";
import { useApplicationStore } from "@/stores/application-store";
import type { ApplicationRecord, ApplicationStatus } from "@/types";

export function DashboardClient() {
  const { applications, loading, error, loadApplications, moveApplication } = useApplicationStore();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  useEffect(() => {
    void loadApplications();
  }, [loadApplications]);

  const byStatus = useMemo(() => {
    const grouped = Object.fromEntries(statusOrder.map((status) => [status, [] as ApplicationRecord[]])) as Record<
      ApplicationStatus,
      ApplicationRecord[]
    >;
    for (const application of applications) {
      grouped[application.status].push(application);
    }
    for (const status of statusOrder) {
      grouped[status].sort((a, b) => a.kanban_order - b.kanban_order);
    }
    return grouped;
  }, [applications]);

  function onDragEnd(event: DragEndEvent) {
    const activeId = String(event.active.id);
    const overId = event.over?.id ? String(event.over.id) : null;
    if (!overId) return;
    const nextStatus = overId.startsWith("column:")
      ? (overId.replace("column:", "") as ApplicationStatus)
      : applications.find((application) => application.id === overId)?.status;
    if (!nextStatus) return;
    const nextOrder = byStatus[nextStatus].findIndex((application) => application.id === overId);
    void moveApplication(activeId, nextStatus, Math.max(nextOrder, 0));
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-5 sm:px-6">
      <div className="mb-5 grid gap-4 lg:grid-cols-[1fr_auto] lg:items-end">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[var(--accent)]">Closed-loop tracker</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">Dashboard</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">Move jobs through your application pipeline after applying on the company site.</p>
        </div>
        <div className="flex h-12 items-center gap-3 rounded-xl border border-[var(--line)] bg-white px-3 shadow-sm">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-[var(--blue-soft)] text-[var(--blue)]">
            <Rows3 size={15} />
          </span>
          <span>
            <span className="block text-[11px] font-bold uppercase tracking-wide text-[var(--muted)]">Tracked</span>
            <span className="block text-sm font-semibold">{applications.length} roles</span>
          </span>
        </div>
      </div>
      {error ? <div className="mb-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div> : null}
      {loading && !applications.length ? (
        <div className="grid gap-3 md:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="h-44 animate-pulse rounded-lg bg-white" />
          ))}
        </div>
      ) : (
        <DndContext sensors={sensors} onDragEnd={onDragEnd}>
          <div className="flex gap-3 overflow-x-auto pb-3">
            {statusOrder.map((status) => (
              <KanbanColumn key={status} status={status} applications={byStatus[status]} />
            ))}
          </div>
        </DndContext>
      )}
      <Toast />
    </main>
  );
}

function KanbanColumn({
  status,
  applications,
}: {
  status: ApplicationStatus;
  applications: ApplicationRecord[];
}) {
  const { setNodeRef } = useDroppable({ id: `column:${status}` });

  return (
    <section ref={setNodeRef} className="min-h-64 w-[280px] shrink-0 rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-2 shadow-sm">
      <div className="mb-2 flex items-center justify-between rounded-lg bg-white px-2 py-2 shadow-sm">
        <h2 className="text-xs font-bold uppercase tracking-wide text-[var(--muted-strong)]">{statusLabels[status]}</h2>
        <span className="rounded-md bg-[var(--surface-strong)] px-1.5 py-0.5 text-xs font-bold text-[var(--muted-strong)]">{applications.length}</span>
      </div>
      <SortableContext items={applications.map((application) => application.id)} strategy={verticalListSortingStrategy}>
        <div className="space-y-2">
          {applications.map((application) => (
            <ApplicationCard key={application.id} application={application} />
          ))}
        </div>
      </SortableContext>
    </section>
  );
}

function ApplicationCard({ application }: { application: ApplicationRecord }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: application.id });
  const { moveApplication, saveNotes } = useApplicationStore();
  const [moveOpen, setMoveOpen] = useState(false);
  const job = application.job;

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  if (!job) return null;

  return (
    <article
      ref={setNodeRef}
      style={style}
      className={`rounded-lg border border-[var(--line)] bg-white p-2.5 shadow-sm transition hover:border-[var(--line-strong)] hover:shadow-md ${isDragging ? "opacity-70" : ""}`}
    >
      <div className="flex items-start gap-2">
        <button
          type="button"
          className="mt-0.5 hidden h-7 w-7 shrink-0 items-center justify-center rounded-md text-[var(--muted)] hover:bg-[var(--surface-strong)] md:inline-flex"
          title="Drag card"
          {...attributes}
          {...listeners}
        >
          <GripVertical size={15} />
        </button>
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-bold uppercase tracking-wide text-[var(--accent)]">{job.company_name}</p>
          <h3 className="mt-1 line-clamp-2 text-sm font-semibold leading-5">{job.job_title}</h3>
          <p className="mt-1 truncate text-xs text-[var(--muted)]">{compactLocation(job.location)}</p>
        </div>
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        <Badge tone="teal">{titleCase(job.program_type)}</Badge>
        <Badge>{titleCase(job.remote_type)}</Badge>
      </div>
      <textarea
        defaultValue={application.notes ?? ""}
        onBlur={(event) => void saveNotes(application.id, event.currentTarget.value)}
        placeholder="Notes"
        className="mt-2 min-h-16 w-full resize-none rounded-md border border-[var(--line)] bg-[var(--background)] p-2 text-xs outline-none focus:border-[var(--accent)]"
      />
      <button
        type="button"
        className="mt-2 inline-flex h-8 w-full items-center justify-center gap-2 rounded-md border border-[var(--line)] text-xs font-semibold text-[var(--muted)] md:hidden"
        onClick={() => setMoveOpen((value) => !value)}
      >
        <MoveRight size={14} />
        Move
      </button>
      {moveOpen ? (
        <div className="mt-2 grid grid-cols-2 gap-1 md:hidden">
          {statusOrder.map((status) => (
            <button
              key={status}
              className="rounded-md bg-[var(--surface-strong)] px-2 py-1.5 text-xs font-medium"
              onClick={() => {
                setMoveOpen(false);
                void moveApplication(application.id, status, 0);
              }}
            >
              {statusLabels[status]}
            </button>
          ))}
        </div>
      ) : null}
    </article>
  );
}
