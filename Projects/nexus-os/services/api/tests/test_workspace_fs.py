from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from app.files.fs import Access, FsError, WorkspaceFS
from app.files.workspace import WorkspaceManager


@pytest.fixture
def fs(tmp_path: Path) -> WorkspaceFS:
    root = WorkspaceManager(tmp_path / "ws").ensure_project("proj_1")
    return WorkspaceFS(root)


def code(exc: pytest.ExceptionInfo[FsError]) -> str:
    return exc.value.code


HOSTILE = [
    "../secret.txt",
    "files/../../secret.txt",
    "files/a/../../../secret.txt",
    "..\\secret.txt",
    "files\\..\\..\\secret.txt",
    "/etc/passwd",
    "\\windows\\system32\\config",
    "C:\\Windows\\win.ini",
    "c:/windows/win.ini",
    "\\\\server\\share\\file.txt",
    "//server/share/file.txt",
    "~/.ssh/id_rsa",
    "files/\x00/../../etc/passwd",
    "files/ok.txt\x00.png",
]


@pytest.mark.parametrize("path", HOSTILE)
@pytest.mark.parametrize("access", [Access.READ, Access.WRITE])
def test_hostile_paths_are_refused_for_read_and_write(fs: WorkspaceFS, path: str, access: Access) -> None:
    with pytest.raises(FsError) as e:
        fs.resolve(path, access)
    assert e.value.code in {"outside_workspace", "invalid_path"}


@pytest.mark.parametrize("name", ["CON", "nul", "COM1.txt", "lpt9", "aux.md", "PRN"])
def test_windows_reserved_names_are_refused(fs: WorkspaceFS, name: str) -> None:
    with pytest.raises(FsError) as e:
        fs.resolve(f"files/{name}", Access.WRITE)
    assert e.value.code == "invalid_path"


@pytest.mark.parametrize(
    "path", ["files/trailing.", "files/space ", "files/" + "x" * 300, "", "   ", ".", "a" * 2000]
)
def test_malformed_paths_are_refused(fs: WorkspaceFS, path: str) -> None:
    with pytest.raises(FsError):
        fs.resolve(path, Access.WRITE)


@pytest.mark.parametrize("area", [".trash", ".history", "memory"])
def test_managed_areas_are_invisible_and_untouchable(fs: WorkspaceFS, area: str) -> None:
    for access in (Access.READ, Access.WRITE):
        with pytest.raises(FsError) as e:
            fs.resolve(f"{area}/x", access)
        assert e.value.code == "outside_workspace"


def test_area_rules(fs: WorkspaceFS) -> None:
    fs.resolve("files/a.txt", Access.WRITE)
    fs.resolve("temp/a.txt", Access.WRITE)
    fs.resolve("artifacts/report.md", Access.READ)
    with pytest.raises(FsError) as e:
        fs.resolve("artifacts/report.md", Access.WRITE)  # deliverables go through the artifact store
    assert e.value.code == "area_not_allowed"
    with pytest.raises(FsError) as e:
        fs.resolve("random.txt", Access.READ)
    assert e.value.code == "area_not_allowed"


def test_redundant_separators_are_harmless(fs: WorkspaceFS) -> None:
    assert fs.resolve("files//", Access.READ)[0] == "files"
    assert fs.resolve("files/./a//b.txt", Access.WRITE)[0] == "files/a/b.txt"


def test_backslashes_are_normalised_not_rejected(fs: WorkspaceFS) -> None:
    fs.write_text("files\\docs\\a.md", "hi")
    assert fs.read_text("files/docs/a.md")[0] == "hi"


symlinks = pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")


@symlinks
def test_symlink_pointing_outside_is_refused_for_reads_and_writes(fs: WorkspaceFS, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("TOP SECRET")
    os.symlink(outside, fs.root / "files" / "link")
    os.symlink(outside / "secret.txt", fs.root / "files" / "filelink.txt")
    for target in ("files/link/secret.txt", "files/filelink.txt"):
        with pytest.raises(FsError) as e:
            fs.read_text(target)
        assert e.value.code == "outside_workspace"
    with pytest.raises(FsError):
        fs.write_text("files/link/new.txt", "x")
    assert not (outside / "new.txt").exists()
    with pytest.raises(FsError):
        fs.write_text("files/filelink.txt", "overwrite attempt")
    assert (outside / "secret.txt").read_text() == "TOP SECRET"


@symlinks
def test_symlink_into_a_hidden_area_is_refused(fs: WorkspaceFS) -> None:
    (fs.root / "memory" / "notes.txt").write_text("private memory")
    os.symlink(fs.root / "memory", fs.root / "files" / "sneaky")
    with pytest.raises(FsError):
        fs.read_text("files/sneaky/notes.txt")


@symlinks
def test_links_leaving_the_workspace_are_invisible_in_listings_and_searches(
    fs: WorkspaceFS, tmp_path: Path
) -> None:
    outside = tmp_path / "out"
    outside.mkdir()
    (outside / "leak.txt").write_text("needle")
    os.symlink(outside, fs.root / "files" / "escape")
    fs.write_text("files/real.txt", "needle")
    assert [e.path for e in fs.list_dir("files")] == ["files/real.txt"]
    assert {h["path"] for h in fs.search("needle")} == {"files/real.txt"}


@symlinks
def test_a_link_pointing_inside_the_workspace_is_fine(fs: WorkspaceFS) -> None:
    fs.write_text("files/real.txt", "hello")
    os.symlink(fs.root / "files" / "real.txt", fs.root / "files" / "alias.txt")
    assert fs.read_text("files/alias.txt")[0] == "hello"


def test_write_read_roundtrip_and_atomic_overwrite_keeps_history(fs: WorkspaceFS) -> None:
    first = fs.write_text("files/notes/todo.md", "v1")
    assert first["created"] is True and first["previous_version"] is None
    second = fs.write_text("files/notes/todo.md", "v2")
    assert second["created"] is False
    hist = fs.root / str(second["previous_version"])
    assert hist.read_text() == "v1"  # never a silent overwrite
    assert fs.read_text("files/notes/todo.md") == ("v2", False)
    assert not list((fs.root / "files" / "notes").glob(".*.tmp"))  # no temp litter


def test_overwrite_false_refuses_existing(fs: WorkspaceFS) -> None:
    fs.write_text("files/a.txt", "one")
    with pytest.raises(FsError) as e:
        fs.write_text("files/a.txt", "two", overwrite=False)
    assert e.value.code == "exists" and fs.read_text("files/a.txt")[0] == "one"


def test_size_limits_and_binary_refusal(fs: WorkspaceFS) -> None:
    with pytest.raises(FsError) as e:
        fs.write_text("files/big.txt", "x" * 5_000_001)
    assert e.value.code == "too_large"
    (fs.root / "files" / "img.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00binary")
    with pytest.raises(FsError) as e:
        fs.read_text("files/img.png")
    assert e.value.code == "binary_file"
    fs.write_text("files/long.txt", "y" * 5000)
    text, truncated = fs.read_text("files/long.txt", max_bytes=100)
    assert len(text) == 100 and truncated


def test_read_errors_are_specific(fs: WorkspaceFS) -> None:
    with pytest.raises(FsError) as e:
        fs.read_text("files/missing.txt")
    assert e.value.code == "not_found"
    fs.mkdir("files/dir")
    with pytest.raises(FsError) as e:
        fs.read_text("files/dir")
    assert e.value.code == "not_a_file"
    with pytest.raises(FsError) as e:
        fs.write_text("files/dir", "x")
    assert e.value.code == "is_a_directory"


def test_list_dir_root_and_hidden_files(fs: WorkspaceFS) -> None:
    assert [e.path for e in fs.list_dir(".")] == ["artifacts", "files", "temp"]  # hidden areas never shown
    fs.write_text("files/b.txt", "1")
    fs.write_text("files/a.txt", "1")
    fs.mkdir("files/zdir")
    (fs.root / "files" / ".secret").write_text("dotfile")
    listing = fs.list_dir("files")
    assert [e.path for e in listing] == [
        "files/zdir",
        "files/a.txt",
        "files/b.txt",
    ]  # dirs first, dotfiles hidden
    with pytest.raises(FsError):
        fs.list_dir("files/a.txt")


def test_move_rules_and_history(fs: WorkspaceFS) -> None:
    fs.write_text("files/a.txt", "A")
    fs.write_text("files/b.txt", "B")
    with pytest.raises(FsError) as e:
        fs.move("files/a.txt", "files/b.txt")
    assert e.value.code == "exists"
    moved = fs.move("files/a.txt", "files/sub/c.txt")
    assert (
        moved["overwrote"] is False
        and fs.read_text("files/sub/c.txt")[0] == "A"
        and not fs.exists("files/a.txt")
    )
    over = fs.move("files/sub/c.txt", "files/b.txt", overwrite=True)
    assert over["overwrote"] is True and (fs.root / str(over["previous_version"])).read_text() == "B"
    with pytest.raises(FsError):
        fs.move("files/nope.txt", "files/x.txt")
    with pytest.raises(FsError):
        fs.move("files/b.txt", "artifacts/x.txt")  # cannot move into a read-only area


def test_soft_delete_is_recoverable_and_never_unlinks(fs: WorkspaceFS) -> None:
    fs.write_text("files/keep.txt", "precious")
    result = fs.soft_delete("files/keep.txt")
    assert not fs.exists("files/keep.txt")
    trashed = fs.root / str(result["moved_to_trash"])
    assert trashed.read_text() == "precious" and ".trash" in trashed.parts
    with pytest.raises(FsError):
        fs.soft_delete("files/keep.txt")
    with pytest.raises(FsError):
        fs.soft_delete("../outside")
    with pytest.raises(FsError):
        fs.soft_delete(".trash/whatever")  # cannot delete from the trash through the tool


def test_search_finds_lines_respects_caps_and_skips_binary(fs: WorkspaceFS) -> None:
    fs.write_text("files/a.md", "alpha\nNeedle here\nomega")
    fs.write_text("files/b.py", "print('needle')")
    (fs.root / "files" / "bin.dat").write_bytes(b"\x00needle\x00")
    hits = fs.search("needle")
    assert {(h["path"], h["line"]) for h in hits} == {("files/a.md", 2), ("files/b.py", 1)}
    assert [h["path"] for h in fs.search("needle", glob="*.py")] == ["files/b.py"]
    assert len(fs.search("needle", max_results=1)) == 1
    assert fs.search(r"n[e]+dle", regex=True)
    with pytest.raises(FsError):
        fs.search("(unclosed", regex=True)
    with pytest.raises(FsError):
        fs.search("")
    with pytest.raises(FsError):
        fs.search("x", subdir="../..")


def test_search_file_cap_bounds_work(fs: WorkspaceFS) -> None:
    for i in range(30):
        fs.write_text(f"files/f{i:02d}.txt", "hit")
    assert len(fs.search("hit", max_files=10)) <= 10


def test_root_symlink_of_project_dir_is_resolved_once(tmp_path: Path) -> None:
    real = WorkspaceManager(tmp_path / "real").ensure_project("p")
    if sys.platform != "win32":
        link = tmp_path / "linkroot"
        os.symlink(real, link)
        fs = WorkspaceFS(link)
        fs.write_text("files/x.txt", "ok")
        assert (real / "files" / "x.txt").read_text() == "ok"
