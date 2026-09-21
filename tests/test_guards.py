"""The AC-6.2 guards actually fire. If these pass, the guards are live for every test."""

import importlib
import socket

import pytest
from conftest import ModelImportBlocked, NetworkBlocked


def test_opening_a_connection_is_blocked() -> None:
    with pytest.raises(NetworkBlocked):
        socket.create_connection(("example.com", 443), timeout=1)


def test_raw_socket_connect_is_blocked() -> None:
    s = socket.socket()
    try:
        with pytest.raises(NetworkBlocked):
            s.connect(("93.184.216.34", 80))
    finally:
        s.close()


def test_dns_lookup_is_blocked() -> None:
    with pytest.raises(NetworkBlocked):
        socket.getaddrinfo("example.com", 443)


@pytest.mark.parametrize("module", ["torch", "ocrmac", "silero_vad", "groq", "google.genai"])
def test_importing_a_model_or_vendor_library_is_blocked(module: str) -> None:
    with pytest.raises(ModelImportBlocked):
        importlib.import_module(module)
