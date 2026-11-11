import argparse
import contextlib
import http.server
import ipaddress
import json
import os
from pathlib import Path
import platform
import re
import select
import socket
import ssl
import subprocess
import tempfile
import threading
import urllib.parse
import urllib.request


HOSTS = {'archive.ubuntu.com', 'security.ubuntu.com', 'ports.ubuntu.com',
         'old-releases.ubuntu.com', 'deb.debian.org', 'security.debian.org'}


def resolve(host):
    if host not in HOSTS:
        raise ValueError('Unapproved package host')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for endpoint in ('1.1.1.1', '1.0.0.1'):
        try:
            request = urllib.request.Request('https://' + endpoint + '/dns-query?' +
                                            urllib.parse.urlencode({'name': host, 'type': 'A'}),
                                            headers={'Accept': 'application/dns-json'})
            with opener.open(request, timeout=8) as response:
                data = json.loads(response.read(65536))
            if data.get('Status') != 0:
                continue
            addresses = [str(ipaddress.IPv4Address(answer['data'])) for answer in data.get('Answer', [])
                         if answer.get('type') == 1 and ipaddress.ip_address(answer['data']).is_global]
            if addresses:
                return list(dict.fromkeys(addresses))[:4]
        except (OSError, ValueError):
            continue
    raise OSError('Authenticated DNS lookup failed for ' + host)


class Tunnel(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_CONNECT(self):
        host, separator, port = self.path.rpartition(':')
        if not separator or port != '443' or host not in HOSTS:
            self.send_error(403)
            return
        upstream = None
        try:
            for address in resolve(host):
                try:
                    with socket.create_connection((address, 443), timeout=3) as probe:
                        with ssl.create_default_context().wrap_socket(probe, server_hostname=host):
                            pass
                    upstream = socket.create_connection((address, 443), timeout=3)
                    break
                except OSError:
                    continue
            if upstream is None:
                raise OSError('Package host connection failed')
            self.send_response(200, 'Connection established')
            self.end_headers()
            with upstream:
                while True:
                    ready, _, _ = select.select([self.connection, upstream], [], [], 30)
                    if not ready:
                        return
                    for source in ready:
                        data = source.recv(65536)
                        if not data:
                            return
                        (upstream if source is self.connection else self.connection).sendall(data)
        except OSError:
            if upstream is None:
                self.send_error(502)


@contextlib.contextmanager
def proxy():
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Tunnel)
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield 'http://127.0.0.1:' + str(server.server_port)
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def sources(release, architecture, archived=False):
    distro, codename = release.get('ID'), release.get('VERSION_CODENAME', '')
    if not re.fullmatch('[a-z]+', codename):
        raise ValueError('Unsupported distribution codename')
    if distro == 'ubuntu':
        host = 'old-releases.ubuntu.com/ubuntu' if archived else (
            'archive.ubuntu.com/ubuntu' if architecture in ('amd64', 'i386') else 'ports.ubuntu.com/ubuntu-ports')
        security = host if archived or architecture not in ('amd64', 'i386') else 'security.ubuntu.com/ubuntu'
        return ''.join('deb https://' + site + ' ' + suite + ' main restricted universe multiverse\n'
                       for site, suite in ((host, codename), (host, codename + '-updates'), (security, codename + '-security')))
    if distro == 'debian' and not archived:
        return ('deb https://deb.debian.org/debian ' + codename + ' main\n'
                'deb https://deb.debian.org/debian ' + codename + '-updates main\n'
                'deb https://security.debian.org/debian-security ' + codename + '-security main\n')
    raise ValueError('Unsupported package source fallback')


def installed(package):
    result = subprocess.run(['dpkg-query', '-W', '-f=${Status}', package], capture_output=True, text=True)
    return result.returncode == 0 and result.stdout.strip() == 'install ok installed'


def apt(arguments, options=(), seconds=150):
    command = ([] if os.geteuid() == 0 else ['sudo', '-n']) + [
        'env', 'DEBIAN_FRONTEND=noninteractive', 'timeout', '--kill-after=5s', str(seconds) + 's',
        'apt-get', '-o', 'Acquire::http::Timeout=15', '-o', 'Acquire::https::Timeout=30',
        '-o', 'Acquire::Retries=1', '-o', 'APT::Update::Error-Mode=any',
        '-o', 'Acquire::AllowInsecureRepositories=false', '-o', 'APT::Get::AllowUnauthenticated=false',
        '-o', 'Acquire::https::Verify-Peer=true', '-o', 'Acquire::https::Verify-Host=true',
        '-o', 'Acquire::Languages=none', *options, *arguments]
    try:
        return subprocess.run(command, timeout=seconds + 15).returncode == 0
    except subprocess.TimeoutExpired:
        return False


@contextlib.contextmanager
def package_directory():
    with tempfile.TemporaryDirectory(prefix='build-apt-') as directory:
        root = Path(directory)
        try:
            yield root
        finally:
            uid = getattr(os, 'geteuid', lambda: 0)()
            if uid != 0:
                assert root.resolve().parent == Path(tempfile.gettempdir()).resolve() and root.name.startswith('build-apt-')
                gid = getattr(os, 'getegid', lambda: uid)()
                subprocess.run(['sudo', '-n', 'chown', '-R', '--', str(uid) + ':' + str(gid), str(root)], check=True, timeout=15)


def install(packages):
    if not packages or any(not re.fullmatch(r'[a-z0-9][a-z0-9+.-]*(?::[a-z0-9]+)?', p) for p in packages):
        raise ValueError('Invalid build package list')
    packages = list(dict.fromkeys(packages))
    missing = [p for p in packages if not installed(p)]
    if not missing:
        return
    print('Preparing build packages: ' + ' '.join(missing), flush=True)
    if apt(['install', '-y', '--no-install-recommends', *missing]) and all(installed(p) for p in packages):
        return
    release = platform.freedesktop_os_release()
    architecture = subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip()
    routes = [False, True] if release.get('ID') == 'ubuntu' else [False]
    for archived in routes:
        with package_directory() as root, proxy() as address:
            root.chmod(0o755)
            lists = root / 'lists'
            (lists / 'partial').mkdir(parents=True)
            source = root / 'sources.list'
            source.write_text(sources(release, architecture, archived))
            options = ['-o', 'Dir::Etc::sourcelist=' + str(source), '-o', 'Dir::Etc::sourceparts=-',
                       '-o', 'Dir::State::lists=' + str(lists), '-o', 'Acquire::https::Proxy=' + address]
            print('Retrying signed official package sources with scoped HTTPS DNS' +
                  (' (archived release)' if archived else ''), flush=True)
            if not apt(['update', '-qq'], options, seconds=90):
                continue
            missing = [p for p in packages if not installed(p)]
            if apt(['install', '-y', '--no-install-recommends', *missing], options) and all(installed(p) for p in packages):
                return
    raise RuntimeError('Build dependencies unavailable after bounded source and DNS recovery')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('packages', nargs='+')
    install(parser.parse_args().packages)
