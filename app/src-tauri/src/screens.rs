//! This PC's screens, for the Size tab's "Your screens": each one's pixels and whether it's the
//! main one. The engine remembers them by size (a laptop away from its desk still offers the desk's
//! screen) and names them; the shell only says what Windows has now.

use serde::Serialize;
use tauri::{AppHandle, Monitor};

/// A screen as the window sees it. Mirrors `SeenScreen` in app/src/lib/screens.ts.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub struct Screen {
    /// Its pixels across, as it shows them (Windows' scaling doesn't change them).
    pub width: u32,
    pub height: u32,
    /// Windows' main screen.
    pub main: bool,
}

/// This PC's screens, the main one first; none when Windows doesn't say.
#[tauri::command]
pub fn screens(app: AppHandle) -> Vec<Screen> {
    let main = app.primary_monitor().ok().flatten();
    let found = app.available_monitors().unwrap_or_default();
    listed(&found, main.as_ref())
}

fn listed(found: &[Monitor], main: Option<&Monitor>) -> Vec<Screen> {
    let mut screens: Vec<Screen> = found
        .iter()
        .map(|monitor| {
            let size = monitor.size();
            screen(
                size.width,
                size.height,
                main.is_some_and(|it| it.name() == monitor.name()),
            )
        })
        .filter(|screen| screen.width > 0 && screen.height > 0)
        .collect();
    screens.sort_by_key(|screen| !screen.main);
    screens
}

fn screen(width: u32, height: u32, main: bool) -> Screen {
    Screen {
        width,
        height,
        main,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_screen_carries_its_pixels_and_whether_its_the_main_one() {
        let found = screen(3440, 1440, true);

        assert_eq!(found.width, 3440);
        assert_eq!(found.height, 1440);
        assert!(found.main);
        let json = serde_json::to_value(found).unwrap();
        assert_eq!(
            json,
            serde_json::json!({"width": 3440, "height": 1440, "main": true})
        );
    }

    #[test]
    fn no_screens_listed_is_none_found() {
        assert!(listed(&[], None).is_empty());
    }
}
