//! Windows' own dialogs. The shell opens them, so the window needs no dialog permission.

use tauri::AppHandle;
use tauri_plugin_dialog::DialogExt;

/// Asks for a folder with Windows' folder picker. `None` when it's cancelled.
#[tauri::command]
pub async fn pick_folder(app: AppHandle, title: String) -> Result<Option<String>, String> {
    let picked = tauri::async_runtime::spawn_blocking(move || {
        app.dialog().file().set_title(title).blocking_pick_folder()
    })
    .await
    .map_err(|error| error.to_string())?;
    Ok(picked
        .and_then(|folder| folder.into_path().ok())
        .map(|folder| folder.display().to_string()))
}

/// The pictures Mado makes, as Windows' file picker offers them: phones', cameras', scanners'
/// and the web's. Camera RAW isn't offered, as Mado can't read it yet; dropped, it's left out
/// with a sentence saying so.
const PICTURES: &[&str] = &[
    "jpg", "jpeg", "jpe", "jfif", "png", "heic", "heif", "hif", "webp", "avif", "tif", "tiff",
    "bmp", "gif",
];

/// Asks for pictures with Windows' file picker, as many as are wanted. Empty when it's
/// cancelled.
#[tauri::command]
pub async fn pick_pictures(app: AppHandle, title: String) -> Result<Vec<String>, String> {
    let picked = tauri::async_runtime::spawn_blocking(move || {
        app.dialog()
            .file()
            .set_title(title)
            .add_filter("Pictures", PICTURES)
            .blocking_pick_files()
    })
    .await
    .map_err(|error| error.to_string())?;
    Ok(paths_of(picked.unwrap_or_default()))
}

/// The files picked, as paths the engine reads.
fn paths_of(picked: Vec<tauri_plugin_dialog::FilePath>) -> Vec<String> {
    picked
        .into_iter()
        .filter_map(|file| file.into_path().ok())
        .map(|file| file.display().to_string())
        .collect()
}

/// Asks for a Mado export (its zip) with Windows' file picker. `None` when it's cancelled.
#[tauri::command]
pub async fn pick_export(app: AppHandle, title: String) -> Result<Option<String>, String> {
    pick_file(app, title, "Mado export", "zip").await
}

/// Asks for a look (a .cube file, as Adobe's apps and DaVinci Resolve write them) with Windows'
/// file picker. `None` when it's cancelled.
#[tauri::command]
pub async fn pick_cube(app: AppHandle, title: String) -> Result<Option<String>, String> {
    pick_file(app, title, "Look (.cube)", "cube").await
}

/// One file of a kind, picked with Windows' file picker.
async fn pick_file(
    app: AppHandle,
    title: String,
    kind: &'static str,
    extension: &'static str,
) -> Result<Option<String>, String> {
    let picked = tauri::async_runtime::spawn_blocking(move || {
        app.dialog()
            .file()
            .set_title(title)
            .add_filter(kind, &[extension])
            .blocking_pick_file()
    })
    .await
    .map_err(|error| error.to_string())?;
    Ok(picked
        .and_then(|file| file.into_path().ok())
        .map(|file| file.display().to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;
    use tauri_plugin_dialog::FilePath;

    #[test]
    fn the_pictures_picked_come_back_as_paths() {
        let picked = vec![
            FilePath::Path(PathBuf::from(r"D:\Pictures\Holiday\Warm dunes.jpg")),
            FilePath::Path(PathBuf::from(r"D:\Pictures\Holiday\Still lake.heic")),
        ];
        assert_eq!(
            paths_of(picked),
            vec![
                r"D:\Pictures\Holiday\Warm dunes.jpg".to_string(),
                r"D:\Pictures\Holiday\Still lake.heic".to_string(),
            ]
        );
    }

    #[test]
    fn the_picker_offers_every_kind_of_picture_mado_reads() {
        for kind in ["jpg", "heic", "png", "webp", "avif", "tif"] {
            assert!(PICTURES.contains(&kind), "{kind}");
        }
    }
}
