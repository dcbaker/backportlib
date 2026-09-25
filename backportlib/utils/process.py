# SPDX-License-Identifier: MIT
# Copyright © 2026 Intel Corporation

import asyncio
import dataclasses
from typing import TYPE_CHECKING

from simple_monads.result import Error, Success, stop, wrap

if TYPE_CHECKING:
    from simple_monads.result import Result


@dataclasses.dataclass
class FailedToRun(Exception):

    """An Exception for processes that failed to run."""

    returncode: int


@wrap(FileNotFoundError)
async def _start_cmd(cmd: str, args: list[str] | None = None) -> asyncio.subprocess.Process:
    """Helper to start a command.

    :param cmd: The command to run
    :param args: The arguments to pass to that command
    :return: A Process object
    """
    p = await asyncio.create_subprocess_exec(
        cmd, *(args or []), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

    return p


@stop
async def output(cmd: str, args: list[str] | None = None
                 ) -> Result[tuple[bytes, bytes], FileNotFoundError | FailedToRun]:
    """Run a command and get its output.

    :param cmd: The command as a string
    :param args: The list of arguments to pass to that command
    :return: A Success holding (stdout, stderr) or an Error holding an error
    """
    p = (await _start_cmd(cmd, args)).propagate()
    ret = await p.wait()
    if ret == 0:
        return Success(await p.communicate())
    return Error(FailedToRun(ret))


@stop
async def returncode(cmd: str, args: list[str] | None = None
                     ) -> Result[None, FileNotFoundError | FailedToRun]:
    """Run a command and get its returncode.

    :param cmd: The command as a string
    :param args: The list of arguments to pass to that command
    :return: A Success holding Nothing or an Error holding the returncode
    """
    p = (await _start_cmd(cmd, args)).propagate()
    ret = await p.wait()
    if ret == 0:
        return Success(None)
    return Error(FailedToRun(ret))


async def git(repo: str, args: list[str]
              ) -> Result[tuple[bytes, bytes], FileNotFoundError | FailedToRun]:
    """Run a git command.

    :param repo: The repo to run the git command on
    :param args: The arguments to pass to git in addition to the repo
    :return: A Success holding (stdout, stderr) or an Error holding the returncode
    """
    return await output('git', ['-C', repo] + args)
