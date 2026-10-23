"""Private R2 backup delivery using HTTPS and S3 Signature Version 4.

Only exact verified automatic archives are sent. No public URLs, bucket
administration, remote deletion, environment values or response bodies in logs.
"""
import datetime
import hashlib
import hmac
import os
import re
import threading
import time
import urllib.parse
import urllib.request


def signed_headers(method, host, path, payload, access_key, secret_key,
                   timestamp, *, region='auto', extra=None):
    digest = hashlib.sha256(payload).hexdigest()
    headers = {'host': host, 'x-amz-content-sha256': digest,
               'x-amz-date': timestamp, **(extra or {})}
    names = ';'.join(sorted(headers))
    canonical_headers = ''.join(k + ':' + headers[k].strip() + '\n'
                                for k in sorted(headers))
    canonical = '\n'.join((method, path, '', canonical_headers, names, digest))
    date = timestamp[:8]
    scope = date + '/' + region + '/s3/aws4_request'
    to_sign = '\n'.join(('AWS4-HMAC-SHA256', timestamp, scope,
                         hashlib.sha256(canonical.encode()).hexdigest()))
    key = ('AWS4' + secret_key).encode()
    for component in (date, region, 's3', 'aws4_request'):
        key = hmac.new(key, component.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    headers['authorization'] = ('AWS4-HMAC-SHA256 Credential=' + access_key +
        '/' + scope + ',SignedHeaders=' + names + ',Signature=' + signature)
    return headers


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class R2Backups:
    MAX_BYTES = 64 * 1024 * 1024

    def __init__(self, env=None):
        env = os.environ if env is None else env
        keys = ('R2_BUCKET', 'R2_ENDPOINT', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY')
        values = [env.get(key, '').strip() for key in keys]
        self.bucket, endpoint, self.access_key, self.secret_key = values
        self.configured = any(values)
        self.valid = False
        self.host = ''
        if all(values):
            try:
                url = urllib.parse.urlsplit(endpoint)
            except ValueError:
                url = urllib.parse.urlsplit('')
            self.host = url.netloc
            self.valid = bool(url.scheme == 'https' and url.path in ('', '/')
                and not url.query and not url.fragment
                and re.fullmatch(r'[0-9a-f]{32}(?:\.(?:eu|us|fedramp))?\.r2\.cloudflarestorage\.com', self.host)
                and re.fullmatch(r'[a-z0-9][a-z0-9-]{1,61}[a-z0-9]', self.bucket)
                and re.fullmatch(r'[A-Za-z0-9]+', self.access_key)
                and re.fullmatch(r'[A-Za-z0-9/+=]+', self.secret_key))
        self.lock = threading.Lock()
        self.cycle_lock = threading.Lock()
        self.last_key = None
        self.last_backup_time = None
        self.last_verified = None
        self.last_failure = None
        self.next_attempt = 0
        self.opener = urllib.request.build_opener(NoRedirect())

    def status(self, interval=86400):
        with self.lock:
            state = ('not_configured' if not self.configured else
                     'invalid_config' if not self.valid else
                     'failed' if self.last_failure else
                     'pending' if self.last_verified is None else
                     'stale' if time.time() - self.last_backup_time > interval + 300 else
                     'verified')
            return {'off_server_status': state,
                    'off_server_last_verified_at': self.last_verified,
                    'off_server_last_failure_at': self.last_failure}

    def request(self, method, key, payload=b''):
        path = '/' + self.bucket + '/' + urllib.parse.quote(key, safe='/~')
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        headers = signed_headers(method, self.host, path, payload,
                                 self.access_key, self.secret_key, stamp)
        if method == 'PUT':
            headers['Content-Type'] = 'application/zip'
        req = urllib.request.Request('https://' + self.host + path,
              data=payload if method == 'PUT' else None, headers=headers, method=method)
        with self.opener.open(req, timeout=20) as response:
            if not 200 <= response.status < 300:
                raise OSError('R2 request failed')
            data = response.read(self.MAX_BYTES + 1)
            if len(data) > self.MAX_BYTES:
                raise ValueError('Backup size limit exceeded')
            return data

    def upload_latest(self, manager):
        if (not self.valid or not manager.enabled or
                not self.cycle_lock.acquire(blocking=False)):
            return
        try:
            if time.monotonic() < self.next_attempt:
                return
            archive = None
            for candidate in manager.archives():
                try:
                    created = manager.verified_time(candidate)
                    if created > time.time() + 300:
                        continue
                except Exception:
                    continue
                archive = candidate
                break
            if archive is None:
                return
            if archive.stat().st_size > self.MAX_BYTES:
                raise ValueError('Backup size limit exceeded')
            payload = archive.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            key = 'automatic/' + digest + '/' + archive.name
            with self.lock:
                if self.last_key == key and not self.last_failure:
                    return
            # Network work is outside the snapshot gate. Upload retries reuse
            # the same content-addressed object rather than creating duplicates.
            self.request('PUT', key, payload)
            downloaded = self.request('GET', key)
            if not hmac.compare_digest(hashlib.sha256(downloaded).hexdigest(), digest):
                raise ValueError('R2 download verification failed')
            with self.lock:
                self.last_key = key
                self.last_backup_time = created
                self.last_verified = datetime.datetime.now(datetime.timezone.utc).isoformat()
                self.last_failure = None
            print('Automatic off-server backup verified: R2 upload and download SHA256 match.', flush=True)
        except Exception as error:
            with self.lock:
                self.last_failure = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self.next_attempt = time.monotonic() + 300
            # Do not log exception messages: HTTP errors may contain secrets.
            print('Automatic off-server backup failed:', type(error).__name__, flush=True)
        finally:
            self.cycle_lock.release()
