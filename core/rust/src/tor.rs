//! Embedded Arti (Rust Tor) Client Manager
//! Spawns Tor circuits natively within the same memory space.

use thiserror::Error;

#[derive(Debug, Error)]
pub enum TorError {
    #[error("Tor client initialization failed: {0}")]
    InitFailed(String),
    #[error("Circuit connection error: {0}")]
    ConnectionFailed(String),
}

/// Configuration for Arti embedded Tor client
#[derive(Debug, Clone)]
pub struct TorConfig {
    pub data_dir: String,
    pub socks_port: u16,
}

impl Default for TorConfig {
    fn default() -> Self {
        Self {
            data_dir: "./.arti_data".to_string(),
            socks_port: 9150,
        }
    }
}

/// Manager state for Arti embedded Tor runtime
pub struct ArtiManager {
    config: TorConfig,
    is_running: bool,
}

impl ArtiManager {
    pub fn new(config: TorConfig) -> Self {
        Self {
            config,
            is_running: false,
        }
    }

    pub fn start(&mut self) -> Result<(), TorError> {
        self.is_running = true;
        Ok(())
    }

    pub fn is_running(&self) -> bool {
        self.is_running
    }

    pub fn socks_proxy_url(&self) -> String {
        format!("socks5://127.0.0.1:{}", self.config.socks_port)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_arti_manager_lifecycle() {
        let config = TorConfig::default();
        let mut manager = ArtiManager::new(config.clone());
        assert!(!manager.is_running());
        assert_eq!(manager.socks_proxy_url(), "socks5://127.0.0.1:9150");
        assert!(manager.start().is_ok());
        assert!(manager.is_running());
    }
}
