"""Hashed ids: deterministic, salted, and reversible only via the local lookup (§7)."""

from __future__ import annotations

from pathlib import Path

from reelkb.eval.ids import (
    HID_LENGTH,
    hash_id,
    load_lookup,
    load_salt,
    resolve,
    save_lookup,
    update_lookup,
)


def test_load_salt_creates_a_32_byte_file_once(tmp_path: Path) -> None:
    salt = load_salt(tmp_path)
    assert len(salt) == 32
    assert (tmp_path / "eval_salt").read_bytes() == salt
    # Calling again must not rotate the salt.
    assert load_salt(tmp_path) == salt


def test_hash_id_is_deterministic_and_16_hex_chars(tmp_path: Path) -> None:
    salt = load_salt(tmp_path)
    hid = hash_id("FAKEmv001", salt)
    assert hid == hash_id("FAKEmv001", salt)
    assert len(hid) == HID_LENGTH
    assert all(c in "0123456789abcdef" for c in hid)


def test_hash_id_depends_on_the_salt(tmp_path: Path) -> None:
    salt_a = load_salt(tmp_path / "a")
    salt_b = load_salt(tmp_path / "b")
    assert salt_a != salt_b
    assert hash_id("FAKEmv001", salt_a) != hash_id("FAKEmv001", salt_b)


def test_different_items_hash_differently(tmp_path: Path) -> None:
    salt = load_salt(tmp_path)
    assert hash_id("FAKEmv001", salt) != hash_id("FAKEmv002", salt)


def test_load_lookup_empty_when_missing(tmp_path: Path) -> None:
    assert load_lookup(tmp_path) == {}


def test_save_and_load_lookup_round_trips(tmp_path: Path) -> None:
    save_lookup(tmp_path, {"abc123": "FAKEmv001"})
    assert load_lookup(tmp_path) == {"abc123": "FAKEmv001"}


def test_update_lookup_hashes_and_records_the_mapping(tmp_path: Path) -> None:
    hid = update_lookup(tmp_path, "FAKEmv001")
    salt = load_salt(tmp_path)
    assert hid == hash_id("FAKEmv001", salt)
    assert load_lookup(tmp_path) == {hid: "FAKEmv001"}


def test_update_lookup_is_idempotent(tmp_path: Path) -> None:
    hid_1 = update_lookup(tmp_path, "FAKEmv001")
    hid_2 = update_lookup(tmp_path, "FAKEmv001")
    assert hid_1 == hid_2
    assert load_lookup(tmp_path) == {hid_1: "FAKEmv001"}


def test_update_lookup_accumulates_multiple_items(tmp_path: Path) -> None:
    hid_1 = update_lookup(tmp_path, "FAKEmv001")
    hid_2 = update_lookup(tmp_path, "FAKEml001")
    assert load_lookup(tmp_path) == {hid_1: "FAKEmv001", hid_2: "FAKEml001"}


def test_resolve_returns_item_id_or_none(tmp_path: Path) -> None:
    hid = update_lookup(tmp_path, "FAKEmv001")
    lookup = load_lookup(tmp_path)
    assert resolve(hid, lookup) == "FAKEmv001"
    assert resolve("0000000000000000", lookup) is None
