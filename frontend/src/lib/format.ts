import type { ApplicationStatus } from "@/types";

export const statusLabels: Record<ApplicationStatus, string> = {
  SAVED: "Saved",
  APPLIED: "Applied",
  PHONE_SCREEN: "Phone Screen",
  TECHNICAL: "Technical",
  FINAL: "Final Round",
  OFFER: "Offer",
  REJECTED: "Rejected",
};

export const statusOrder: ApplicationStatus[] = [
  "SAVED",
  "APPLIED",
  "PHONE_SCREEN",
  "TECHNICAL",
  "FINAL",
  "OFFER",
  "REJECTED",
];

export function titleCase(value: string) {
  return value
    .replaceAll("_", " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function daysSince(value: string | null) {
  if (!value) return "Fresh";
  const date = new Date(value);
  const diff = Date.now() - date.getTime();
  const days = Math.max(0, Math.floor(diff / 86_400_000));
  if (days === 0) return "Today";
  if (days === 1) return "1 day";
  return `${days} days`;
}

export function compactLocation(locations: string[]) {
  if (!locations.length) return "Unspecified";
  if (locations.length === 1) return locations[0];
  return `${locations[0]} +${locations.length - 1}`;
}

export function companyInitials(company: string) {
  const words = company.split(/\s+/).filter(Boolean);
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return words.slice(0, 2).map((word) => word[0]).join("").toUpperCase();
}
