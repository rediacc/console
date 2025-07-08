// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::process::Command;
use std::fs;
use std::path::Path;

#[derive(Debug, Serialize, Deserialize)]
struct CommandResult {
    success: bool,
    output: String,
    error: String,
}

// Execute Python script file
#[tauri::command]
async fn execute_python_script(
    script_path: String,
    args: Vec<String>,
) -> Result<CommandResult, String> {
    let output = Command::new("python3")
        .arg(&script_path)
        .args(&args)
        .output()
        .or_else(|_| Command::new("python")
            .arg(&script_path)
            .args(&args)
            .output())
        .map_err(|e| format!("Failed to execute Python script: {}", e))?;

    Ok(CommandResult {
        success: output.status.success(),
        output: String::from_utf8_lossy(&output.stdout).to_string(),
        error: String::from_utf8_lossy(&output.stderr).to_string(),
    })
}

// Execute sync command
#[tauri::command]
async fn sync_command(
    action: String,
    local_path: String,
    machine: String,
    repo: String,
    options: Vec<String>,
) -> Result<CommandResult, String> {
    let mut args = vec![action];
    args.push("--local".to_string());
    args.push(local_path);
    args.push("--machine".to_string());
    args.push(machine);
    args.push("--repo".to_string());
    args.push(repo);
    args.extend(options);

    let output = Command::new("rediacc-cli-sync")
        .args(&args)
        .output()
        .map_err(|e| format!("Failed to execute sync command: {}", e))?;

    Ok(CommandResult {
        success: output.status.success(),
        output: String::from_utf8_lossy(&output.stdout).to_string(),
        error: String::from_utf8_lossy(&output.stderr).to_string(),
    })
}

// Execute terminal command
#[tauri::command]
async fn terminal_command(
    machine: String,
    repo: Option<String>,
    command: Option<String>,
) -> Result<CommandResult, String> {
    let mut args = vec!["--machine".to_string(), machine];
    
    if let Some(r) = repo {
        args.push("--repo".to_string());
        args.push(r);
    }
    
    if let Some(cmd) = command {
        args.push("--command".to_string());
        args.push(cmd);
    }

    let output = Command::new("rediacc-cli-term")
        .args(&args)
        .output()
        .map_err(|e| format!("Failed to execute terminal command: {}", e))?;

    Ok(CommandResult {
        success: output.status.success(),
        output: String::from_utf8_lossy(&output.stdout).to_string(),
        error: String::from_utf8_lossy(&output.stderr).to_string(),
    })
}

// Check if Python is installed
#[tauri::command]
async fn check_python_installed() -> Result<bool, String> {
    let output = Command::new("python3")
        .arg("--version")
        .output()
        .or_else(|_| Command::new("python").arg("--version").output());

    match output {
        Ok(output) => Ok(output.status.success()),
        Err(_) => Ok(false),
    }
}

// Check if CLI is installed
#[tauri::command]
async fn check_cli_installed() -> Result<bool, String> {
    let output = Command::new("rediacc-cli")
        .arg("--version")
        .output();

    match output {
        Ok(output) => Ok(output.status.success()),
        Err(_) => Ok(false),
    }
}

// List local directories
#[tauri::command]
async fn list_local_directories(path: String) -> Result<Vec<String>, String> {
    let path = Path::new(&path);
    
    if !path.exists() {
        return Err("Path does not exist".to_string());
    }
    
    if !path.is_dir() {
        return Err("Path is not a directory".to_string());
    }
    
    let mut directories = Vec::new();
    
    match fs::read_dir(path) {
        Ok(entries) => {
            for entry in entries {
                if let Ok(entry) = entry {
                    if let Ok(metadata) = entry.metadata() {
                        if metadata.is_dir() {
                            if let Some(name) = entry.file_name().to_str() {
                                directories.push(name.to_string());
                            }
                        }
                    }
                }
            }
        }
        Err(e) => return Err(format!("Failed to read directory: {}", e)),
    }
    
    directories.sort();
    Ok(directories)
}

// Detect Linux distribution
#[cfg(target_os = "linux")]
#[tauri::command]
async fn detect_linux_distro() -> Result<String, String> {
    let output = Command::new("lsb_release")
        .arg("-d")
        .output()
        .map_err(|e| format!("Failed to detect Linux distribution: {}", e))?;

    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
    } else {
        // Fallback to reading /etc/os-release
        match fs::read_to_string("/etc/os-release") {
            Ok(content) => {
                for line in content.lines() {
                    if line.starts_with("PRETTY_NAME=") {
                        return Ok(line.replace("PRETTY_NAME=", "").trim_matches('"').to_string());
                    }
                }
                Ok("Unknown Linux".to_string())
            }
            Err(_) => Ok("Unknown Linux".to_string()),
        }
    }
}

// Execute Python CLI commands
#[tauri::command]
async fn execute_python_command(
    script: String,
    args: Vec<String>,
) -> Result<CommandResult, String> {
    let output = Command::new("python3")
        .arg(script)
        .args(args)
        .output()
        .map_err(|e| format!("Failed to execute Python command: {}", e))?;

    Ok(CommandResult {
        success: output.status.success(),
        output: String::from_utf8_lossy(&output.stdout).to_string(),
        error: String::from_utf8_lossy(&output.stderr).to_string(),
    })
}

// Execute Rediacc CLI commands
#[tauri::command]
async fn execute_rediacc_cli(
    command: String,
    args: Vec<String>,
) -> Result<CommandResult, String> {
    let cli_path = match command.as_str() {
        "sync" => "rediacc-cli-sync",
        "term" => "rediacc-cli-term",
        "plugin" => "rediacc-cli-plugin",
        _ => "rediacc-cli",
    };

    let output = Command::new(cli_path)
        .args(args)
        .output()
        .map_err(|e| format!("Failed to execute CLI command: {}", e))?;

    Ok(CommandResult {
        success: output.status.success(),
        output: String::from_utf8_lossy(&output.stdout).to_string(),
        error: String::from_utf8_lossy(&output.stderr).to_string(),
    })
}

// Execute shell commands with proper escaping
#[tauri::command]
async fn execute_shell_command(command: String) -> Result<CommandResult, String> {
    let output = if cfg!(target_os = "windows") {
        Command::new("cmd")
            .args(["/C", &command])
            .output()
            .map_err(|e| format!("Failed to execute command: {}", e))?
    } else {
        Command::new("sh")
            .arg("-c")
            .arg(&command)
            .output()
            .map_err(|e| format!("Failed to execute command: {}", e))?
    };

    Ok(CommandResult {
        success: output.status.success(),
        output: String::from_utf8_lossy(&output.stdout).to_string(),
        error: String::from_utf8_lossy(&output.stderr).to_string(),
    })
}

// Check if Python is available
#[tauri::command]
async fn check_python_available() -> Result<bool, String> {
    let output = Command::new("python3")
        .arg("--version")
        .output()
        .or_else(|_| Command::new("python").arg("--version").output());

    match output {
        Ok(output) => Ok(output.status.success()),
        Err(_) => Ok(false),
    }
}

// Get Python version
#[tauri::command]
async fn get_python_version() -> Result<String, String> {
    let output = Command::new("python3")
        .arg("--version")
        .output()
        .or_else(|_| Command::new("python").arg("--version").output())
        .map_err(|e| format!("Python not found: {}", e))?;

    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

// Check if Rediacc CLI is available
#[tauri::command]
async fn check_rediacc_cli_available() -> Result<bool, String> {
    let output = Command::new("rediacc-cli")
        .arg("--version")
        .output();

    match output {
        Ok(output) => Ok(output.status.success()),
        Err(_) => Ok(false),
    }
}

// Get system information
#[tauri::command]
async fn get_system_info() -> Result<serde_json::Value, String> {
    Ok(serde_json::json!({
        "platform": std::env::consts::OS,
        "arch": std::env::consts::ARCH,
        "family": std::env::consts::FAMILY,
    }))
}

fn main() {
    #[allow(unused_mut)]
    let mut builder = tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            execute_python_command,
            execute_python_script,
            execute_rediacc_cli,
            execute_shell_command,
            sync_command,
            terminal_command,
            check_python_available,
            check_python_installed,
            check_cli_installed,
            get_python_version,
            check_rediacc_cli_available,
            get_system_info,
            list_local_directories,
        ]);
    
    #[cfg(target_os = "linux")]
    {
        builder = builder.invoke_handler(tauri::generate_handler![
            execute_python_command,
            execute_python_script,
            execute_rediacc_cli,
            execute_shell_command,
            sync_command,
            terminal_command,
            check_python_available,
            check_python_installed,
            check_cli_installed,
            get_python_version,
            check_rediacc_cli_available,
            get_system_info,
            list_local_directories,
            detect_linux_distro,
        ]);
    }
    
    builder
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}