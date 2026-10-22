"""Opt-in checkpoint before server.py loads or changes persistent state.

Use only with a single instance whose previous process has fully exited, as
Render enforces when deploying a service with an attached persistent disk.
"""
import os
from pathlib import Path
import re

from backup_state import create_backup, read_backup


def backup_before_start(environ=None):
    env = os.environ if environ is None else environ
    name = env.get('GAME_STARTUP_BACKUP_NAME', '').strip()
    if not name:
        return None
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', name):
        raise ValueError('GAME_STARTUP_BACKUP_NAME must be a simple checkpoint name')
    if not env.get('GAME_DATA_DIR', '').strip():
        raise ValueError('Startup backup requires an explicit GAME_DATA_DIR')
    data = Path(env['GAME_DATA_DIR']).expanduser().resolve(strict=True)
    folder = data / 'backups'
    if folder.is_symlink():
        raise ValueError('Startup backup directory must not be a symbolic link')
    folder.mkdir(mode=0o700, exist_ok=True)
    archive = folder / (name + '.zip')
    if archive.is_symlink():
        raise ValueError('Startup backup archive must not be a symbolic link')
    if archive.exists():
        # A named checkpoint is immutable. A retry validates the original;
        # use a new name when a newer backup is wanted.
        read_backup(archive)
    else:
        create_backup(data, archive, server_stopped=True,
                      results_db=env.get('RESULTS_DB') or None)
    return archive
