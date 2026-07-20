import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Merge Tailwind classes so a later class always wins over an earlier one. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Stable per-browser id, so ADK sessions belong to a returning user. */
export function userId(): string {
  const KEY = "sugam.userId";
  let id = localStorage.getItem(KEY);
  if (!id) {
    id = `u_${crypto.randomUUID().slice(0, 12)}`;
    localStorage.setItem(KEY, id);
  }
  return id;
}
