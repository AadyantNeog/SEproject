import socket
from ipaddress import ip_address

import pytest


def _require_loopback(host):
    if isinstance(host, bytes):
        host = host.decode("ascii")
    if host is None or host == "localhost":
        return
    try:
        address = ip_address(host)
    except ValueError:
        pass
    else:
        if address.is_loopback:
            return
    raise AssertionError("Offline tests may only use loopback network addresses")


@pytest.fixture(autouse=True)
def deny_external_network(request, monkeypatch):
    """Keep fixture tests offline while allowing local callbacks and socketpairs."""
    if request.node.get_closest_marker("live") is not None:
        return
    getaddrinfo = socket.getaddrinfo
    connect = socket.socket.connect
    connect_ex = socket.socket.connect_ex
    sendto = socket.socket.sendto

    def guarded_getaddrinfo(host, *args, **kwargs):
        _require_loopback(host)
        return getaddrinfo(host, *args, **kwargs)

    def guarded_socket_call(original):
        def guarded(sock, *args):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                _require_loopback(args[-1][0])
            return original(sock, *args)

        return guarded

    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", guarded_socket_call(connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_socket_call(connect_ex))
    monkeypatch.setattr(socket.socket, "sendto", guarded_socket_call(sendto))
