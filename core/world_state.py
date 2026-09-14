"""Feature 99 — World State Model.

``WorldState`` tracks entities with versioned attributes (value + timestamp +
unit), can answer point-in-time queries, projects attribute values via real
linear extrapolation from history deltas, keeps a delta history, and reports
stale attributes and conflicting "twin" entities. Persisted via kv.
"""

import copy
import time

from core.kv import KeyValueStore

_KEY = "worldstate.entities"
_DEFAULT_PATH = "data/runtime/world_state.json"
_DEFAULT_STALE = 86400.0 * 30.0


class WorldState:

    def __init__(self, path=None, now_fn=None):
        self.store = KeyValueStore(str(path) if path else _DEFAULT_PATH)
        self.now_fn = now_fn if now_fn is not None else time.time

    # ------------------------------------------------------------------
    def _entities(self):
        return dict(self.store.get(_KEY) or {})

    def _save(self, entities):
        self.store.set(_KEY, entities)

    def list_entities(self):
        return sorted(self._entities().keys())

    def get_entity(self, name):
        entity = self._entities().get(str(name))
        if entity is None:
            raise KeyError(f"unknown entity: {name}")
        return copy.deepcopy(entity)

    # ------------------------------------------------------------------
    # writes
    # ------------------------------------------------------------------
    def set_entity(self, name, attributes=None, status="known", tags=None,
                   created_at=None):
        entities = self._entities()
        now = self.now_fn()
        name = str(name)
        entity = entities.get(name)
        if entity is None:
            entity = {
                "name": name,
                "attributes": {},
                "status": str(status),
                "tags": [str(t) for t in (tags or [])],
                "created_at": float(created_at) if created_at is not None else now,
                "updated_at": now,
            }
        else:
            entity = dict(entity)
            entity["name"] = name
            if tags is not None:
                entity["tags"] = [str(t) for t in tags]
            if status is not None:
                entity["status"] = str(status)
            entity["updated_at"] = now
        for key, value in (attributes or {}).items():
            entity = self._apply_attr(entity, str(key), value, None, now)
        entities[name] = entity
        self._save(entities)
        return copy.deepcopy(entity)

    def update_attribute(self, name, key, value, unit=None, ts=None):
        entities = self._entities()
        name = str(name)
        if name not in entities:
            raise KeyError(f"unknown entity: {name}")
        now = self.now_fn()
        stamp = float(ts) if ts is not None else now
        entity = dict(entities[name])
        entity = self._apply_attr(entity, str(key), value, unit, stamp)
        entity["updated_at"] = now
        entities[name] = entity
        self._save(entities)
        return copy.deepcopy(entity["attributes"][str(key)])

    def _apply_attr(self, entity, key, value, unit, ts):
        attributes = dict(entity.get("attributes", {}))
        attr = dict(attributes.get(key, {"history": []}))
        history = list(attr.get("history", []))
        history.append({"value": value, "ts": float(ts)})
        if len(history) > 200:
            history = history[-200:]
        attr["history"] = history
        attr["value"] = value
        attr["ts"] = float(ts)
        attr["unit"] = unit
        attributes[key] = attr
        entity = dict(entity)
        entity["attributes"] = attributes
        return entity

    # ------------------------------------------------------------------
    # reads
    # ------------------------------------------------------------------
    def history(self, name, attribute):
        entity = self.get_entity(name)
        attr = entity["attributes"].get(str(attribute))
        if attr is None:
            return []
        return [
            {"ts": sample["ts"], "value": sample["value"]}
            for sample in attr.get("history", [])
        ]

    def delta_history(self, name, attribute):
        entries = self.history(name, attribute)
        deltas = []
        previous = None
        for entry in entries:
            delta = None
            if previous is not None:
                try:
                    delta = float(entry["value"]) - float(previous)
                except (TypeError, ValueError):
                    delta = None
            deltas.append({
                "ts": entry["ts"],
                "value": entry["value"],
                "delta": delta,
            })
            previous = entry["value"]
        return deltas

    def _value_as_of(self, attr, as_of):
        if attr is None:
            return None
        if as_of is None:
            return attr.get("value")
        last = None
        for sample in attr.get("history", []):
            if float(sample["ts"]) <= float(as_of):
                last = sample["value"]
        return last

    def query(self, conditions=None, as_of=None):
        conditions = dict(conditions or {})
        matched = []
        for name, entity in self._entities().items():
            if as_of is not None and float(entity.get("created_at", 0)) > float(as_of):
                continue
            ok = True
            for key, want in conditions.items():
                if key == "name":
                    if str(want) != name:
                        ok = False
                        break
                elif key == "status":
                    if entity.get("status") != str(want):
                        ok = False
                        break
                elif key == "tag":
                    if str(want) not in entity.get("tags", []):
                        ok = False
                        break
                else:
                    attr_name = key[len("attr:"):] if key.startswith("attr:") else key
                    value = self._value_as_of(
                        entity.get("attributes", {}).get(attr_name), as_of
                    )
                    if value != want:
                        ok = False
                        break
            if ok:
                matched.append(copy.deepcopy(entity))
        return matched

    # ------------------------------------------------------------------
    # projection — real linear change-rate extrapolation
    # ------------------------------------------------------------------
    def project(self, name, attribute, dt_hours):
        entity = self.get_entity(name)
        attr = entity["attributes"].get(str(attribute))
        if attr is None:
            return {"projected": False, "reason": "unknown attribute"}
        samples = attr.get("history") or []
        if len(samples) < 2:
            return {
                "projected": False,
                "reason": "insufficient history (<2 samples)",
            }
        first, last = samples[0], samples[-1]
        span = float(last["ts"]) - float(first["ts"])
        if span <= 0:
            return {
                "projected": False,
                "reason": "no elapsed time between samples",
            }
        try:
            delta = float(last["value"]) - float(first["value"])
        except (TypeError, ValueError):
            return {"projected": False, "reason": "non-numeric values"}
        rate = delta / span
        value = float(last["value"]) + rate * float(dt_hours) * 3600.0
        return {
            "projected": True,
            "entity": str(name),
            "attribute": str(attribute),
            "value": value,
            "rate": rate,
            "dt_hours": float(dt_hours),
            "from_ts": first["ts"],
            "to_ts": last["ts"],
            "unit": attr.get("unit"),
        }

    # ------------------------------------------------------------------
    # consistency
    # ------------------------------------------------------------------
    def consistency_check(self, stale_threshold_seconds=None, now=None):
        threshold = float(
            stale_threshold_seconds
            if stale_threshold_seconds is not None else _DEFAULT_STALE
        )
        now = now if now is not None else self.now_fn()
        entities = self._entities()
        issues = []
        for name, entity in entities.items():
            for key, attr in entity.get("attributes", {}).items():
                age = now - float(attr.get("ts", now))
                if age > threshold:
                    issues.append({
                        "severity": "stale",
                        "entity": name,
                        "attribute": key,
                        "age_seconds": round(age, 1),
                        "threshold_seconds": threshold,
                        "detail": (
                            f"attribute '{key}' on '{name}' is stale "
                            f"({round(age / 86400.0, 1)} days)"
                        ),
                    })
        names = sorted(entities)
        for i, name_a in enumerate(names):
            entity_a = entities[name_a]
            for name_b in names[i + 1:]:
                entity_b = entities[name_b]
                shared_tags = (
                    {t.lower() for t in entity_a.get("tags", [])}
                    & {t.lower() for t in entity_b.get("tags", [])}
                )
                if not shared_tags:
                    continue
                for key in sorted(
                    set(entity_a.get("attributes", {}))
                    & set(entity_b.get("attributes", {}))
                ):
                    value_a = entity_a["attributes"][key]["value"]
                    value_b = entity_b["attributes"][key]["value"]
                    try:
                        conflict = abs(float(value_a) - float(value_b)) > 1e-9
                    except (TypeError, ValueError):
                        conflict = value_a != value_b
                    if conflict:
                        issues.append({
                            "severity": "conflict",
                            "entity": name_a,
                            "twin": name_b,
                            "attribute": key,
                            "values": [value_a, value_b],
                            "detail": (
                                f"twin entities '{name_a}' and '{name_b}' "
                                f"disagree on '{key}'"
                            ),
                        })
        return {"issues": issues, "count": len(issues)}


__all__ = ["WorldState"]