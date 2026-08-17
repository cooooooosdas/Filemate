use std::{
    io::Write,
    net::{SocketAddr, TcpStream},
    sync::Mutex,
    thread,
    time::Duration,
};

use tauri::Manager;
use tauri_plugin_shell::{process::CommandChild, process::CommandEvent, ShellExt};
use uuid::Uuid;

struct BackendProcess {
    child: Mutex<Option<CommandChild>>,
    shutdown_token: String,
}
fn request_graceful_shutdown(token: &str) {
    let address: SocketAddr = "127.0.0.1:8001".parse().expect("valid backend address");
    if let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(300)) {
        let request = format!(
            "POST /internal/shutdown HTTP/1.1\r\n\
             Host: 127.0.0.1:8001\r\n\
             X-FileMate-Shutdown-Token: {token}\r\n\
             Content-Length: 0\r\n\
             Connection: close\r\n\r\n"
        );
        let _ = stream.write_all(request.as_bytes());
        let _ = stream.flush();
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let data_dir = app.path().app_data_dir()?;
            let archive_dir = app
                .path()
                .document_dir()
                .unwrap_or_else(|_| data_dir.clone())
                .join("FileMate");
            std::fs::create_dir_all(&data_dir)?;
            std::fs::create_dir_all(&archive_dir)?;

            let shutdown_token = Uuid::new_v4().to_string();
            let sidecar = app
                .shell()
                .sidecar("filemate-server")?
                .env("FILEMATE_DATA_DIR", &data_dir)
                .env("FILEMATE_DB_PATH", data_dir.join("filemate.db"))
                .env("FILEMATE_UPLOAD_DIR", data_dir.join("inbox"))
                .env("FILEMATE_ARCHIVE_DIR", &archive_dir)
                .env("FILEMATE_SHUTDOWN_TOKEN", &shutdown_token);
            let (mut receiver, child) = sidecar.spawn()?;

            tauri::async_runtime::spawn(async move {
                while let Some(event) = receiver.recv().await {
                    match event {
                        CommandEvent::Stdout(line) => {
                            println!("[filemate-backend] {}", String::from_utf8_lossy(&line));
                        }
                        CommandEvent::Stderr(line) => {
                            eprintln!("[filemate-backend] {}", String::from_utf8_lossy(&line));
                        }
                        _ => {}
                    }
                }
            });

            app.manage(BackendProcess {
                child: Mutex::new(Some(child)),
                shutdown_token,
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build FileMate desktop app");

    app.run(|app_handle, event| {
        if let tauri::RunEvent::Exit = event {
            let state = app_handle.state::<BackendProcess>();
            request_graceful_shutdown(&state.shutdown_token);
            thread::sleep(Duration::from_millis(500));
            if let Some(child) = state.child.lock().expect("backend state poisoned").take() {
                let _ = child.kill();
            }
        }
    });
}
