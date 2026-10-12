# SPDX-License-Identifier: MIT
# Copyright © 2026 Intel Corporation

"""Tests for the commitlist module."""

from pathlib import Path

import pytest

from backportlib.commitlist import CommitList
from backportlib.commits import Commit


@pytest.mark.asyncio
async def test_write_and_load_from_disk(tmp_path: Path) -> None:
    path = tmp_path / 'commits.json'
    commit_list = CommitList(path=path, commits=[Commit(hashsum=f'{0:040x}')])

    result = await commit_list.write()

    assert result.is_ok()
    assert path.is_file()
    assert not path.with_suffix('.json.tmp').exists()

    # Validate the persisted JSON with Pydantic before constructing the model.
    loaded = CommitList.load(path)
    assert loaded.is_ok()
    loaded_commit_list = loaded.unwrap()
    assert loaded_commit_list.commits == commit_list.commits


@pytest.mark.asyncio
async def test_write_returns_error_when_parent_directory_is_missing(tmp_path: Path) -> None:
    path = tmp_path / 'missing' / 'commits.json'
    commit_list = CommitList(path=path)

    result = await commit_list.write()

    assert result.is_err()
    assert not path.exists()
