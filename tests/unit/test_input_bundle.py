import hashlib
import json
from pathlib import Path

import pytest


def native_bundle(tmp_path):
    root = tmp_path / "native"
    (root / "Example").mkdir(parents=True)
    (root / "Input").mkdir()
    main = root / "Example/main.inp"
    main.write_bytes(b'*Include, input=../Input/model.inp\r\n')
    (root / "Input/model.inp").write_bytes(b'*Include, input=../Input/mesh.inp\n')
    (root / "Input/mesh.inp").write_bytes(b'*Node\n1,0,0,0\n')
    (root / "umat.for").write_bytes(b'C synthetic test only\n')
    return root, main


def stage(root, main, destination, **kwargs):
    from experiment_to_cpfe.solvers.abaqus.bundle import stage_input_bundle

    return stage_input_bundle(
        main, source_root=root, submission_dir=root / "Example",
        destination=destination, license="synthetic", **kwargs,
    )


def test_nested_includes_resolve_from_submission_directory_not_parent_file(tmp_path):
    root, main = native_bundle(tmp_path)
    result = stage(root, main, tmp_path / "staged", auxiliary_files=(root / "umat.for",))

    assert result.entrypoint == tmp_path / "staged/Example/main.inp"
    assert result.submission_dir == tmp_path / "staged/Example"
    for relative in ("Example/main.inp", "Input/model.inp", "Input/mesh.inp", "umat.for"):
        assert (tmp_path / "staged" / relative).read_bytes() == (root / relative).read_bytes()
    receipt = json.loads(result.manifest_path.read_text())
    assert len(receipt["assets"]) == 8
    originals = {a["asset_id"]: a for a in receipt["assets"] if a["parent_asset_id"] is None}
    for asset in receipt["assets"]:
        assert asset["source_kind"] == "input"
        assert asset["layer"] == "raw"
        assert asset["lossy_transformations"] == []
        assert asset["sha256"] == hashlib.sha256(Path(asset["uri"]).read_bytes()).hexdigest()
        if asset["parent_asset_id"]:
            parent = originals[asset["parent_asset_id"]]
            assert asset["sha256"] == parent["sha256"]
            assert asset["original_format"] == asset["target_format"]


@pytest.mark.parametrize("line,name", [
    ('*include,\n input="../Input/mesh, one.inp"\n', 'mesh, one.inp'),
    ('*INCLUDE, INPUT=../Input/m e s h.inp\n', 'mesh.inp'),
])
def test_include_continuation_quotes_and_abaqus_unquoted_space_rules(tmp_path, line, name):
    root, main = native_bundle(tmp_path)
    main.write_text(line)
    (root / "Input" / name).write_text('*Node\n1,0,0,0\n')
    result = stage(root, main, tmp_path / "staged")
    assert (result.submission_dir.parent / "Input" / name).is_file()


@pytest.mark.parametrize("reference", ["../../outside.inp", "/tmp/outside.inp", "C:/outside.inp", "C:outside.inp", "//host/share/outside.inp"])
def test_external_paths_block_before_any_destination_is_created(tmp_path, reference):
    root, main = native_bundle(tmp_path)
    main.write_text(f'*Include, input={reference}\n')
    destination = tmp_path / "staged"
    with pytest.raises(ValueError, match="outside|absolute|drive"):
        stage(root, main, destination)
    assert not destination.exists()


def test_missing_include_blocks_before_copying(tmp_path):
    root, main = native_bundle(tmp_path)
    main.write_text('*Include, input=missing.inp\n')
    with pytest.raises(FileNotFoundError):
        stage(root, main, tmp_path / "staged")
    assert not (tmp_path / "staged").exists()


def test_include_cycle_blocks_before_copying(tmp_path):
    root, main = native_bundle(tmp_path)
    (root / "Input/model.inp").write_text('*Include, input=main.inp\n')
    with pytest.raises(ValueError, match="cycle"):
        stage(root, main, tmp_path / "staged")
    assert not (tmp_path / "staged").exists()


def test_repeated_noncyclic_include_is_copied_once(tmp_path):
    root, main = native_bundle(tmp_path)
    main.write_text('*Include, input=../Input/mesh.inp\n' * 2)
    result = stage(root, main, tmp_path / "staged")
    receipt = json.loads(result.manifest_path.read_text())
    assert len(receipt["assets"]) == 4
    assert len(receipt["include_edges"]) == 2


def test_existing_destination_even_empty_is_never_reused(tmp_path):
    root, main = native_bundle(tmp_path)
    destination = tmp_path / "staged"
    destination.mkdir()
    with pytest.raises(FileExistsError):
        stage(root, main, destination)
    assert not list(destination.iterdir())


def test_cannot_stage_inside_or_over_source_tree(tmp_path):
    root, main = native_bundle(tmp_path)
    before = main.read_bytes()
    with pytest.raises(ValueError, match="overlap"):
        stage(root, main, root / "copy")
    assert main.read_bytes() == before


@pytest.mark.parametrize("keyword", [
    '*Include, input=a.inp, input=b.inp\n',
    '*Include\n',
    '*Inc, input=a.inp\n',
    '*Node, input=mesh.inp\n',
    '*Node, inp=mesh.inp\n',
    '*Include, input="../Input/mesh.inp\n',
])
def test_unsupported_or_ambiguous_dependency_syntax_fails_closed(tmp_path, keyword):
    root, main = native_bundle(tmp_path)
    main.write_text(keyword)
    with pytest.raises(ValueError):
        stage(root, main, tmp_path / "staged")
    assert not (tmp_path / "staged").exists()


def test_bundle_size_limit_blocks_before_writing(tmp_path):
    root, main = native_bundle(tmp_path)
    with pytest.raises(ValueError, match="byte limit"):
        stage(root, main, tmp_path / "staged", max_total_bytes=10)
    assert not (tmp_path / "staged").exists()


def test_bundle_file_limit_blocks_before_writing(tmp_path):
    root, main = native_bundle(tmp_path)
    with pytest.raises(ValueError, match="file limit"):
        stage(root, main, tmp_path / "staged", max_files=1)
    assert not (tmp_path / "staged").exists()
