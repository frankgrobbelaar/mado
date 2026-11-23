import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HashRouter, Route, Routes } from "react-router";
import { ScreenError } from "@/components/screen-error";
import { AppShell } from "@/components/shell/app-shell";
import { UpdateCard } from "@/components/shell/update-card";
import { BatchPage } from "@/features/batch/batch-page";
import { DuplicatesPage } from "@/features/duplicates/duplicates-page";
import { HistoryPage } from "@/features/history/history-page";
import { HomePage } from "@/features/home/home-page";
import { LibraryPage } from "@/features/library/library-page";
import { PicturePage } from "@/features/picture/picture-page";
import { QueuePage } from "@/features/queue/queue-page";
import { RecipesPage } from "@/features/recipes/recipes-page";
import { SettingsPage } from "@/features/settings/settings-page";
import { SetupPage } from "@/features/setup/setup-page";
import { WallpaperPage } from "@/features/wallpaper/wallpaper-page";
import { EngineProvider } from "@/lib/engine";

const queryClient = new QueryClient();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <EngineProvider>
        <HashRouter>
          <Routes>
            <Route
              path="/setup"
              element={
                <ScreenError>
                  <SetupPage />
                </ScreenError>
              }
            />
            <Route element={<AppShell />}>
              <Route index element={<HomePage />} />
              <Route path="/library" element={<LibraryPage />} />
              <Route path="/library/pictures/:id" element={<PicturePage />} />
              <Route path="/pictures/:id" element={<PicturePage />} />
              <Route path="/wallpaper" element={<WallpaperPage />} />
              <Route path="/batch" element={<BatchPage />} />
              <Route path="/queue" element={<QueuePage />} />
              <Route path="/recipes" element={<RecipesPage />} />
              <Route path="/history" element={<HistoryPage />} />
              <Route path="/duplicates" element={<DuplicatesPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/settings/:section" element={<SettingsPage />} />
            </Route>
          </Routes>
          <SetupUpdates />
        </HashRouter>
      </EngineProvider>
    </QueryClientProvider>
  );
}

/** The update card lives in the shell; setup has its own frame, so it shows the card itself. */
function SetupUpdates() {
  return (
    <Routes>
      <Route path="/setup" element={<UpdateCard />} />
      <Route path="*" element={null} />
    </Routes>
  );
}
