"""Media control contract (row 21) — natural-phrase mapping."""

from tools.media import _phrase_to_command, media_command_phrase, media_status


class TestPhraseMapping:

    def test_turn_up_volume(self):
        assert _phrase_to_command("turn up the volume") == "volume_up"

    def test_turn_down_volume(self):
        assert _phrase_to_command("turn down the volume") == "volume_down"

    def test_mute(self):
        assert _phrase_to_command("mute the sound") == "mute"

    def test_set_volume(self):
        command = _phrase_to_command("set volume to 50 percent")
        assert command is not None
        assert command.startswith("set_volume_")

    def test_unknown_phrase(self):
        assert _phrase_to_command("how are you") is None


class TestCommandPhrase:

    def test_unknown_phrase_returns_unavailable(self):
        outcome = media_command_phrase("what do you recommend for lunch")
        assert outcome["success"] is False
        assert outcome.get("unknown") is True

    def test_status_available_shape(self):
        status = media_status()
        assert status["success"] is True
        assert "available" in status

    def test_known_mapping_routes_when_backend_missing(self):
        # With pycaw present the command executes; without it the call still
        # returns a structured unavailable (never crashes).
        outcome = media_command_phrase("turn up the volume")
        assert "success" in outcome