"""Multimodal Interaction (Day 2, feature 107).

Ingests a turn that may carry text, an image path, a transcribed audio text or
a voice file path, classifies which modalities are present, routes each to an
honest channel (conversation record, vision routing via the provider registry,
speech record), and persists a unified turn record.
"""

import uuid
from datetime import datetime

from core.kv import KeyValueStore


class MultimodalInput:

    def __init__(self, kv=None, now_fn=None):
        self.kv = kv or KeyValueStore("data/multimodal.json")
        self._now = now_fn or (lambda: datetime.now())

    # ------------------------------------------------------------------
    @staticmethod
    def _classify(turn):
        modalities = []
        if turn.get("text"):
            modalities.append("text")
        if turn.get("image_path"):
            modalities.append("image")
        if turn.get("audio_text"):
            modalities.append("audio")
        if turn.get("voice_path"):
            modalities.append("voice")
        if not modalities:
            modalities.append("empty")
        return modalities

    def ingest(self, turn):
        turn = dict(turn or {})
        turn_id = str(uuid.uuid4())[:8]
        modalities = self._classify(turn)
        record = {
            "turn_id": turn_id,
            "modalities": modalities,
            "channels": [],
            "at": self._now().isoformat(),
            "speaker": turn.get("speaker"),
            "payload": {k: v for k, v in turn.items()
                        if k not in ("speaker", "modalities")},
        }
        records = self.kv.get("turns", [])
        records.append(record)
        self.kv.set("turns", records)
        return record

    # ------------------------------------------------------------------
    def route(self, turn):
        record = self.ingest(turn)
        results = []
        for modality in record["modalities"]:
            if modality == "empty":
                results.append({"modality": "empty",
                                "status": "UNAVAILABLE",
                                "message": "no detectable modality in turn"})
                continue
            outcome = self._route_modality(modality, turn)
            results.append(outcome)
            record["channels"].append(outcome["channel"])
        records = self.kv.get("turns", [])
        for stored in records:
            if stored["turn_id"] == record["turn_id"]:
                stored["channels"] = record["channels"]
        self.kv.set("turns", records)
        return {"turn_id": record["turn_id"], "results": results,
                "modalities": record["modalities"],
                "channels": record["channels"]}

    def _route_modality(self, modality, turn):
        if modality == "text":
            return {
                "modality": "text",
                "channel": "conversation",
                "status": "AVAILABLE",
                "recorded": self._append_channel_text(turn.get("text", "")),
            }
        if modality == "image":
            return self._route_image(turn.get("image_path"))
        if modality in ("audio", "voice"):
            return self._route_speech(turn)
        return {"modality": modality, "channel": "unknown",
                "status": "UNAVAILABLE", "message": "unroutable modality"}

    def _append_channel_text(self, text):
        log = self.kv.get("conversation_records", [])
        log.append({"text": text, "at": self._now().isoformat()})
        self.kv.set("conversation_records", log)
        return len(log)

    def _route_image(self, image_path):
        if not image_path:
            return {"modality": "image", "channel": "vision",
                    "status": "UNAVAILABLE", "message": "no image path"}
        from core.providers.registry import providers_registry
        capability = ("screen_coordinates"
                      if providers_registry.providers_for("screen_coordinates")
                      else "image_metadata")
        outcome = providers_registry.execute(capability,
                                             image_path=image_path,
                                             task="analyse_visual_input")
        status = (outcome.get("status")
                  if isinstance(outcome, dict) else "FAILED")
        return {
            "modality": "image",
            "channel": "vision",
            "delegated": capability,
            "status": status or "NOT_CONFIGURED",
            "result": outcome if isinstance(outcome, dict) else None,
        }

    def _route_speech(self, turn):
        recorded = self._speech_record(turn)
        return {
            "modality": "audio" if turn.get("audio_text") else "voice",
            "channel": "speech",
            "status": "AVAILABLE",
            "speaker": turn.get("speaker"),
            "recorded": recorded,
        }

    def _speech_record(self, turn):
        store = self.kv.get("speech_records", [])
        store.append({
            "speaker": turn.get("speaker", "unknown"),
            "transcript": turn.get("audio_text") or turn.get("voice_path"),
            "at": self._now().isoformat(),
        })
        self.kv.set("speech_records", store)
        return len(store)

    # ------------------------------------------------------------------
    def recent_turns(self, n=5):
        turns = self.kv.get("turns", [])
        return turns[-int(n):]

    def conversation_records(self):
        return self.kv.get("conversation_records", [])

    def speech_records(self):
        return self.kv.get("speech_records", [])


__all__ = ["MultimodalInput"]