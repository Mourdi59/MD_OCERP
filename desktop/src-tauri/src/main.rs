// OpenConstructionERP Desktop, Tauri v2 application.
//
// Manages the FastAPI backend as a sidecar process.
// The React frontend loads in a native webview window.
// Backend communicates via http://localhost:{port}/api/
//
// Robustness contract (why this file is defensive):
//   In release builds the process has no console (windows_subsystem = "windows"),
//   so any panic dies silently and, if it happens inside setup(), the window
//   never appears. That is exactly the "I click the icon and nothing happens"
//   failure. So setup() must NEVER panic: every fallible step is handled, the
//   splash window is kept open, a human-readable error is shown via setError(),
//   and a full diagnostic log is always written to
//   ~/.openestimate/desktop-launcher.log (alongside the backend's own data).

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use tauri::{
    menu::{MenuBuilder, MenuItemBuilder, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, RunEvent,
};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// Asks GitHub, once per start, whether a newer release exists, and offers it in
/// the failure window. Kept in its own file because it must be able to speak
/// when nothing else in this one worked.
mod update_check;

struct AppState {
    /// Handle to the spawned backend process so it survives past setup() and
    /// can be killed when the app exits.
    backend_child: Mutex<Option<CommandChild>>,
    /// The local URL the app is served on (e.g. http://127.0.0.1:8732/).
    ///
    /// Resolved once the backend is healthy and the webview is pointed at it.
    /// Stored here so the tray menu and the "open in your browser" command can
    /// hand the user the exact same address the app window is showing, even
    /// though the port is chosen dynamically at startup.
    app_url: Mutex<Option<String>>,
    /// Set the moment the app decides to exit, before the sidecar is stopped.
    ///
    /// Everything that watches the backend has to be able to tell a crash from
    /// a shutdown we asked for. Without this flag the watchers below would see
    /// the very kill we just issued and announce to a user who is closing the
    /// app that their backend has died.
    shutting_down: Arc<AtomicBool>,
    /// Set by the output pump when the sidecar process is observed to exit, so
    /// the exit path can wait for the process to really be gone rather than
    /// assume it.
    backend_exited: Arc<AtomicBool>,
    /// Set by whichever watcher first told the user the backend was lost, so
    /// the same failure is never reported twice through two channels.
    backend_lost_reported: Arc<AtomicBool>,
}

/// How long to give the platform opener a chance to report failure.
///
/// `cmd /c start` and `open` hand the target to the OS and exit within a few
/// milliseconds, so a real failure lands well inside this window. `xdg-open`
/// may exec the browser in place instead and stay alive for the whole desktop
/// session, which is why the opener is never simply waited on: that would block
/// the caller until the user closed their browser. Polling for an early
/// non-zero exit catches the failures the OS does report and returns
/// immediately on the normal path.
const OPENER_FAILURE_WINDOW: Duration = Duration::from_millis(400);
const OPENER_POLL_INTERVAL: Duration = Duration::from_millis(20);

/// Start the platform opener for a URL or file path.
///
/// Uses the platform opener directly (`cmd /c start` on Windows, `open` on
/// macOS, `xdg-open` on Linux) rather than the tauri shell plugin's deprecated
/// `open`: it is fully cross-platform and adds no dependency.
///
/// Split per platform by `cfg` attribute rather than by a runtime `cfg!`
/// branch inside one body, because the Windows arm needs `CommandExt`, which
/// only exists on Windows.
#[cfg(target_os = "windows")]
fn spawn_os_opener(target: &str) -> std::io::Result<std::process::Child> {
    use std::os::windows::process::CommandExt;

    /// `CREATE_NO_WINDOW`. A console subsystem process spawned from a GUI app
    /// allocates and shows its own console, so without this every outbound
    /// link put a black command window on screen ahead of the browser. It is
    /// the launcher's window, not the browser's, and it is what made clicking
    /// a link in the app look like it opened a separate window rather than a
    /// page.
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;

    // The empty "" is start's title argument; without it a quoted target is
    // mis-parsed as the window title and nothing opens.
    std::process::Command::new("cmd")
        .args(["/c", "start", "", target])
        .creation_flags(CREATE_NO_WINDOW)
        .spawn()
}

#[cfg(target_os = "macos")]
fn spawn_os_opener(target: &str) -> std::io::Result<std::process::Child> {
    std::process::Command::new("open").arg(target).spawn()
}

#[cfg(not(any(target_os = "windows", target_os = "macos")))]
fn spawn_os_opener(target: &str) -> std::io::Result<std::process::Child> {
    std::process::Command::new("xdg-open").arg(target).spawn()
}

/// Open a URL or file path in the operating system's default handler, and say
/// so honestly when the operating system refuses.
///
/// For a URL this lands the user in their normal web browser at the local
/// address. Spawning alone proves nothing: it succeeds the moment the launcher
/// process starts, so a machine with no registered browser, a broken file
/// association or no `xdg-open` handler used to be reported back as a success
/// and the user was told nothing at all.
///
/// This is not a complete detector, and callers should not present it as one.
/// Windows `start` still exits 0 when it puts up the "How do you want to open
/// this file?" chooser, so `Ok` here means the OS accepted the request, not
/// that a browser window appeared.
fn open_with_os_default(target: &str) -> Result<(), String> {
    let mut child = spawn_os_opener(target).map_err(|e| e.to_string())?;
    let deadline = Instant::now() + OPENER_FAILURE_WINDOW;
    loop {
        match child.try_wait() {
            Ok(Some(status)) if status.success() => return Ok(()),
            Ok(Some(status)) => {
                return Err(match status.code() {
                    Some(code) => format!("the system opener exited with code {code}"),
                    None => "the system opener was terminated".to_string(),
                })
            }
            Ok(None) => {
                if Instant::now() >= deadline {
                    // Still running past the window: it has taken ownership of
                    // the target (the normal xdg-open case) and there is
                    // nothing left to report.
                    return Ok(());
                }
                std::thread::sleep(OPENER_POLL_INTERVAL);
            }
            Err(e) => return Err(e.to_string()),
        }
    }
}

/// Open the running app in the user's default web browser.
///
/// Exposed to the splash first-run card and to any in-app control (via
/// `withGlobalTauri`). Reads the resolved local URL from `AppState`; if startup
/// has not gotten that far yet it returns a friendly error the caller can show.
///
/// `path` lets the in-app toolbar open the EXACT page the user is on rather
/// than just the home page. It is treated as a path within the app (for example
/// "/boq" or "/projects/123/finance"); anything that is not a clean local path
/// is ignored and the home page is opened, so a caller can never be redirected
/// somewhere off the local origin.
#[tauri::command]
fn open_app_in_browser(app: tauri::AppHandle, path: Option<String>) -> Result<(), String> {
    let base = {
        let state = app.state::<AppState>();
        let guard = state.app_url.lock().unwrap();
        guard.clone()
    };
    let base = base.ok_or_else(|| {
        "The app is still starting. Please try again in a moment.".to_string()
    })?;
    let url = build_local_url(&base, path.as_deref());
    open_with_os_default(&url).map_err(|e| format!("Could not open your browser: {e}"))
}

/// Open an arbitrary external link (http/https/mailto) in the OS default handler.
///
/// The in-app UI carries many outbound links - the docs, the GitHub repo, the
/// marketing site, contact mail. Inside the webview a `target="_blank"` anchor is
/// swallowed and nothing opens, so the frontend routes every external-link click
/// here. Only web and mail schemes are honoured, so a stray or crafted href can
/// never launch an arbitrary local program through the opener.
#[tauri::command]
fn open_external_url(url: String) -> Result<(), String> {
    let target = url.trim();
    let lower = target.to_ascii_lowercase();
    let allowed = lower.starts_with("http://")
        || lower.starts_with("https://")
        || lower.starts_with("mailto:");
    if !allowed {
        return Err("Only http, https and mailto links can be opened".to_string());
    }
    open_with_os_default(target).map_err(|e| format!("Could not open the link: {e}"))
}

/// Combine the resolved local base URL with a caller-supplied app path.
///
/// Only same-origin paths are honoured: the path must start with a single "/"
/// (not "//", which a browser reads as a protocol-relative host) and must not
/// contain a scheme. Anything else falls back to the bare base URL. This keeps
/// the "open in browser" action firmly on the local app and never lets a path
/// argument send the user to an arbitrary site.
fn build_local_url(base: &str, path: Option<&str>) -> String {
    let trimmed = base.trim_end_matches('/');
    match path {
        Some(p)
            if p.starts_with('/')
                && !p.starts_with("//")
                && !p.contains("://")
                && !p.contains('\\') =>
        {
            format!("{trimmed}{p}")
        }
        _ => format!("{trimmed}/"),
    }
}

/// Return the resolved local URL the app is served on, for the UI to display or
/// open. Empty string until the backend is healthy and the URL is known.
#[tauri::command]
fn get_app_url(app: tauri::AppHandle) -> String {
    let state = app.state::<AppState>();
    let guard = state.app_url.lock().unwrap();
    guard.clone().unwrap_or_default()
}

/// Open the launcher diagnostic log in the OS default handler.
///
/// Exposed to the splash screen (via `withGlobalTauri`) so the failure UI can
/// offer a one-click "Open log" button. Returns an error string the splash can
/// show if the log path cannot be resolved or opened. Shares `open_with_os_default`
/// with the browser and link commands rather than repeating the platform block:
/// this is the surface a user reaches for when something has already gone
/// wrong, so it is the last place that should quietly claim success.
#[tauri::command]
fn open_log_file(_app: tauri::AppHandle) -> Result<(), String> {
    let path = log_path().ok_or_else(|| "Could not resolve the log file path".to_string())?;
    let path_str = path.to_string_lossy().to_string();
    open_with_os_default(&path_str).map_err(|e| format!("Could not open the log file: {e}"))
}

/// Resolve the user's home directory without pulling in extra crates.
fn home_dir() -> Option<PathBuf> {
    for var in ["USERPROFILE", "HOME"] {
        if let Ok(p) = std::env::var(var) {
            if !p.is_empty() {
                return Some(PathBuf::from(p));
            }
        }
    }
    None
}

/// Path of the launcher diagnostic log (same folder the backend uses for data).
fn log_path() -> Option<PathBuf> {
    home_dir().map(|h| h.join(".openestimate").join("desktop-launcher.log"))
}

/// Append one line to the diagnostic log (best effort) and to stderr.
///
/// This is the single most important diagnostic when a user reports "nothing
/// happens": even if the window never paints, the log records how far startup
/// got and the exact error.
fn log_line(msg: &str) {
    let secs = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let line = format!("[{secs}] {msg}\n");

    if let Some(path) = log_path() {
        if let Some(parent) = path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        use std::io::Write;
        if let Ok(mut f) = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&path)
        {
            let _ = f.write_all(line.as_bytes());
        }
    }
    eprintln!("{}", line.trim_end());
}

/// Escape a string for embedding inside a single-quoted JavaScript literal.
fn js_escape(s: &str) -> String {
    s.replace('\\', "\\\\")
        .replace('\'', "\\'")
        .replace('\n', " ")
        .replace('\r', " ")
}

/// Run a snippet of JavaScript in the main window, retried a few times.
///
/// setup() may run before the page has finished loading its inline script, so
/// we retry the eval over ~2 seconds. Every snippet sent through here must
/// therefore be idempotent, because it will run up to eight times.
///
/// `raise_window` brings the window to the front on each attempt. That is right
/// while the splash is up and the window is what the user just asked for, and
/// wrong afterwards: an app sitting in the tray would be yanked onto the screen
/// by a message that could have waited.
fn eval_retrying(handle: &tauri::AppHandle, js: String, raise_window: bool) {
    let handle = handle.clone();
    tauri::async_runtime::spawn(async move {
        for _ in 0..8 {
            if let Some(window) = handle.get_webview_window("main") {
                if raise_window {
                    let _ = window.show();
                }
                let _ = window.eval(&js);
            }
            tokio::time::sleep(std::time::Duration::from_millis(250)).await;
        }
    });
}

/// Run a snippet in the splash window. The splash boot functions are idempotent
/// (they just set DOM state), so repeated calls are harmless.
fn eval_in_splash(handle: &tauri::AppHandle, js: String) {
    eval_retrying(handle, js, true);
}

/// Tell the splash where the diagnostic log lives so a failure message can point
/// the user straight at it.
fn report_log_path(handle: &tauri::AppHandle) {
    if let Some(path) = log_path() {
        let p = js_escape(&path.to_string_lossy());
        eval_in_splash(
            handle,
            format!("(function(){{if(typeof setLogPath==='function'){{setLogPath('{p}');}}}})()"),
        );
    }
}

/// Tell the splash which build it is, so a startup failure carries its version.
///
/// This is the one screen a user with a backend that will not start can still
/// read, and the version is the first thing anyone answering their report has to
/// know: the same message is produced by faults that were fixed releases ago and
/// by faults that are still open. Without it a report cannot be triaged at all.
/// Every other place that names the version lives behind a running application,
/// which is precisely what these users do not have.
fn report_app_version(handle: &tauri::AppHandle) {
    let v = js_escape(env!("CARGO_PKG_VERSION"));
    eval_in_splash(
        handle,
        format!("(function(){{if(typeof setAppVersion==='function'){{setAppVersion('{v}');}}}})()"),
    );
}

/// Advance one step of the visible boot checklist on the splash screen.
///
/// `status` is one of "pending" | "active" | "done" | "failed". Never panics;
/// if the splash is not ready yet the retrying eval picks it up shortly.
fn boot_stage(handle: &tauri::AppHandle, id: &str, status: &str, detail: &str) {
    let id = js_escape(id);
    let status = js_escape(status);
    let detail = js_escape(detail);
    eval_in_splash(
        handle,
        format!(
            "(function(){{if(typeof bootStage==='function'){{bootStage('{id}','{status}','{detail}');}}}})()"
        ),
    );
}

/// Show a fatal error on the splash screen and mark a checklist step as failed,
/// without ever panicking. Always pairs the message with the log path so the
/// user can find the full diagnostics.
fn report_fatal_stage(handle: &tauri::AppHandle, stage: &str, message: &str) {
    log_line(&format!("FATAL [{stage}]: {message}"));
    report_log_path(handle);
    report_app_version(handle);
    // Every way startup can fail comes through here, so this is the one place
    // that has to carry the offer of a newer version. For a user whose
    // installed build cannot start at all, that sentence is the entire fix, and
    // the application's own update notice can never reach them: it is served by
    // the backend that just failed. Adds nothing to the failure path but a flag
    // read, and shows nothing unless an answer has already come back.
    update_check::note_startup_failed(handle, env!("CARGO_PKG_VERSION"));
    let stage_js = js_escape(stage);
    let msg = js_escape(message);
    eval_in_splash(
        handle,
        format!(
            "(function(){{\
                if(typeof failStage==='function'){{failStage('{stage_js}','{msg}');}}\
                else if(typeof setError==='function'){{setError('{msg}');}}\
            }})()"
        ),
    );
}

/// Tell the user the backend is gone, in whatever page the window is showing.
///
/// The splash reporting above is unusable once startup has succeeded. The
/// moment the webview navigates to the application the splash document is torn
/// down with every function the launcher talks to it through, so `failStage`
/// and `setError` are no longer defined and the `typeof` guards turn every
/// later report into a silent no-op. A backend that died an hour into the
/// session therefore had no way at all to reach the person using it: the window
/// kept showing the last screen it had rendered while every action on it failed.
///
/// So this builds its own overlay out of plain DOM instead of calling into the
/// page, which works on the splash and on the application alike, and needs
/// nothing from the frontend bundle. It is idempotent by element id because
/// `eval_retrying` will run it up to eight times.
fn report_backend_lost(
    handle: &tauri::AppHandle,
    reported: &AtomicBool,
    headline: &str,
    detail: &str,
) {
    // First reporter wins. The process pump and the liveness watch can both
    // see the same death, and the user should hear about it once.
    if reported
        .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
        .is_err()
    {
        return;
    }

    log_line(&format!("BACKEND LOST: {headline} {detail}"));
    let log_hint = log_path()
        .map(|p| format!(" The launcher log is at {}.", p.display()))
        .unwrap_or_default();
    let head_js = js_escape(headline);
    let body_js = js_escape(&format!("{detail}{log_hint}"));

    eval_retrying(
        handle,
        format!(
            "(function(){{\
                var d=document;\
                if(!d||d.getElementById('oe-backend-lost')){{return;}}\
                var host=d.body||d.documentElement;\
                if(!host){{return;}}\
                var o=d.createElement('div');\
                o.id='oe-backend-lost';\
                o.setAttribute('style','position:fixed;top:0;left:0;right:0;bottom:0;\
z-index:2147483647;background:rgba(15,17,21,0.94);color:#f5f7fa;display:flex;\
align-items:center;justify-content:center;padding:32px;text-align:left;\
font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;font-size:15px;\
line-height:1.55');\
                var c=d.createElement('div');\
                c.setAttribute('style','max-width:620px');\
                var h=d.createElement('div');\
                h.setAttribute('style','font-size:20px;font-weight:600;margin-bottom:12px');\
                h.textContent='{head_js}';\
                var p=d.createElement('div');\
                p.textContent='{body_js}';\
                c.appendChild(h);c.appendChild(p);o.appendChild(c);host.appendChild(o);\
            }})()"
        ),
        false,
    );
}

/// Show or clear the notice that says the backend has gone quiet.
///
/// Deliberately not the modal above. Silence is a symptom that can end: a long
/// import holding the database pool keeps the health check waiting on a backend
/// that is working perfectly well, and telling that person their app is dead,
/// behind a sheet they cannot dismiss, would cost them the very work that
/// caused the delay. So this is a strip along the bottom that takes no clicks
/// (`pointer-events:none`) and is removed again the moment the backend answers.
fn set_backend_silent_notice(handle: &tauri::AppHandle, shown: bool) {
    let js = if shown {
        let text = js_escape(
            "The application backend has not answered for about two minutes. It may be working \
through a long operation, such as a large import, and this notice will disappear as soon as it \
responds. If the window stays unusable, close it and start OpenConstructionERP again.",
        );
        format!(
            "(function(){{\
                var d=document;\
                if(!d||d.getElementById('oe-backend-silent')){{return;}}\
                var host=d.body||d.documentElement;\
                if(!host){{return;}}\
                var o=d.createElement('div');\
                o.id='oe-backend-silent';\
                o.setAttribute('style','position:fixed;left:0;right:0;bottom:0;\
z-index:2147483646;pointer-events:none;background:rgba(15,17,21,0.94);color:#f5f7fa;\
padding:14px 20px;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;\
font-size:14px;line-height:1.5');\
                o.textContent='{text}';\
                host.appendChild(o);\
            }})()"
        )
    } else {
        "(function(){\
            var d=document;if(!d){return;}\
            var e=d.getElementById('oe-backend-silent');\
            if(e&&e.parentNode){e.parentNode.removeChild(e);}\
        })()"
            .to_string()
    };
    eval_retrying(handle, js, false);
}

/// How often the liveness watch asks the backend whether it is still there.
const LIVENESS_POLL_INTERVAL: Duration = Duration::from_secs(10);
/// How long one liveness probe may take before it counts as unanswered.
const LIVENESS_PROBE_TIMEOUT: Duration = Duration::from_secs(5);
/// Consecutive refused connections before the backend is called dead. A refusal
/// is an immediate and unambiguous answer from the operating system: nothing is
/// listening on that port any more.
const LIVENESS_REFUSED_STRIKES: u32 = 2;
/// Consecutive unanswered probes before the user is told the backend has gone
/// quiet. Silence is much weaker evidence than a refusal, because a machine
/// waking from sleep, a heavy import or a long migration can all keep a request
/// waiting, so this threshold is deliberately several times longer and what it
/// triggers is a reversible notice rather than a verdict. Two minutes is not
/// generous by accident: the health check takes a database connection, and a
/// large import holding the pool keeps every probe waiting on a backend that is
/// working perfectly well.
const LIVENESS_SILENT_STRIKES: u32 = 12;

/// Keep watching the backend AFTER it has answered its first health check.
///
/// Readiness was the end of the launcher's attention: past that point nothing
/// asked whether the backend was still alive. When it went away the window
/// stayed exactly as it was, so a user went on clicking a screen whose every
/// request was failing, with no message anywhere saying why.
///
/// This is also the only cover for the attach path, where the backend belongs
/// to another process entirely: there is no child to wait on and no output to
/// pump, so its death is invisible by construction.
async fn watch_backend_liveness(
    handle: tauri::AppHandle,
    port: u16,
    shutting_down: Arc<AtomicBool>,
    reported: Arc<AtomicBool>,
) {
    let client = reqwest::Client::new();
    let url = format!("http://127.0.0.1:{port}/api/health");
    let mut refused: u32 = 0;
    let mut silent: u32 = 0;
    let mut silent_notice = false;

    loop {
        tokio::time::sleep(LIVENESS_POLL_INTERVAL).await;
        // A shutdown we asked for is not a failure, and a death already
        // reported by the process pump does not need saying twice.
        if shutting_down.load(Ordering::SeqCst) || reported.load(Ordering::SeqCst) {
            return;
        }

        match client.get(&url).timeout(LIVENESS_PROBE_TIMEOUT).send().await {
            // Any answer at all, including an error status, proves the process
            // is alive and serving. Only absence is evidence of death here.
            Ok(_) => {
                refused = 0;
                silent = 0;
                if silent_notice {
                    silent_notice = false;
                    log_line("liveness: the backend is answering again");
                    set_backend_silent_notice(&handle, false);
                }
            }
            Err(e) if e.is_connect() => {
                refused += 1;
                silent = 0;
                log_line(&format!(
                    "liveness: connection to the backend refused ({}/{})",
                    refused, LIVENESS_REFUSED_STRIKES
                ));
            }
            Err(e) => {
                silent += 1;
                log_line(&format!(
                    "liveness: backend did not answer ({}/{}): {e}",
                    silent, LIVENESS_SILENT_STRIKES
                ));
            }
        }

        if refused >= LIVENESS_REFUSED_STRIKES {
            if silent_notice {
                set_backend_silent_notice(&handle, false);
            }
            report_backend_lost(
                &handle,
                &reported,
                "The application backend has stopped",
                "Nothing is listening on the local address any more, so this window can no \
longer load or save anything. Please close it and start OpenConstructionERP again. If this \
keeps happening, send the log file to info@datadrivenconstruction.io.",
            );
            return;
        }
        // Silence is not a verdict, so the watch does not end here. It says
        // what it sees, keeps polling, and takes the notice down again if the
        // backend comes back. Only a refusal, above, is final.
        if silent >= LIVENESS_SILENT_STRIKES && !silent_notice {
            silent_notice = true;
            log_line("liveness: the backend has gone quiet, telling the user");
            set_backend_silent_notice(&handle, true);
        }
    }
}

/// Parse a backend ``STAGE:<id>:<status>[:<detail>]`` marker line.
///
/// Returns ``Some((id, splash_status, detail))`` where splash_status is mapped
/// to the values the splash checklist understands. Returns ``None`` for lines
/// that are not stage markers.
fn parse_stage_marker(line: &str) -> Option<(String, String, String)> {
    let rest = line.trim().strip_prefix("STAGE:")?;
    let mut parts = rest.splitn(3, ':');
    let id = parts.next()?.trim().to_string();
    let raw_status = parts.next()?.trim().to_string();
    let detail = parts.next().unwrap_or("").trim().to_string();
    if id.is_empty() || raw_status.is_empty() {
        return None;
    }
    let splash_status = match raw_status.as_str() {
        "start" | "progress" => "active",
        "done" => "done",
        "fail" => "failed",
        _ => "active",
    }
    .to_string();
    Some((id, splash_status, detail))
}

/// Accumulates a Python traceback seen on the sidecar's stderr so the launcher
/// can report the real exception line as the failure cause when the backend
/// crashed too early to emit a `STAGE:server:fail` marker. Only the exception
/// summary line is kept (chained tracebacks overwrite it, which is what Python
/// prints last and what the user needs to see), so the database-shutdown noise
/// that follows a crash can never become the reported cause.
#[derive(Default)]
struct TracebackCapture {
    capturing: bool,
    cause: Option<String>,
}

impl TracebackCapture {
    /// Feed one stderr line (the caller has already split on `\n`).
    fn feed_line(&mut self, raw: &str) {
        let line = raw.trim_end();
        if line.contains("Traceback (most recent call last)") {
            self.capturing = true;
            return;
        }
        if !self.capturing {
            return;
        }
        let body = line.trim();
        if body.is_empty() {
            return;
        }
        // Stack-frame lines are indented; keep reading until the summary line.
        if line.starts_with(' ') || line.starts_with('\t') {
            return;
        }
        // Chained-exception connectors are not the cause; the traceback that
        // follows them re-triggers capture and overwrites with the later cause.
        if body.starts_with("During handling of the above exception")
            || body.starts_with("The above exception was the direct cause")
        {
            return;
        }
        // A non-indented, non-connector line is the exception summary
        // (`ExceptionType: message`): record it (bounded, on a char boundary)
        // and stop until another traceback re-triggers capture.
        let mut summary = body.to_string();
        if summary.len() > 300 {
            let mut end = 300;
            while end > 0 && !summary.is_char_boundary(end) {
                end -= 1;
            }
            summary.truncate(end);
        }
        self.cause = Some(summary);
        self.capturing = false;
    }
}

/// The port the desktop app serves on whenever it can have it.
///
/// It is also one of the ports the attach probe below looks at, so a backend
/// left over from a previous run is found and reused instead of becoming a
/// second owner of the same PostgreSQL cluster.
const DEFAULT_BACKEND_PORT: u16 = 8732;

/// Find a port for the backend server, preferring a STABLE one.
///
/// The webview loads the application from `http://127.0.0.1:<port>/`, so the
/// port is the browser origin, and everything the app stores per origin lives
/// and dies with it: the saved session, the chosen interface language, the
/// user's own translation overrides. Picking a fresh random port on every run
/// therefore signed the user out and reset their language on every restart,
/// with nothing on screen to connect the two. Take the default port whenever it
/// is free and only fall back to a picked one when something else holds it.
///
/// Binding and dropping a listener is the only honest way to ask: the bind
/// releases the port at the end of the expression, which leaves the usual tiny
/// race between the check and the sidecar's own bind. That race is what the
/// picker has always had, so this is no weaker than what it replaces.
fn find_available_port() -> u16 {
    if std::net::TcpListener::bind(("127.0.0.1", DEFAULT_BACKEND_PORT)).is_ok() {
        return DEFAULT_BACKEND_PORT;
    }
    portpicker::pick_unused_port().unwrap_or(DEFAULT_BACKEND_PORT)
}

/// Resolve the bundled read-only converters directory shipped as an app
/// resource, if present.
///
/// The Windows installer ships the small (~30 MB) DDC IFC converter under
/// `resources/converters/ifc_windows/` so a fresh install can convert .ifc
/// offline with zero first-use download. We resolve the Tauri resource dir and
/// return the `converters` subfolder only when it actually exists on disk.
/// Returns `None` on platforms or builds that did not ship the converter (every
/// non-Windows build, and any Windows build where the workflow download step was
/// skipped), so the backend silently falls back to its normal install path.
fn bundled_converters_dir(app: &tauri::App) -> Option<PathBuf> {
    let resource_dir = app.path().resource_dir().ok()?;
    let converters = resource_dir.join("converters");
    if converters.is_dir() {
        Some(converters)
    } else {
        None
    }
}

/// Record the resolved local URL so the tray menu and the "open in your
/// browser" command can hand the user the same address the window is showing.
///
/// Also tells the webview the URL (via `setAppUrl`) so the splash first-run
/// card and any in-app control can offer the browser option without having to
/// re-derive the dynamic port.
fn set_app_url(handle: &tauri::AppHandle, url: &str) {
    {
        let state = handle.state::<AppState>();
        *state.app_url.lock().unwrap() = Some(url.to_string());
    }
    let url_js = js_escape(url);
    eval_in_splash(
        handle,
        format!("(function(){{if(typeof setAppUrl==='function'){{setAppUrl('{url_js}');}}}})()"),
    );
}

/// Bring the main app window to the front (used by the tray).
fn show_main_window(handle: &tauri::AppHandle) {
    if let Some(window) = handle.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

/// Ports an already-running OpenConstructionERP backend is likely to be on.
///
/// Checked in order before we spawn our own sidecar. This is what lets the
/// desktop app coexist with a developer backend or a CLI ``openconstructionerp
/// serve`` already running on the same machine: rather than booting a SECOND
/// backend that fights the first one over the shared embedded-PostgreSQL cluster
/// at ``~/.openestimate/pgdata`` (a real founder-machine failure mode), we
/// simply attach to the healthy instance that is already there.
const ATTACH_CANDIDATE_PORTS: [u16; 4] = [8000, 8080, 8732, 8765];

/// Probe ``127.0.0.1:<port>/api/health`` and decide whether we may attach to it.
///
/// Returns ``true`` only when the responder is unambiguously a HEALTHY backend
/// of EXACTLY OUR version. Attaching to anything less is dangerous: a stale dev
/// backend of a different version (the founder-machine case is a degraded
/// v6.10.0 on :8000) would serve the desktop app the wrong frontend/schema, and
/// a merely "degraded" instance may not actually work. So all of the following
/// must hold, and every rejected candidate is logged with its port, version and
/// status so attach decisions are auditable from the launcher log:
///   * HTTP 2xx
///   * ``status`` is "ok" or "healthy" (NOT "degraded"/"unhealthy")
///   * ``version`` equals our own ``CARGO_PKG_VERSION`` exactly
///   * ``alembic_head_matches`` is not ``false`` (migrations not known-stale)
async fn is_our_backend_healthy(client: &reqwest::Client, port: u16) -> bool {
    let url = format!("http://127.0.0.1:{port}/api/health");
    let resp = match client
        .get(&url)
        .timeout(std::time::Duration::from_millis(1500))
        .send()
        .await
    {
        Ok(resp) => resp,
        // No listener / connection refused / timeout: nothing to log, this is
        // the normal "port is free" case.
        Err(_) => return false,
    };

    let http_status = resp.status();
    if !http_status.is_success() {
        log_line(&format!(
            "attach: rejected candidate on port {port}: HTTP {}",
            http_status.as_u16()
        ));
        return false;
    }

    let body = match resp.text().await {
        Ok(body) => body,
        Err(e) => {
            log_line(&format!(
                "attach: rejected candidate on port {port}: could not read health body ({e})"
            ));
            return false;
        }
    };

    // Parse the health JSON properly so the decision is on real fields, not
    // substring guesses. serde_json is already a dependency.
    let json: serde_json::Value = match serde_json::from_str(&body) {
        Ok(v) => v,
        Err(_) => {
            log_line(&format!(
                "attach: rejected candidate on port {port}: health body is not JSON"
            ));
            return false;
        }
    };

    let status = json.get("status").and_then(|v| v.as_str()).unwrap_or("");
    let version = json.get("version").and_then(|v| v.as_str()).unwrap_or("");
    // Missing key is treated as "not known false" (acceptable); only an explicit
    // false rejects.
    let alembic_ok = json
        .get("alembic_head_matches")
        .and_then(|v| v.as_bool())
        .unwrap_or(true);
    let our_version = env!("CARGO_PKG_VERSION");

    let status_ok = matches!(status, "ok" | "healthy");
    let version_ok = version == our_version;

    if status_ok && version_ok && alembic_ok {
        log_line(&format!(
            "attach: accepted candidate on port {port}: status={status} version={version}"
        ));
        return true;
    }

    log_line(&format!(
        "attach: rejected candidate on port {port}: status={status:?} version={version:?} \
(ours={our_version}) alembic_head_matches={alembic_ok}"
    ));
    false
}

/// Scan the candidate ports for an existing healthy backend to attach to.
///
/// Returns the first port that responds as our backend, or ``None`` if none do
/// (the normal cold-start case, where we then spawn our own sidecar).
async fn find_existing_backend(client: &reqwest::Client) -> Option<u16> {
    for port in ATTACH_CANDIDATE_PORTS {
        if is_our_backend_healthy(client, port).await {
            return Some(port);
        }
    }
    None
}

/// What one health answer said about the backend.
enum HealthProbe {
    /// No usable answer: nothing listening yet, no reply in time, or a non-2xx.
    Unreachable,
    /// Fit to open the application against.
    Ready,
    /// Answered, and named a fault that makes the application unusable.
    Broken(String),
}

/// The outcome of waiting for the backend to become ready.
enum StartupOutcome {
    Ready,
    /// The backend is up and says it cannot do its job; carries the reason.
    Broken(String),
    TimedOut,
}

/// How long one health probe may take before it counts as no answer.
///
/// Without a per-request bound a backend that accepts the connection and then
/// never answers holds the poll open forever. The deadline below is only tested
/// between polls, so that single hung request outlived the entire startup
/// window: the user waited on the spinner with no timeout message ever shown,
/// because the code that would have shown it never got another turn.
///
/// Generous on purpose. The bound exists to stop one request holding the loop,
/// not to judge how quick the backend is, and this endpoint does real work: a
/// database round trip, a walk of the whole Alembic version tree and a process
/// memory reading. A tight bound would turn a slow first answer on a cold disk
/// into a startup timeout, which is the same lie in the other direction. At
/// twelve seconds there are still dozens of polls inside the startup window.
const HEALTH_PROBE_TIMEOUT: Duration = Duration::from_secs(12);

/// How long the backend may keep reporting a fault that makes it unusable
/// before we stop waiting for it to sort itself out and say so. Startup states
/// clear in seconds; a fault still standing after this is the real state.
const DEGRADED_GRACE: Duration = Duration::from_secs(30);

/// Judge one health body, and fail OPEN.
///
/// The health endpoint answers 200 whether it is healthy or degraded, and the
/// old check read only the status code. So a backend that had answered
/// "degraded, database: error" was treated as ready, the webview was pointed at
/// it, and the user got the application shell with every request inside it
/// failing and nothing to say why. The two faults tested here are the ones that
/// leave nothing working: no database, and an installation with no application
/// files to serve, which answers every route in the app with a 404.
///
/// Everything else stays open on purpose. This function decides whether anyone
/// can start the app at all, so an unreadable body, a missing field, a renamed
/// field or a status word we do not know all mean ready. Only a fault the
/// backend positively reports may hold a user out of their own installation,
/// and stale migrations do not qualify: that is a real problem, and it is one
/// the user can still see and act on from inside the app.
fn judge_health(body: &str) -> HealthProbe {
    let json: serde_json::Value = match serde_json::from_str(body) {
        Ok(v) => v,
        Err(_) => return HealthProbe::Ready,
    };

    let status = json.get("status").and_then(|v| v.as_str()).unwrap_or("");
    if status != "degraded" {
        return HealthProbe::Ready;
    }

    let database_down = json
        .get("database")
        .and_then(|v| v.as_str())
        .map(|s| s != "ok")
        .unwrap_or(false);
    if database_down {
        return HealthProbe::Broken("the local database is not answering".to_string());
    }

    let frontend_missing = json
        .get("frontend_dist_present")
        .and_then(|v| v.as_bool())
        .map(|present| !present)
        .unwrap_or(false);
    if frontend_missing {
        return HealthProbe::Broken(
            "this installation is missing the application files it serves".to_string(),
        );
    }

    HealthProbe::Ready
}

/// Wait for the backend to become fit to open.
///
/// Polls `/api/health` every ~500ms until it is ready, reports a standing fault,
/// or the timeout elapses. While waiting, updates the splash screen so the user
/// sees progress; first-run embedded-PostgreSQL setup can be slow.
async fn wait_for_backend(
    handle: &tauri::AppHandle,
    port: u16,
    timeout_secs: u64,
) -> StartupOutcome {
    let client = reqwest::Client::new();
    let url = format!("http://127.0.0.1:{port}/api/health");
    let start = Instant::now();
    let mut progress_shown = false;
    let mut broken_since: Option<Instant> = None;
    let mut broken_logged = false;

    while start.elapsed().as_secs() < timeout_secs {
        let probe = match client.get(&url).timeout(HEALTH_PROBE_TIMEOUT).send().await {
            Ok(resp) if resp.status().is_success() => match resp.text().await {
                Ok(body) => judge_health(&body),
                // The status line arrived and the body did not. Something is
                // serving; do not hold the user out over a lost read.
                Err(_) => HealthProbe::Ready,
            },
            _ => HealthProbe::Unreachable,
        };

        match probe {
            HealthProbe::Ready => return StartupOutcome::Ready,
            HealthProbe::Broken(reason) => {
                if !broken_logged {
                    broken_logged = true;
                    log_line(&format!("backend answered but reports a fatal fault: {reason}"));
                }
                let since = *broken_since.get_or_insert_with(Instant::now);
                if since.elapsed() >= DEGRADED_GRACE {
                    return StartupOutcome::Broken(reason);
                }
            }
            HealthProbe::Unreachable => {
                // A backend that has stopped answering is starting or dying,
                // not degraded, so an earlier degraded reading must not be held
                // against the next one.
                broken_since = None;
                broken_logged = false;
            }
        }

        if !progress_shown && start.elapsed().as_secs() >= 8 {
            progress_shown = true;
            if let Some(window) = handle.get_webview_window("main") {
                let _ = window.eval("setStatus('Setting up the local database, almost there')");
            }
        }

        tokio::time::sleep(std::time::Duration::from_millis(500)).await;
    }
    StartupOutcome::TimedOut
}

fn main() {
    // Write the diagnostic log at the VERY FIRST instruction, before anything
    // else in startup can fail. If the user reports "I click the icon and
    // nothing happens", this line guarantees the log file at least exists and
    // records that the process launched -- so the failure is never invisible,
    // even if building the Tauri app itself (WebView2 missing, etc.) blows up
    // before any window appears.
    log_line(&format!(
        "=== OpenConstructionERP desktop launcher starting (v{}) ===",
        env!("CARGO_PKG_VERSION")
    ));

    let port = find_available_port();
    log_line(&format!("selected backend port {port}"));

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_process::init())
        .manage(AppState {
            backend_child: Mutex::new(None),
            app_url: Mutex::new(None),
            shutting_down: Arc::new(AtomicBool::new(false)),
            backend_exited: Arc::new(AtomicBool::new(false)),
            backend_lost_reported: Arc::new(AtomicBool::new(false)),
        })
        .invoke_handler(tauri::generate_handler![
            open_log_file,
            open_app_in_browser,
            open_external_url,
            get_app_url,
            update_check::set_update_check_enabled,
            update_check::decline_update_version
        ])
        .setup(move |app| {
            let handle = app.handle().clone();
            log_line(&format!("setup() running; backend port = {port}"));

            // Take the shared flags out of managed state once, here in
            // synchronous code, and hand the tasks below plain Arcs. A
            // `State` borrow lives on the handle it came from, and the tasks
            // that need these flags are async and long-lived.
            let (shutting_down, backend_lost) = {
                let state = handle.state::<AppState>();
                (
                    state.shutting_down.clone(),
                    state.backend_lost_reported.clone(),
                )
            };

            // Resolve the bundled read-only converters dir (Windows ships the
            // DDC IFC converter as an app resource) BEFORE the attach/spawn
            // branches so we can hand its path to whichever sidecar we start.
            // None on builds that did not ship it, in which case the backend
            // keeps its normal auto-download behaviour.
            let bundled_converters = bundled_converters_dir(app);
            if let Some(ref dir) = bundled_converters {
                log_line(&format!("bundled converters dir: {}", dir.display()));
            }

            // Surface the log path and the first two checklist steps right away
            // so the user sees a live boot screen the instant the window paints.
            report_log_path(&handle);
            boot_stage(&handle, "launcher", "done", "");
            // Show the version from the first frame, not only once something has
            // failed, so a user who is merely puzzled can also read it off.
            report_app_version(&handle);
            boot_stage(&handle, "sidecar", "active", "Locating the backend");

            // Ask, in the background, whether a newer release exists. Started
            // here rather than when a failure is reported because a failure can
            // arrive in milliseconds - a sidecar binary that is not there fails
            // long before any request could finish - and a user staring at an
            // error is not going to be made to wait for a web request on top of
            // it. Never awaited, never blocking, and silent unless startup
            // fails: see the file for what it does and does not do.
            update_check::spawn(handle.clone(), env!("CARGO_PKG_VERSION").to_string());

            // Tray icon with a right-click menu. The menu is the always-present
            // home for the "open in your browser" choice the founder asked for:
            // however the app was started, the user can right-click the tray
            // icon and pick whether to keep using the app window or hand the
            // local address to their normal web browser. Building the tray is a
            // nice-to-have, so its failure must never abort startup.
            let tray_menu_result = (|| {
                let show_item = MenuItemBuilder::with_id("tray_show", "Show app window")
                    .build(app)?;
                let browser_item =
                    MenuItemBuilder::with_id("tray_open_browser", "Open in your browser")
                        .build(app)?;
                let quit_item = MenuItemBuilder::with_id("tray_quit", "Quit").build(app)?;
                let sep = PredefinedMenuItem::separator(app)?;
                MenuBuilder::new(app)
                    .item(&show_item)
                    .item(&browser_item)
                    .item(&sep)
                    .item(&quit_item)
                    .build()
            })();

            let tray_build = match tray_menu_result {
                Ok(menu) => TrayIconBuilder::new()
                    .icon(app.default_window_icon().cloned().unwrap_or_else(|| {
                        // Should never happen (the bundle always ships an icon),
                        // but fall back to a 1x1 transparent pixel rather than
                        // panic, keeping the no-panic startup contract.
                        tauri::image::Image::new_owned(vec![0, 0, 0, 0], 1, 1)
                    }))
                    .tooltip("OpenConstructionERP")
                    .menu(&menu)
                    // Keep the existing left-click-to-show behaviour. The menu
                    // shows on right-click; suppressing menu-on-left-click means
                    // a single left click still just raises the window.
                    .show_menu_on_left_click(false)
                    .on_menu_event(|app, event| match event.id().as_ref() {
                        "tray_show" => show_main_window(app),
                        "tray_open_browser" => {
                            if let Err(e) = open_app_in_browser(app.clone(), None) {
                                log_line(&format!("tray: open in browser failed: {e}"));
                            }
                        }
                        "tray_quit" => app.exit(0),
                        _ => {}
                    })
                    .on_tray_icon_event(|tray, event| {
                        if let TrayIconEvent::Click {
                            button: MouseButton::Left,
                            button_state: MouseButtonState::Up,
                            ..
                        } = event
                        {
                            show_main_window(tray.app_handle());
                        }
                    })
                    .build(app),
                Err(e) => {
                    log_line(&format!("warning: tray menu build failed (non-fatal): {e}"));
                    // Fall back to the plain icon-only tray (left-click shows).
                    TrayIconBuilder::new()
                        .tooltip("OpenConstructionERP")
                        .on_tray_icon_event(|tray, event| {
                            if let TrayIconEvent::Click {
                                button: MouseButton::Left,
                                button_state: MouseButtonState::Up,
                                ..
                            } = event
                            {
                                show_main_window(tray.app_handle());
                            }
                        })
                        .build(app)
                }
            };
            if let Err(e) = tray_build {
                log_line(&format!("warning: tray icon build failed (non-fatal): {e}"));
            }

            // Attach to an existing healthy backend instead of booting a second
            // one.
            //
            // If a developer backend or a CLI `openconstructionerp serve` is
            // already running on this machine, it already owns the embedded
            // PostgreSQL cluster at ~/.openestimate/pgdata. Spawning our own
            // sidecar against the SAME default data dir makes two processes
            // share one cluster; when the desktop app later exits it tells
            // pixeltable-pgserver to clean up, which can stop the postmaster out
            // from under the still-running developer backend. Attaching instead
            // is both safer and faster (no second boot, no second cluster
            // handle). We only attach to a server that self-identifies as ours.
            //
            // The probe is short (four ports, 1.5s each at worst, only while
            // they are actually open) and is run to completion here so the
            // decision to spawn is made BEFORE we start a sidecar -- otherwise a
            // concurrent probe would race the spawn and we could end up with two
            // backends anyway. block_on is safe: setup() already runs on the
            // Tauri async runtime's worker, and the probe never blocks
            // indefinitely.
            let attached_port = tauri::async_runtime::block_on(async {
                let client = reqwest::Client::new();
                find_existing_backend(&client).await
            });

            if let Some(existing) = attached_port {
                log_line(&format!(
                    "found an existing OpenConstructionERP backend on port {existing}; attaching instead of starting a second one"
                ));
                boot_stage(&handle, "sidecar", "done", "Found a running backend");
                boot_stage(&handle, "pg", "done", "");
                boot_stage(&handle, "migrate", "done", "");
                boot_stage(&handle, "server", "done", "");
                boot_stage(&handle, "open", "done", "Ready");
                let url = format!("http://127.0.0.1:{existing}/");
                set_app_url(&handle, &url);
                let handle_nav = handle.clone();
                tauri::async_runtime::spawn(async move {
                    // Give the splash script a moment to finish loading, then
                    // let it offer the one-time "app window or browser" choice
                    // before navigating the webview to the running app.
                    tokio::time::sleep(std::time::Duration::from_millis(400)).await;
                    if let Some(window) = handle_nav.get_webview_window("main") {
                        let _ = window.show();
                        let _ = window.set_focus();
                        let url_js = js_escape(&url);
                        let _ = window.eval(&format!(
                            "(function(){{if(typeof offerLaunchChoice==='function'){{\
                                offerLaunchChoice('{url_js}');}}\
                                else{{window.location.replace('{url_js}');}}}})()"
                        ));
                    }
                    update_check::note_app_started(&handle_nav, env!("CARGO_PKG_VERSION"));
                });
                // We did not spawn a sidecar, so there is no child to manage.
                // That is exactly why the liveness watch matters most here: the
                // backend belongs to another process, nothing reports its exit
                // to us, and without this its death would leave the window
                // showing an application that no longer has a server.
                tauri::async_runtime::spawn(watch_backend_liveness(
                    handle.clone(),
                    existing,
                    shutting_down.clone(),
                    backend_lost.clone(),
                ));
                return Ok(());
            }

            log_line("no existing backend found; starting our own sidecar");

            // Start the backend sidecar.
            //
            // The "serve" subcommand is required: the CLI only accepts --host /
            // --port under a subcommand. Invoked bare it would ignore them,
            // fall back to defaults, and on first run block on an interactive
            // "open in browser?" stdin prompt that a sidecar has no terminal
            // for. With --data-dir left unset the sidecar uses its default
            // (~/.openestimate), which stays writable even for a per-machine
            // install under Program Files.
            let shell = handle.shell();
            let sidecar_cmd = match shell.sidecar("openconstructionerp-server") {
                Ok(cmd) => {
                    // OE_DESKTOP=1 marks this backend as one we spawned from the
                    // desktop shell (so the backend can run desktop-only
                    // bootstrapping). We deliberately do NOT set it on the attach
                    // path above, because an already-running dev backend must not
                    // be treated as a desktop-bootstrapped one.
                    let mut cmd = cmd.env("OE_DESKTOP", "1").args([
                        "serve",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        &port.to_string(),
                    ]);
                    // Point the backend at the bundled read-only converters so
                    // an .ifc upload converts offline with no first-use download.
                    // Only set when we actually shipped a converters dir; absent
                    // env keeps the normal auto-download path intact.
                    if let Some(ref dir) = bundled_converters {
                        cmd = cmd.env("OE_BUNDLED_CONVERTERS_DIR", dir.as_os_str());
                    }
                    // Give the sidecar a working directory it is allowed to
                    // write to. Eighteen upload roots across ten modules are
                    // declared as working-directory-relative literals and
                    // create themselves with mkdir on first use, bypassing the
                    // data-dir plumbing the rest of the platform goes through.
                    // Nothing set the child's working directory, so it inherited
                    // this process's, and the Start Menu shortcut of a
                    // per-machine install starts the app in the install folder
                    // under Program Files. Creating a directory there is denied
                    // to an unelevated user, so attaching a file to a request
                    // for information, a submittal, an inspection, a punch item,
                    // a letter, a diary entry, a lien waiver, a closeout item or
                    // a compliance document returned a bare 500 on every such
                    // install, with ten registers carrying an attach button that
                    // could not work.
                    //
                    // The note above about --data-dir is correct and was not
                    // enough: it keeps the data directory writable and says
                    // nothing about the working directory, which is a second
                    // path the same process resolves against. Development and CI
                    // both run with the repository root as the working
                    // directory, which is writable, so those eighteen modules
                    // look healthy everywhere they are ever tested.
                    //
                    // This moves them somewhere writable without editing the
                    // eighteen declarations. It is a floor, not the repair: they
                    // should answer to OE_CLI_DATA_DIR like everything else, and
                    // until they do, a relative path written by any new module
                    // lands here by accident rather than by design. Failing
                    // through silently is deliberate, because an inherited
                    // working directory is exactly what shipped, so a machine
                    // whose home directory cannot be read is left no worse off
                    // than it is today.
                    if let Some(home) = home_dir() {
                        let workdir = home.join(".openestimate");
                        if std::fs::create_dir_all(&workdir).is_ok() {
                            cmd = cmd.current_dir(&workdir);
                        }
                    }
                    cmd
                }
                Err(e) => {
                    report_fatal_stage(
                        &handle,
                        "sidecar",
                        &format!(
                            "Could not locate the backend component ({e}). Please reinstall \
the application."
                        ),
                    );
                    // Keep the window open so the user sees the error.
                    return Ok(());
                }
            };

            let (mut rx, child) = match sidecar_cmd.spawn() {
                Ok(pair) => pair,
                Err(e) => {
                    report_fatal_stage(
                        &handle,
                        "sidecar",
                        &format!(
                            "The backend component could not be started ({e}). Some antivirus \
tools block newly installed programs; allow OpenConstructionERP and try again."
                        ),
                    );
                    return Ok(());
                }
            };
            log_line("sidecar spawned");
            boot_stage(&handle, "sidecar", "done", "");
            boot_stage(&handle, "pg", "active", "Starting the local database");

            // Keep the child handle alive (and killable on exit).
            let backend_exited = {
                let state = handle.state::<AppState>();
                *state.backend_child.lock().unwrap() = Some(child);
                state.backend_exited.clone()
            };

            let backend_ready = Arc::new(AtomicBool::new(false));
            // Separate from readiness on purpose. Readiness means the backend
            // answered a health check, so it is only ever set on success and
            // says nothing about whether a failure has already been explained.
            // This one means the user has been shown a precise reason, which is
            // the question the startup timeout below actually needs answered.
            let fatal_reported = Arc::new(AtomicBool::new(false));
            let last_stderr = Arc::new(Mutex::new(String::new()));
            // Latch the real startup failure cause so the database-shutdown
            // noise that follows a crash cannot mask it: a STAGE:server:fail
            // marker (preferred), or the exception line of a Python traceback
            // on stderr when the backend died too early to emit a marker.
            let latched_fail = Arc::new(Mutex::new(None::<String>));
            let traceback = Arc::new(Mutex::new(TracebackCapture::default()));

            // Pump the sidecar's output into the log file and remember recent
            // stderr so a startup crash can be shown to the user verbatim.
            {
                let ready = backend_ready.clone();
                let fatal_flag = fatal_reported.clone();
                let stderr_buf = last_stderr.clone();
                let latched = latched_fail.clone();
                let traceback = traceback.clone();
                let handle_evt = handle.clone();
                let exited_flag = backend_exited.clone();
                let deliberate = shutting_down.clone();
                let lost_flag = backend_lost.clone();
                tauri::async_runtime::spawn(async move {
                    while let Some(event) = rx.recv().await {
                        match event {
                            CommandEvent::Stdout(bytes) => {
                                let line = String::from_utf8_lossy(&bytes);
                                log_line(&format!("[backend] {}", line.trim_end()));
                                // Drive the visible boot checklist from the
                                // backend's machine-readable progress markers.
                                for raw in line.split('\n') {
                                    if let Some((id, status, detail)) = parse_stage_marker(raw) {
                                        boot_stage(&handle_evt, &id, &status, &detail);
                                        // Latch the first real failure cause.
                                        if status == "failed" && !detail.is_empty() {
                                            let mut lf = latched.lock().unwrap();
                                            if lf.is_none() {
                                                *lf = Some(detail.clone());
                                            }
                                        }
                                    }
                                }
                            }
                            CommandEvent::Stderr(bytes) => {
                                let line = String::from_utf8_lossy(&bytes);
                                log_line(&format!("[backend:err] {}", line.trim_end()));
                                // Some launchers/loggers route progress markers
                                // to stderr; honour them there too. Non-marker
                                // lines feed the traceback capture so a hard
                                // crash still yields a real cause with no marker.
                                for raw in line.split('\n') {
                                    if let Some((id, status, detail)) = parse_stage_marker(raw) {
                                        boot_stage(&handle_evt, &id, &status, &detail);
                                        if status == "failed" && !detail.is_empty() {
                                            let mut lf = latched.lock().unwrap();
                                            if lf.is_none() {
                                                *lf = Some(detail.clone());
                                            }
                                        }
                                    } else {
                                        traceback.lock().unwrap().feed_line(raw);
                                    }
                                }
                                let mut buf = stderr_buf.lock().unwrap();
                                buf.push_str(&line);
                                if buf.len() > 4000 {
                                    // Advance the cut to a char boundary so
                                    // slicing a UTF-8 string can never panic and
                                    // kill the pump (which would strand the user
                                    // on the splash for the whole timeout).
                                    let mut cut = buf.len() - 4000;
                                    while cut < buf.len() && !buf.is_char_boundary(cut) {
                                        cut += 1;
                                    }
                                    *buf = buf[cut..].to_string();
                                }
                            }
                            CommandEvent::Error(err) => {
                                log_line(&format!("[backend:error] {err}"));
                                // A failure reading the child's own pipes went
                                // to the log and nowhere else, so on a startup
                                // that then failed the user was shown a tail of
                                // stderr with no sign of it. Add it to that tail
                                // rather than latching it as the cause: it is
                                // usually a symptom of the crash, and it must
                                // not displace the exception that explains it.
                                let mut buf = stderr_buf.lock().unwrap();
                                buf.push_str(&format!("launcher: {err}\n"));
                            }
                            CommandEvent::Terminated(payload) => {
                                log_line(&format!(
                                    "[backend] terminated: code={:?} signal={:?}",
                                    payload.code, payload.signal
                                ));
                                // Record the exit before anything else, so the
                                // shutdown path can wait for the process to
                                // really be gone instead of assuming it.
                                exited_flag.store(true, Ordering::SeqCst);
                                // If the backend died before ever becoming
                                // healthy, surface it now instead of leaving the
                                // user staring at the spinner for the full timeout.
                                if !ready.load(Ordering::SeqCst) {
                                    // Prefer the real cause the backend reported
                                    // (STAGE:server:fail), then the exception line
                                    // of a captured Python traceback, and only as a
                                    // last resort the raw stderr tail. This is what
                                    // keeps the database-shutdown noise from masking
                                    // the real reason startup failed.
                                    let latched_cause = latched.lock().unwrap().clone();
                                    let tb_cause = traceback.lock().unwrap().cause.clone();
                                    let core = if let Some(cause) = latched_cause.or(tb_cause) {
                                        format!("The backend could not finish starting: {cause}")
                                    } else {
                                        let tail = stderr_buf.lock().unwrap().clone();
                                        if tail.trim().is_empty() {
                                            format!(
                                                "The backend stopped unexpectedly (exit code {:?}) \
before it finished starting.",
                                                payload.code
                                            )
                                        } else {
                                            // Last resort: show the tail of stderr,
                                            // which usually carries the cause.
                                            let trimmed = tail.trim();
                                            let shown = if trimmed.len() > 600 {
                                                let mut start = trimmed.len() - 600;
                                                while start < trimmed.len()
                                                    && !trimmed.is_char_boundary(start)
                                                {
                                                    start += 1;
                                                }
                                                &trimmed[start..]
                                            } else {
                                                trimmed
                                            };
                                            format!(
                                                "The backend stopped unexpectedly during startup: {shown}"
                                            )
                                        }
                                    };
                                    // Always pair the cause with a clear next step.
                                    // report_fatal_stage also surfaces the log path
                                    // (the splash shows an Open-log button).
                                    let detail = format!(
                                        "{core} Open the log file for the full details, and if \
this keeps happening send it to info@datadrivenconstruction.io."
                                    );
                                    // Attribute the failure to the server step so
                                    // the checklist shows a clear red mark.
                                    report_fatal_stage(&handle_evt, "server", &detail);
                                    // Record that the user now has the real
                                    // reason, so the startup timeout does not
                                    // replace it with a vaguer one later.
                                    fatal_flag.store(true, Ordering::SeqCst);
                                } else if !deliberate.load(Ordering::SeqCst) {
                                    // The backend had already gone healthy, and
                                    // nobody asked it to stop. This case was
                                    // silent: readiness was the end of the
                                    // launcher's attention, so a sidecar that
                                    // died an hour in left the window showing
                                    // the last screen it had rendered while
                                    // every request inside it failed, and the
                                    // only record was a line in a log file the
                                    // user had no reason to open.
                                    report_backend_lost(
                                        &handle_evt,
                                        &lost_flag,
                                        "The application backend has stopped",
                                        &format!(
                                            "The backend exited unexpectedly (exit code {:?}), so \
this window can no longer load or save anything. Please close it and start \
OpenConstructionERP again. If this keeps happening, send the log file to \
info@datadrivenconstruction.io.",
                                            payload.code
                                        ),
                                    );
                                }
                                break;
                            }
                            _ => {}
                        }
                    }

                    // The event channel can also just end: the sender is
                    // dropped and no Terminated event ever arrives. Reaching
                    // here means we have stopped watching the backend, and
                    // saying nothing would leave whoever is using it to find
                    // out from a screen that no longer works.
                    if !exited_flag.load(Ordering::SeqCst)
                        && !deliberate.load(Ordering::SeqCst)
                        && ready.load(Ordering::SeqCst)
                    {
                        log_line("backend event stream ended without a termination event");
                        report_backend_lost(
                            &handle_evt,
                            &lost_flag,
                            "The connection to the application backend was lost",
                            "The launcher can no longer see the backend it started, so this \
window may stop working. Please close it and start OpenConstructionERP again. If this keeps \
happening, send the log file to info@datadrivenconstruction.io.",
                        );
                    }
                });
            }

            // Wait for the backend to be ready, then navigate the webview from
            // the splash screen to the live application. First-run embedded
            // PostgreSQL setup (initdb, migrations, module load, demo seed) can
            // be slow on a cold machine, so allow up to 240 seconds.
            let handle_clone = handle.clone();
            let ready_flag = backend_ready.clone();
            let fatal_flag_wait = fatal_reported.clone();
            let shutting_down_wait = shutting_down.clone();
            let backend_lost_wait = backend_lost.clone();
            tauri::async_runtime::spawn(async move {
                // A first run that has to recover a large local database (WAL
                // replay + fsync) can take several minutes, so allow a generous
                // window. This number has one hard requirement: it must exceed
                // the backend's own budget for bringing embedded PostgreSQL up,
                // which is OE_PG_BOOT_TIMEOUT and defaults to 600s. It used to
                // be 600 as well, so the two were equal and a database that
                // spent its whole budget recovering left nothing at all for the
                // work that follows it: migrations, the module load, table
                // creation and first-run seeding. That is not a hypothetical
                // ordering. The installer stops a running instance by killing
                // the process tree, which crash-stops the embedded database, so
                // the next start after every upgrade is exactly the WAL replay
                // the 600s budget exists for. The user then saw a healthy,
                // still-working backend reported as one that had not started,
                // and retrying reproduced it because nothing had gone wrong to
                // clear. Doubling it keeps a comfortable margin above the inner
                // budget and costs nothing when a backend has genuinely failed,
                // because that path reports itself the moment the sidecar dies
                // rather than waiting for this window to close.
                match wait_for_backend(&handle_clone, port, 1200).await {
                    StartupOutcome::Ready => {
                        ready_flag.store(true, Ordering::SeqCst);
                        log_line("backend healthy; navigating to app");
                        boot_stage(&handle_clone, "server", "done", "");
                        boot_stage(&handle_clone, "open", "done", "Ready");
                        let url = format!("http://127.0.0.1:{port}/");
                        set_app_url(&handle_clone, &url);
                        if let Some(window) = handle_clone.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                            // Let the splash offer the one-time "app window or
                            // browser" choice; if that helper is missing for any
                            // reason, fall straight through to the app window so
                            // the user is never left on the splash.
                            let url_js = js_escape(&url);
                            let _ = window.eval(&format!(
                                "(function(){{if(typeof offerLaunchChoice==='function'){{\
                                    offerLaunchChoice('{url_js}');}}\
                                    else{{window.location.replace('{url_js}');}}}})()"
                            ));
                        }
                        update_check::note_app_started(&handle_clone, env!("CARGO_PKG_VERSION"));
                        // Readiness is where the launcher used to stop looking.
                        // Keep watching, so a backend that goes away later is
                        // reported instead of being left for the user to find.
                        tauri::async_runtime::spawn(watch_backend_liveness(
                            handle_clone.clone(),
                            port,
                            shutting_down_wait,
                            backend_lost_wait,
                        ));
                    }
                    StartupOutcome::Broken(reason) => {
                        // The backend is answering and telling us it cannot do
                        // its job. Opening the app on top of that hands the user
                        // a shell whose every action fails, which is how this
                        // ended up looking like the product was broken rather
                        // than the installation.
                        log_line(&format!("backend is up but not fit to serve: {reason}"));
                        if !fatal_flag_wait.load(Ordering::SeqCst) {
                            report_fatal_stage(
                                &handle_clone,
                                "server",
                                &format!(
                                    "The backend started, but {reason}, so the app cannot open. \
Please close this window and try again. If the problem persists, please send the log file to \
info@datadrivenconstruction.io."
                                ),
                            );
                        }
                    }
                    StartupOutcome::TimedOut => {
                        log_line("backend did not become healthy within the startup window");
                        // Only say "slow" when nothing better has been said. The
                        // termination handler above names the real cause the
                        // moment the sidecar dies, and this branch used to guard
                        // on the readiness flag, which is set only when the
                        // backend goes healthy. A backend that died during
                        // startup therefore left readiness false and satisfied
                        // this condition, so the timeout fired minutes afterwards
                        // and overwrote a message carrying the actual exception
                        // with one that said only that the backend had not
                        // started in time. A user whose sidecar exited with a
                        // FileNotFoundError nine minutes earlier read the second
                        // message, looked for the fault on their own machine, and
                        // had no way to know the first had ever been shown.
                        if !ready_flag.load(Ordering::SeqCst)
                            && !fatal_flag_wait.load(Ordering::SeqCst)
                        {
                            report_fatal_stage(
                                &handle_clone,
                                "server",
                                "The application backend did not start in time. Please close \
this window and try again. If the problem persists, please send the log file to \
info@datadrivenconstruction.io.",
                            );
                        }
                    }
                }
            });

            Ok(())
        })
        .build(tauri::generate_context!());

    match app {
        Ok(app) => app.run(|app_handle, event| match event {
            // Both events, because nothing the sidecar owns may outlive the
            // launcher on any exit path, and stopping it twice is a no-op.
            RunEvent::ExitRequested { .. } | RunEvent::Exit => stop_backend(app_handle),
            _ => {}
        }),
        Err(e) => {
            // Building the Tauri app itself failed. There is no Tauri window to
            // show an error in, so at least leave a breadcrumb in the log...
            let message = format!("FATAL: error building Tauri application: {e}");
            log_line(&message);
            // ...and, on Windows, pop a NATIVE message box so the failure is
            // never silent again (the v7.0.0 updater-plugin crash exited within
            // 2s with nothing on screen). MessageBoxW is a bare Win32 call via
            // windows-sys, so it works even though no Tauri/WebView2 window
            // exists.
            show_startup_failure_dialog(&message);
        }
    }
}

/// How long the launcher waits for the backend to actually be gone.
///
/// A window that is already closed while its process lingers reads as a hang,
/// and at session logoff Windows gives an application very little time before it
/// is killed anyway, so this is a short wait for confirmation and not a budget
/// for the backend to finish work in.
const BACKEND_STOP_WAIT: Duration = Duration::from_secs(5);

/// Ask the operating system to stop the backend process and everything it
/// started.
///
/// `taskkill /T` is the same tool and the same reason as the installer hooks in
/// `windows/hooks.nsh`, which already stop the sidecar tree so a reinstall can
/// replace the locked files. The launcher had no equivalent, which is how the
/// database server outlived the app that started it.
#[cfg(target_os = "windows")]
fn request_backend_stop(pid: u32) {
    use std::os::windows::process::CommandExt;

    /// `CREATE_NO_WINDOW`: a console process spawned from a windowed one puts a
    /// black console on screen, and a console flashing up as the app closes is
    /// the last thing a user should see of it.
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;

    let pid_arg = pid.to_string();
    match std::process::Command::new("taskkill")
        .args(["/PID", pid_arg.as_str(), "/T", "/F"])
        .creation_flags(CREATE_NO_WINDOW)
        .status()
    {
        Ok(status) => log_line(&format!("backend stop: taskkill on pid {pid} exited {status}")),
        Err(e) => log_line(&format!("backend stop: could not run taskkill on pid {pid}: {e}")),
    }
}

/// Ask the backend to stop, the way this platform asks.
///
/// SIGTERM is a real request rather than a kill: the server runs its own
/// shutdown handler, which stops the embedded PostgreSQL cluster cleanly, so
/// the next start has no write-ahead log to replay. The kill below is only the
/// backstop for a process that ignores it.
#[cfg(not(target_os = "windows"))]
fn request_backend_stop(pid: u32) {
    let pid_arg = pid.to_string();
    match std::process::Command::new("kill")
        .args(["-TERM", pid_arg.as_str()])
        .status()
    {
        Ok(status) => log_line(&format!("backend stop: SIGTERM to pid {pid} exited {status}")),
        Err(e) => log_line(&format!("backend stop: could not signal pid {pid}: {e}")),
    }
}

/// Stop the backend sidecar on the way out, and take its children with it.
///
/// Why a tree stop and not just the handle we hold: `CommandChild::kill` is
/// `TerminateProcess` on Windows, which stops that one process and nothing it
/// started. The sidecar starts the embedded PostgreSQL postmaster as a child of
/// its own, and the shipped sidecar is a one-file bundle whose bootloader runs
/// the real interpreter as a further child, so the process the launcher holds a
/// handle to need not be the process holding the database open. What was left
/// behind kept running with nobody to stop it: a postmaster still attached to
/// the cluster after the app had closed, killed eventually by the operating
/// system at logoff, which is an unclean stop, which is why the next launch
/// found a cluster to recover and spent minutes replaying its log before the
/// window would open.
///
/// What this does NOT fix: a forced stop is still an unclean stop for
/// PostgreSQL. The clean path is the backend's own shutdown handler, and
/// reaching it needs a request Windows can deliver to a console process whose
/// parent has no console. On Unix the signal sent above is exactly that request
/// and the handler does run; on Windows the honest answer is a shutdown the
/// backend serves for itself, which is a change on that side of the line.
fn stop_backend(app_handle: &tauri::AppHandle) {
    let state = app_handle.state::<AppState>();
    // Announce the shutdown before causing it. Every watcher treats a backend
    // that disappears as a failure worth telling the user about, and the stop
    // below is a disappearance; without this flag, closing the app would end
    // with a message claiming the backend had crashed.
    state.shutting_down.store(true, Ordering::SeqCst);
    let exited = state.backend_exited.clone();
    // Take the child out in its own statement so the MutexGuard temporary is
    // dropped at the semicolon, before `state` (the State borrow it is taken
    // from) goes out of scope. Holding the guard across the body below borrowed
    // `state` too long and failed to compile (E0597) in the release build.
    let child = state.backend_child.lock().unwrap().take();
    let child = match child {
        Some(child) => child,
        // Nothing to stop: either we attached to a backend somebody else owns,
        // or this has already run once on the way out.
        None => return,
    };

    // Read the pid BEFORE kill(), which consumes the handle.
    let pid = child.pid();
    log_line(&format!("stopping the backend sidecar (pid {pid})"));
    request_backend_stop(pid);

    let deadline = Instant::now() + BACKEND_STOP_WAIT;
    while !exited.load(Ordering::SeqCst) && Instant::now() < deadline {
        std::thread::sleep(Duration::from_millis(100));
    }
    if exited.load(Ordering::SeqCst) {
        log_line("the backend sidecar has exited");
    } else {
        log_line("the backend sidecar did not exit in time; killing the process handle");
        let _ = child.kill();
    }
}

/// Show a native, blocking failure dialog when the app cannot even be built.
///
/// On Windows this calls `MessageBoxW` directly (no Tauri window is available at
/// this point), pairing the error text with the launcher log path so the user
/// can find full diagnostics. On every other platform it is a no-op beyond the
/// log line and stderr that the caller already emitted.
#[cfg(windows)]
fn show_startup_failure_dialog(message: &str) {
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        MessageBoxW, MB_ICONERROR, MB_OK, MB_SETFOREGROUND, MB_TOPMOST,
    };

    let log_hint = log_path()
        .map(|p| format!("\n\nA full diagnostic log was written to:\n{}", p.display()))
        .unwrap_or_default();
    let body = format!(
        "OpenConstructionERP could not start.\n\n{message}{log_hint}\n\n\
If this keeps happening, please send the log file to info@datadrivenconstruction.io."
    );

    let to_wide = |s: &str| -> Vec<u16> {
        s.encode_utf16().chain(std::iter::once(0)).collect::<Vec<u16>>()
    };
    let body_w = to_wide(&body);
    let title_w = to_wide("OpenConstructionERP failed to start");

    // SAFETY: both buffers are valid, NUL-terminated UTF-16; a null HWND is the
    // documented way to show an owner-less message box.
    unsafe {
        MessageBoxW(
            std::ptr::null_mut(),
            body_w.as_ptr(),
            title_w.as_ptr(),
            MB_OK | MB_ICONERROR | MB_SETFOREGROUND | MB_TOPMOST,
        );
    }
}

/// Non-Windows fallback: the log line and stderr from the caller are the whole
/// story, so there is nothing extra to do here.
#[cfg(not(windows))]
fn show_startup_failure_dialog(_message: &str) {}
