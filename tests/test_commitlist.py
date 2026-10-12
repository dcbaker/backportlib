# SPDX-License-Identifier: MIT
# Copyright © 2026 Intel Corporation

"""Tests for the commitlist module."""

from pathlib import Path

import pytest
import pytest_mock
from simple_monads.result import Error, Success

from backportlib.commitlist import COMMIT_LOG_DIVIDER, CommitList, UpdateException
from backportlib.commits import Commit, NominationType
from backportlib.utils import process

from .utils import make_commit


@pytest.mark.asyncio
async def test_write_and_load_from_disk(tmp_path: Path) -> None:
    path = tmp_path / 'commits.json'
    git_path = tmp_path / 'repo'
    commit_list = CommitList(path=path, git_dir=git_path, commits=[Commit(hashsum=make_commit(0))])

    result = await commit_list.save()

    assert result.is_ok()
    assert path.is_file()
    assert not path.with_suffix('.json.tmp').exists()

    # Validate the persisted JSON with Pydantic before constructing the model.
    loaded = CommitList.load(path, git_path)
    assert loaded.is_ok()
    loaded_commit_list = loaded.unwrap()
    assert loaded_commit_list.commits == commit_list.commits


@pytest.mark.asyncio
async def test_write_returns_error_when_parent_directory_is_missing(tmp_path: Path) -> None:
    path = tmp_path / 'missing' / 'commits.json'
    git_path = tmp_path / 'repo'
    commit_list = CommitList(path=path, git_dir=git_path)

    result = await commit_list.save()

    assert result.is_err()
    assert not path.exists()


class TestUpdate:
    """Tests for the update functionality of the CommitList."""

    @pytest.mark.asyncio
    async def test_adds_new_commits_ahead_of_existing_commits(
        self, tmp_path: Path, mocker: pytest_mock.MockerFixture
    ) -> None:
        existing = Commit(hashsum=make_commit(1))
        new_hash = make_commit(2)
        commit_list = CommitList(
            path=tmp_path / 'commits.json',
            git_dir=tmp_path / 'repo',
            commits=[existing],
        )

        git_mock = mocker.patch.object(
            commit_list,
            '_run_git',
            side_effect=[
                Success((b'', b'')),
                Success((f'{new_hash}{COMMIT_LOG_DIVIDER}A new commit'.encode(), b'')),
            ],
        )

        result = await commit_list.update()

        assert result.is_ok()
        assert [commit.hashsum for commit in commit_list.commits] == [new_hash, existing.hashsum]
        assert commit_list.commits[0].nomination is NominationType.UNNOMINATED
        assert [await_call.args for await_call in git_mock.await_args_list] == [
            ('merge-base', '--is-ancestor', existing.hashsum, 'HEAD'),
            ('log', f'--pretty=format:%H{COMMIT_LOG_DIVIDER}%s', f'{existing.hashsum}..'),
        ]

    @pytest.mark.asyncio
    async def test_returns_error_when_commit_list_is_empty(self, tmp_path: Path) -> None:
        commit_list = CommitList(path=tmp_path / 'commits.json', git_dir=tmp_path / 'repo')

        result = await commit_list.update()

        assert result.is_err()
        assert isinstance(result.unwrap_err(), UpdateException)
        assert str(result.unwrap_err()) == 'No commits available in the commit list.'

    @pytest.mark.asyncio
    async def test_reports_rewritten_history(
        self, tmp_path: Path, mocker: pytest_mock.MockerFixture
    ) -> None:
        existing = Commit(hashsum=make_commit(1))
        commit_list = CommitList(
            path=tmp_path / 'commits.json',
            git_dir=tmp_path / 'repo',
            commits=[existing],
        )

        mocker.patch.object(commit_list, '_run_git', return_value=Error(process.FailedToRun(1)))

        result = await commit_list.update()

        assert result.is_err()
        assert isinstance(result.unwrap_err(), UpdateException)
        assert str(result.unwrap_err()) == 'A force push has rewritten commit history.'
        assert commit_list.commits == [existing]
