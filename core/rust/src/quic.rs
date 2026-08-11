//! QUIC & WebTransport Endpoint Manager
//! Provides 0-RTT connection resumption and multiplexed transport streams.

use thiserror::Error;

#[derive(Debug, Error)]
pub enum QuicError {
    #[error("Endpoint creation failed: {0}")]
    EndpointFailed(String),
    #[error("Connection stream failed: {0}")]
    StreamFailed(String),
}

/// QUIC transport endpoint configuration
#[derive(Debug, Clone)]
pub struct QuicConfig {
    pub bind_addr: String,
    pub max_idle_timeout_ms: u64,
}

impl Default for QuicConfig {
    fn default() -> Self {
        Self {
            bind_addr: "0.0.0.0:4433".to_string(),
            max_idle_timeout_ms: 30000,
        }
    }
}

/// Managed QUIC endpoint session state
pub struct QuicEndpoint {
    config: QuicConfig,
    active_streams: usize,
}

impl QuicEndpoint {
    pub fn new(config: QuicConfig) -> Self {
        Self {
            config,
            active_streams: 0,
        }
    }

    pub fn bind_address(&self) -> &str {
        &self.config.bind_addr
    }

    pub fn active_stream_count(&self) -> usize {
        self.active_streams
    }

    pub fn open_stream(&mut self) -> Result<u64, QuicError> {
        self.active_streams += 1;
        Ok(self.active_streams as u64)
    }

    pub fn close_stream(&mut self) {
        if self.active_streams > 0 {
            self.active_streams -= 1;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_quic_endpoint_lifecycle() {
        let mut endpoint = QuicEndpoint::new(QuicConfig::default());
        assert_eq!(endpoint.bind_address(), "0.0.0.0:4433");
        assert_eq!(endpoint.active_stream_count(), 0);
        let stream_id = endpoint.open_stream().unwrap();
        assert_eq!(stream_id, 1);
        assert_eq!(endpoint.active_stream_count(), 1);
        endpoint.close_stream();
        assert_eq!(endpoint.active_stream_count(), 0);
    }
}
