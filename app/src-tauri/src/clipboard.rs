//! Files copied in File Explorer, for pasting into Mado. The window can't learn their paths (a
//! web page is never given them), so the shell reads the clipboard's list of files (CF_HDROP)
//! itself. A picture or words on the clipboard come to the window as they would to any page.
//!
//! Read through windows-sys, the windows crate's own bindings, already in Mado's build through
//! Tauri: the Tauri clipboard plugin reads only words and pictures, not a list of files.

/// The clipboard's list of files: what Explorer's Copy puts there.
const CF_HDROP: u32 = 15;
/// DROPFILES, before its list: where the list starts (4 bytes), a point (8), a flag (4), and
/// whether the names are wide (4).
const HEADER: usize = 20;

/// The paths of the files copied in File Explorer, in the order they were copied; none when
/// the clipboard holds anything else. Read off the main thread: another app holding the
/// clipboard a moment makes it wait.
#[tauri::command]
pub async fn clipboard_files() -> Result<Vec<String>, String> {
    #[cfg(windows)]
    {
        tauri::async_runtime::spawn_blocking(read)
            .await
            .map_err(|error| error.to_string())?
            .map(|bytes| bytes.map(|list| files_in(&list)).unwrap_or_default())
    }
    #[cfg(not(windows))]
    {
        Ok(Vec::new())
    }
}

/// The clipboard's DROPFILES, as bytes; none when it holds no files.
#[cfg(windows)]
fn read() -> Result<Option<Vec<u8>>, String> {
    use std::thread;
    use std::time::Duration;
    use windows_sys::Win32::System::DataExchange::{
        CloseClipboard, GetClipboardData, IsClipboardFormatAvailable, OpenClipboard,
    };
    use windows_sys::Win32::System::Memory::{GlobalLock, GlobalSize, GlobalUnlock};

    // SAFETY: the clipboard is opened, read and closed here; what GetClipboardData gives stays
    // the clipboard's, read only while locked.
    unsafe {
        if IsClipboardFormatAvailable(CF_HDROP) == 0 {
            return Ok(None);
        }
        // Another app may have the clipboard open for a moment.
        let mut open = false;
        for _ in 0..10 {
            if OpenClipboard(std::ptr::null_mut()) != 0 {
                open = true;
                break;
            }
            thread::sleep(Duration::from_millis(20));
        }
        if !open {
            return Err("Another app is using the clipboard. Try pasting again.".into());
        }
        let handle = GetClipboardData(CF_HDROP);
        let mut bytes = None;
        if !handle.is_null() {
            let size = GlobalSize(handle);
            let data = GlobalLock(handle) as *const u8;
            if !data.is_null() {
                bytes = Some(std::slice::from_raw_parts(data, size).to_vec());
                GlobalUnlock(handle);
            }
        }
        CloseClipboard();
        Ok(bytes)
    }
}

/// The paths in a DROPFILES: names one after another from where it says, each ending in a nought,
/// the list in two. Explorer writes them wide (UTF-16); an old app's narrow ones are read as they
/// come.
fn files_in(drop: &[u8]) -> Vec<String> {
    if drop.len() < HEADER {
        return Vec::new();
    }
    let word = |at: usize| u32::from_le_bytes([drop[at], drop[at + 1], drop[at + 2], drop[at + 3]]);
    let start = word(0) as usize;
    let wide = word(16) != 0;
    let Some(list) = drop.get(start..) else {
        return Vec::new();
    };
    let names: Vec<String> = if wide {
        let units: Vec<u16> = list
            .as_chunks::<2>()
            .0
            .iter()
            .map(|pair| u16::from_le_bytes(*pair))
            .collect();
        units
            .split(|unit| *unit == 0)
            .take_while(|name| !name.is_empty())
            .map(String::from_utf16_lossy)
            .collect()
    } else {
        list.split(|byte| *byte == 0)
            .take_while(|name| !name.is_empty())
            .map(|name| String::from_utf8_lossy(name).into_owned())
            .collect()
    };
    names
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A DROPFILES as Explorer writes it for these files.
    fn dropped(files: &[&str], wide: bool) -> Vec<u8> {
        let mut bytes = Vec::new();
        bytes.extend_from_slice(&(HEADER as u32).to_le_bytes());
        bytes.extend_from_slice(&[0; 12]); // the point and the flag
        bytes.extend_from_slice(&u32::from(wide).to_le_bytes());
        for file in files {
            if wide {
                for unit in file.encode_utf16().chain(std::iter::once(0)) {
                    bytes.extend_from_slice(&unit.to_le_bytes());
                }
            } else {
                bytes.extend_from_slice(file.as_bytes());
                bytes.push(0);
            }
        }
        bytes.extend_from_slice(if wide { &[0, 0] } else { &[0] });
        bytes
    }

    #[test]
    fn the_files_copied_in_explorer_come_back_as_their_paths() {
        let files = [
            r"D:\Fotos del viaje\Ōsaka 夜景.jpg",
            r"\\nas\photos\Harbour at dusk.heic",
            r"D:\Holiday",
        ];
        assert_eq!(files_in(&dropped(&files, true)), files);
    }

    #[test]
    fn an_old_apps_narrow_names_are_read_too() {
        assert_eq!(
            files_in(&dropped(&[r"D:\Trip\Pier.jpg"], false)),
            [r"D:\Trip\Pier.jpg"]
        );
    }

    #[test]
    fn a_damaged_list_gives_nothing_rather_than_a_fault() {
        assert!(files_in(&[1, 2, 3]).is_empty());
        let mut far = dropped(&[r"D:\Trip\Pier.jpg"], true);
        far[0] = 250; // its list would start past its end
        assert!(files_in(&far).is_empty());
        assert!(files_in(&dropped(&[], true)).is_empty());
    }
}
