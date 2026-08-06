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


class TestFix:
    """Test for fixes detection."""

    @pytest.fixture
    @staticmethod
    def patch_full_sha(monkeypatch: MonkeyPatch) -> None:
        async def _full_sha(repo: str, sha: str) -> Result[str, FileNotFoundError | FailedToRun]:
            return Success('{:0>40}'.format(sha))

        monkeypatch.setattr(commits, '_full_sha', _full_sha)

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
