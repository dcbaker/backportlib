# SPDX-License-Identifier: MIT
# Copyright © 2026 Intel Corporation

"""Utility functions for tests."""


def make_commit(num: int) -> str:
    """Make a SHA1 compatible has from a number.

    :param num: The number for the hash.
    :return: A hash in SHA1 compatible format.
    """
    return f'{num:0>40}'
