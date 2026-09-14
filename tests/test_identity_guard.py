"""Identity guard contract (row 02) — canonical name, conflict drop."""

from brain.identity import IdentityDNA, IdentityGuard, identity_dna, identity_guard


class TestIdentityDNA:

    def test_dna_fields(self):
        assert identity_dna.name == "ARVEN"
        assert identity_dna.boss == "Saket"
        assert identity_dna.version

    def test_greeting_mentions_name(self):
        assert "ARVEN" in identity_dna.greeting()

    def test_system_prompt_canonical(self):
        prompt = identity_dna.system_prompt()
        assert "arven" in prompt.lower()
        assert "saket" in prompt.lower()
        assert "Never claim a different identity" in prompt


class TestNormalization:

    def test_canonical_boss_name(self):
        assert identity_dna.is_canonical_boss_name("saket") is True
        assert identity_dna.is_canonical_boss_name("Saket") is True

    def test_sakeet_normalizes_to_canonical(self):
        assert identity_guard.canonical_name("sakeet") == "Saket"
        assert identity_guard.canonical_name("saket") == "Saket"

    def test_canonical_name_returns_none_for_unrelated(self):
        assert identity_guard.canonical_name("arvind") is None
        assert identity_guard.canonical_name("") is None

    def test_normalize_fact_rewrites_variant(self):
        assert identity_guard.normalize_fact("the boss is sakeet") == \
            "the boss is Saket"


class TestFilterMemories:

    def test_conflicting_claim_dropped(self):
        rows = [
            (1, "you are a personal assistant", "identity", "", "", 0.5, "", ""),
            (2, "my boss is Arvind", "identity", "", "", 0.5, "", ""),
        ]
        cleaned = identity_guard.filter_memories(rows)
        assert len(cleaned) == 1
        assert "Arvind" not in str(cleaned[0])

    def test_non_identity_rows_kept(self):
        rows = [
            (1, "the code uses sqlite", "technical", "", "", 0.5, "", ""),
            (2, "my boss is Arvind", "identity", "", "", 0.5, "", ""),
        ]
        cleaned = identity_guard.filter_memories(rows)
        # technical row is never dropped; only the conflicting identity row is
        assert len(cleaned) == 1
        assert "sqlite" in str(cleaned[0])

    def test_blank_fact_dropped(self):
        assert identity_guard.blank_fact_dropped("") is True
        assert identity_guard.blank_fact_dropped("hello") is False


class TestStripConflicts:

    def test_strips_conflicting_lines(self):
        text = "line one\nI am Arvind\nline three"
        stripped = identity_guard.strip_conflicts(text)
        assert "Arvind" not in stripped
        assert "line one" in stripped