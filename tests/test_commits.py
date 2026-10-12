# SPDX-License-Identifier: MIT
# Copyright © 2026 Intel Corporation

"""Tests for the utilites package."""

import json
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
import pytest_mock
from simple_monads.maybe import Maybe, Nothing, Something
from simple_monads.result import Error, Success

from backportlib import commits

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import MonkeyPatch
    from simple_monads.result import Result

    from backportlib.utils.process import FailedToRun


@pytest.fixture
def patch_full_sha(monkeypatch: MonkeyPatch) -> None:
    async def _full_sha(repo: str, sha: str) -> Result[str, FileNotFoundError | FailedToRun]:
        return Success(f'{sha:0>40}')

    monkeypatch.setattr(commits, '_full_sha', _full_sha)


def _make_commit(num: int) -> str:
    return f'{num:0>40}'


class TestFix:
    """Test for fixes detection."""

    @pytest.mark.asyncio
    async def test_single_fix(self, tmp_path: Path, patch_full_sha: None) -> None:
        """Find a single fix."""
        msg = """\
            commit: This is a commit

            fixes: abc123456 ("foo")
            """

        fixes = await commits.is_fix(tmp_path, msg)
        assert fixes.is_ok()
        because = fixes.unwrap()
        assert len(because) == 1
        assert '{:0>40}'.format('abc123456') in because

    @pytest.mark.asyncio
    async def test_multiline_fix(self, tmp_path: Path, patch_full_sha: None) -> None:
        """Find a single fix on multiple lines."""
        msg = """\
            commit: This is a commit

            fixes: abc123456
                   ("foo")
            """

        fixes = await commits.is_fix(tmp_path, msg)
        assert fixes.is_ok()
        because = fixes.unwrap()
        assert len(because) == 1
        assert '{:0>40}'.format('abc123456') in because

    @pytest.mark.asyncio
    async def test_multiple_fixes(self, tmp_path: Path, patch_full_sha: None) -> None:
        """Find multiple fixes."""
        msg = """\
            commit: This is a commit

            fixes: abc123456 ("foo")
            fixes: def123456 ("foo")
            """

        fixes = await commits.is_fix(tmp_path, msg)
        assert fixes.is_ok()
        because = fixes.unwrap()
        assert len(because) == 2
        assert because.issubset(
            {(await commits._full_sha(tmp_path, s)).unwrap() for s in ['abc123456', 'def123456']}
        )


class TestBackport:
    def test_single_star(self) -> None:
        """Find a backport with a single star."""
        msg = """\
            commit: This is a commit

            backport-to: *
            """

        backports = commits.is_backport(msg)
        assert backports.is_ok()
        because = backports.unwrap()
        assert len(because) == 1
        assert '*' in because

    def test_single_version(self) -> None:
        """Find a backport with a single version."""
        msg = """\
            commit: This is a commit

            backport-to: 11.22
            """

        backports = commits.is_backport(msg)
        assert backports.is_ok()
        because = backports.unwrap()
        assert len(because) == 1
        assert '11.22' in because

    def test_many_version(self) -> None:
        """Find a backport with multiple versions."""
        msg = """\
            commit: This is a commit

            backport-to: 11.22      22.33
            """

        backports = commits.is_backport(msg)
        assert backports.is_ok()
        because = backports.unwrap()
        assert len(because) == 2
        assert because == {'11.22', '22.33'}

    def test_many_version_star(self) -> None:
        """Find a backport with multiple versions and star."""
        msg = """\
            commit: This is a commit

            backport-to: * 11.22      22.33
            """

        backports = commits.is_backport(msg)
        assert backports.is_ok()
        because = backports.unwrap()
        assert len(because) == 1
        assert because == {'*'}

    @pytest.mark.xfail
    def test_many_version_star2(self) -> None:
        """Find a backport with multiple versions and star."""
        msg = """\
            commit: This is a commit

            backport-to: 11.22 *     22.33
            """

        backports = commits.is_backport(msg)
        assert backports.is_ok()
        because = backports.unwrap()
        assert len(because) == 1
        assert because == {'*'}

    @pytest.mark.xfail
    def test_many_version_star3(self) -> None:
        """Find a backport with multiple versions and star."""
        msg = """\
            commit: This is a commit

            backport-to: 11.22     22.33     *
            """

        backports = commits.is_backport(msg)
        assert backports.is_ok()
        because = backports.unwrap()
        assert len(because) == 1
        assert because == {'*'}


class TestCherryPick:
    def test_basic(self) -> None:
        msg = """
            This is a commit

            (cherry picked from commit 0000000000000000000000000000000000000000)
            """

        c = commits.is_cherry_pick(msg)
        assert c.is_something()
        assert c.unwrap() == '0' * 40


class TestParse:
    @pytest.mark.asyncio
    async def test_basic(self, tmp_path: Path, patch_full_sha: None) -> None:
        msg = """\
            commit: This is a commit

            fixes: abc123456 ("foo")
            fixes: def123456 ("foo")
            backport-to: 25.3
            (cherry picked from commit 0000000000000000000000000000000000000000)
            """

        p = await commits.parse_commit(tmp_path, '123abc456', msg)
        assert p.is_ok()
        c = p.unwrap()
        assert c.hashsum.endswith('123abc456')
        assert len(c.fixes) == 2
        assert len(c.backports) == 1
        assert c.main_hashsum.is_something()
        assert c.main_hashsum.unwrap() == '0' * 40


@pytest.mark.parametrize(
    ('main_hashsum', 'serialized_value'),
    [(Nothing(), None), (Something(_make_commit(2)), _make_commit(2))],
    ids=['nothing', 'something'],
)
@pytest.mark.parametrize('nomination', list(commits.NominationType))
@pytest.mark.parametrize('status', list(commits.BackportStatus))
@pytest.mark.parametrize('populated', [False, True], ids=['empty-sets', 'populated-sets'])
def test_commit_round_trip(
    main_hashsum: Maybe[str],
    serialized_value: str | None,
    nomination: commits.NominationType,
    status: commits.BackportStatus,
    populated: bool,
) -> None:
    fields: dict[str, object] = {}
    if populated:
        fields = {
            'fixes': {_make_commit(3)},
            'backports': {'25.3', '25.4'},
            'blocked_by': {_make_commit(4)},
            'blocking': {_make_commit(5)},
        }
    original = commits.Commit(
        hashsum=_make_commit(1),
        main_hashsum=main_hashsum,
        nomination=nomination,
        status=status,
        **fields,
    )

    dumped = original.model_dump()
    assert dumped['main_hashsum'] == serialized_value
    restored_from_python = commits.Commit.model_validate(dumped)
    serialized = original.model_dump_json()
    assert json.loads(serialized)['main_hashsum'] == serialized_value

    restored = commits.Commit.model_validate_json(serialized)
    for reloaded in (restored_from_python, restored):
        assert reloaded.hashsum == original.hashsum
        assert reloaded.fixes == original.fixes
        assert reloaded.backports == original.backports
        assert reloaded.nomination is nomination
        assert reloaded.status is status
        assert reloaded.main_hashsum.is_something() is main_hashsum.is_something()
        assert reloaded.main_hashsum.get() == serialized_value
        assert reloaded.blocked_by == original.blocked_by
        assert reloaded.blocking == original.blocking


class TestSetNomination:
    class TestFixes:
        @pytest_asyncio.fixture(scope='class')
        @classmethod
        async def _setup_commits(
            cls,
            tmp_path_factory: pytest.TempPathFactory,
            class_mocker: pytest_mock.MockerFixture,
        ) -> tuple[list[commits.Commit], list[commits.Commit]]:
            tmp_path = tmp_path_factory.mktemp('set-nomination')
            to_pick: list[commits.Commit] = [
                commits.Commit(
                    hashsum=_make_commit(1), fixes={_make_commit(10)}
                ),  # fixes already committed tests
                commits.Commit(
                    hashsum=_make_commit(2), fixes={_make_commit(11)}
                ),  # fixes test that is in cherry_picked set
                commits.Commit(
                    hashsum=_make_commit(3), fixes={_make_commit(1)}
                ),  # fixes test that is queued but not yet applied
                commits.Commit(
                    hashsum=_make_commit(4), fixes={_make_commit(10), _make_commit(11)}
                ),  # fixes two tests, one of which is already committed, one is in the cherry-picked set
                commits.Commit(
                    hashsum=_make_commit(5), fixes={_make_commit(12)}
                ),  # fixes test that is neither in the cherry_picked set nor already applied
                commits.Commit(
                    hashsum=_make_commit(6), fixes={_make_commit(11), _make_commit(12)}
                ),  # applies to cherry-picked commit but missing one dependency
                commits.Commit(
                    hashsum=_make_commit(7), fixes={_make_commit(10), _make_commit(12)}
                ),  # applies to previously applied commit but missing one dependency
                commits.Commit(
                    hashsum=_make_commit(8),
                    fixes={_make_commit(10), _make_commit(11), _make_commit(12)},
                ),  # applies to cherry-picked and previously applied commits but missing one dependency
            ]

            cherry_picked: list[commits.Commit] = [
                commits.Commit(hashsum=_make_commit(20), main_hashsum=Something(_make_commit(11))),
            ]
            for c in cherry_picked:
                c.status = commits.BackportStatus.APPLIED

            async def mock_git(
                _repo: Path, _args: list[str]
            ) -> Result[tuple[bytes, bytes], Exception]:
                need = _args[2]
                if need in {_make_commit(10)}:
                    return Success((b'stdout', b'stderr'))
                return Error(Exception('need not found'))

            class_mocker.patch('backportlib.commits.git', mock_git)

            await commits.set_nomination(to_pick, cherry_picked, tmp_path, 'stable')

            return to_pick, cherry_picked

        @pytest.mark.asyncio
        async def test_fixes_previously_applied(
            self, _setup_commits: tuple[list[commits.Commit], list[commits.Commit]]
        ) -> None:
            to_pick, _ = _setup_commits
            com = to_pick[0]
            assert com.nomination is commits.NominationType.FIXES
            assert com.status is commits.BackportStatus.WAITING
            assert not com.blocked_by
            # Block skipped because another test depends on this

        @pytest.mark.asyncio
        async def test_fixes_cherry_picked(
            self, _setup_commits: tuple[list[commits.Commit], list[commits.Commit]]
        ) -> None:
            to_pick, _ = _setup_commits
            com = to_pick[1]
            assert com.nomination is commits.NominationType.FIXES
            assert com.status is commits.BackportStatus.WAITING
            assert not com.blocked_by
            assert not com.blocking

        @pytest.mark.asyncio
        async def test_fixes_blocked(
            self, _setup_commits: tuple[list[commits.Commit], list[commits.Commit]]
        ) -> None:
            to_pick, _ = _setup_commits
            blocker = to_pick[0]
            com = to_pick[2]
            assert com.nomination is commits.NominationType.FIXES
            assert com.status is commits.BackportStatus.BLOCKED
            assert com.blocked_by == {blocker.hashsum}
            assert not com.blocking
            assert blocker.blocking == {com.hashsum}
            assert not blocker.blocked_by

        @pytest.mark.asyncio
        async def test_fixes_branch_and_cherry_picked(
            self, _setup_commits: tuple[list[commits.Commit], list[commits.Commit]]
        ) -> None:
            to_pick, _ = _setup_commits
            com = to_pick[3]
            assert com.nomination is commits.NominationType.FIXES
            assert com.status is commits.BackportStatus.WAITING
            assert not com.blocked_by
            assert not com.blocking

        @pytest.mark.asyncio
        async def test_fixes_neither_applied_nor_cherry_picked(
            self, _setup_commits: tuple[list[commits.Commit], list[commits.Commit]]
        ) -> None:
            to_pick, _ = _setup_commits
            com = to_pick[4]
            assert com.nomination is commits.NominationType.FIXES
            assert com.status is commits.BackportStatus.MISSING_DEPENDENCIES
            assert com.blocked_by == {_make_commit(12)}
            assert not com.blocking

        @pytest.mark.asyncio
        async def test_applies_to_cherry_picked_but_missing_one(
            self, _setup_commits: tuple[list[commits.Commit], list[commits.Commit]]
        ) -> None:
            to_pick, _ = _setup_commits
            com = to_pick[5]
            assert com.nomination is commits.NominationType.FIXES
            assert com.status is commits.BackportStatus.MISSING_DEPENDENCIES
            assert com.blocked_by == {_make_commit(12)}
            assert not com.blocking

        @pytest.mark.asyncio
        async def test_applies_to_previously_applied_but_missing_one(
            self, _setup_commits: tuple[list[commits.Commit], list[commits.Commit]]
        ) -> None:
            to_pick, _ = _setup_commits
            com = to_pick[6]
            assert com.nomination is commits.NominationType.FIXES
            assert com.status is commits.BackportStatus.MISSING_DEPENDENCIES
            assert com.blocked_by == {_make_commit(12)}
            assert not com.blocking

        @pytest.mark.asyncio
        async def test_applies_cherry_and_previous_but_missing_one(
            self, _setup_commits: tuple[list[commits.Commit], list[commits.Commit]]
        ) -> None:
            to_pick, _ = _setup_commits
            com = to_pick[7]
            assert com.nomination is commits.NominationType.FIXES
            assert com.status is commits.BackportStatus.MISSING_DEPENDENCIES
            assert com.blocked_by == {_make_commit(12)}
            assert not com.blocking

    class TestBackport:
        @pytest_asyncio.fixture(scope='class')
        @classmethod
        async def _setup_commits(
            cls,
            tmp_path_factory: pytest.TempPathFactory,
            class_mocker: pytest_mock.MockerFixture,
        ) -> list[commits.Commit]:
            tmp_path = tmp_path_factory.mktemp('set-nomination')
            to_pick: list[commits.Commit] = [
                commits.Commit(hashsum=_make_commit(1), backports={'*'}),  # should be backported
                commits.Commit(
                    hashsum=_make_commit(2), backports={'stable'}
                ),  # should be backported
                commits.Commit(
                    hashsum=_make_commit(3), backports={'stable', 'old-stable'}
                ),  # should be backported
                commits.Commit(
                    hashsum=_make_commit(4), backports={'old-stable'}
                ),  # should not be backported
                commits.Commit(
                    hashsum=_make_commit(5), backports={'*'}, fixes={_make_commit(100)}
                ),  # should be backported as a backport, not a fix
            ]

            async def mock_git(
                _repo: Path, _args: list[str]
            ) -> Result[tuple[bytes, bytes], Exception]:
                need = _args[2]
                if need in {_make_commit(100)}:
                    return Success((b'stdout', b'stderr'))
                return Error(Exception('need not found'))

            class_mocker.patch('backportlib.commits.git', mock_git)

            await commits.set_nomination(to_pick, [], tmp_path, 'stable')

            return to_pick

        @pytest.mark.asyncio
        async def test_star_backport(self, _setup_commits: list[commits.Commit]) -> None:
            com = _setup_commits[0]
            assert com.nomination is commits.NominationType.BACKPORT
            assert com.status is commits.BackportStatus.WAITING

        @pytest.mark.asyncio
        async def test_matching_branch_backport(self, _setup_commits: list[commits.Commit]) -> None:
            com = _setup_commits[1]
            assert com.nomination is commits.NominationType.BACKPORT
            assert com.status is commits.BackportStatus.WAITING

        @pytest.mark.asyncio
        async def test_one_of_multiple_matching_branches(
            self, _setup_commits: list[commits.Commit]
        ) -> None:
            com = _setup_commits[2]
            assert com.nomination is commits.NominationType.BACKPORT
            assert com.status is commits.BackportStatus.WAITING

        @pytest.mark.asyncio
        async def test_nonmatching_branch_backport(
            self, _setup_commits: list[commits.Commit]
        ) -> None:
            com = _setup_commits[3]
            assert com.nomination is commits.NominationType.UNNOMINATED
            assert com.status is commits.BackportStatus.NOT_NOMINATED

        @pytest.mark.asyncio
        async def test_backport_takes_precedence_over_fixes(
            self, _setup_commits: list[commits.Commit]
        ) -> None:
            com = _setup_commits[4]
            assert com.nomination is commits.NominationType.BACKPORT
            assert com.status is commits.BackportStatus.WAITING
            assert not com.blocked_by
            assert not com.blocking
