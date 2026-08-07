# SPDX-License-Identifier: MIT
# Copyright © 2026 Intel Corporation

"""Tests for the utilites package."""

from typing import TYPE_CHECKING

import pytest
from simple_monads.result import Success

from backportlib import commits

if TYPE_CHECKING:
    from pytest import MonkeyPatch
    from simple_monads.result import Result

    from backportlib.utils.process import FailedToRun


@pytest.fixture
def patch_full_sha(monkeypatch: MonkeyPatch) -> None:
    async def _full_sha(repo: str, sha: str) -> Result[str, FileNotFoundError | FailedToRun]:
        return Success('{:0>40}'.format(sha))

    monkeypatch.setattr(commits, '_full_sha', _full_sha)


class TestFix:
    """Test for fixes detection."""

    @pytest.mark.asyncio
    async def test_single_fix(self, patch_full_sha: None) -> None:
        """Find a single fix."""
        msg = """\
            commit: This is a commit

            fixes: abc123456 ("foo")
            """

        fixes = await commits.is_fix('', msg)
        assert fixes.is_ok()
        because = fixes.unwrap()
        assert len(because) == 1
        assert '{:0>40}'.format('abc123456') in because

    @pytest.mark.asyncio
    async def test_multiline_fix(self, patch_full_sha: None) -> None:
        """Find a single fix on multiple lines."""
        msg = """\
            commit: This is a commit

            fixes: abc123456
                   ("foo")
            """

        fixes = await commits.is_fix('', msg)
        assert fixes.is_ok()
        because = fixes.unwrap()
        assert len(because) == 1
        assert '{:0>40}'.format('abc123456') in because

    @pytest.mark.asyncio
    async def test_multiple_fixes(self, patch_full_sha: None) -> None:
        """Find multiple fixes."""
        msg = """\
            commit: This is a commit

            fixes: abc123456 ("foo")
            fixes: def123456 ("foo")
            """

        fixes = await commits.is_fix('', msg)
        assert fixes.is_ok()
        because = fixes.unwrap()
        assert len(because) == 2
        assert because.issubset({(await commits._full_sha('', s)).unwrap()
                                  for s in ['abc123456', 'def123456']})


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


class TestParse:

    @pytest.mark.asyncio
    async def test_basic(self, patch_full_sha: None) -> None:
        msg = """\
            commit: This is a commit

            fixes: abc123456 ("foo")
            fixes: def123456 ("foo")
            backport-to: 25.3
            """

        p = await commits.parse_commit('', '123abc456', msg)
        assert p.is_ok()
        c = p.unwrap()
        assert c.hashsum.endswith('123abc456')
        assert len(c.fixes) == 2
        assert len(c.backports) == 1
