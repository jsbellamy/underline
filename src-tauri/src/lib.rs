use tauri::{AppHandle, Manager};
use tauri_plugin_window_state::StateFlags;

#[tauri::command]
fn quit_app(app: AppHandle) {
    app.exit(0);
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        // Pane position is user-chosen and should persist; size and chrome come from
        // tauri.conf.json. The dock is denylisted: size and position are owned by
        // createDockWindow and dockRect, and restoring either fights that code.
        .plugin(
            tauri_plugin_window_state::Builder::default()
                .with_state_flags(StateFlags::POSITION)
                .with_denylist(&["dock"])
                .build(),
        )
        .invoke_handler(tauri::generate_handler![quit_app])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
