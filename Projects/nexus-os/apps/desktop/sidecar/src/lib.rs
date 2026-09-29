//! Launches and supervises the NEXUS API process.
//!
//! This crate deliberately has no GUI dependencies so its logic (token, port, health wait,
//! process lifecycle) is unit-tested independently of Tauri.

use std::collections::HashMap;
use std::fmt;
use std::fs::File;
use std::io::{self, Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

#[derive(Debug)]
pub enum SidecarError {
    Io(io::Error),
    EmptyCommand,
    ExitedEarly(Option<i32>),
    HealthTimeout(Duration),
}

impl fmt::Display for SidecarError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            SidecarError::Io(e) => write!(f, "could not run the NEXUS API: {e}"),
            SidecarError::EmptyCommand => write!(f, "no API command configured"),
            SidecarError::ExitedEarly(code) => {
                write!(f, "the NEXUS API exited during startup (code {code:?})")
            }
            SidecarError::HealthTimeout(d) => {
                write!(f, "the NEXUS API did not become healthy within {d:?}")
            }
        }
    }
}

impl std::error::Error for SidecarError {}

impl From<io::Error> for SidecarError {
    fn from(e: io::Error) -> Self {
        SidecarError::Io(e)
    }
}

/// Ask the OS for a free loopback port.
pub fn free_port() -> io::Result<u16> {
    let listener = TcpListener::bind(("127.0.0.1", 0))?;
    Ok(listener.local_addr()?.port())
}

/// 256 bits of OS randomness, hex encoded. Read from the OS CSPRNG, never derived from time.
pub fn new_token() -> io::Result<String> {
    let mut bytes = [0u8; 32];
    read_os_random(&mut bytes)?;
    Ok(bytes.iter().map(|b| format!("{b:02x}")).collect())
}

#[cfg(unix)]
fn read_os_random(buf: &mut [u8]) -> io::Result<()> {
    File::open("/dev/urandom")?.read_exact(buf)
}

#[cfg(windows)]
fn read_os_random(buf: &mut [u8]) -> io::Result<()> {
    // BCryptGenRandom with the system-preferred RNG.
    #[link(name = "bcrypt")]
    extern "system" {
        fn BCryptGenRandom(alg: *mut core::ffi::c_void, buf: *mut u8, len: u32, flags: u32) -> i32;
    }
    const USE_SYSTEM_PREFERRED_RNG: u32 = 0x0000_0002;
    let status = unsafe {
        BCryptGenRandom(
            core::ptr::null_mut(),
            buf.as_mut_ptr(),
            buf.len() as u32,
            USE_SYSTEM_PREFERRED_RNG,
        )
    };
    if status == 0 {
        Ok(())
    } else {
        Err(io::Error::new(
            io::ErrorKind::Other,
            format!("BCryptGenRandom failed: {status:#x}"),
        ))
    }
}

#[derive(Debug, Clone)]
pub struct SidecarConfig {
    /// Program and arguments, e.g. `["uv", "run", "--project", "services/api", "nexus", "serve"]`.
    pub command: Vec<String>,
    pub cwd: Option<PathBuf>,
    pub home: PathBuf,
    pub port: u16,
    pub token: String,
    pub extra_env: HashMap<String, String>,
    pub startup_timeout: Duration,
}

pub struct Sidecar {
    child: Child,
    pub base_url: String,
    pub token: String,
}

/// One HTTP/1.1 GET over a plain TCP socket. Enough for the unauthenticated ping.
pub fn http_get_ok(addr: SocketAddr, path: &str, timeout: Duration) -> bool {
    let Ok(mut stream) = TcpStream::connect_timeout(&addr, timeout) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(timeout));
    let _ = stream.set_write_timeout(Some(timeout));
    let request = format!("GET {path} HTTP/1.1\r\nHost: {addr}\r\nConnection: close\r\n\r\n");
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut response = String::new();
    let _ = stream.read_to_string(&mut response);
    response.starts_with("HTTP/1.1 200") && response.contains("\"ok\":true")
}

/// Poll until `/api/health/ping` answers, the process dies, or the timeout passes.
pub fn wait_for_health(
    addr: SocketAddr,
    timeout: Duration,
    mut still_running: impl FnMut() -> Result<(), SidecarError>,
) -> Result<(), SidecarError> {
    let deadline = Instant::now() + timeout;
    loop {
        if http_get_ok(addr, "/api/health/ping", Duration::from_millis(500)) {
            return Ok(());
        }
        still_running()?;
        if Instant::now() >= deadline {
            return Err(SidecarError::HealthTimeout(timeout));
        }
        std::thread::sleep(Duration::from_millis(150));
    }
}

impl Sidecar {
    pub fn start(cfg: SidecarConfig) -> Result<Sidecar, SidecarError> {
        let (program, args) = cfg
            .command
            .split_first()
            .ok_or(SidecarError::EmptyCommand)?;
        std::fs::create_dir_all(&cfg.home)?;
        let mut cmd = Command::new(program);
        cmd.args(args)
            .env("NEXUS_HOME", &cfg.home)
            .env("NEXUS_PORT", cfg.port.to_string())
            .env("NEXUS_API_TOKEN", &cfg.token)
            .envs(&cfg.extra_env)
            .stdin(Stdio::null())
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit());
        if let Some(cwd) = &cfg.cwd {
            cmd.current_dir(cwd);
        }
        let mut child = cmd.spawn()?;
        let addr: SocketAddr = ([127, 0, 0, 1], cfg.port).into();
        let result = wait_for_health(addr, cfg.startup_timeout, || match child.try_wait()? {
            Some(status) => Err(SidecarError::ExitedEarly(status.code())),
            None => Ok(()),
        });
        if let Err(e) = result {
            let _ = child.kill();
            let _ = child.wait();
            return Err(e);
        }
        Ok(Sidecar {
            child,
            base_url: format!("http://127.0.0.1:{}", cfg.port),
            token: cfg.token,
        })
    }

    /// The script the shell injects so the web app learns where the API is. The token is only
    /// ever handed to this window and never written to disk by the shell.
    pub fn init_script(&self) -> String {
        init_script(&self.base_url, &self.token)
    }

    pub fn stop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

impl Drop for Sidecar {
    fn drop(&mut self) {
        self.stop();
    }
}

/// Encode `value` as a JavaScript/JSON string literal that is also safe inside HTML.
pub fn js_string(value: &str) -> String {
    let mut out = String::with_capacity(value.len() + 2);
    out.push('"');
    for ch in value.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '<' | '>' | '&' | '\u{2028}' | '\u{2029}' => {
                out.push_str(&format!("\\u{:04x}", ch as u32))
            }
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

pub fn init_script(base_url: &str, token: &str) -> String {
    format!(
        "window.__NEXUS__ = {{ baseUrl: {}, token: {} }};",
        js_string(base_url),
        js_string(token)
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;
    use std::thread;

    #[test]
    fn free_ports_are_bindable() {
        let p = free_port().unwrap();
        assert!(p > 1023);
        TcpListener::bind(("127.0.0.1", p)).unwrap();
    }

    #[test]
    fn tokens_are_long_hex_and_unique() {
        let a = new_token().unwrap();
        let b = new_token().unwrap();
        assert_eq!(a.len(), 64);
        assert!(a.chars().all(|c| c.is_ascii_hexdigit()));
        assert_ne!(a, b);
    }

    fn serve_once(body: &'static str, status: &'static str) -> SocketAddr {
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let addr = listener.local_addr().unwrap();
        thread::spawn(move || {
            for stream in listener.incoming().take(20) {
                let mut s = stream.unwrap();
                let mut buf = [0u8; 512];
                let _ = s.read(&mut buf);
                let resp = format!(
                    "HTTP/1.1 {status}\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{body}",
                    body.len()
                );
                let _ = s.write_all(resp.as_bytes());
            }
        });
        addr
    }

    #[test]
    fn health_ok_when_ping_answers() {
        let addr = serve_once("{\"ok\":true}", "200 OK");
        assert!(http_get_ok(
            addr,
            "/api/health/ping",
            Duration::from_secs(1)
        ));
        wait_for_health(addr, Duration::from_secs(2), || Ok(())).unwrap();
    }

    #[test]
    fn health_rejects_wrong_status_or_body() {
        let bad_status = serve_once("{\"ok\":true}", "500 Internal Server Error");
        assert!(!http_get_ok(
            bad_status,
            "/api/health/ping",
            Duration::from_secs(1)
        ));
        let bad_body = serve_once("{\"ok\":false}", "200 OK");
        assert!(!http_get_ok(
            bad_body,
            "/api/health/ping",
            Duration::from_secs(1)
        ));
    }

    #[test]
    fn health_times_out_when_nothing_listens() {
        let port = free_port().unwrap();
        let addr: SocketAddr = ([127, 0, 0, 1], port).into();
        let err = wait_for_health(addr, Duration::from_millis(400), || Ok(())).unwrap_err();
        assert!(matches!(err, SidecarError::HealthTimeout(_)));
    }

    #[test]
    fn startup_aborts_when_the_process_dies() {
        let port = free_port().unwrap();
        let addr: SocketAddr = ([127, 0, 0, 1], port).into();
        let err = wait_for_health(addr, Duration::from_secs(5), || {
            Err(SidecarError::ExitedEarly(Some(1)))
        })
        .unwrap_err();
        assert!(matches!(err, SidecarError::ExitedEarly(Some(1))));
    }

    #[test]
    fn empty_command_is_rejected() {
        let cfg = SidecarConfig {
            command: vec![],
            cwd: None,
            home: std::env::temp_dir().join("nexus-sidecar-test"),
            port: 1,
            token: "t".into(),
            extra_env: HashMap::new(),
            startup_timeout: Duration::from_millis(10),
        };
        assert!(matches!(
            Sidecar::start(cfg),
            Err(SidecarError::EmptyCommand)
        ));
    }

    #[test]
    fn js_strings_cannot_break_out() {
        assert_eq!(js_string("abc"), "\"abc\"");
        assert_eq!(js_string("a\"b"), "\"a\\\"b\"");
        assert_eq!(js_string("a\\b"), "\"a\\\\b\"");
        assert_eq!(js_string("x\ny"), "\"x\\ny\"");
        assert_eq!(js_string("</script>"), "\"\\u003c/script\\u003e\"");
        assert_eq!(js_string("\u{1b}"), "\"\\u001b\"");
        let script = init_script("http://127.0.0.1:9", "tok\"; alert(1); //");
        // The hostile quote stays inside the string literal, escaped.
        assert!(script.ends_with("token: \"tok\\\"; alert(1); //\" };"));
    }
}
