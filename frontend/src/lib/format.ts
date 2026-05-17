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

export function daysSinceLabel(value: string | null) {
  const age = daysSince(value);
  if (age === "Fresh") return "Fresh posting";
  if (age === "Today") return "Posted today";
  return `Posted ${age} ago`;
}

export function shortDate(value: string | null) {
  if (!value) return "Not available";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
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

export function plainTextDescription(value: string | null) {
  if (!value) return "No description available.";
  return value
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/p>/gi, "\n\n")
    .replace(/<li>/gi, "\n- ")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&#x2019;|&rsquo;/g, "'")
    .replace(/&#x201C;|&ldquo;/g, '"')
    .replace(/&#x201D;|&rdquo;/g, '"')
    .replace(/\n{3,}/g, "\n\n")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}
