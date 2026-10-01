# SPDX-License-Identifier: MIT
# Copyright © 2026 Intel Corporation

"""General utility functions.

The little things you need that don't really have a good place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from simple_monads.maybe import Nothing, Something

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from simple_monads.maybe import Maybe


def find[T](predicate: Callable[[T], bool], iterable: Iterable[T]) -> Maybe[T]:
    """Find the first instance in an iterable that matches the predicate.

    :param predicate:
        A function that takes an item and returns True if it matches the condition.
    :param iterable: An iterable of items to search through.
    :return:
        A Maybe containing the first matching item, or Nothing if no match is found.
    """
    for item in iterable:
        if predicate(item):
            return Something(item)
    return Nothing()
