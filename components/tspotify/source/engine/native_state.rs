    #[cfg(feature = "streaming")]
    pub(crate) fn tspotify_player_event(&self, event: &librespot_playback::player::PlayerEvent) {
        use librespot_playback::player::PlayerEvent as E;
        let now = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default().as_millis() as u64;
        let mut state = self.tspotify_state.lock();
        if let Some(id) = event.get_play_request_id() {
            if id < state["play_request_id"].as_u64().unwrap_or(0) { return; }
        }
        match event {
            E::Playing { play_request_id, track_id, position_ms } |
            E::Paused { play_request_id, track_id, position_ms } |
            E::Loading { play_request_id, track_id, position_ms } => {
                state["play_request_id"] = serde_json::json!(play_request_id);
                state["track_uri"] = serde_json::json!(track_id.to_uri().unwrap_or_default());
                state["position_ms"] = serde_json::json!(position_ms);
                state["position_at_ms"] = serde_json::json!(now);
                state["is_playing"] = serde_json::json!(matches!(event, E::Playing { .. }));
                state["is_loading"] = serde_json::json!(matches!(event, E::Loading { .. }));
            }
            E::Seeked { track_id, position_ms, .. } |
            E::PositionChanged { track_id, position_ms, .. } |
            E::PositionCorrection { track_id, position_ms, .. } => {
                state["track_uri"] = serde_json::json!(track_id.to_uri().unwrap_or_default());
                state["position_ms"] = serde_json::json!(position_ms);
                state["position_at_ms"] = serde_json::json!(now);
                if matches!(event, E::Seeked { .. }) {
                    state["seek_revision"] = serde_json::json!(state["seek_revision"].as_u64().unwrap_or(0) + 1);
                }
            }
            E::Stopped { .. } | E::EndOfTrack { .. } => {
                let elapsed = if state["is_playing"].as_bool().unwrap_or(false) {
                    now.saturating_sub(state["position_at_ms"].as_u64().unwrap_or(now))
                } else { 0 };
                state["position_ms"] = serde_json::json!(state["position_ms"].as_u64().unwrap_or(0) + elapsed);
                state["position_at_ms"] = serde_json::json!(now);
                state["is_playing"] = serde_json::json!(false);
                state["is_loading"] = serde_json::json!(false);
            }
            E::Unavailable { track_id, .. } => {
                state["failure_uri"] = serde_json::json!(track_id.to_uri().unwrap_or_default());
                state["failure_at_ms"] = serde_json::json!(now);
            }
            E::ShuffleChanged { shuffle } => {
                state["shuffle_state"] = serde_json::json!(shuffle);
            },
            E::RepeatChanged { context, track } => {
                let mode = if *track { "track" } else if *context { "context" } else { "off" };
                state["repeat_state"] = serde_json::json!(mode);
            }
            E::VolumeChanged { volume } => {
                state["volume_percent"] = serde_json::json!((u32::from(*volume) * 100 + 32767) / 65535);
            }
            _ => return,
        }
        state["revision"] = serde_json::json!(state["revision"].as_u64().unwrap_or(0) + 1);
        state["event_at_ms"] = serde_json::json!(now);
    }
