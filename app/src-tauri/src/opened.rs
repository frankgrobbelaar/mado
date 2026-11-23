//! Pictures Windows hands to Mado: named on its command line (`mado.exe <paths…>`), and from File
//! Explorer's "Open in Mado" and Open with, which start Mado with them. A second start hands what
//! it was given to the Mado already running (the single-instance plugin) and ends. Explorer
//! starts Mado once for each file of a selection, so what arrives close together is gathered into
//! one choice. A start's words become paths off the main thread, as looking at a path on a
//! network share not there can take a while. The window takes each choice once it's ready for it
//! (`take_opened`, told by the `opened` event), so nothing that arrives while Mado starts is lost;
//! the engine says what each path is (app/src/features/batch/open.ts).

use std::path::{Path, PathBuf};
use std::sync::{Mutex, mpsc};
use std::thread;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Emitter, Manager, State};

/// How long a gathering waits after the latest path arrives before it's one choice. With 15 or
/// 100 selected, Explorer's starts handed their paths over 22 ms apart at most to a Mado running,
/// and 146 ms apart at most to one only just starting (measured on the owner's PC,
/// docs/stack/tauri.md, "Open in Mado"): this is four of the longest. One file waits it too.
pub const QUIET: Duration = Duration::from_millis(600);
/// The words of a path with spaces, given without quotes, that are tried together at most.
const MOST_WORDS: usize = 32;

/// The paths gathering now, and the choices ready for the window.
#[derive(Default)]
pub struct Opened {
    gathering: Mutex<Gathering>,
}

/// One start's words, and the folder it was started in, as they arrived.
struct Arrival {
    args: Vec<String>,
    cwd: PathBuf,
}

#[derive(Default)]
struct Gathering {
    arrivals: Vec<Arrival>,
    /// When the latest start arrived; none while nothing is gathering.
    last: Option<Instant>,
    /// Choices made, waiting for the window to take them.
    ready: Vec<Vec<String>>,
    /// A thread is waiting for this gathering to settle.
    waiting: bool,
}

impl Gathering {
    fn arrive(&mut self, args: Vec<String>, cwd: PathBuf, at: Instant) {
        self.arrivals.push(Arrival { args, cwd });
        self.last = Some(at);
    }

    /// When the gathering may settle: its quiet after the latest arrival.
    fn due(&self) -> Option<Instant> {
        self.last.map(|last| last + QUIET)
    }

    /// Takes what's gathered, once nothing has arrived for `QUIET`.
    fn settle(&mut self, now: Instant) -> Option<Vec<Arrival>> {
        match self.due() {
            Some(due) if now >= due => {
                self.last = None;
                Some(std::mem::take(&mut self.arrivals))
            }
            _ => None,
        }
    }

    fn take(&mut self) -> Vec<Vec<String>> {
        std::mem::take(&mut self.ready)
    }
}

/// A gathering's choice: its starts' paths, each once, whatever its case, in the order they came.
fn choice_of(arrivals: &[Arrival], exists: impl Fn(&Path) -> bool) -> Vec<String> {
    let mut paths: Vec<String> = Vec::new();
    for arrival in arrivals {
        for path in paths_in(&arrival.args, &arrival.cwd, &exists) {
            let folded = path.to_lowercase();
            if !paths.iter().any(|kept| kept.to_lowercase() == folded) {
                paths.push(path);
            }
        }
    }
    paths
}

/// Whether a start names anything: a start with nothing but Mado's own switches only brings the
/// window forward.
fn names_anything(args: &[String]) -> bool {
    args.iter()
        .skip(1)
        .map(|arg| arg.trim())
        .any(|arg| !arg.is_empty() && !arg.starts_with("--"))
}

/// Mado was started with these arguments (its own start, or a second one handing them over,
/// from `cwd`): they join what's gathering.
pub fn arrived(app: &AppHandle, args: &[String], cwd: &Path) {
    if !names_anything(args) {
        return;
    }
    let start = {
        let opened = app.state::<Opened>();
        let mut gathering = opened.gathering.lock().unwrap();
        gathering.arrive(args.to_vec(), cwd.to_path_buf(), Instant::now());
        !std::mem::replace(&mut gathering.waiting, true)
    };
    if start {
        let app = app.clone();
        thread::spawn(move || settle(&app));
    }
}

/// Waits for a gathering to go quiet, then makes it a choice and tells the window. The last look
/// is made on the main thread, where the second starts arrive: a main thread too busy to take
/// them (Mado starting) can't make them look quiet. Their words become paths back on this thread.
fn settle(app: &AppHandle) {
    loop {
        let due = app.state::<Opened>().gathering.lock().unwrap().due();
        let Some(due) = due else { return };
        let now = Instant::now();
        if now < due {
            thread::sleep(due - now);
            continue;
        }
        let (told, heard) = mpsc::channel();
        let looking = app.clone();
        let asked = app.run_on_main_thread(move || {
            let opened = looking.state::<Opened>();
            let mut gathering = opened.gathering.lock().unwrap();
            let settled = gathering.settle(Instant::now());
            if settled.is_some() {
                gathering.waiting = false;
            }
            let _ = told.send(settled);
        });
        if asked.is_err() {
            return; // Mado is closing
        }
        match heard.recv() {
            Ok(Some(arrivals)) => {
                let paths = choice_of(&arrivals, |path| path.exists());
                if !paths.is_empty() {
                    let opened = app.state::<Opened>();
                    opened.gathering.lock().unwrap().ready.push(paths);
                    let _ = app.emit("opened", ());
                }
                return;
            }
            Ok(None) => {} // more arrived: wait on
            Err(_) => return,
        }
    }
}

/// The choices gathered since the window last asked: each a list of paths.
#[tauri::command]
pub fn take_opened(opened: State<'_, Opened>) -> Vec<Vec<String>> {
    opened.gathering.lock().unwrap().take()
}

/// The paths in a start's arguments: every argument but the program and Mado's own switches
/// (`--in-tray`), as given, against `cwd` when not whole. A path with spaces given without
/// quotes comes as several words: those that aren't there alone are tried together, the
/// longest run that's there taken as one.
pub fn paths_in(args: &[String], cwd: &Path, exists: impl Fn(&Path) -> bool) -> Vec<String> {
    let words: Vec<&str> = args
        .iter()
        .skip(1)
        .map(|arg| arg.trim())
        .filter(|arg| !arg.is_empty() && !arg.starts_with("--"))
        .collect();
    let mut found: Vec<PathBuf> = Vec::new();
    let mut at = 0;
    while at < words.len() {
        let alone = whole(words[at], cwd);
        if exists(&alone) {
            found.push(alone);
            at += 1;
            continue;
        }
        let last = words.len().min(at + MOST_WORDS);
        let joined = (at + 2..=last).rev().find_map(|end| {
            let path = whole(&words[at..end].join(" "), cwd);
            exists(&path).then_some((end, path))
        });
        match joined {
            Some((end, path)) => {
                found.push(path);
                at = end;
            }
            None => {
                found.push(alone);
                at += 1;
            }
        }
    }
    found
        .into_iter()
        .map(|path| path.to_string_lossy().into_owned())
        .collect()
}

/// A path as given, against `cwd` when it isn't whole ("Pier.jpg" from a terminal in D:\Trip).
fn whole(given: &str, cwd: &Path) -> PathBuf {
    let path = Path::new(given.trim_matches('"'));
    if path.is_absolute() {
        path.to_path_buf()
    } else {
        cwd.join(path)
    }
}

/// A second start must find the first Mado's window to hand its paths over: in the moment
/// between the first taking the single-instance lock and making that window, the plugin would
/// let the second carry on as Mado itself (two Mados on one database). So a start that finds
/// the lock taken waits for the window first, two seconds at most (tauri-plugin-single-instance
/// names both after the app's identifier).
pub fn wait_for_first(identifier: &str) {
    #[cfg(windows)]
    {
        use windows_sys::Win32::Foundation::CloseHandle;
        use windows_sys::Win32::System::Threading::{OpenMutexW, SYNCHRONIZATION_SYNCHRONIZE};
        use windows_sys::Win32::UI::WindowsAndMessaging::FindWindowW;

        let lock = wide(&format!("{identifier}-sim"));
        let class = wide(&format!("{identifier}-sic"));
        let title = wide(&format!("{identifier}-siw"));
        // SAFETY: the names are NUL-terminated wide strings that outlive the calls.
        unsafe {
            let held = OpenMutexW(SYNCHRONIZATION_SYNCHRONIZE, 0, lock.as_ptr());
            if held.is_null() {
                return; // no Mado running: this one is it
            }
            CloseHandle(held);
            let until = Instant::now() + Duration::from_secs(2);
            while FindWindowW(class.as_ptr(), title.as_ptr()).is_null() && Instant::now() < until {
                thread::sleep(Duration::from_millis(10));
            }
        }
    }
    #[cfg(not(windows))]
    let _ = identifier;
}

#[cfg(windows)]
fn wide(text: &str) -> Vec<u16> {
    text.encode_utf16().chain(std::iter::once(0)).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(given: &[&str]) -> Vec<String> {
        std::iter::once("mado.exe")
            .chain(given.iter().copied())
            .map(String::from)
            .collect()
    }

    fn there<'a>(paths: &'a [&'a str]) -> impl Fn(&Path) -> bool + 'a {
        move |path| paths.iter().any(|known| Path::new(known) == path)
    }

    #[test]
    fn paths_are_taken_as_given_quoted_or_not() {
        let cwd = Path::new(r"C:\Users\owner");
        let known = [
            r"D:\Fotos del viaje\Ōsaka 夜景.jpg",
            r"\\nas\photos\Harbour.heic",
            r"D:\Trip",
        ];
        let found = paths_in(
            &args(&[
                r"D:\Fotos del viaje\Ōsaka 夜景.jpg",
                r"\\nas\photos\Harbour.heic",
                "--in-tray",
                r"D:\Trip",
            ]),
            cwd,
            there(&known),
        );
        assert_eq!(found, known);
    }

    #[test]
    fn a_path_with_spaces_given_without_quotes_is_put_back_together() {
        let cwd = Path::new(r"C:\Users\owner");
        let known = [r"D:\My Pictures\Pier at dawn.jpg", r"D:\Trip\Lake.png"];
        let found = paths_in(
            &args(&[
                r"D:\My",
                "Pictures\\Pier",
                "at",
                "dawn.jpg",
                r"D:\Trip\Lake.png",
            ]),
            cwd,
            there(&known),
        );
        assert_eq!(found, known);
    }

    #[test]
    fn a_path_not_there_is_still_handed_over_for_the_engine_to_say_so() {
        let found = paths_in(
            &args(&[r"F:\Unplugged\Pier.jpg"]),
            Path::new(r"C:\"),
            there(&[]),
        );
        assert_eq!(found, [r"F:\Unplugged\Pier.jpg"]);
    }

    #[test]
    fn a_path_from_a_terminal_is_found_where_it_was_typed() {
        let found = paths_in(
            &args(&["Pier.jpg", r"..\Lake.png"]),
            Path::new(r"D:\Trip"),
            there(&[r"D:\Trip\Pier.jpg"]),
        );
        assert_eq!(found, [r"D:\Trip\Pier.jpg", r"D:\Trip\..\Lake.png"]);
    }

    #[test]
    fn starting_with_windows_names_no_paths() {
        assert!(paths_in(&args(&["--in-tray"]), Path::new(r"C:\"), there(&[])).is_empty());
        assert!(paths_in(&args(&[]), Path::new(r"C:\"), there(&[])).is_empty());
    }

    /// A start of Explorer's for one file, as the single-instance plugin hands it over.
    fn start(file: &str) -> (Vec<String>, PathBuf) {
        (
            args(&[file]),
            PathBuf::from(r"C:\Windows\System32"), // Explorer's starts' folder
        )
    }

    #[test]
    fn what_arrives_close_together_is_one_choice() {
        let begun = Instant::now();
        let mut gathering = Gathering::default();
        let (a, cwd) = start(r"D:\Trip\a.jpg");
        gathering.arrive(a, cwd.clone(), begun);
        gathering.arrive(start(r"D:\Trip\b.jpg").0, cwd.clone(), begun + QUIET / 2);
        gathering.arrive(start(r"d:\trip\A.JPG").0, cwd, begun + QUIET / 2);

        assert!(gathering.settle(begun + QUIET).is_none());
        let settled = gathering
            .settle(begun + QUIET / 2 + QUIET)
            .expect("quiet now");
        let everything = |_: &Path| true;
        assert_eq!(
            choice_of(&settled, everything),
            [r"D:\Trip\a.jpg".to_string(), r"D:\Trip\b.jpg".to_string()]
        );
        assert!(
            gathering.settle(begun + QUIET * 9).is_none(),
            "nothing gathering now"
        );
    }

    #[test]
    fn what_arrives_after_a_quiet_spell_is_a_choice_of_its_own() {
        let begun = Instant::now();
        let mut gathering = Gathering::default();
        let (a, cwd) = start(r"D:\Trip\a.jpg");
        gathering.arrive(a, cwd.clone(), begun);
        let first = gathering.settle(begun + QUIET).expect("quiet");
        gathering.arrive(start(r"D:\Trip\b.jpg").0, cwd, begun + QUIET * 3);
        let second = gathering.settle(begun + QUIET * 4).expect("quiet again");

        assert_eq!(choice_of(&first, |_| true), [r"D:\Trip\a.jpg"]);
        assert_eq!(choice_of(&second, |_| true), [r"D:\Trip\b.jpg"]);
    }

    #[test]
    fn a_start_naming_nothing_gathers_nothing() {
        assert!(!names_anything(&args(&["--in-tray"])));
        assert!(!names_anything(&args(&[" "])));
        assert!(names_anything(&args(&[r"D:\Trip\a.jpg"])));
    }
}
