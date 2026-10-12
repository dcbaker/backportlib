# SPDX-License-Identifier: MIT
# Copyright © 2026 Intel Corporation

"""Commit list management for backportlib.

This module provides functionality for handling and manipulating
lists of commits within the backportlib framework.
"""

import asyncio
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, PrivateAttr, TypeAdapter
from simple_monads.result import Error, Result, Success, stop

from backportlib.commits import Commit, parse_commit, set_nomination
from backportlib.utils import process

COMMIT_LOG_DIVIDER = '|&<">&|'


class UpdateException(Exception):
    """Exception raised for errors during the update of the commit list."""


class CommitList(BaseModel):
    commits: list[Commit] = Field(
        default_factory=list,
        description='List of commits in the commit list, stored from newest to oldest.',
    )

    _file_path: Path = PrivateAttr()
    _file_lock: asyncio.Lock = PrivateAttr(
        default_factory=asyncio.Lock,
        init=False,
    )

    _git_dir: Path = PrivateAttr()
    _git_lock: asyncio.Lock = PrivateAttr(
        default_factory=asyncio.Lock,
        init=False,
    )

    def __init__(self, *, path: Path, git_dir: Path, **data: Any) -> None:
        super().__init__(**data)
        self._file_path = path
        self._git_dir = git_dir

    async def save(self) -> Result[None, OSError]:
        """Write the commit list to its configured file path.

        :return: A Result indicating success or failure of the write operation.
        """
        data = self.model_dump_json(indent=4)

        def write_file() -> Result[None, OSError]:
            try:
                tmpfile = self._file_path.with_suffix(self._file_path.suffix + '.tmp')
                with tmpfile.open('w', encoding='utf-8') as f:
                    f.write(data)
                tmpfile.replace(self._file_path)
            except OSError as e:
                return Error(e)
            return Success(None)

        async with self._file_lock:
            return await asyncio.to_thread(write_file)

    @classmethod
    def load(cls, path: Path, git_dir: Path, /) -> Result[CommitList, OSError | ValueError]:
        """Load a commit list from the specified file path.

        :param path: The file path from which to load the commit list.
        :param git_dir: The path to the Git repository associated with the commit list.
        :return: A Result containing the loaded CommitList on success, or an Error on failure.
        """
        try:
            data = TypeAdapter(dict[str, list[Commit]]).validate_json(
                path.read_text(encoding='utf-8')
            )
            return Success(cls(path=path, git_dir=git_dir, **data))
        except (OSError, ValueError) as e:
            return Error(e)

    async def _run_git(
        self, *args: str
    ) -> Result[tuple[bytes, bytes], FileNotFoundError | process.FailedToRun]:
        async with self._git_lock:
            return await process.git(self._git_dir, list(args))

    @stop
    async def update(
        self,
    ) -> Result[None, UpdateException | FileNotFoundError | process.FailedToRun]:
        """Update the commit list with the latest changes.

        :return: A Result indicating success or failure of the update operation.
        """
        try:
            last_commit = self.commits[0].hashsum
        except IndexError:
            return Error(UpdateException('No commits available in the commit list.'))

        # Ensure the most recently processed commit remains in HEAD's history.
        (await self._run_git('merge-base', '--is-ancestor', last_commit, 'HEAD')).map_err(
            lambda e: UpdateException(
                'A force push has rewritten commit history.'
                if isinstance(e, process.FailedToRun) and e.returncode == 1
                else str(e)
            )
        ).propagate()

        git_range = f'{last_commit}..'

        # Get the list of commits since the last time we processed commits
        new_hashes_bytes, _ = (
            await self._run_git('log', f'--pretty=format:%H{COMMIT_LOG_DIVIDER}%s', git_range)
        ).propagate()
        new_hashes = new_hashes_bytes.decode('utf-8')

        async def parse_new_commit(raw: str) -> Commit:
            commit, msg = raw.split(COMMIT_LOG_DIVIDER, 1)
            return (
                (await parse_commit(self._git_dir, commit, msg))
                .map_err(lambda e: UpdateException(str(e)))
                .propagate()
            )

        new_commits = await asyncio.gather(
            *(parse_new_commit(raw) for raw in new_hashes.splitlines())
        )

        # TODO: get branch name
        async with self._git_lock:
            await set_nomination(new_commits, self.commits, self._git_dir, 'stable')

        self.commits = new_commits + self.commits
        return Success(None)
