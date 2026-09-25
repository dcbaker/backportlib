# SPDX-License-Identifier: MIT
# Copyright © 2026 Intel Corporation

"""Processing of git commits."""

from __future__ import annotations

import enum
import pathlib
import re
from typing import TYPE_CHECKING, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator
from simple_monads.maybe import Maybe, Nothing, Something
from simple_monads.result import Success, stop

from backportlib.utils.process import FailedToRun, git
from backportlib.utils.utils import find

if TYPE_CHECKING:
    from simple_monads.result import Result


_IS_FIX = re.compile(r'^\s*fixes:\s*([a-f0-9]{6,40})', flags=re.MULTILINE | re.IGNORECASE)
_IS_BACKPORT = re.compile(
    r'^\s*backport-to:\s*(?:(\d+\.\d+),?\s*(\d+\.\d+)?|(\*))', flags=re.MULTILINE | re.IGNORECASE
)
_IS_CHERRY_PICK = re.compile(r'\(cherry picked from commit ([a-f0-9]{40})\)')


@enum.unique
class NominationType(enum.Enum):
    """Backport status of a commit.

    Information about the kind of nomination this commit has received.

    .. note::
        This does not indicate whether a patch is backported or not, simply whether
        it has been nominated for backport, and the kind of nomination it has.

    .. note::
        see also :class:`BackportStatus` for the current backport status of this commit.
    """

    UNCLASSIFIED = 0
    """This commit has not yet been classified for backporting."""

    UNNOMINATED = 1
    """This commit has not been nominated for backporting."""

    DENOMINATED = 2
    """This commit was nominated for backporting, but has been rejected."""

    FIXES = 3
    """This commit has been nominated due to fixing one or more commits."""

    BACKPORT = 4
    """This commit has been nominated due to a backport tag."""

    MANUAL_BACKPORT = 5
    """This commiit was not automatically nominted, but has since been manuall nominated."""


@enum.unique
class BackportStatus(enum.Enum):
    """Backport status of a commit.

    The current status of this commit with respect to backporting.

    .. note::
        This does not reflect the kind of nomination this has, but whether it is
        applied, queued, or not queued for backport.

    .. note::
        see also :class:`NominationType` for the nomination status of this commit.
    """

    NOT_NOMINATED = 0
    """This commit has not been nominated for backporting."""

    WAITING = 1
    """This commit is ready to be backported."""

    BLOCKED = 2
    """This commit is blocked from being backported.

    This means that it is a valid backport, but that there are other backports
    waiting to be applied that must be applied first.
    """

    MANUAL_BACKPORT_REQUIRED = 3
    """This commit requires a manual backport.

    This means that the backport has conflicts or requires manual intervention
    to be applied.
    """

    APPLIED = 4
    """This commit has been successfully backported."""

    MISSING_DEPENDENCIES = 5
    """This commit is missing dependencies required for backporting."""


class Commit(BaseModel):
    """The representation of a commit"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    hashsum: Final[str] = Field(description='The hash of this commit, currently sha1')
    fixes: set[str] = Field(
        default_factory=set, description='The set of commits that this commit fixes'
    )
    backports: set[str] = Field(
        default_factory=set, description='The set of versions that this commit targets'
    )
    nomination: NominationType = Field(
        default=NominationType.UNCLASSIFIED, description='The type of nomination for this patch'
    )
    status: BackportStatus = Field(
        default=BackportStatus.NOT_NOMINATED,
        description='The current backport status of this patch',
    )
    main_hashsum: Maybe[str] = Field(
        default_factory=Nothing,
        description='If this is a cherry pick, the sha that this commit had on the main branch',
    )
    blocked_by: set[str] = Field(
        default_factory=set,
        description='The set of commits that this commit requires to be applied before it can be applied.',
    )
    blocking: set[str] = Field(
        default_factory=set,
        description='The set of commits that this commit prevents from being applied until it is applied.',
    )

    @staticmethod
    def __validate_hash(v: str) -> str:
        if not v:
            raise ValueError('hashsum cannot be empty')
        if not re.fullmatch(r'[a-f0-9]{40}', v):
            raise ValueError('hashsum must be a valid sha1 string')
        return v

    @field_validator('hashsum', mode='before')
    @classmethod
    def _validate_hashsum(cls, v: str) -> str:
        """Validate that the hashsum is is a valid sha1 string.

        It must be 40 characters long, and only contain hexadecimal characters.

        :param v: The hashsum to validate.
        :raises ValueError: If the hashsum is empty or not a valid sha1 string.
        :return: The validated hashsum.
        """
        return cls.__validate_hash(v)

    @field_validator('main_hashsum', mode='before')
    @classmethod
    def _validate_main_hashsum(cls, v: Maybe[str]) -> Maybe[str]:
        """Validate that the main_hashsum is a valid sha1 string if it is not None.

        :param v: The main_hashsum to validate.
        :raises ValueError: If the main_hashsum is not a valid sha1 string.
        :return: The validated main_hashsum.
        """
        return v.map(cls.__validate_hash)

    @field_validator('blocked_by', mode='after')
    @classmethod
    def _validate_blocked_by(cls, v: set[str]) -> set[str]:
        """Validate that all blocked_by commits have valid hashsums.

        :param v: The set of blocked_by commit hashsums.
        :raises ValueError: If any hashsum is not a valid sha1 string.
        :return: The validated set of blocked_by commit hashsums.
        """
        return {cls.__validate_hash(h) for h in v}

    @field_validator('blocking', mode='after')
    @classmethod
    def _validate_blocking(cls, v: set[str]) -> set[str]:
        """Validate that all blocking commits have valid hashsums.

        :param v: The set of blocking commit hashsums.
        :raises ValueError: If any hashsum is not a valid sha1 string.
        :return: The validated set of blocking commit hashsums.
        """
        return {cls.__validate_hash(h) for h in v}

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Commit):
            return NotImplemented
        return self.hashsum == other.hashsum

    def __hash__(self) -> int:
        return int(self.hashsum, base=16)


async def _full_sha(repo: pathlib.Path, sha: str) -> Result[str, FileNotFoundError | FailedToRun]:
    """Expand a short sha into a full sha.

    :param repo: The git repo (as a pathlib.Path) to act on
    :param sha: The sha to be lengthened
    :return: A Success with the full sha, or an Error with an Exception
    """
    return (await git(repo, ['rev-parse', sha])).and_then(lambda x: Success(x[0].decode().strip()))


@stop
async def is_fix(repo: pathlib.Path, msg: str) -> Result[set[str], Exception]:
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
    for match in _IS_BACKPORT.finditer(msg):
        for backport in match.groups():
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
async def parse_commit(repo: pathlib.Path, sha: str, msg: str) -> Result[Commit, Exception]:
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
    cherry_pick = is_cherry_pick(msg)

    return Success(Commit(hashsum=sha, fixes=fixes, backports=backports, main_hashsum=cherry_pick))


async def set_nomination(
    new: list[Commit], existing: list[Commit], repo: pathlib.Path, branch: str
) -> None:
    """Set the nomination type and required fields for each patch.

    If a patch has a fixes or backport field, we need nominate it if:
      - the current branch matches the target branch
      - a fixes tag matches a commit in the tree
      - a fixes tag matches the main_hashsum of a commit in the tree
      - a fixes tag fixes a commit in the list of nominated patches
        in this case we need to set the requires field so that we don't attempt
        to apply a patch that doesn't have it's pre-requisites met.

    :param new: The list of new commits to be considered for nomination.
    :param existing: The list of existing commits in the repository.
    :param repo: The path to the repository.
    :param branch: The current branch to backport to.
    """
    # first, build a set of all known cherry pick hashes we need to
    # account for
    cherry_picked = {h for c in existing if (h := c.main_hashsum.get()) is not None}
    to_commit = {h.hashsum for h in new}

    for commit in new:
        if commit.backports and ('*' in commit.backports or branch in commit.backports):
            commit.nomination = NominationType.BACKPORT
            commit.status = BackportStatus.WAITING
            continue

        if commit.fixes:
            commit.nomination = NominationType.FIXES

            if commit.fixes.issubset(cherry_picked):
                # If the commit has fixes, and all of those fixes are the cherry_pick list,
                # then we can nominate it as a fix.
                commit.status = BackportStatus.WAITING
            else:
                # Otherwise, we first remove any fixes that are not in the cherry_pick list,
                # then we use git to see if those remaining fixes exist in the
                # repository.
                needed = commit.fixes - cherry_picked

                for need in list(needed):
                    if need in to_commit:
                        blocker = find(lambda x, n=need: x.hashsum == n, new)  # type: ignore[misc]
                        msg = (
                            'Somehow we did not find the needed commit, which should have been '
                            'in the new commits list per the check above.'
                        )
                        blocker.unwrap(msg).blocking.add(commit.hashsum)
                        commit.blocked_by.add(need)

                if commit.blocked_by == needed:
                    commit.status = BackportStatus.BLOCKED
                    continue

                if not needed:
                    commit.status = BackportStatus.WAITING
                    continue

                # Check if the needed patches are already applied in the branch
                # before the branch point
                for need in needed.copy():
                    res = await git(repo, ['merge-base', '--is-ancestor', need, branch])
                    if res:
                        needed.remove(need)

                if not needed:
                    commit.status = BackportStatus.WAITING
                    continue

                # finally, check the to_commit set, if all of the remaining
                # needed commits are in to_commit, we set the status to blocked,
                # as this can be applied once the blocked commits are applied.
                # if they are not all in the to_commit set, we mark the commit
                # as not applicable, since not all of the needed commits are
                # available in the to_commit set.
                # TODO: What if the missing commits are later backported, and
                # ths end up in the cherry_picked set?
                if missing := needed - to_commit:
                    commit.status = BackportStatus.MISSING_DEPENDENCIES
                    commit.blocked_by.update(missing)
                    continue

                # Create a relationship between this commit and the commits it is blocked by.
                commit.status = BackportStatus.BLOCKED
                commit.blocked_by.update(needed)
                for need in needed:
                    # Mypy can't infer the lambda type for some reason, pylance can.
                    blocker = find(lambda x, n=need: x.hashsum == n, new)  # type: ignore[misc]
                    msg = (
                        'Somehow we did not find the needed commit, which should have been '
                        'in the new commits list per the check above.'
                    )
                    blocker.unwrap(msg).blocking.add(commit.hashsum)
                    commit.blocked_by.add(need)
        else:
            commit.nomination = NominationType.UNNOMINATED
            commit.status = BackportStatus.NOT_NOMINATED
