// Mado's desktop shell: one window for the UI, with the engine running beside it.
// See docs/stack/tauri.md.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod choices;
mod clipboard;
mod dialogs;
mod engine;
mod explorer;
mod links;
mod look;
mod open_in_mado;
mod opened;
mod process;
mod screens;
mod tray;
mod updater;

use std::path::Path;

use tauri::{Manager, RunEvent, WindowEvent};

fn main() {
    let context = tauri::generate_context!();
    // A second start hands its pictures to the Mado running: it waits for that Mado's window if
    // it's only just starting, rather than run as a second Mado (opened.rs).
    opened::wait_for_first(&context.config().identifier);
    let app = tauri::Builder::default()
        // Opening Mado again shows the window that's already open (or waiting in the tray), with
        // the pictures it was given: two copies would share one database.
        .plugin(tauri_plugin_single_instance::init(|app, args, cwd| {
            opened::arrived(app, &args, Path::new(&cwd));
            tray::show(app);
        }))
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(
            tauri_plugin_autostart::Builder::new()
                .arg(tray::IN_TRAY)
                .build(),
        )
        .manage(engine::Engine::default())
        .manage(updater::PendingUpdate::default())
        .manage(tray::Tray::default())
        .manage(opened::Opened::default())
        .invoke_handler(tauri::generate_handler![
            engine::engine_status,
            engine::restart_engine,
            updater::prepare_update,
            updater::install_update,
            links::open_downloads_page,
            dialogs::pick_folder,
            dialogs::pick_pictures,
            dialogs::pick_export,
            dialogs::pick_cube,
            explorer::open_folder,
            explorer::show_in_folder,
            explorer::show_files,
            tray::start_with_windows,
            tray::set_start_with_windows,
            tray::keep_in_tray,
            tray::set_keep_in_tray,
            look::look,
            look::set_look,
            screens::screens,
            opened::take_opened,
            clipboard::clipboard_files,
            open_in_mado::open_in_explorer,
            open_in_mado::set_open_in_explorer,
        ])
        .on_window_event(|window, event| match event {
            // As the owner chose in Settings > General, closing the window keeps Mado working in
            // the tray, or quits it.
            WindowEvent::CloseRequested { api, .. }
                if window.app_handle().state::<tray::Tray>().keeps() =>
            {
                api.prevent_close();
                let _ = window.hide();
            }
            // Light or dark changed: Windows' own setting, or the owner's choice.
            WindowEvent::ThemeChanged(theme) => look::follow(window, *theme),
            _ => {}
        })
        .setup(|app| {
            let args = arguments();
            tray::set_up(app.handle())?;
            look::make_window(app.handle())?;
            if !tray::started_in_tray(args.iter().cloned()) {
                tray::show(app.handle());
            }
            engine::start(app.handle().clone());
            open_in_mado::keep_up(app.handle());
            // The pictures Mado was started with: the window takes them once it's ready.
            let here = std::env::current_dir().unwrap_or_default();
            opened::arrived(app.handle(), &args, &here);
            Ok(())
        })
        .build(context)
        .expect("Mado's window couldn't be created");

    app.run(|app, event| {
        if let RunEvent::Exit = event {
            app.state::<engine::Engine>().stop();
        }
    });
}

/// Mado's own arguments, as Windows gave them: a name Windows can't put in letters is kept as
/// near as it can be, rather than stopping Mado.
fn arguments() -> Vec<String> {
    std::env::args_os()
        .map(|arg| arg.to_string_lossy().into_owned())
        .collect()
}
