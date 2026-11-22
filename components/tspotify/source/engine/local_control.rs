    /// tspotify's synchronous local IPC: controls librespot, never Spotify Web API.
    pub fn tspotify_local_control(&self, command: &str, value: i64) -> Result<Vec<u8>> {
        if command == "capabilities" {
            return Ok(serde_json::to_vec(&serde_json::json!({
                "protocol": 1, "local_volume": true, "local_seek": true,
                "local_transport": true, "local_load": true, "local_queue": true, "native_state": true, "local_modes": true, "native_queue": true, "native_jam": true, "atomic_modes": true, "engine": "tspotify-librespot"
            }))?);
        }
        #[cfg(feature = "streaming")]
        if command.starts_with("jam-") {
            return self.tspotify_jam_control(command);
        }
        #[cfg(feature = "streaming")]
        if command == "state" {
            let mut state = self.tspotify_state.lock().clone();
            if let Some(spirc) = self.stream_conn.lock().as_ref() {
                if let Some(queue) = spirc.tspotify_queue().as_object() {
                    for (key, value) in queue { state[key] = value.clone(); }
                }
            }
            if state["applied_mode_revision"].is_number() {
                if !state["actual_shuffle"].is_null() {
                    state["shuffle_state"] = state["actual_shuffle"].clone();
                    if state["desired_shuffle"] == state["actual_shuffle"] && state["applied_mode_revision"].as_u64().unwrap_or(0) >= state["shuffle_revision"].as_u64().unwrap_or(u64::MAX) {
                        state.as_object_mut().unwrap().remove("desired_shuffle");
                        let mut shared = self.tspotify_state.lock();
                        if shared["desired_shuffle"] == state["actual_shuffle"] {
                            shared.as_object_mut().unwrap().remove("desired_shuffle");
                        }
                    }
                }
                if !state["actual_repeat"].is_null() {
                    state["repeat_state"] = state["actual_repeat"].clone();
                    if state["desired_repeat"] == state["actual_repeat"] && state["applied_mode_revision"].as_u64().unwrap_or(0) >= state["repeat_revision"].as_u64().unwrap_or(u64::MAX) {
                        state.as_object_mut().unwrap().remove("desired_repeat");
                        let mut shared = self.tspotify_state.lock();
                        if shared["desired_repeat"] == state["actual_repeat"] {
                            shared.as_object_mut().unwrap().remove("desired_repeat");
                        }
                    }
                }
            }
            return Ok(serde_json::to_vec(&state)?);
        }
        #[cfg(feature = "streaming")]
        {
            let connection = self.stream_conn.lock();
            let spirc = connection.as_ref().context("Integrated playback is still connecting")?;
            if let Some(json) = command.strip_prefix("load:") {
                use librespot_connect::{LoadRequest, LoadRequestOptions, LoadContextOptions, Options, PlayingTrack};
                let payload: serde_json::Value = serde_json::from_str(json)?;
                let uri = payload["uri"].as_str().context("Missing track URI")?;
                anyhow::ensure!(uri.starts_with("spotify:track:") && uri.len() == 36, "Invalid track URI");
                let modes = self.tspotify_state.lock().clone();
                let applied = spirc.tspotify_queue();
                let repeat = modes["desired_repeat"].as_str().or_else(|| applied["actual_repeat"].as_str()).or_else(|| modes["repeat_state"].as_str()).unwrap_or("off");
                let options = LoadRequestOptions {
                    start_playing: true,
                    seek_to: value.clamp(0, u32::MAX as i64) as u32,
                    playing_track: Some(PlayingTrack::Uri(uri.to_owned())),
                    context_options: Some(LoadContextOptions::Options(Options {
                        shuffle: modes["desired_shuffle"].as_bool().or_else(|| applied["actual_shuffle"].as_bool()).or_else(|| modes["shuffle_state"].as_bool()).unwrap_or(false),
                        repeat: repeat == "context", repeat_track: repeat == "track",
                    })),
                    ..Default::default()
                };
                let tracks: Vec<String> = payload["uris"].as_array().map(|entries| entries.iter().take(100)
                    .filter_map(|entry| entry.as_str())
                    .filter(|track| track.starts_with("spotify:track:") && track.len() == 36)
                    .map(str::to_owned).collect()).unwrap_or_default();
                let request = if !tracks.is_empty() {
                    LoadRequest::from_tracks(tracks, options)
                } else { match payload["context_uri"].as_str() {
                    Some(context) if context.starts_with("spotify:playlist:") || context.starts_with("spotify:album:") =>
                        LoadRequest::from_context_uri(context.to_owned(), options),
                    _ => LoadRequest::from_tracks(vec![uri.to_owned()], options),
                }
                };
                spirc.activate()?;
                spirc.load(request)?;
                return Ok(serde_json::to_vec(&serde_json::json!({"accepted": true, "local": true}))?);
            }
            match command {
                "volume" => spirc.set_volume((value.clamp(0, 100) as u32 * 65535 / 100) as u16)?,
                "seek" => spirc.set_position_ms(value.clamp(0, u32::MAX as i64) as u32)?,
                "play" => spirc.play()?,
                "pause" => spirc.pause()?,
                "play-pause" => spirc.play_pause()?,
                "next" => spirc.next()?,
                "previous" => spirc.prev()?,
                "shuffle" | "repeat" => {
                    let mut state = self.tspotify_state.lock();
                    let revision = state["requested_mode_revision"].as_u64().unwrap_or(0) + 1;
                    state["requested_mode_revision"] = serde_json::json!(revision);
                    if command == "shuffle" {
                        state["desired_shuffle"] = serde_json::json!(value != 0);
                        state["shuffle_revision"] = serde_json::json!(revision);
                    } else {
                        state["desired_repeat"] = serde_json::json!(if value == 2 { "track" } else if value == 1 { "context" } else { "off" });
                        state["repeat_revision"] = serde_json::json!(revision);
                    }
                    drop(state);
                    spirc.tspotify_mode(command, value, revision)?;
                },
                _ => anyhow::bail!("Unsupported local control: {command}"),
            }
            return Ok(serde_json::to_vec(&serde_json::json!({"accepted": true, "local": true}))?);
        }
        #[cfg(not(feature = "streaming"))]
        anyhow::bail!("This engine was built without streaming")
    }
