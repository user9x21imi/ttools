#[cfg(test)]
mod tspotify_connect_tests {
    use librespot_connect::PlayingTrack;
    use librespot_core::dealer::protocol::SkipTo;

    #[test]
    fn tspotify_skip_empty_uri_uses_actual_uid() {
        let skip: SkipTo = serde_json::from_str(r#"{"track_uri":"","track_uid":"chosen","track_index":0}"#).unwrap();
        assert!(matches!(PlayingTrack::try_from(skip), Ok(PlayingTrack::Uid(uid)) if uid == "chosen"));
    }
    #[test]
    fn tspotify_skip_empty_identifiers_use_actual_index() {
        let skip: SkipTo = serde_json::from_str(r#"{"track_uri":"","track_uid":"","track_index":7}"#).unwrap();
        assert!(matches!(PlayingTrack::try_from(skip), Ok(PlayingTrack::Index(7))));
    }
    #[test]
    fn tspotify_skip_valid_uri_remains_authoritative() {
        let skip: SkipTo = serde_json::from_str(r#"{"track_uri":"spotify:track:aaaaaaaaaaaaaaaaaaaaaa","track_uid":"","track_index":0}"#).unwrap();
        assert!(matches!(PlayingTrack::try_from(skip), Ok(PlayingTrack::Uri(uri)) if uri.ends_with("aaaaaaaaaaaaaaaaaaaaaa")));
    }
}
