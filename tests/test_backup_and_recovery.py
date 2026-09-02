import os
import pytest
from app.database.backup import backup_manager

def test_backup_creation_and_integrity():
    res = backup_manager.create_backup()
    assert res["success"] is True
    assert res["filename"].startswith("agency_backup_")
    assert res["filename"].endswith(".db.gz")
    assert res["integrity_verified"] is True
    assert os.path.exists(res["filepath"])

def test_list_backups():
    backups = backup_manager.list_backups()
    assert isinstance(backups, list)
    assert len(backups) >= 1
    assert "filename" in backups[0]
    assert "filepath" in backups[0]
    assert "size_bytes" in backups[0]

def test_restore_backup_verification():
    # Take a backup first
    backup_meta = backup_manager.create_backup()
    filepath = backup_meta["filepath"]

    # Verify restore executes cleanly and checks integrity
    restore_res = backup_manager.restore_backup(filepath)
    assert restore_res["success"] is True
    assert "restored_from" in restore_res
