"""Tests for Meeting Management (67), Conversation State (68),
Emotional Intelligence (69), Speaker Recognition (48), and Language
Detection (49).  Each test uses isolated temp paths."""

import os
import numpy as np

from core.meetings import MeetingManager, ParticipantRegistry, ConversationState
from core.affect import AffectEngine, _DISCLAIMER
from core.speech import SpeakerRecognition, LanguageDetector, _voiceprint, _cosine
from core.kv import KeyValueStore


# ------------------------------------------------------------------
# Meetings (67 + 68)
# ------------------------------------------------------------------


class TestMeetingLifecycle:

    def test_create_meeting(self, tmp_path):
        kv = str(tmp_path / "m.json")
        mm = MeetingManager(kv_path=kv)
        mid = mm.create_meeting("Sprint Review", agenda=["Demo", "Retrospective"])
        meeting = mm._get(mid)
        assert meeting["title"] == "Sprint Review"
        assert meeting["agenda"] == ["Demo", "Retrospective"]

    def test_add_topic_and_decision(self, tmp_path):
        mm = MeetingManager(kv_path=str(tmp_path / "m.json"))
        mid = mm.create_meeting("Planning")
        mm.add_topic(mid, "Budget")
        mm.add_decision(mid, "Use Scrum")
        meeting = mm._get(mid)
        assert meeting["topics"][0]["title"] == "Budget"
        assert meeting["decisions"][0]["text"] == "Use Scrum"

    def test_add_action_item(self, tmp_path):
        mm = MeetingManager(kv_path=str(tmp_path / "m.json"))
        mid = mm.create_meeting("Retro")
        item = mm.add_action_item(mid, "Alice", "2025-12-01", "Update docs")
        assert item["owner"] == "Alice"
        assert item["status"] == "open"

    def test_capture_transcript(self, tmp_path):
        mm = MeetingManager(kv_path=str(tmp_path / "m.json"))
        mid = mm.create_meeting("Standup")
        line = mm.capture(mid, "Bob", "Yesterday I finished the API")
        assert line["speaker"] == "Bob"
        assert "Yesterday" in line["text"]

    def test_missing_meeting_raises(self, tmp_path):
        mm = MeetingManager(kv_path=str(tmp_path / "m.json"))
        import pytest
        with pytest.raises(KeyError):
            mm._get("nonexistent")


class TestMeetingMinutes:

    def test_summary_content(self, tmp_path):
        mm = MeetingManager(kv_path=str(tmp_path / "m.json"))
        mid = mm.create_meeting("Design Review", agenda=["Mockups"])
        mm.add_topic(mid, "Colors")
        mm.add_decision(mid, "Use blue theme")
        mm.add_action_item(mid, "Eve", "2025-11-15", "Update palette")
        mm.capture(mid, "Eve", "I prefer blue")
        mm.participants.register_participant("Eve", "designer")
        minutes = mm.summary(mid)
        assert minutes["title"] == "Design Review"
        assert len(minutes["decisions"]) == 1
        assert minutes["decisions"][0]["text"] == "Use blue theme"
        assert len(minutes["action_items"]) == 1
        assert "Eve" in minutes["participants"]

    def test_export_minutes_creates_file(self, tmp_path):
        mm = MeetingManager(kv_path=str(tmp_path / "m.json"), output_root=str(tmp_path))
        mid = mm.create_meeting("Export Test", agenda=["A", "B"])
        mm.add_decision(mid, "Do X")
        path = mm.export_minutes(mid)
        assert path.endswith(".md")
        assert os.path.exists(path)
        content = open(path, encoding="utf-8").read()
        assert "Export Test" in content
        assert "Do X" in content


class TestParticipantRegistry:

    def test_register_and_list(self, tmp_path):
        kv = KeyValueStore(str(tmp_path / "p.json"))
        reg = ParticipantRegistry(kv)
        reg.register_participant("Alice", "lead")
        reg.register_participant("Bob", "member")
        participants = reg.list_participants()
        assert "Alice" in participants
        assert participants["Alice"]["role"] == "lead"
        assert "Bob" in participants


class TestConversationState:

    def test_turn_and_context_switch(self, tmp_path):
        kv = KeyValueStore(str(tmp_path / "c.json"))
        cs = ConversationState(kv)
        s = cs.turn("Alice")
        assert s["active_participant"] == "Alice"
        assert len(s["turns"]) == 1
        cs.context_switch("Budget")
        s2 = cs.current()
        assert s2["current_topic"] == "Budget"

    def test_turns_accumulate(self, tmp_path):
        kv = KeyValueStore(str(tmp_path / "c.json"))
        cs = ConversationState(kv)
        cs.turn("Alice")
        cs.turn("Bob")
        s = cs.current()
        assert len(s["turns"]) == 2
        assert s["turns"][1]["speaker"] == "Bob"


class TestMeetingPersistence:

    def test_survives_new_instance(self, tmp_path):
        kv = str(tmp_path / "m.json")
        mm1 = MeetingManager(kv_path=kv)
        mid = mm1.create_meeting("Persist")
        mm1.capture(mid, "Zed", "Test line")
        mm2 = MeetingManager(kv_path=kv)
        meeting = mm2._get(mid)
        assert meeting["transcript"][0]["text"] == "Test line"


# ------------------------------------------------------------------
# Affect Engine (69)
# ------------------------------------------------------------------


class TestAffectValence:

    def test_positive_text(self):
        ae = AffectEngine()
        entry = ae.observe("Alice", "I love this! It is awesome and great!")
        assert entry["valence"] > 0

    def test_negative_text(self):
        ae = AffectEngine()
        entry = ae.observe("Bob", "This is terrible and I hate it so much.")
        assert entry["valence"] < 0

    def test_neutral_text(self):
        ae = AffectEngine()
        entry = ae.observe("Carol", "The meeting is at three o'clock.")
        assert entry["valence"] == 0

    def test_energy_punctuation(self):
        ae = AffectEngine()
        entry = ae.observe("Dan", "WOW!!! That is incredible!!!")
        assert entry["energy"] > 0

    def test_energy_calm(self):
        ae = AffectEngine()
        entry = ae.observe("Eve", "ok")
        assert entry["energy"] < 0.2


class TestAffectMood:

    def test_mood_updates(self):
        ae = AffectEngine()
        ae.observe("A", "I am so happy and excited")
        ae.observe("B", "This is really bad and sad")
        mood = ae.mood()
        assert mood["observations"] == 2

    def test_affect_map_label(self):
        ae = AffectEngine()
        for _ in range(5):
            ae.observe("A", "This is wonderful and great and awesome")
        amap = ae.affect_map()
        assert amap["label"] in ("content", "elated", "neutral")


class TestAffectAdaptTone:

    def test_supportive_for_negative(self):
        ae = AffectEngine()
        ae.observe("A", "I feel sad and frustrated about everything")
        result = ae.adapt_tone()
        assert result["suggested_tone"] == "supportive"

    def test_calm_for_low_energy(self):
        ae = AffectEngine()
        ae.observe("A", "ok")
        result = ae.adapt_tone()
        assert result["suggested_tone"] in ("calm", "neutral")


class TestAffectEmpathyReply:

    def test_negative_empathy(self):
        ae = AffectEngine()
        ae.observe("A", "I am sad and angry and frustrated")
        reply = ae.empathy_reply(context="work stress")
        assert "work stress" in reply["template"]
        assert _DISCLAIMER in reply["disclaimer"]

    def test_positive_empathy(self):
        ae = AffectEngine()
        ae.observe("A", "I love this! It is wonderful!")
        reply = ae.empathy_reply("project completion")
        assert "wonderful" in reply["template"].lower() or "glad" in reply["template"].lower()

    def test_neutral_empathy(self):
        ae = AffectEngine()
        ae.observe("A", "The weather is fine.")
        reply = ae.empathy_reply()
        assert reply["template"]


# ------------------------------------------------------------------
# Speaker Recognition (48)
# ------------------------------------------------------------------


def _sine_wave(freq, sr=16000, duration=0.2):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return np.sin(2 * np.pi * freq * t)


class TestVoiceprint:

    def test_voiceprint_shape_and_norm(self):
        vp = _voiceprint(_sine_wave(440), sr=16000)
        assert len(vp) == 32
        assert abs(np.linalg.norm(vp) - 1.0) < 0.01

    def test_cosine_similar(self):
        a = _voiceprint(_sine_wave(440))
        b = _voiceprint(_sine_wave(440))
        assert _cosine(a, b) > 0.8

    def test_cosine_different(self):
        a = _voiceprint(_sine_wave(440))
        b = _voiceprint(_sine_wave(880))
        assert _cosine(a, b) < _cosine(a, a)


class TestEnroll:

    def test_enroll_with_consent(self, tmp_path):
        sr = SpeakerRecognition(kv_path=str(tmp_path / "sp.json"))
        result = sr.enroll("Alice", _sine_wave(440), consent=True)
        assert result["status"] == "AVAILABLE"

    def test_enroll_without_consent_refused(self, tmp_path):
        sr = SpeakerRecognition(kv_path=str(tmp_path / "sp.json"))
        result = sr.enroll("Alice", _sine_wave(440), consent=False)
        assert result["status"] == "REQUIRES_PERMISSION"

    def test_enroll_persists(self, tmp_path):
        kv = str(tmp_path / "sp.json")
        sr1 = SpeakerRecognition(kv_path=kv)
        sr1.enroll("Alice", _sine_wave(440))
        sr2 = SpeakerRecognition(kv_path=kv)
        speakers = sr2.list_speakers()
        assert "Alice" in [s["speaker_id"] for s in speakers]


class TestRecognize:

    def test_distinguish_speakers(self, tmp_path):
        sr = SpeakerRecognition(kv_path=str(tmp_path / "sp.json"))
        sr.enroll("SpeakerA", _sine_wave(440))
        sr.enroll("SpeakerB", _sine_wave(990))
        result = sr.recognize(_sine_wave(440))
        assert result["best_match"] == "SpeakerA"
        result_b = sr.recognize(_sine_wave(990))
        assert result_b["best_match"] == "SpeakerB"

    def test_authorized_always_false(self, tmp_path):
        sr = SpeakerRecognition(kv_path=str(tmp_path / "sp.json"))
        sr.enroll("Alice", _sine_wave(440))
        result = sr.recognize(_sine_wave(440))
        assert result["authorized"] is False

    def test_no_speakers(self, tmp_path):
        sr = SpeakerRecognition(kv_path=str(tmp_path / "sp.json"))
        result = sr.recognize(_sine_wave(440))
        assert result["authorized"] is False
        assert result["status"] == "UNAVAILABLE"

    def test_delete_speaker(self, tmp_path):
        sr = SpeakerRecognition(kv_path=str(tmp_path / "sp.json"))
        sr.enroll("Alice", _sine_wave(440))
        result = sr.delete_speaker("Alice")
        assert result["removed"] is True
        assert sr.list_speakers() == []


# ------------------------------------------------------------------
# Language Detection (49)
# ------------------------------------------------------------------


class TestLanguageDetector:

    def test_english_detection(self):
        ld = LanguageDetector()
        result = ld.detect("The quick brown fox jumps over the lazy dog")
        assert result["language"] == "en"

    def test_german_detection(self):
        ld = LanguageDetector()
        result = ld.detect("der hund ist sehr schnell und freundlich")
        assert result["language"] == "de"

    def test_forced_override(self):
        ld = LanguageDetector()
        ld.set_language("fr", force=True)
        result = ld.detect("random english text")
        assert result["language"] == "fr"

    def test_insufficient_text_unknown(self):
        ld = LanguageDetector()
        result = ld.detect("")
        assert result["language"] == "UNKNOWN"
        assert result["status"] == "NOT_CONFIGURED"

    def test_confidence_present(self):
        ld = LanguageDetector()
        result = ld.detect("this is a clear english sentence for sure")
        assert "confidence" in result
