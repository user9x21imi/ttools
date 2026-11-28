    /// Use the authenticated streaming session without exposing its bearer token to the UI.
    #[cfg(feature = "streaming")]
    pub fn tspotify_jam_control(&self, action: &str) -> Result<Vec<u8>> {
        anyhow::ensure!(matches!(action, "jam-current" | "jam-start"), "Unsupported Jam action");
        let mut state = self.tspotify_state.lock();
        if state["jam"]["status"].as_str() == Some("loading") {
            return Ok(serde_json::to_vec(&serde_json::json!({"accepted": true}))?);
        }
        state["jam"] = serde_json::json!({"status": "loading"});
        drop(state);
        let client = self.clone();
        let create = action == "jam-start";
        tokio::spawn(async move {
            let request = async {
                let session = client.spotify.session().await;
                let endpoint = if create {
                    "/social-connect/v2/sessions/current_or_new?activate=true&alt=json"
                } else { "/social-connect/v2/sessions/current?alt=json" };
                let bytes = session.spclient().request_as_json(&http::Method::GET, endpoint, None, None).await?;
                let response: serde_json::Value = serde_json::from_slice(&bytes)?;
                let data = response.get("session").unwrap_or(&response);
                let url = data["join_session_url"].as_str().unwrap_or("");
                let members = data["session_members"].as_array().map(|list| list.iter().map(|member| {
                    serde_json::json!({
                        "name": member["display_name"].as_str().or_else(|| member["username"].as_str()).unwrap_or("Участник"),
                    })
                }).collect::<Vec<_>>()).unwrap_or_default();
                anyhow::ensure!(!url.is_empty(), "Spotify did not return a Jam invitation URL");
                Ok::<_, anyhow::Error>(serde_json::json!({"status": "ready", "url": url, "members": members}))
            };
            let result = match tokio::time::timeout(std::time::Duration::from_secs(18), request).await {
                Ok(Ok(value)) => value,
                Ok(Err(error)) => serde_json::json!({"status": "error", "message": format!("{error}")}),
                Err(_) => serde_json::json!({"status": "error", "message": "Spotify Jam request timed out"}),
            };
            client.tspotify_state.lock()["jam"] = result;
        });
        Ok(serde_json::to_vec(&serde_json::json!({"accepted": true}))?)
    }
