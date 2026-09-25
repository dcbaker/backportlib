# SPDX-License-Identifier: MIT
# Copyright © 2026 Intel Corporation

"""Processing of git commits."""

import enum
import re
from typing import TYPE_CHECKING, Final

from pydantic import BaseModel, ConfigDict, Field
from simple_monads.maybe import Maybe, Nothing, Something
from simple_monads.result import Success, stop

from backportlib.utils.process import FailedToRun, git

if TYPE_CHECKING:
    from simple_monads.result import Result


_IS_FIX = re.compile(
    r'^\s*fixes:\s*([a-f0-9]{6,40})', flags=re.MULTILINE | re.IGNORECASE)
_IS_BACKPORT = re.compile(r'^\s*backport-to:\s*(?:(\d+\.\d+),?\s*(\d+\.\d+)?|(\*))',
                          flags=re.MULTILINE | re.IGNORECASE)
_IS_CHERRY_PICK = re.compile(r'\(cherry picked from commit ([a-f0-9]{40})\)')


@enum.unique
class NominationStatus(enum.Enum):
    """Backport status of a commit."""

    UNCLASSIFIED = 0
    UNNOMINATED = 1
    DENOMINATED = 2
    FIXES = 3
    BACKPORT = 4
    MANUAL_BACKPORT = 5


class Commit(BaseModel):
    """The representation of a commit"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    hashsum: Final[str] = Field(description='The hash of this commit, currently sha1')
    fixes: set[str] = Field(
        default_factory=set, description='The set of commits that this commit fixes')
    backports: set[str] = Field(
        default_factory=set, description='The set of versions that this commit targets')
    nomination: NominationStatus = Field(
        default=NominationStatus.UNCLASSIFIED,
        description='The type of nomination for this patch')
    applied: bool = Field(
        default=False, description='Whether this patch has been applied or not')
    main_hashsum: Maybe[str] = Field(
        default_factory=Nothing,
        description='If this is a cherry pick, the sha that this commit had on the main branch')

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Commit):
            return NotImplemented
        return self.hashsum == other.hashsum

    def __hash__(self) -> int:
        return int(self.hashsum, base=16)


async def _full_sha(repo: str, sha: str) -> Result[str, FileNotFoundError | FailedToRun]:
    """Expand a short sha into a full sha.

    :param repo: The git repo to act on
    :param sha: The sha to be lengthened
    :return: A Success with the full sha, or an Error with an Exception
    """
    return (await git(repo, ['rev-parse', sha])).and_then(lambda x: Success(x[0].decode().strip()))


@stop
async def is_fix(repo: str, msg: str) -> Result[set[str], Exception]:
    """Extract any `fixes:` tags in the commit message.

    :param repo: The git repository that this commit is from.
    :param msg: The commit message of this commit.
    :return: Success with the commit sha or an Error with an exception.
    """
    fixed_shas = set[str]()

    for fix in _IS_FIX.finditer(msg):
        full_sha = (await _full_sha(repo, fix.group(1))).propagate()
        fixed_shas.add(full_sha)

    return Success(fixed_shas)


def is_backport(msg: str) -> Result[set[str], Exception]:
    """Extract any `backport-to:` tag in the commit message.

    :param msg: The commit message of this commit.
    :return: Success with a set of backport tags or an Error with an exception.
    """
    backports = set[str]()
    if m := _IS_BACKPORT.findall(msg):
        for match in m:
            for backport in match:
                if backport:
                    backports.add(backport)

    if '*' in backports:
        backports = {'*'}

    return Success(backports)


def is_cherry_pick(msg: str) -> Maybe[str]:
    """Is this commit cherry picked from

    :param msg: The commit message of this commit.
    :return: A Maybe with the cherry pick sha if it exists, or Nothing otherwise.
    """
    if m := _IS_CHERRY_PICK.search(msg):
        return Something(m.group(1))
    return Nothing()


@stop
async def parse_commit(repo: str, sha: str, msg: str) -> Result[Commit, Exception]:
    """Create a Commit object from commit data.

    :param repo: The repo that the commit is from.
    :param sha: the hash of the commit.
    :param msg: the commit message of the commit.
    :return: A Success with the Commit object or an Error with an Exception.
    """
    if len(sha) != 40:
        sha = (await _full_sha(repo, sha)).propagate()

    fixes = (await is_fix(repo, msg)).propagate()
    backports = is_backport(msg).propagate()

    return Success(Commit(hashsum=sha, fixes=fixes, backports=backports))
