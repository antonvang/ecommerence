"""Module-level guard for every test module: no sockets, no DNS.

Import `setUpModule` and `tearDownModule` from here into each test module.
Any accidental network use then fails loudly instead of reaching a real host.
"""
from unittest import mock


class NetworkBlocked(AssertionError):
    pass


def _deny(*args, **kwargs):
    raise NetworkBlocked("Network access is forbidden in jupiter_bot tests")


_patchers = []


def setUpModule():
    for target in ("socket.socket.connect", "socket.socket.connect_ex",
                   "socket.create_connection", "socket.getaddrinfo"):
        patcher = mock.patch(target, _deny)
        patcher.start()
        _patchers.append(patcher)


def tearDownModule():
    while _patchers:
        _patchers.pop().stop()

