use tauri_plugin_window_state::StateFlags;

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
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
