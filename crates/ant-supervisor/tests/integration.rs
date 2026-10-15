//! Supervisor <-> worker end-to-end test.
//!
//! Requires:
//!   - uv installed and on PATH
//!   - `workers/` synced (`cd workers && uv sync`)
//!
//! Skipped automatically when uv is not available.

use ant_supervisor::{Supervisor, WorkerConfig};
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

fn uv_available() -> bool {
    std::process::Command::new("uv")
        .arg("--version")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

fn repo_root() -> PathBuf {
    let here = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    here.parent().unwrap().parent().unwrap().to_path_buf()
}

#[tokio::test]
async fn supervisor_spawns_test_worker_and_echoes() {
    if !uv_available() {
        eprintln!("uv not on PATH; skipping");
        return;
    }

    let socket_dir = std::env::temp_dir().join(format!("arikizu-test-{}", std::process::id()));
    std::fs::create_dir_all(&socket_dir).unwrap();

    let supervisor = Arc::new(Supervisor::new(socket_dir.clone()).unwrap());

    let workers_dir = repo_root().join("workers");
    let config = WorkerConfig {
        name: "test".to_string(),
        python_path: PathBuf::from("uv"),
        args: vec![
            "run".to_string(),
            "--package".to_string(),
            "test-worker".to_string(),
            "python".to_string(),
            "-m".to_string(),
            "test_worker".to_string(),
        ],
        cwd: Some(workers_dir),
        env: vec![],
        max_memory_mb: None,
    };

    supervisor.spawn_worker(config).await.expect("spawn worker");

    // Give the worker a moment to send its Hello.
    tokio::time::sleep(Duration::from_millis(500)).await;

    let worker = supervisor.worker("test").expect("worker registered");
    let result = worker
        .call(
            "test.echo",
            serde_json::json!({ "message": "hello" }),
            5000,
        )
        .await
        .expect("call succeeds");

    assert_eq!(result["echo"], "hello");

    supervisor.shutdown().await.unwrap();
}
