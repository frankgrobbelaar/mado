import { House, type LucideIcon, SlidersHorizontal } from "lucide-react";

export interface Section {
  path: string;
  label: string;
  icon: LucideIcon;
}

/** The places in Mado, in nav rail order. More join as Mado is built. */
export const sections: Section[] = [
  { path: "/", label: "Home", icon: House },
  { path: "/settings", label: "Settings", icon: SlidersHorizontal },
];

/** The section a page sits in, whose tile stays lit while it's open: its address's first part. */
export function sectionOf(pathname: string): string {
  const [, first = ""] = pathname.split("/");
  return `/${first}`;
}
