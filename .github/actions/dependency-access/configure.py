import json
import os
from pathlib import Path
import re
import shlex
import shutil
import tempfile
import urllib.request


def setup(keys, root, known_hosts):
    if not isinstance(keys, dict) or not keys or len(keys) > 32:
        raise ValueError('Missing read-only dependency configuration')
    for repository, key in keys.items():
        if (not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository)
                or not isinstance(key, str)
                or not key.startswith('-----BEGIN OPENSSH PRIVATE KEY-----\n')
                or len(key) > 8192):
            raise ValueError('Invalid dependency access configuration')
    root.mkdir(mode=0o700)
    (root / 'known_hosts').write_text(known_hosts, encoding='utf-8')
    ssh_config = []
    git_config = []
    for index, (repository, key) in enumerate(sorted(keys.items())):
        identity = root / ('key-' + str(index))
        identity.write_text(key, encoding='utf-8')
        identity.chmod(0o600)
        alias = 'build-dependency-' + str(index)
        ssh_config.extend([
            'Host ' + alias, '  HostName github.com', '  User git',
            '  HostKeyAlias github.com', '  IdentitiesOnly yes',
            '  IdentityFile ' + json.dumps(str(identity)),
            '  UserKnownHostsFile ' + json.dumps(str(root / 'known_hosts')),
            '  StrictHostKeyChecking yes', '  BatchMode yes',
        ])
        prefix = 'ssh://git@' + alias + '/' + repository
        git_config.extend([
            '[url ' + json.dumps(prefix) + ']',
            '  insteadOf = https://github.com/' + repository,
            '  insteadOf = git@github.com:' + repository,
            '  insteadOf = ssh://git@github.com/' + repository,
        ])
    (root / 'ssh_config').write_text('\n'.join(ssh_config) + '\n', encoding='utf-8')
    (root / 'git_config').write_text('\n'.join(git_config) + '\n', encoding='utf-8')
    return {
        'DEPENDENCY_ACCESS_DIR': str(root),
        'GIT_CONFIG_GLOBAL': str(root / 'git_config'),
        'GIT_SSH_COMMAND': 'ssh -F ' + shlex.quote(str(root / 'ssh_config')),
        'CARGO_NET_GIT_FETCH_WITH_CLI': 'true',
    }


def cleanup(root, temporary):
    root = root.resolve()
    if root.parent != temporary.resolve() or not root.name.startswith('dependency-access-'):
        raise ValueError('Invalid dependency cleanup directory')
    shutil.rmtree(root, ignore_errors=False)


def main():
    temporary = Path(os.environ['RUNNER_TEMP'])
    if os.environ.get('DEPENDENCY_ACCESS_CLEANUP') == 'true':
        value = os.environ.get('DEPENDENCY_ACCESS_DIR')
        if value:
            cleanup(Path(value), temporary)
        return
    if os.environ.get('GITHUB_EVENT_NAME') in ('pull_request', 'pull_request_target'):
        raise SystemExit('Private dependencies require a trusted build event')
    keys = json.loads(os.environ.get('DEPENDENCY_SSH_KEYS', '') or '{}')
    for repository, key in keys.items():
        for value in (repository, *repository.split('/'), *key.splitlines()):
            print('::add-mask::' + value)
    request = urllib.request.Request('https://api.github.com/meta',
                                     headers={'User-Agent': 'build-dependency-access'})
    with urllib.request.urlopen(request, timeout=30) as response:
        public_keys = json.load(response)['ssh_keys']
    if not public_keys or any('\n' in value or '\r' in value for value in public_keys):
        raise ValueError('Invalid SSH host keys')
    hosts = ''.join('github.com ' + value + '\n' for value in public_keys)
    root = Path(tempfile.mkdtemp(prefix='dependency-access-', dir=temporary))
    root.rmdir()
    try:
        environment = setup(keys, root, hosts)
        with open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8') as output:
            for name, value in environment.items():
                output.write(name + '=' + value + '\n')
    except BaseException:
        if root.exists():
            cleanup(root, temporary)
        raise
    print('Read-only dependency access configured')


if __name__ == '__main__':
    main()
