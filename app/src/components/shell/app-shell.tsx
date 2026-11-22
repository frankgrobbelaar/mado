import { Outlet, useLocation } from "react-router";
import { ScreenError } from "@/components/screen-error";
import { DamagedRecords } from "@/features/records/damaged-records";
import { useRecords } from "@/lib/engine";
import { DropZone } from "./drop-zone";
import { NavRail } from "./nav-rail";
import { Notices } from "./notices";
import { Offline } from "./offline";
import { StatusBar } from "./status-bar";
import { TitleBar } from "./title-bar";
import { UpdateCard } from "./update-card";

/**
 * The window, as Graphite draws it: the rail down the left side, and beside it the title bar,
 * the current page and the status bar. Only the page scrolls: the rail, the title bar and the
 * status bar stay where they are. Pictures dropped anywhere on it open (DropZone). While Mado's
 * records are damaged, the way back stands in for every page.
 */
export function AppShell() {
  const location = useLocation();
  const damage = useRecords().data;

  return (
    <div className="flex h-screen overflow-hidden">
      <NavRail />
      <div className="flex min-w-0 flex-1 flex-col">
        <TitleBar />
        {/* A fresh start on every screen: it opens at its top, and one that failed to draw
          doesn't follow you around. Every part of a page keeps its full height, so a long
          page scrolls instead of squashing a panel that clips its corners. */}
        <main
          key={location.pathname}
          id="main"
          className="flex min-h-0 min-w-0 flex-1 flex-col gap-6 overflow-y-auto px-7 pb-12 *:shrink-0"
        >
          <ScreenError>{damage ? <DamagedRecords damage={damage} /> : <Outlet />}</ScreenError>
        </main>
        <StatusBar />
      </div>
      <UpdateCard />
      {!damage && <DropZone />}
      {/* Notes at the foot of the window, over the page: being offline, and what the engine
        tells of. */}
      <div className="pointer-events-none fixed bottom-12 left-1/2 z-10 flex w-[min(30rem,calc(100vw-3rem))] -translate-x-1/2 flex-col gap-3 *:pointer-events-auto">
        <Offline />
        <Notices />
      </div>
    </div>
  );
}
