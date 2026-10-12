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
from simple_monads.result import Error, Result, Success

from backportlib.commits import Commit


class CommitList(BaseModel):
    commits: list[Commit] = Field(
        default_factory=list,
        description='List of commits in the commit list, stored from newest to oldest.',
    )

    _path: Path = PrivateAttr()
    _file_lock: asyncio.Lock = PrivateAttr(
        default_factory=asyncio.Lock,
        init=False,
    )

    def __init__(self, *, path: Path, **data: Any) -> None:
        super().__init__(**data)
        self._path = path

    async def write(self) -> Result[None, OSError]:
        """Write the commit list to its configured file path.

        :return: A Result indicating success or failure of the write operation.
        """
        data = self.model_dump_json(indent=4)

        def write_file() -> Result[None, OSError]:
            try:
                tmpfile = self._path.with_suffix(self._path.suffix + '.tmp')
                with tmpfile.open('w', encoding='utf-8') as f:
                    f.write(data)
                tmpfile.replace(self._path)
            except OSError as e:
                return Error(e)
            return Success(None)

        async with self._file_lock:
            return await asyncio.to_thread(write_file)

    @classmethod
    def load(cls, path: Path, /) -> Result[CommitList, OSError | ValueError]:
        """Load a commit list from the specified file path.

        :param path: The file path from which to load the commit list.
        :return: A Result containing the loaded CommitList on success, or an Error on failure.
        """
        try:
            data = TypeAdapter(dict[str, list[Commit]]).validate_json(
                path.read_text(encoding='utf-8')
            )
            return Success(cls(path=path, **data))
        except (OSError, ValueError) as e:
            return Error(e)
