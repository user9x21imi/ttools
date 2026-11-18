    /// tspotify's synchronous local IPC: controls librespot, never Spotify Web API.
    pub fn tspotify_local_control(&self, command: &str, value: i64) -> Result<Vec<u8>> {
        if command == "capabilities" {
            return Ok(serde_json::to_vec(&serde_json::json!({
                "protocol": 1, "local_volume": true, "local_seek": true,
                "local_transport": true, "engine": "tspotify-librespot"
            }))?);
        }
        #[cfg(feature = "streaming")]
        {
            let connection = self.stream_conn.lock();
            let spirc = connection.as_ref().context("Integrated playback is still connecting")?;
            match command {
                "volume" => spirc.set_volume((value.clamp(0, 100) as u32 * 65535 / 100) as u16)?,
                "seek" => spirc.set_position_ms(value.clamp(0, u32::MAX as i64) as u32)?,
                "play" => spirc.play()?,
                "pause" => spirc.pause()?,
                "play-pause" => spirc.play_pause()?,
                "next" => spirc.next()?,
                "previous" => spirc.prev()?,
                _ => anyhow::bail!("Unsupported local control: {command}"),
            }
            return Ok(serde_json::to_vec(&serde_json::json!({"accepted": true, "local": true}))?);
        }
        #[cfg(not(feature = "streaming"))]
        anyhow::bail!("This engine was built without streaming")
    }
