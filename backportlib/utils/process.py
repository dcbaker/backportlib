# SPDX-License-Identifier: MIT
# Copyright © 2026 Intel Corporation

from __future__ import annotations

import asyncio
import dataclasses
import pathlib
from typing import TYPE_CHECKING

from simple_monads.result import Error, Success, stop, wrap

if TYPE_CHECKING:
    from simple_monads.result import Result


@dataclasses.dataclass
class FailedToRun(Exception):
    """An Exception for processes that failed to run."""

    returncode: int


@wrap(FileNotFoundError)
async def _start_cmd(
    cmd: str, args: list[str] | None = None, *, capture: bool = True
) -> asyncio.subprocess.Process:
    """Helper to start a command.

    :param cmd: The command to run
    :param args: The arguments to pass to that command
    :param capture: Whether to capture the output of the command or not (default: True)
    :return: A :class:`asyncio.subprocess.Process` object
    """
    pipe = asyncio.subprocess.PIPE if capture else asyncio.subprocess.DEVNULL
    p = await asyncio.create_subprocess_exec(cmd, *(args or []), stdout=pipe, stderr=pipe)

    return p


@stop
async def output(
    cmd: str, args: list[str] | None = None
) -> Result[tuple[bytes, bytes], FileNotFoundError | FailedToRun]:
    """Run a command and get its output.

    :param cmd: The command as a string
    :param args: The list of arguments to pass to that command
    :return: A Success holding (stdout, stderr) or an Error holding an error
    """
    p = (await _start_cmd(cmd, args)).propagate()
    std = await p.communicate()
    if ret := p.returncode:
        return Error(FailedToRun(ret))
    return Success(std)


@stop
async def returncode(
    cmd: str, args: list[str] | None = None
) -> Result[None, FileNotFoundError | FailedToRun]:
    """Run a command and get its returncode.

    :param cmd: The command as a string
    :param args: The list of arguments to pass to that command
    :return: A Success holding None or an Error holding the returncode
    """
    p = (await _start_cmd(cmd, args, capture=False)).propagate()
    if ret := await p.wait():
        return Error(FailedToRun(ret))
    return Success(None)


async def git(
    repo: pathlib.Path, args: list[str]
) -> Result[tuple[bytes, bytes], FileNotFoundError | FailedToRun]:
    """Run a git command.

    :param repo: The repo to run the git command on
    :param args: The arguments to pass to git in addition to the repo
    :return: A Success holding (stdout, stderr) or an Error holding the returncode
    """
    return await output('git', ['-C', str(repo)] + args)
