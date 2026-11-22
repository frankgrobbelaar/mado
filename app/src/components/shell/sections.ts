import { House, type LucideIcon, Settings } from "lucide-react";

export interface Section {
  path: string;
  label: string;
  icon: LucideIcon;
  /** At the rail's foot, apart from the places above it. */
  foot?: boolean;
}

/** The places in Mado, in rail order. More join as Mado is built. */
export const sections: Section[] = [
  { path: "/", label: "Home", icon: House },
  { path: "/settings", label: "Settings", icon: Settings, foot: true },
];

/** The section a page sits in, whose place stays lit while it's open: its address's first part. */
export function sectionOf(pathname: string): string {
  const [, first = ""] = pathname.split("/");
  return `/${first}`;
}
