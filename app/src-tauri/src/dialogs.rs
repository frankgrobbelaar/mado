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
