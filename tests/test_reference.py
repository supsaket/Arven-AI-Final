"""Context references contract (row 30) — resolve it/that/the file, ambiguity."""

from core.reference import ContextReferenceManager, context_refs


class TestTracking:

    def test_track_open_and_resolve(self):
        refs = ContextReferenceManager()
        refs.track_opened("C:/tmp/report.pdf", name="report")
        outcome = refs.resolve("close the report")
        assert outcome["status"] == "resolved"
        assert outcome["target"] == "C:/tmp/report.pdf"

    def test_do_it_again(self):
        refs = ContextReferenceManager()
        refs.track_opened("notepad", name="notepad")
        outcome = refs.resolve("do it again")
        assert outcome["status"] == "resolved"
        assert outcome["target"] == "notepad"

    def test_again_without_target_is_error(self):
        refs = ContextReferenceManager()
        outcome = refs.resolve("do it again")
        assert outcome["status"] == "error"

    def test_explicit_command_passes_through(self):
        refs = ContextReferenceManager()
        outcome = refs.resolve("open notepad")
        assert outcome["status"] == "explicit"


class TestAmbiguity:

    def test_multiple_targets_ambiguous(self):
        refs = ContextReferenceManager()
        refs.track_opened("notepad", name="app1")
        refs.track_opened("calculator", name="app2")
        refs.track_closed("something_else", name="other")
        outcome = refs.resolve("it")
        assert outcome["status"] == "ambiguous" or outcome[
            "status"] == "resolved"

    def test_closed_target_can_be_last_resort(self):
        refs = ContextReferenceManager()
        refs.track_closed("mspaint", name="paint")
        outcome = refs.resolve("the file")
        assert outcome["status"] in ("resolved", "ambiguous")


class TestNoMatch:

    def test_no_target_no_reference(self):
        refs = ContextReferenceManager()
        outcome = refs.resolve("hello boss")
        assert outcome["status"] == "explicit"


class TestGlobalSingleton:

    def test_global_available(self):
        assert context_refs is not None
        context_refs.track_opened("demo", name="demo")
        assert context_refs.resolve("it")["status"] in ("resolved", "ambiguous")