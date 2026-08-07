# SPDX-License-Identifier: MIT
# Copyright © 2026 Intel Corporation

"""Processing of git commits."""

import dataclasses
import enum
import re
from typing import TYPE_CHECKING

from simple_monads.result import Success, stop_async

from backportlib.utils.process import FailedToRun, git

if TYPE_CHECKING:
    from typing import Final

    from simple_monads.result import Result


_IS_FIX = re.compile(r'^\s*fixes:\s*([a-f0-9]{6,40})', flags=re.MULTILINE | re.IGNORECASE)
_IS_BACKPORT = re.compile(r'^\s*backport-to:\s*(?:(\d+\.\d+),?\s*(\d+\.\d+)?|(\*))',
                          flags=re.MULTILINE | re.IGNORECASE)


@enum.unique
class NominationStatus(enum.Enum):
    """Backport status of a commit."""

    UNCLASSIFIED = 0
    UNNOMINATED = 1
    DENOMINATED = 2
    FIXES = 3
    BACKPORT = 4
    MANUAL_BACKPORT = 5


@dataclasses.dataclass(slots=True, order=True)
class Commit:
    """The representation of a commit"""

    hashsum: Final[str] = dataclasses.field(doc='The hash of this commit, currently sha256')
    fixes: set[str] = dataclasses.field(
        default_factory=set, compare=False, doc='The set of commits that this commit fixes')
    backports: set[str] = dataclasses.field(
        default_factory=set, compare=False, doc='The set of versions that this ')
    nomination: NominationStatus = dataclasses.field(
        default=NominationStatus.UNCLASSIFIED, compare=False,
        doc='The type of nomination for this patch')
    applied: bool = dataclasses.field(
        default=False, compare=False, doc='Whether this patch has been applied or not')

    def __hash__(self) -> int:
        return int(self.hashsum, base=16)


async def _full_sha(repo: str, sha: str) -> Result[str, FileNotFoundError | FailedToRun]:
    """Expand a short sha into a full sha.

    :param repo: The git repo to act on
    :param sha: The shat to be lengthened
    :return: A Success with the full sha, or an Error with an Exception
    """
    return (await git(repo, ['rev-parse', sha])).and_then(lambda x: Success(x[0].decode()))


@stop_async
async def is_fix(repo: str, msg: str) -> Result[set[str], Exception]:
    because = set[str]()

    for fix in _IS_FIX.finditer(msg):
        if fix:
            full_sha = (await _full_sha(repo, fix.group(1))).propagate()
            because.add(full_sha)

    return Success(because)


def is_backport(repo: str, msg: str) -> Result[set[str], Exception]:
    backports = set[str]()
    if m := _IS_BACKPORT.findall(msg):
        for match in m:
            for backport in match:
                if backport:
                    backports.add(backport)

    if '*' in backports:
        backports = {'*'}

    return Success(backports)


@stop_async
async def parse_commit(repo: str, sha: str, msg: str) -> Result[Commit, Exception]:
    if len(sha) != 40:
        sha = (await _full_sha(repo, sha)).propagate()

    fixes = (await is_fix(repo, msg)).propagate()
    backports = is_backport(repo, msg).propagate()

    return Success(Commit(sha, fixes, backports))
