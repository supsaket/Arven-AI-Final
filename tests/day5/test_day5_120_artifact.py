"""Feature 120 — Artifact engine: real output for all 7 kinds + templates."""

import os
import zipfile

from core import artifact_engine


def test_render_md_and_csv_and_json(tmp_path):
    data = {"title": "R1", "body": "hello world"}
    for kind in ("md", "csv", "json"):
        out = artifact_engine.generate(kind, data, name=f"art_{kind}",
                                       out_dir=str(tmp_path), attempt_install=False)
        assert out["success"] is True, out
        assert os.path.exists(out["path"]), out


def test_render_docx_is_real_ooxml(tmp_path):
    data = {"title": "R1", "body": "document body"}
    out = artifact_engine.generate("docx", data, name="art_docx",
                                   out_dir=str(tmp_path), attempt_install=False)
    assert out["success"] is True
    with zipfile.ZipFile(out["path"]) as zf:
        assert "[Content_Types].xml" in zf.namelist()
        assert any(n.endswith("document.xml") for n in zf.namelist())


def test_render_xlsx_is_real_ooxml(tmp_path):
    data = {"title": "S", "body": "rows below"}
    out = artifact_engine.generate("xlsx", data, name="art_xlsx",
                                   rows=[["a", "b"], ["1", "2"]],
                                   out_dir=str(tmp_path), attempt_install=False)
    assert out["success"] is True
    with zipfile.ZipFile(out["path"]) as zf:
        assert any(n.endswith("workbook.xml") for n in zf.namelist())


def test_render_pdf_has_real_xref(tmp_path):
    data = {"title": "PDF", "body": "minimal pdf body"}
    out = artifact_engine.generate("pdf", data, name="art_pdf",
                                   out_dir=str(tmp_path), attempt_install=False)
    assert out["success"] is True
    raw = open(out["path"], "rb").read()
    assert b"%PDF-" in raw
    assert b"xref" in raw
    assert out.get("backend") in ("reportlab", "pdf_minimal")


def test_render_pptx_is_real_zip(tmp_path):
    data = {"title": "DECK", "body": "slide one"}
    out = artifact_engine.generate("pptx", data, name="art_pptx",
                                   out_dir=str(tmp_path), attempt_install=False)
    assert out["success"] is True, out
    with zipfile.ZipFile(out["path"]) as zf:
        assert "ppt/presentation.xml" in zf.namelist()
        assert any(n.startswith("ppt/slides/") for n in zf.namelist())


def test_unsupported_kind_is_honest(tmp_path):
    out = artifact_engine.generate("holocube", {}, name="art_hologram",
                                   out_dir=str(tmp_path), attempt_install=False)
    assert out["success"] is False


def test_template_flow_detects_missing_placeholders(tmp_path):
    template = tmp_path / "template.md"
    template.write_text(
        "# {{title}}\n\n{{body}}\n\n{{missing_holder}}",
        encoding="utf-8")
    spec = artifact_engine.inspect_template(str(template))
    assert spec["success"] is True
    placeholders = spec["inspect"]["placeholders"]
    assert "title" in placeholders
    assert "missing_holder" in placeholders
    out = artifact_engine.generate(
        "md",
        {"title": "T", "body": "B"},
        name="tmpl_out", template_file=str(template),
        out_dir=str(tmp_path), attempt_install=False)
    assert out["success"] is False  # missing placeholder blocks the render


def test_template_flow_renders_when_all_placeholders_filled(tmp_path):
    template = tmp_path / "full.md"
    template.write_text("# {{title}}\n\n{{body}}", encoding="utf-8")
    out = artifact_engine.generate(
        "md",
        {"title": "T", "body": "B"},
        name="tmpl_full", template_file=str(template),
        out_dir=str(tmp_path), attempt_install=False)
    assert out["success"] is True
    content = open(out["path"], encoding="utf-8").read()
    assert "{{" not in content


def test_comparison_verifies_template_and_artifact(tmp_path):
    template = tmp_path / "tpl.md"
    template.write_text("# {{title}}\n\n{{body}}", encoding="utf-8")
    made = artifact_engine.generate(
        "md", {"title": "X", "body": "Y"}, name="cmp_art",
        template_file=str(template), out_dir=str(tmp_path),
        attempt_install=False)
    assert made["success"] is True
    cmp = artifact_engine.compare_files(str(template), made["path"])
    assert cmp["template_intact"] is True
    assert cmp["artifact_present"] is True
    assert cmp["artifact_reopen"][0] == "PASS"


def test_reopen_covers_all_kinds(tmp_path):
    data = {"title": "RT", "body": "round trip body"}
    for kind in ("md", "csv", "json", "docx", "xlsx", "pdf"):
        made = artifact_engine.generate(kind, data, name=f"rt_{kind}",
                                        out_dir=str(tmp_path), attempt_install=False)
        assert made["success"] is True, (kind, made)
        verdict, _detail = artifact_engine._reopen(kind, made["path"], "RT")
        assert verdict == "PASS", (kind, verdict)