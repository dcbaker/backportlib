# SPDX-License-Identifier: MIT
# Copyright © 2026 Intel Corporation

"""Tests for the utilites package."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from backportlib.utils import process, utils

if TYPE_CHECKING:
    from pathlib import Path


class TestProcess:
    """Tests for the Process module."""

    class TestOutput:
        """Tests for the output function."""

        @pytest.mark.asyncio
        async def test_basic(self) -> None:
            """Basic stdout checking."""
            ret = await process.output('python', ['--version'])
            assert ret.is_ok()
            assert ret.unwrap()[0].startswith(b'Python 3')

        @pytest.mark.asyncio
        async def test_non_existing(self) -> None:
            """Error handling for non-existant binary."""
            ret = await process.output('doesnt-exist')
            assert not ret.is_ok()
            assert isinstance(ret.unwrap_err(), FileNotFoundError)

        @pytest.mark.asyncio
        async def test_bad_arguments(self) -> None:
            """Error handling for bad arguments."""
            ret = await process.output('python', ['--bad-argument'])
            assert not ret.is_ok()
            assert isinstance(ret.unwrap_err(), process.FailedToRun)

    class TestReturncode:
        """Tests for the returncode function."""

        @pytest.mark.asyncio
        async def test_basic(self) -> None:
            """Basic stdout checking."""
            ret = await process.returncode('python', ['--version'])
            assert ret.is_ok()

        @pytest.mark.asyncio
        async def test_non_existing(self) -> None:
            """Error handling for non-existant binary."""
            ret = await process.output('doesnt-exist')
            assert not ret.is_ok()
            assert isinstance(ret.unwrap_err(), FileNotFoundError)

        @pytest.mark.asyncio
        async def test_bad_arguments(self) -> None:
            """Error handling for bad arguments."""
            ret = await process.output('python', ['--bad-argument'])
            assert not ret.is_ok()
            assert isinstance(ret.unwrap_err(), process.FailedToRun)

    class TestGit:
        """Tests for the git function."""

        @pytest.mark.asyncio
        async def test_basic(self, tmp_path: Path) -> None:
            """Simple test that checks the git command."""
            repo = tmp_path
            assert (await process.output('git', ['init', str(repo), '-q'])).is_ok()
            assert (await process.git(repo, ['checkout', '-b', 'newbranch'])).is_ok()


class TestUtils:
    """Tests for the utils module."""

    class TestFind:
        """Tests for the find function."""

        def test_match(self) -> None:
            """A matching item is returned."""
            ret = utils.find(lambda x: x == 2, [1, 2, 3])
            assert ret.is_something()
            assert ret.unwrap() == 2

        def test_no_match(self) -> None:
            """Nothing is returned when no item matches."""
            ret = utils.find(lambda x: x == 4, [1, 2, 3])
            assert ret.is_nothing()

        def test_first_match(self) -> None:
            """The first matching item is returned when multiple items match."""
            ret = utils.find(lambda x: x[0] == 'a', [('b', 1), ('a', 2), ('a', 3)])
            assert ret.is_something()
            assert ret.unwrap() == ('a', 2)
