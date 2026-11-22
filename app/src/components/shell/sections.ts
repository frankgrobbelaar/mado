import { Clock, House, ImageIcon, type LucideIcon, Settings, TextAlignStart } from "lucide-react";

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
  { path: "/library", label: "Library", icon: ImageIcon },
  { path: "/queue", label: "Queue", icon: TextAlignStart },
  { path: "/history", label: "History", icon: Clock },
  { path: "/settings", label: "Settings", icon: Settings, foot: true },
];

/** Pages that sit in another's place: Many at once is made from the Library's pictures, and the
 * recipes and watch folders feed the queue, as the boards light them. */
const BELONGS: Record<string, string> = { "/batch": "/library", "/recipes": "/queue" };

/** The section a page sits in, whose place stays lit while it's open: its address's first part. */
export function sectionOf(pathname: string): string {
  const [, first = ""] = pathname.split("/");
  const section = `/${first}`;
  return BELONGS[section] ?? section;
}
