"""Pastas, recentes e sessões."""

import json

import pytest

from app.services.workspace import (
    SessionData,
    SessionError,
    SessionFile,
    add_recent,
    existing_recent,
    load_session,
    pdfs_in_folder,
    save_session,
)


def test_pdfs_in_folder_natural_order(tmp_path):
    for name in ("v10.pdf", "v2.pdf", "V1.PDF", "nota.txt"):
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "sub.pdf").mkdir()
    assert [p.name for p in pdfs_in_folder(tmp_path)] == ["V1.PDF", "v2.pdf", "v10.pdf"]
    assert pdfs_in_folder(tmp_path / "nao_existe") == []


def test_recent_list(tmp_path):
    items = []
    for name in ("a", "b", "a"):
        items = add_recent(items, tmp_path / name)
    assert items == [str(tmp_path / "a"), str(tmp_path / "b")]
    many = []
    for i in range(15):
        many = add_recent(many, f"f{i}", limit=10)
    assert len(many) == 10 and many[0] == "f14"
    (tmp_path / "a").write_text("x")
    assert existing_recent(items) == [str(tmp_path / "a")]


def test_session_roundtrip(tmp_path):
    a, b = tmp_path / "a.pdf", tmp_path / "b.pdf"
    a.write_bytes(b"x")
    b.write_bytes(b"x")
    saved = save_session(tmp_path / "minha", SessionData([SessionFile(a, 0), SessionFile(b, -2)], 3, 1.25))
    assert saved.name == "minha.pdfcompare"
    data, missing = load_session(saved)
    assert missing == []
    assert [(f.path.name, f.offset) for f in data.files] == [("a.pdf", 0), ("b.pdf", -2)]
    assert (data.current, data.zoom) == (3, 1.25)


def test_session_moved_folder_uses_relative_paths(tmp_path):
    folder = tmp_path / "proj"
    folder.mkdir()
    (folder / "a.pdf").write_bytes(b"x")
    session = save_session(folder / "s.pdfcompare", SessionData([SessionFile(folder / "a.pdf")]))
    moved = tmp_path / "movido"
    folder.rename(moved)
    data, missing = load_session(moved / session.name)
    assert missing == [] and data.files[0].path == moved / "a.pdf"


def test_session_reports_missing_files(tmp_path):
    a = tmp_path / "a.pdf"
    a.write_bytes(b"x")
    s = save_session(tmp_path / "s.pdfcompare", SessionData([SessionFile(a), SessionFile(tmp_path / "sumiu.pdf")]))
    data, missing = load_session(s)
    assert [f.path.name for f in data.files] == ["a.pdf"] and missing == ["sumiu.pdf"]


@pytest.mark.parametrize("content", ["nao json", "[]", json.dumps({"files": 3}),
                                     json.dumps({"version": 99, "files": []})])
def test_invalid_sessions(tmp_path, content):
    path = tmp_path / "x.pdfcompare"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(SessionError):
        load_session(path)


def test_session_tolerates_bad_values(tmp_path):
    a = tmp_path / "a.pdf"
    a.write_bytes(b"x")
    path = tmp_path / "x.pdfcompare"
    path.write_text(json.dumps({"files": [{"path": str(a), "offset": "?"}, 5], "zoom": True,
                                "current": "x"}), encoding="utf-8")
    data, _ = load_session(path)
    assert data.files[0].offset == 0 and data.zoom is None and data.current == 0


def test_missing_session_file(tmp_path):
    with pytest.raises(SessionError):
        load_session(tmp_path / "nada.pdfcompare")
