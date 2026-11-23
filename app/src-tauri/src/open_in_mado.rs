//! File Explorer's "Open in Mado" on pictures and folders, and Mado in Open with for the
//! pictures it reads. Written for this Windows user only (HKCU\Software\Classes, no
//! administrator), only ever Mado's own keys and values, and never which app opens a picture by
//! default: no type's default value, no UserChoice. Windows reads each value of a type from the
//! user's keys first and the PC's after, so an `.ext` key holding only Mado's OpenWithProgids
//! value leaves the PC's default as it is.
//!
//! On by default; Settings > General's "Open in Mado in File Explorer" writes them or takes them
//! away, and each start keeps them pointing at this Mado. Only an installed Mado writes them (its
//! uninstaller beside it), so a build run from the source tree never points Explorer at itself.
//! The uninstaller takes them away too (windows/hooks.nsh, `MadoForgetExplorer`), by what
//! SupportedTypes says was written. On Windows 11 the entry is under "Show more options": the
//! first menu takes only apps in a signed package with an identity, which Mado can't have.

use std::path::Path;

use serde_json::Value;
use tauri::AppHandle;

use crate::choices;

/// "Open in Mado": the verb's key, on a picture's type and on folders.
pub const VERB: &str = "Mado.Open";
/// Mado's own file type, which Open with lists Mado by.
pub const PROG_ID: &str = "Mado.Picture";
/// Mado among the applications, by its program's name.
pub const APP: &str = r"Applications\mado.exe";

/// Every picture Mado reads, by extension, camera RAW included: PICTURES, HEIF and RAW in
/// engine/src/mado/core/files.py (a test holds the two together).
pub const EXTENSIONS: &[&str] = &[
    ".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".webp", ".avif", ".tif", ".tiff", ".bmp", ".dib",
    ".gif", ".heic", ".heif", ".hif", ".3fr", ".arw", ".cr2", ".cr3", ".crw", ".dng", ".erf",
    ".iiq", ".kdc", ".mos", ".mrw", ".nef", ".nrw", ".orf", ".pef", ".raf", ".raw", ".rw2", ".rwl",
    ".sr2", ".srf", ".srw", ".x3f",
];

/// What the menu says.
const LABEL: &str = "Open in Mado";
/// Shown for any number of items: with the default ("Document"), Explorer drops a verb once
/// more than 15 are selected. Explorer still starts Mado once for each (opened.rs gathers them),
/// and starts none past 100 (measured: docs/stack/tauri.md); a folder's own entry has no limit.
const MANY: &str = "Player";
/// Where the switch's choice is kept, beside the shell's others (choices.rs).
const CHOICE: &str = "openInExplorer";

/// One value Mado writes: its key under the classes, its name ("" for the key's own), and what
/// it holds.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Entry {
    pub key: String,
    pub name: String,
    pub value: String,
}

fn entry(key: impl Into<String>, name: impl Into<String>, value: impl Into<String>) -> Entry {
    Entry {
        key: key.into(),
        name: name.into(),
        value: value.into(),
    }
}

/// Every value Mado writes, for the program at `exe`.
pub fn entries(exe: &Path) -> Vec<Entry> {
    let exe = exe.display();
    let command = format!("\"{exe}\" \"%1\"");
    let icon = format!("{exe},0");
    let verb = |base: &str| -> Vec<Entry> {
        let key = format!(r"{base}\shell\{VERB}");
        vec![
            entry(&key, "", LABEL),
            entry(&key, "Icon", &icon),
            entry(&key, "MultiSelectModel", MANY),
            entry(format!(r"{key}\command"), "", &command),
        ]
    };
    let mut found = Vec::new();
    for extension in EXTENSIONS {
        // SupportedTypes first: the uninstaller goes by it to take Open with's values away, so
        // it names every type that has one, even had writing stopped half way.
        found.push(entry(format!(r"{APP}\SupportedTypes"), *extension, ""));
        found.push(entry(format!(r"{extension}\OpenWithProgids"), PROG_ID, ""));
        found.extend(verb(&format!(r"SystemFileAssociations\{extension}")));
    }
    found.extend(verb("Directory"));
    found.push(entry(APP, "FriendlyAppName", "Mado"));
    found.push(entry(format!(r"{APP}\DefaultIcon"), "", &icon));
    found.push(entry(format!(r"{APP}\shell\open\command"), "", &command));
    found.push(entry(format!(r"{PROG_ID}\DefaultIcon"), "", &icon));
    found.push(entry(
        format!(r"{PROG_ID}\shell\open\command"),
        "",
        &command,
    ));
    found
}

/// Whether the choice is on: Mado in File Explorer, as it is till the owner turns it off.
pub fn chosen(app: &AppHandle) -> bool {
    choices::read(app, CHOICE)
        .and_then(|value| value.as_bool())
        .unwrap_or(true)
}

/// Whether "Open in Mado" is in File Explorer: the choice kept.
#[tauri::command]
pub fn open_in_explorer(app: AppHandle) -> Result<bool, String> {
    Ok(chosen(&app))
}

/// Puts "Open in Mado" in File Explorer, or takes it away: from now, and at every start. Off the
/// main thread, as it writes many values.
#[tauri::command]
pub async fn set_open_in_explorer(app: AppHandle, on: bool) -> Result<bool, String> {
    choices::save(&app, CHOICE, Value::Bool(on))?;
    #[cfg(windows)]
    if let Some(exe) = installed() {
        tauri::async_runtime::spawn_blocking(move || windows::apply(on, &exe))
            .await
            .map_err(|error| error.to_string())?
            .map_err(|error| format!("Windows didn't take that ({error}). Try again."))?;
    }
    Ok(on)
}

/// At start: the keys as the choice says, pointing at this Mado (moved or updated, say), on a
/// thread of their own.
pub fn keep_up(app: &AppHandle) {
    #[cfg(windows)]
    if let Some(exe) = installed() {
        let on = chosen(app);
        std::thread::spawn(move || {
            if let Err(error) = windows::apply(on, &exe) {
                eprintln!("Mado couldn't keep File Explorer's \"Open in Mado\" ({error})");
            }
        });
    }
    #[cfg(not(windows))]
    let _ = app;
}

/// This Mado's program, when it runs installed: its uninstaller is beside it.
fn installed() -> Option<std::path::PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let beside = exe.parent()?.join("uninstall.exe");
    beside.is_file().then_some(exe)
}

#[cfg(windows)]
pub mod windows {
    //! Writing and taking away the keys, under a root of classes: HKCU\Software\Classes, or a
    //! test's own.

    use std::path::Path;

    use windows_registry::{CURRENT_USER, Key, Result};

    use super::{APP, EXTENSIONS, PROG_ID, VERB, entries};

    /// The keys as `on` says, for the program at `exe`, under the user's own classes; Explorer
    /// is told once something changed.
    pub fn apply(on: bool, exe: &Path) -> Result<()> {
        let classes = CURRENT_USER.create(r"Software\Classes")?;
        let changed = if on {
            let fresh = !written(&classes, exe);
            if fresh {
                forget(&classes)?;
                write(&classes, exe)?;
            }
            fresh
        } else {
            forget(&classes)?
        };
        if changed {
            tell_explorer();
        }
        Ok(())
    }

    /// Writes every value Mado's keys hold.
    pub fn write(classes: &Key, exe: &Path) -> Result<()> {
        for each in entries(exe) {
            classes
                .create(&each.key)?
                .set_string(&each.name, &each.value)?;
        }
        Ok(())
    }

    /// Whether every value is there as Mado would write it for `exe`.
    pub fn written(classes: &Key, exe: &Path) -> bool {
        entries(exe).iter().all(|each| {
            classes
                .open(&each.key)
                .and_then(|key| key.get_string(&each.name))
                .is_ok_and(|value| value == each.value)
        })
    }

    /// Takes away Mado's keys and values, and then each key above them that holds nothing else
    /// now: "Open in Mado" under any type (an older Mado's too), Open with's value under the
    /// types it says it was written for, Mado's file type and its place among the applications.
    /// True when there was anything to take away.
    pub fn forget(classes: &Key) -> Result<bool> {
        let mut any = false;
        if let Ok(associations) = classes.open("SystemFileAssociations") {
            let types: Vec<String> = associations.keys()?.collect();
            for kind in types {
                any |= remove_tree(
                    classes,
                    &format!(r"SystemFileAssociations\{kind}\shell\{VERB}"),
                )?;
            }
        }
        any |= remove_tree(classes, &format!(r"Directory\shell\{VERB}"))?;
        let mut types: Vec<String> = EXTENSIONS.iter().map(|each| each.to_string()).collect();
        if let Ok(supported) = classes.open(format!(r"{APP}\SupportedTypes")) {
            types.extend(supported.values()?.map(|(name, _)| name));
        }
        for kind in types {
            let key = format!(r"{kind}\OpenWithProgids");
            if let Ok(found) = classes.options().read().write().open(&key)
                && found.get_type(PROG_ID).is_ok()
            {
                found.remove_value(PROG_ID)?;
                prune(classes, &key)?;
                any = true;
            }
        }
        any |= remove_tree(classes, APP)?;
        any |= remove_tree(classes, PROG_ID)?;
        Ok(any)
    }

    /// Whether a key is there.
    pub fn exists(classes: &Key, key: &str) -> bool {
        classes.open(key).is_ok()
    }

    /// Takes a key away with all it holds, if it's there, then the keys above it left empty.
    /// True when it was there.
    fn remove_tree(classes: &Key, key: &str) -> Result<bool> {
        if !exists(classes, key) {
            return Ok(false);
        }
        classes.remove_tree(key)?;
        if let Some((parent, _)) = key.rsplit_once('\\') {
            prune(classes, parent)?;
        }
        Ok(true)
    }

    /// Takes a key away while it holds nothing, then its parent likewise, up to the classes.
    fn prune(classes: &Key, key: &str) -> Result<()> {
        let mut at = key.to_string();
        loop {
            let Ok(found) = classes.open(&at) else {
                return Ok(());
            };
            let empty = found.keys()?.next().is_none() && found.values()?.next().is_none();
            drop(found);
            if !empty {
                return Ok(());
            }
            classes.remove_tree(&at)?;
            match at.rsplit_once('\\') {
                Some((parent, _)) => at = parent.to_string(),
                None => return Ok(()),
            }
        }
    }

    /// Tells Explorer the types' apps changed, so Open with and the menu show it now.
    fn tell_explorer() {
        use windows_sys::Win32::UI::Shell::{SHCNE_ASSOCCHANGED, SHCNF_IDLIST, SHChangeNotify};
        // SAFETY: no items are passed with this event.
        unsafe {
            SHChangeNotify(
                SHCNE_ASSOCCHANGED as i32,
                SHCNF_IDLIST,
                std::ptr::null(),
                std::ptr::null(),
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    const EXE: &str = r"C:\Users\owner\AppData\Local\Programs\Mado\mado.exe";

    #[test]
    fn mado_offers_itself_for_every_picture_the_engine_reads() {
        let files = std::fs::read_to_string(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../engine/src/mado/core/files.py"
        ))
        .expect("the engine's list of formats");
        let mut engine: Vec<String> = files
            .split(['"', '\''])
            .filter(|word| word.starts_with('.') && word.len() > 2 && word.len() < 7)
            .filter(|word| word[1..].chars().all(|c| c.is_ascii_alphanumeric()))
            .map(str::to_string)
            .collect();
        engine.sort();
        engine.dedup();
        let mut shell: Vec<String> = EXTENSIONS.iter().map(|each| each.to_string()).collect();
        shell.sort();
        assert_eq!(shell, engine);
    }

    #[test]
    fn the_menu_entry_and_open_with_point_at_this_mado_and_never_set_a_default() {
        let found = entries(&PathBuf::from(EXE));
        let command = format!("\"{EXE}\" \"%1\"");
        let jpg = r"SystemFileAssociations\.jpg\shell\Mado.Open";
        assert!(found.contains(&entry(jpg, "", "Open in Mado")));
        assert!(found.contains(&entry(jpg, "MultiSelectModel", "Player")));
        assert!(found.contains(&entry(format!(r"{jpg}\command"), "", &command)));
        assert!(found.contains(&entry(r"Directory\shell\Mado.Open\command", "", &command)));
        assert!(found.contains(&entry(r".cr3\OpenWithProgids", "Mado.Picture", "")));
        assert!(found.contains(&entry(r"Applications\mado.exe\SupportedTypes", ".heic", "")));
        // Nothing sets which app opens a type: no type's own value, nothing under FileExts.
        for each in &found {
            let type_default = each.key.starts_with('.') && !each.key.contains('\\');
            assert!(!type_default, "{each:?}");
            assert!(!each.key.contains("FileExts") && !each.key.contains("UserChoice"));
        }
    }

    #[cfg(windows)]
    mod registry {
        use super::super::windows::{exists, forget, write, written};
        use super::super::{APP, EXTENSIONS, PROG_ID};
        use super::EXE;
        use std::path::PathBuf;
        use std::sync::atomic::{AtomicU32, Ordering};
        use windows_registry::{CURRENT_USER, Key};

        /// A root of classes of a test's own, in HKCU\Software, taken away after: never the
        /// owner's real classes.
        struct Root {
            path: String,
            classes: Key,
        }

        impl Root {
            fn new() -> Self {
                static COUNT: AtomicU32 = AtomicU32::new(0);
                let number = COUNT.fetch_add(1, Ordering::Relaxed);
                let path = format!(
                    r"Software\Mado registry test {} {number}",
                    std::process::id()
                );
                let classes = CURRENT_USER
                    .create(format!(r"{path}\Classes"))
                    .expect("a test root");
                Root { path, classes }
            }
        }

        impl Drop for Root {
            fn drop(&mut self) {
                let _ = CURRENT_USER.remove_tree(&self.path);
            }
        }

        /// Every key and value under a root, as text, to compare before and after.
        fn listing(key: &Key, at: &str, into: &mut Vec<String>) {
            let mut values: Vec<String> = key
                .values()
                .unwrap()
                .map(|(name, value)| format!("{at} [{name}] = {:?}", value.ty()))
                .collect();
            values.sort();
            into.push(at.to_string());
            into.extend(values);
            let mut keys: Vec<String> = key.keys().unwrap().collect();
            keys.sort();
            for name in keys {
                listing(&key.open(&name).unwrap(), &format!(r"{at}\{name}"), into);
            }
        }

        fn everything(classes: &Key) -> Vec<String> {
            let mut found = Vec::new();
            listing(classes, "", &mut found);
            found
        }

        /// What another app and Windows keep there already: other apps' Open with values, a
        /// type's own default, other verbs.
        fn others(classes: &Key) {
            let jpg = classes.create(".jpg").unwrap();
            jpg.set_string("", "jpegfile").unwrap();
            jpg.create("OpenWithProgids")
                .unwrap()
                .set_string("AppX43hnxtbyyps62jhe9sqpdzxn1790zetc", "")
                .unwrap();
            classes
                .create(r"SystemFileAssociations\.jpg\shell\edit\command")
                .unwrap()
                .set_string("", r#""C:\Paint\paint.exe" "%1""#)
                .unwrap();
            classes
                .create(r"Directory\shell\find")
                .unwrap()
                .set_string("", "Search")
                .unwrap();
        }

        #[test]
        fn mado_writes_its_keys_and_takes_away_exactly_them() {
            let root = Root::new();
            others(&root.classes);
            let before = everything(&root.classes);
            let exe = PathBuf::from(EXE);

            write(&root.classes, &exe).unwrap();

            assert!(written(&root.classes, &exe));
            assert!(!written(
                &root.classes,
                &PathBuf::from(r"D:\Elsewhere\mado.exe")
            ));
            let jpg = root.classes.open(".jpg").unwrap();
            assert_eq!(jpg.get_string("").unwrap(), "jpegfile"); // the type's default as it was
            let cr3 = root.classes.open(r".cr3\OpenWithProgids").unwrap();
            assert_eq!(cr3.get_string(PROG_ID).unwrap(), "");
            assert!(exists(&root.classes, APP));

            forget(&root.classes).unwrap();

            assert_eq!(everything(&root.classes), before);
        }

        #[test]
        fn taking_them_away_twice_or_before_they_were_written_changes_nothing() {
            let root = Root::new();
            others(&root.classes);
            let before = everything(&root.classes);

            assert!(
                !forget(&root.classes).unwrap(),
                "nothing of Mado's was there"
            );
            write(&root.classes, &PathBuf::from(EXE)).unwrap();
            assert!(forget(&root.classes).unwrap());
            assert!(!forget(&root.classes).unwrap());

            assert_eq!(everything(&root.classes), before);
        }

        #[test]
        fn an_older_mados_types_go_too() {
            let root = Root::new();
            let exe = PathBuf::from(EXE);
            write(&root.classes, &exe).unwrap();
            // A type an older Mado offered itself for, that this one doesn't.
            let old = root
                .classes
                .create(r"SystemFileAssociations\.jxl\shell\Mado.Open")
                .unwrap();
            old.set_string("", "Open in Mado").unwrap();
            root.classes
                .create(r".jxl\OpenWithProgids")
                .unwrap()
                .set_string(PROG_ID, "")
                .unwrap();
            root.classes
                .create(format!(r"{APP}\SupportedTypes"))
                .unwrap()
                .set_string(".jxl", "")
                .unwrap();
            assert!(!EXTENSIONS.contains(&".jxl"));

            forget(&root.classes).unwrap();

            assert_eq!(everything(&root.classes), [String::new()]);
        }
    }
}
