import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

import backup_state
from automatic_backups import AutomaticBackups, SnapshotGate
from r2_backups import NoRedirect, R2Backups, signed_headers


ENV = {'R2_BUCKET': 'make-the-cut-backups',
       'R2_ENDPOINT': 'https://' + 'a' * 32 + '.r2.cloudflarestorage.com',
       'R2_ACCESS_KEY_ID': 'exampleaccess', 'R2_SECRET_ACCESS_KEY': 'examplesecret'}


class MemoryR2:
    def __init__(self):
        self.objects = {}
        self.calls = []
        self.corrupt = False
        self.fail = False

    def open(self, req, timeout):
        self.calls.append(req)
        if self.fail:
            raise OSError('Do not log: examplesecret')
        if req.method == 'PUT':
            self.objects[req.full_url] = req.data
            body = b''
        else:
            body = b'wrong bytes' if self.corrupt else self.objects[req.full_url]
        response = io.BytesIO(body)
        response.status = 200
        return response


class R2BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = Path(self.temp.name)
        for name, kind in backup_state.JSON_FILES.items():
            (self.data / name).write_text(json.dumps(kind()))
        dbpath = self.data / backup_state.DATABASE
        with sqlite3.connect(dbpath) as db:
            db.execute('CREATE TABLE game_results (puzzle_id TEXT, points INTEGER, route_json TEXT, hints_used INTEGER)')
            db.execute("INSERT INTO game_results VALUES ('original',25,'[]',0)")
        self.gate = SnapshotGate()
        self.remote = R2Backups(ENV)
        self.memory = MemoryR2()
        self.remote.opener = self.memory
        self.manager = AutomaticBackups(self.data, dbpath, self.gate,
                                        enabled=True, remote=self.remote)
        self.archive = self.manager.maybe_backup()

    def tearDown(self):
        self.temp.cleanup()

    def test_aws_official_get_signature_vector(self):
        # Public dummy credentials and expected signature from the AWS guide.
        headers = signed_headers('GET', 'examplebucket.s3.amazonaws.com',
            '/test.txt', b'', 'AKIAIOSFODNN7EXAMPLE',
            'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY', '20130524T000000Z',
            region='us-east-1', extra={'range': 'bytes=0-9'})
        self.assertTrue(headers['authorization'].endswith(
            'Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41'))

    def test_aws_official_put_signature_vector(self):
        headers = signed_headers('PUT', 'examplebucket.s3.amazonaws.com',
            '/test%24file.text', b'Welcome to Amazon S3.', 'AKIAIOSFODNN7EXAMPLE',
            'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY', '20130524T000000Z',
            region='us-east-1', extra={'date': 'Fri, 24 May 2013 00:00:00 GMT',
                                     'x-amz-storage-class': 'REDUCED_REDUNDANCY'})
        self.assertTrue(headers['authorization'].endswith(
            'Signature=98ad721746da40c64f1a55b78f14c238d841ea1380cd77a1b5971af0ece108bd'))

    def test_upload_download_verify_and_no_repeat_until_new_backup(self):
        self.assertEqual(self.manager.status()['off_server_status'], 'pending')
        self.remote.upload_latest(self.manager)
        self.assertEqual(self.manager.status()['off_server_status'], 'verified')
        self.assertEqual([r.method for r in self.memory.calls], ['PUT', 'GET'])
        self.assertEqual(next(iter(self.memory.objects.values())), self.archive.read_bytes())
        for request in self.memory.calls:
            self.assertTrue(request.full_url.startswith(ENV['R2_ENDPOINT'] + '/make-the-cut-backups/automatic/'))
            self.assertIsNotNone(request.get_header('Authorization'))
        self.remote.upload_latest(self.manager)
        self.assertEqual(len(self.memory.calls), 2)
        self.manager.interval_seconds = 0
        self.manager.maybe_backup()
        self.remote.upload_latest(self.manager)
        self.assertEqual(len(self.memory.objects), 2)
        self.assertEqual(len(self.memory.calls), 4)

    def test_mismatch_never_claims_success_and_retry_recovers(self):
        original = self.archive.read_bytes()
        self.memory.corrupt = True
        self.remote.upload_latest(self.manager)
        self.assertEqual(self.remote.status()['off_server_status'], 'failed')
        self.assertIsNone(self.remote.status()['off_server_last_verified_at'])
        self.assertEqual(self.archive.read_bytes(), original)
        self.assertEqual(self.manager.status()['local_status'], 'verified')
        self.remote.upload_latest(self.manager)
        self.assertEqual(len(self.memory.calls), 2)  # Backoff, not a tight retry.
        self.remote.next_attempt = 0
        self.memory.corrupt = False
        self.remote.upload_latest(self.manager)
        self.assertEqual(self.remote.status()['off_server_status'], 'verified')
        self.assertEqual(len(self.memory.objects), 1)  # Same deterministic key.

    def test_upload_failure_log_and_status_do_not_disclose_credentials(self):
        self.memory.fail = True
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.remote.upload_latest(self.manager)
        status = json.dumps(self.manager.status())
        for secret in ('examplesecret', 'exampleaccess', ENV['R2_ENDPOINT']):
            self.assertNotIn(secret, out.getvalue() + status)
        self.assertEqual(self.remote.status()['off_server_status'], 'failed')

    def test_network_is_outside_gate_and_requests_remain_available(self):
        call = self.memory.open
        def checked(req, timeout):
            self.assertFalse(self.gate.snapshot_pending)
            with self.gate.operation():
                return call(req, timeout)
        self.memory.open = checked
        self.remote.upload_latest(self.manager)
        self.assertEqual(self.remote.status()['off_server_status'], 'verified')

    def test_restart_reverifies_same_object_and_old_backup_is_stale(self):
        self.remote.upload_latest(self.manager)
        restarted = R2Backups(ENV)
        restarted.opener = self.memory
        self.assertEqual(restarted.status()['off_server_status'], 'pending')
        restarted.upload_latest(self.manager)
        self.assertEqual(len(self.memory.objects), 1)
        self.assertEqual(len(self.memory.calls), 4)
        restarted.last_backup_time = time.time() - 87000
        self.assertEqual(restarted.status()['off_server_status'], 'stale')

    def test_invalid_or_incomplete_config_is_nonfatal_and_no_network(self):
        for endpoint in ('http://localhost', 'https://evil.example',
                         ENV['R2_ENDPOINT'] + '/bucket', 'https://[bad'):
            remote = R2Backups({**ENV, 'R2_ENDPOINT': endpoint})
            self.assertEqual(remote.status()['off_server_status'], 'invalid_config')
            with patch.object(remote, 'request') as request:
                remote.upload_latest(self.manager)
                request.assert_not_called()
        self.assertEqual(R2Backups({}).status()['off_server_status'], 'not_configured')
        self.assertEqual(R2Backups({'R2_BUCKET': ENV['R2_BUCKET']}).status()['off_server_status'], 'invalid_config')

    def test_corrupt_archive_not_uploaded_and_redirects_rejected(self):
        self.archive.write_bytes(b'corrupt')
        self.remote.upload_latest(self.manager)
        self.assertEqual(self.memory.calls, [])
        self.assertEqual(self.remote.status()['off_server_status'], 'pending')
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.example'))

    def test_size_cap_never_claims_verified(self):
        self.remote.MAX_BYTES = 1
        self.remote.upload_latest(self.manager)
        self.assertEqual(self.remote.status()['off_server_status'], 'failed')
        self.assertEqual(self.memory.calls, [])

    def test_worker_uploads_existing_snapshot_without_waiting_a_day(self):
        upload = self.remote.upload_latest
        def upload_and_stop(manager):
            upload(manager)
            manager.stop.set()
        with patch.object(self.remote, 'upload_latest', side_effect=upload_and_stop):
            worker = self.manager.start()
            worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(self.manager.status()['off_server_status'], 'verified')
        self.assertEqual(len(self.manager.archives()), 1)

    def test_download_response_is_bounded(self):
        self.memory.objects[ENV['R2_ENDPOINT'] + '/make-the-cut-backups/test.zip'] = b'12345'
        self.remote.MAX_BYTES = 4
        with self.assertRaises(ValueError):
            self.remote.request('GET', 'test.zip')


if __name__ == '__main__':
    unittest.main()
