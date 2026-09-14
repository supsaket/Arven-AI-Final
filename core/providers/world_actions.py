"""Real-World Action Execution / Coordinates (feature 79).

Capabilities:
* ``action_status`` - honest status: the local rule/action store is real;
  an executive backend for real-world actuation is NOT_CONFIGURED.
* ``action_create`` - persist a rule/action ``{id, name, trigger,
  action_type, target{}, enabled, dry_run}`` in kv (REAL).
* ``action_dry_run``- fully realised evaluation: walks through the steps that
  WOULD happen, producing a plan transcript. No side effects, ever.
* ``action_execute``- confirm-gated. Physical/external action types return
  ``requires_confirmation: True`` and are NOT executed. Only simulated
  (local-safe) targets are executed via ``_run_local`` and the result is
  clearly flagged. Honest NOT_CONFIGURED without an executive backend.

``action_execute`` is a confirm capability whose action classifies as medium
risk — this provider ships a strict ``execute()`` that requires an explicit
confirmed + approved request_id.
"""

import time

from core.confirmation import CONFIRMATION
from core.kv import KeyValueStore
from core.providers.base import (
    Provider,
    ok,
    reject,
    STATUS_AVAILABLE,
    STATUS_FAILED,
    STATUS_NOT_CONFIGURED,
    STATUS_OFFLINE,
    STATUS_REQUIRES_AUTH,
)

_ACTIONS_KEY = "world.actions"

# action_type values that touch the real world and therefore always need a
# backend and an approved gate before any execution may happen.
_EXTERNAL_TYPES = {"physical", "email", "message", "api", "webhook", "http",
                   "booking", "purchase", "device"}
_LOCAL_TYPES = {"simulated", "local_simulated", "local", "script_local"}

_DEFAULT_STEPS = [
    {"id": "trigger", "description": "Evaluate the declared trigger condition"},
    {"id": "target", "description": "Resolve the action target"},
    {"id": "act", "description": "Perform the action_type on the target"},
    {"id": "verify", "description": "Verify expected result and report"},
]


class ActionStore:
    """Persisted rule/action library over a shared kv store."""

    def __init__(self, kv):
        if not isinstance(kv, KeyValueStore):
            raise TypeError("ActionStore requires a core.kv.KeyValueStore")
        self._kv = kv

    def _load(self):
        return dict(self._kv.get(_ACTIONS_KEY, {}))

    def _save(self, actions):
        self._kv.set(_ACTIONS_KEY, actions)

    def create(self, name, trigger="manual", action_type="simulated",
               target=None, enabled=True, dry_run=True, action_id=None):
        actions = self._load()
        action_id = str(action_id or f"action_{time.time_ns()}")
        action = {
            "id": action_id,
            "name": str(name or action_id),
            "trigger": str(trigger or "manual"),
            "action_type": str(action_type),
            "target": dict(target or {}),
            "enabled": bool(enabled),
            "dry_run": bool(dry_run),
            "created_at": time.time(),
        }
        actions[action_id] = action
        self._save(actions)
        return dict(action)

    def get(self, action_id):
        return self._load().get(str(action_id))

    def list_actions(self):
        return list(self._load().values())


class WorldActionsProvider(Provider):
    name = "world_actions"
    capabilities = (
        "action_status",
        "action_create",
        "action_dry_run",
        "action_execute",
    )
    category = "actions"
    requires_network = False
    confirm_capabilities = ("action_execute",)

    def __init__(self, settings=None, kv=None, executive_backend=None):
        super().__init__(settings)
        self.store = ActionStore(
            kv if kv is not None else KeyValueStore("data/kv_world.json"))
        self._executive_backend = bool(executive_backend)
        self.set_status(STATUS_NOT_CONFIGURED, "action store not probed")

    def check(self):
        count = len(self.store.list_actions())
        return self.set_status(
            STATUS_AVAILABLE,
            f"action/rule store operational ({count} action(s)); real-world "
            "executive backend NOT_CONFIGURED — only simulated local targets "
            "can execute",
            {"actions": count, "executive_backend": bool(self._executive_backend)},
        )

    # ------------------------------------------------------------------
    def execute(self, capability, **kwargs):
        """Strict gate for ``action_execute`` (medium-classified risk)."""
        try:
            target = self.describe_capability(capability)
            method = getattr(self, f"_cap_{target.replace('-', '_')}", None)
            if self.needing_network():
                return self._honest(STATUS_OFFLINE,
                                    f"{self.name} requires network access")
            if method is None:
                return self._honest(
                    STATUS_NOT_CONFIGURED,
                    f"{self.name} does not implement capability '{capability}'")
            if target in self.confirm_capabilities:
                confirmed = bool(kwargs.get("confirmed", False))
                trusted = bool(kwargs.get("trusted", False))
                request_id = kwargs.get("request_id")
                allowed, _reason = CONFIRMATION.gate(
                    f"{self.name}.{target}",
                    confirmed=confirmed,
                    trusted=trusted,
                    request_id=request_id,
                )
                approved = bool(
                    allowed and confirmed and request_id
                    and CONFIRMATION.is_pending_ok(request_id))
                if not approved:
                    payload = self._honest(
                        STATUS_REQUIRES_AUTH, f"{target} requires confirmation")
                    payload["requires_confirmation"] = True
                    return payload
                kwargs["_cleared"] = True
                kwargs.pop("confirmed", None)
                kwargs.pop("trusted", None)
                kwargs.pop("request_id", None)
            return method(**kwargs)
        except Exception as exc:
            return self._honest(STATUS_FAILED, f"{self.name} error: {exc}")

    # ------------------------------------------------------------------
    def _cap_action_status(self, **_kw):
        actions = self.store.list_actions()
        return ok(
            "action/rule store operational; only simulated local execution is "
            "possible",
            {"actions": actions, "executive_backend": bool(self._executive_backend),
             "requires_confirmation": True},
        )

    def _cap_action_create(self, name=None, trigger="manual",
                           action_type="simulated", target=None, enabled=True,
                           dry_run=True, **_kw):
        if not name:
            return reject(STATUS_FAILED, "action_create requires a name")
        action = self.store.create(
            name=name, trigger=trigger, action_type=action_type,
            target=target, enabled=enabled, dry_run=dry_run)
        return ok("action created (stored)", {"action": action})

    def _cap_action_dry_run(self, action_id=None, **_kw):
        action = self.store.get(action_id) if action_id else None
        if action is None and action_id:
            return reject(STATUS_FAILED, f"no such action '{action_id}'")
        action = action or {
            "id": "adhoc", "name": "adhoc", "trigger": "manual",
            "action_type": "simulated", "target": {}, "enabled": True}
        action_type = action.get("action_type", "simulated")
        local_safe = action_type in _LOCAL_TYPES
        transcript = []
        for index, step in enumerate(_DEFAULT_STEPS, start=1):
            transcript.append({
                "step": index,
                "phase": step["id"],
                "description": step["description"].format(
                    action_type=action_type,
                    target=action.get("target", {}),
                    name=action.get("name")),
                "side_effect": False,
            })
        transcript.append({
            "step": len(transcript) + 1,
            "phase": "confirmation",
            "description": "Request explicit confirmation before any execution",
            "side_effect": False,
        })
        return ok(
            "dry-run transcript produced — nothing was executed",
            {"transcript": transcript, "dry_run": True, "executed": False,
             "local_safe": local_safe, "requires_confirmation": True},
        )

    def _cap_action_execute(self, action_id=None, **_kw):
        action = self.store.get(action_id) if action_id else None
        if action is None:
            return reject(STATUS_FAILED,
                          "action_execute requires a stored action_id")
        if not action.get("enabled", True):
            return reject(STATUS_FAILED, f"action '{action_id}' is disabled")
        action_type = action.get("action_type", "simulated")
        local_safe = action_type in _LOCAL_TYPES
        simulated_target = bool(
            action.get("target", {}).get("simulated")
            or local_safe)

        if not local_safe:
            if not self._executive_backend:
                return reject(
                    STATUS_NOT_CONFIGURED,
                    f"action '{action_id}' is a real-world ('{action_type}') "
                    "execution and no executive backend is configured — NOT "
                    "executed",
                    {"action_id": action_id, "executed": False,
                     "requires_confirmation": True,
                     "executive_backend": False},
                )
            return reject(
                STATUS_REQUIRES_AUTH,
                f"action '{action_id}' is a real-world ('{action_type}') "
                "execution — requires an approved confirmation gate",
                {"action_id": action_id, "executed": False,
                 "requires_confirmation": True},
            )

        if not simulated_target:
            return reject(
                STATUS_NOT_CONFIGURED,
                f"action '{action_id}' target is not simulated — local "
                "execution only supports simulated targets",
                {"simulated": False, "executed": False},
            )

        result = self._run_local(action)
        return ok("simulated local action executed (flagged)",
                  {"simulated": True, "executed": True, "action_id": action_id,
                   "result": result})

    def _run_local(self, action):
        """Run a local-safe (simulated) action — clearly flagged."""
        target = action.get("target", {})
        return {
            "action_id": action["id"],
            "action_type": action.get("action_type", "simulated"),
            "target": {"name": target.get("name"), "simulated": True},
            "message": "simulated outcome only — no physical side effects",
            "simulated": True,
            "physical_side_effect": False,
        }


def register_world_actions():
    from core.providers.registry import providers_registry
    if not providers_registry.has("world_actions"):
        providers_registry.register(WorldActionsProvider())
    return providers_registry.get("world_actions")


__all__ = ["WorldActionsProvider", "ActionStore", "register_world_actions"]