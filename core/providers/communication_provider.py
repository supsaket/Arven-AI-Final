"""Email / Messaging / Communication (feature 45).

Capabilities:
* ``email_templates`` - template library (kv): add / list / apply
  (``{placeholder}`` substitution onto a subject + body).
* ``email_compose``   - compose subject/body from a template + variables.
* ``email_draft``     - compose + persist a draft (kv).
* ``message_draft``   - persist a short-message draft (kv).
* ``email_send`` / ``message_send`` - confirm-gated sends. Honest backend
  detection: no SMTP / messaging backend configured -> NOT_CONFIGURED and the
  provider NEVER sends anything. If an approved confirmation exists AND a
  backend is somehow present, the message is only RECORDED locally (no
  network transmission in this codebase) and marked ``delivered: False``.

The provider is named ``messaging`` so both ``email_send`` and ``message_send``
are classified high-risk by the shared safety engine and are therefore
refused by the base ``Provider.execute()`` gate unless confirmed.
"""

import re
import time

from core.kv import KeyValueStore
from core.providers.base import (
    Provider,
    ok,
    reject,
    STATUS_AVAILABLE,
    STATUS_FAILED,
    STATUS_NOT_CONFIGURED,
)

_TEMPLATES_KEY = "messaging.templates"
_DRAFTS_KEY = "messaging.drafts"
_SENT_KEY = "messaging.sent"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
_PHONE_RE = re.compile(r"^\+?[0-9][0-9 \-()]{6,20}[0-9]$")

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_.]+)\}")


def validate_recipient(recipient):
    """Email regex or phone rules. Returns (ok, kind, error)."""
    recipient = str(recipient or "").strip()
    if not recipient:
        return False, None, "recipient is empty"
    if _EMAIL_RE.match(recipient):
        return True, "email", None
    if _PHONE_RE.match(recipient):
        return True, "phone", None
    return False, None, "recipient must be a valid email or phone number"


def apply_template(template, variables=None):
    """Substitute ``{key}`` placeholders from ``variables`` (keeps unknown)."""
    variables = variables or {}
    subject = _PLACEHOLDER_RE.sub(
        lambda m: str(variables.get(m.group(1), m.group(0))),
        str(template.get("subject", "")))
    body = _PLACEHOLDER_RE.sub(
        lambda m: str(variables.get(m.group(1), m.group(0))),
        str(template.get("body", "")))
    return {"subject": subject, "body": body}


def _backend_env(var_names):
    import os
    return [v for v in var_names if os.environ.get(v)]


class MessageLibrary:
    """Persisted templates + drafts over a shared kv store."""

    def __init__(self, kv):
        if not isinstance(kv, KeyValueStore):
            raise TypeError("MessageLibrary requires a core.kv.KeyValueStore")
        self._kv = kv

    # -- templates ----------------------------------------------------
    def add_template(self, name, subject, body):
        templates = dict(self._kv.get(_TEMPLATES_KEY, {}))
        template = {"name": str(name), "subject": str(subject),
                    "body": str(body)}
        templates[str(name)] = template
        self._kv.set(_TEMPLATES_KEY, templates)
        return dict(template)

    def get_template(self, name):
        return self._kv.get(_TEMPLATES_KEY, {}).get(str(name))

    def list_templates(self):
        return list(self._kv.get(_TEMPLATES_KEY, {}).values())

    # -- drafts -------------------------------------------------------
    def save_draft(self, kind, subject, body, recipient=None):
        drafts = dict(self._kv.get(_DRAFTS_KEY, {}))
        draft_id = f"{kind}_{time.time_ns()}"
        draft = {
            "id": draft_id,
            "kind": str(kind),
            "subject": str(subject),
            "body": str(body),
            "recipient": recipient,
            "created_at": time.time(),
        }
        drafts[draft_id] = draft
        self._kv.set(_DRAFTS_KEY, drafts)
        return dict(draft)

    def list_drafts(self):
        return list(self._kv.get(_DRAFTS_KEY, {}).values())

    def load_draft(self, draft_id):
        return self._kv.get(_DRAFTS_KEY, {}).get(str(draft_id))

    # -- outgoing record ------------------------------------------------
    def record_sent(self, kind, subject, body, recipient):
        sent = list(self._kv.get(_SENT_KEY, []))
        record = {
            "kind": str(kind), "subject": str(subject), "body": str(body),
            "recipient": str(recipient), "at": time.time(),
            "delivered": False, "recorded_locally": True,
        }
        sent.append(record)
        self._kv.set(_SENT_KEY, sent)
        return record


class CommunicationProvider(Provider):
    name = "messaging"
    capabilities = (
        "email_draft",
        "email_compose",
        "email_templates",
        "message_draft",
        "message_send",
        "email_send",
    )
    category = "communication"
    requires_network = False
    confirm_capabilities = ("email_send", "message_send")

    SMTP_VARS = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD",
                 "EMAIL_SMTP_HOST", "EMAIL_SMTP_PORT")
    MESSAGING_VARS = ("MESSAGING_HUB", "MESSAGING_API_KEY", "TWILIO_SID",
                      "TWILIO_TOKEN")

    def __init__(self, settings=None, kv=None):
        super().__init__(settings)
        self.library = MessageLibrary(
            kv if kv is not None else KeyValueStore("data/kv_messaging.json"))
        self.set_status(STATUS_NOT_CONFIGURED, "messaging provider not probed")

    def check(self):
        smtp = _backend_env(self.SMTP_VARS)
        hub = _backend_env(self.MESSAGING_VARS)
        if not smtp and not hub:
            return self.set_status(
                STATUS_NOT_CONFIGURED,
                "no email/SMTP or messaging hub backend configured — draft and "
                "template capabilities still work locally, sends are refused",
                {"smtp_env": [], "messaging_env": [],
                 "sending_backend": None},
            )
        backend = "smtp" if smtp else "messaging"
        return self.set_status(
            STATUS_AVAILABLE, f"{backend} backend environment present",
            {"smtp_env": smtp, "messaging_env": hub,
             "sending_backend": backend},
        )

    def _sending_backend(self):
        """Return 'smtp' / 'messaging' / None with the present env vars."""
        smtp = _backend_env(self.SMTP_VARS)
        if smtp:
            return "smtp", smtp
        hub = _backend_env(self.MESSAGING_VARS)
        if hub:
            return "messaging", hub
        return None, []

    # ------------------------------------------------------------------
    def _cap_email_templates(self, action=None, name=None, subject=None,
                             body=None, variables=None, **_kw):
        if action == "add":
            if not name:
                return reject(STATUS_FAILED, "template add requires name")
            template = self.library.add_template(name, subject or "", body or "")
            return ok("template added", {"template": template})
        if action == "apply":
            template = self.library.get_template(name) if name else None
            if template is None and name:
                return reject(STATUS_FAILED, f"no such template '{name}'")
            return ok("template applied",
                      {"template": name,
                       "result": apply_template(
                           template if template else
                           {"subject": subject or "", "body": body or ""},
                           variables)})
        return ok("templates listed", {"templates": self.library.list_templates()})

    def _cap_email_compose(self, template=None, variables=None, recipient=None,
                           subject=None, body=None, **_kw):
        if template and not subject and not body:
            found = self.library.get_template(template) if isinstance(template, str) else template
            if found is None:
                return reject(STATUS_FAILED, f"no such template '{template}'")
            composed = apply_template(found, variables)
        else:
            composed = {"subject": subject or "", "body": body or ""}
        if recipient:
            valid, kind, error = validate_recipient(recipient)
            if not valid:
                return reject(STATUS_FAILED, f"invalid recipient: {error}")
        return ok("email composed",
                  {"subject": composed["subject"], "body": composed["body"],
                   "recipient": recipient})

    def _cap_email_draft(self, template=None, variables=None, recipient=None,
                         subject=None, body=None, **_kw):
        composed = self._cap_email_compose(
            template=template, variables=variables, recipient=recipient,
            subject=subject, body=body)
        if not composed["success"] or composed.get("status") != "AVAILABLE":
            return composed
        draft = self.library.save_draft(
            "email", composed["data"]["subject"], composed["data"]["body"],
            recipient=recipient)
        return ok("email draft saved", {"draft": draft})

    def _cap_message_draft(self, message=None, recipient=None, **_kw):
        if recipient:
            valid, _, error = validate_recipient(recipient)
            if not valid:
                return reject(STATUS_FAILED, f"invalid recipient: {error}")
        draft = self.library.save_draft(
            "message", "", str(message or ""), recipient=recipient)
        return ok("message draft saved", {"draft": draft})

    def _cap_email_send(self, to=None, subject=None, body=None, template=None,
                        variables=None, **_kw):
        if not to:
            return reject(STATUS_FAILED, "email_send requires 'to'")
        valid, _, error = validate_recipient(to)
        if not valid:
            return reject(STATUS_FAILED, f"invalid recipient: {error}")
        backend, present = self._sending_backend()
        if backend is None:
            return reject(
                STATUS_NOT_CONFIGURED,
                "no SMTP backend configured — email was NOT sent and nothing "
                "was transmitted (honest)",
                {"sending_backend": None, "sent": False,
                 "requires_confirmation": True},
            )
        record = self.library.record_sent(
            "email", subject or "", body or "", to)
        return ok(
            "email recorded locally; no network delivery attempted by this "
            "codebase (backend stub)",
            {"sent": False, "delivered": False, "recorded": record,
             "sending_backend": backend},
        )

    def _cap_message_send(self, to=None, text=None, **_kw):
        if not to:
            return reject(STATUS_FAILED, "message_send requires 'to'")
        valid, _, error = validate_recipient(to)
        if not valid:
            return reject(STATUS_FAILED, f"invalid recipient: {error}")
        backend, present = self._sending_backend()
        if backend is None:
            return reject(
                STATUS_NOT_CONFIGURED,
                "no messaging hub backend configured — message was NOT sent "
                "and nothing was transmitted (honest)",
                {"sending_backend": None, "sent": False,
                 "requires_confirmation": True},
            )
        record = self.library.record_sent("message", "", str(text or ""), to)
        return ok(
            "message recorded locally; no network delivery attempted by this "
            "codebase (backend stub)",
            {"sent": False, "delivered": False, "recorded": record,
             "sending_backend": backend},
        )


def register_communication():
    from core.providers.registry import providers_registry
    if not providers_registry.has("messaging"):
        providers_registry.register(CommunicationProvider())
    return providers_registry.get("messaging")


__all__ = [
    "CommunicationProvider", "MessageLibrary", "validate_recipient",
    "apply_template", "register_communication",
]