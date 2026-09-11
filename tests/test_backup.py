import sqlite3
import sys
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from scripts.backup import main


def test_backup_and_restore(client, auth, settings, tmp_path, monkeypatch):
    client.post(
        "/api/v1/links", headers=auth, json={"url": "https://example.com", "custom_alias": "backup"}
    )
    client.get("/backup", follow_redirects=False)
    destination = tmp_path / "backup.db"
    monkeypatch.setattr(sys, "argv", ["backup.py", settings.database_path, str(destination)])
    main()
    with TestClient(create_app(replace(settings, database_path=str(destination)))) as restored:
        stats = restored.get("/api/v1/links/backup/analytics", headers=auth).json()
        assert stats["total_clicks"] == 1
        assert restored.get("/backup", follow_redirects=False).status_code == 302
    with pytest.raises(FileExistsError):
        main()


def test_backup_missing_source_does_not_create_database(tmp_path, monkeypatch):
    source, destination = tmp_path / "missing.db", tmp_path / "backup.db"
    monkeypatch.setattr(sys, "argv", ["backup.py", str(source), str(destination)])
    with pytest.raises(sqlite3.OperationalError):
        main()
    assert not source.exists()
    assert not destination.exists()
