import json
import os
from datetime import datetime, timedelta, timezone
import re
import urllib.error
import urllib.request


class GitHub:
    def __init__(self, environment):
        repository = environment.get('GITHUB_REPOSITORY', '')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('Invalid cleanup repository')
        self.root = '/repos/' + repository
        self.token = environment['GITHUB_TOKEN']
        metadata = self.request(self.root)
        if metadata.get('private') is not False or str(metadata['id']) != environment['GITHUB_REPOSITORY_ID']:
            raise ValueError('Cleanup requires the current public repository')

    def request(self, path, method='GET'):
        if path != self.root and not path.startswith(self.root + '/'):
            raise ValueError('Cleanup request outside the current repository')
        request = urllib.request.Request('https://api.github.com' + path, method=method,
                    headers={'Authorization': 'Bearer ' + self.token,
                             'Accept': 'application/vnd.github+json',
                             'X-GitHub-Api-Version': '2022-11-28',
                             'User-Agent': 'actions-retention-cleanup'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise RuntimeError('Cleanup API failed: HTTP ' + str(error.code)) from None
            return None

    def items(self, path, key):
        page = 1
        while True:
            data = self.request(path + '?per_page=100&page=' + str(page))
            if data is None:
                raise ValueError('Cleanup inventory unavailable')
            rows = data[key]
            yield from rows
            if len(rows) < 100:
                return
            page += 1


def old(item, cutoff):
    dates = [item.get('created_at'), item.get('updated_at')]
    if not all(dates):
        return False
    return all(datetime.fromisoformat(value.replace('Z', '+00:00')) < cutoff for value in dates)


def cleanup(environment, client=None, current=None):
    days = environment.get('CLEANUP_RETENTION_DAYS', '3')
    keep = environment.get('CLEANUP_KEEP_RUN_IDS', '')
    if days not in ('0', '3') or (keep and not re.fullmatch(r'[1-9][0-9]*(?:,[1-9][0-9]*)*', keep)):
        raise ValueError('Invalid retention options')
    client = client or GitHub(environment)
    cutoff = (current or datetime.now(timezone.utc)) - timedelta(days=int(days))
    own = int(environment['GITHUB_RUN_ID'])
    protected = {own, *(int(value) for value in keep.split(',') if value)}
    dry = environment.get('CLEANUP_DRY_RUN', 'false') == 'true'
    runs = list(client.items(client.root + '/actions/runs', 'workflow_runs'))
    artifacts = list(client.items(client.root + '/actions/artifacts', 'artifacts'))
    counts = {'runs': 0, 'artifacts': 0, 'dry_run': dry}
    for artifact in artifacts:
        if not old(artifact, cutoff):
            continue
        run_id = (artifact.get('workflow_run') or {}).get('id')
        if run_id is not None:
            if int(run_id) in protected:
                continue
            run = client.request(client.root + '/actions/runs/' + str(int(run_id)))
            if run is not None and (run.get('status') != 'completed' or not old(run, cutoff)):
                continue
        if not dry:
            client.request(client.root + '/actions/artifacts/' + str(int(artifact['id'])), 'DELETE')
        counts['artifacts'] += 1
    for previous in runs:
        identity = int(previous['id'])
        if identity in protected or previous.get('status') != 'completed' or not old(previous, cutoff):
            continue
        path = client.root + '/actions/runs/' + str(identity)
        run = client.request(path)
        if run is None or run.get('status') != 'completed' or not old(run, cutoff):
            continue
        if not dry:
            client.request(path, 'DELETE')
        counts['runs'] += 1
    print(json.dumps(counts, sort_keys=True))
    return counts


if __name__ == '__main__':
    cleanup(os.environ)
