"""Personal knowledge contract (row 3) — notes vs tasks, ordering."""

from personal.store import PersonalStore


def new_store(tmp_path):
    return PersonalStore(directory=tmp_path / "personal")


class TestNotes:

    def test_add_and_get(self, tmp_path):
        store = new_store(tmp_path)
        note_id = store.add_note("buy milk")
        note = store.get_note(note_id)
        assert note["content"] == "buy milk"

    def test_list_newest_first(self, tmp_path):
        store = new_store(tmp_path)
        store.add_note("first")
        store.add_note("second")
        notes = store.list_notes()
        assert notes[0]["content"] == "second"

    def test_update_and_delete(self, tmp_path):
        store = new_store(tmp_path)
        note_id = store.add_note("old")
        assert store.update_note(note_id, "new") is True
        assert store.get_note(note_id)["content"] == "new"
        assert store.delete_note(note_id) is True
        assert store.get_note(note_id) is None


class TestTasks:

    def test_add_task(self, tmp_path):
        store = new_store(tmp_path)
        task_id = store.add_task("send the report", priority="high")
        tasks = store.list_tasks()
        assert tasks
        assert tasks[0]["text"] == "send the report"
        assert tasks[0]["priority"] == "high"
        assert tasks[0]["done"] is False

    def test_pending_filter(self, tmp_path):
        store = new_store(tmp_path)
        first_id = store.add_task("do the dishes")
        store.add_task("done task")
        store.complete_task(store.list_tasks()[0]["id"])
        pending = store.pending_tasks()
        assert all(not task["done"] for task in pending)
        assert pending

    def test_complete_task(self, tmp_path):
        store = new_store(tmp_path)
        task_id = store.add_task("finish homework")
        assert store.complete_task(task_id) is True
        task = [t for t in store.list_tasks() if t["id"] == task_id][0]
        assert task["done"] is True
        assert "completed_at" in task and task["completed_at"]

    def test_delete_task(self, tmp_path):
        store = new_store(tmp_path)
        task_id = store.add_task("clean desk")
        assert store.delete_task(task_id) is True
        assert store.delete_task(task_id) is False


class TestSeparation:

    def test_notes_are_not_tasks(self, tmp_path):
        store = new_store(tmp_path)
        store.add_note("a thought")
        store.add_task("a task")
        assert len(store.list_notes()) == 1
        assert len(store.list_tasks()) == 1