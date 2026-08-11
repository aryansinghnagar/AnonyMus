// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use anonymus_core::identity::UserIdentity;

#[tauri::command]
fn generate_user_identity() -> String {
    let identity = UserIdentity::generate();
    identity.public_key_b64()
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![generate_user_identity])
        .run(tauri::generate_context!())
        .expect("error while running tauri desktop application");
}
