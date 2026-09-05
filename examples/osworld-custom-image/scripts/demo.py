"""Small SDK example: OCI -> custom Tool -> desktop -> optional customization."""
from __future__ import annotations

import argparse
import io
import json
import os
import re
from pathlib import Path
import shlex
import subprocess
import time
import uuid
from urllib.parse import urlencode

from dotenv import load_dotenv
from PIL import Image, ImageStat
import requests
import websocket
from tencentcloud.ags.v20250920 import ags_client
from tencentcloud.common.credential import Credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile

ROOT = Path(__file__).resolve().parents[1]


def tool_config(image: str) -> dict:
    # Official ags-image bases are public and can be read across accounts.
    # `custom` is the API's anonymous registry mode, including public CCR/TCR.
    registry_type = ('custom' if '/ags-image/' in image else
                     'personal' if '.ccs.tencentyun.com/' in image else 'enterprise')
    digest = None
    if '@' in image:
        reference, digest = image.rsplit('@', 1)
        prefix, name = reference.rsplit('/', 1)
        if registry_type == 'personal':
            if ':' not in name:
                raise ValueError('Personal CCR needs an immutable tag; supply tag@sha256:digest')
            image = reference
        else:
            image = prefix + '/' + name.split(':', 1)[0] + '@' + digest
    result = {
        'Image': image,
        'ImageRegistryType': registry_type,
        'Command': ['/sbin/init'],
        'Ports': [{'Name': name, 'Port': port, 'Protocol': 'TCP'} for name, port in
                  [('osworld', 5000), ('novnc', 5910), ('vlc', 8080), ('cdp', 9222)]],
        'Resources': {'CPU': '8', 'Memory': '16Gi', 'Storage': '20Gi'},
        'Probe': {'HttpGet': {'Path': '/platform', 'Port': 5000, 'Scheme': 'HTTP'},
                  'ReadyTimeoutMs': 30000, 'ProbeTimeoutMs': 3000,
                  'ProbePeriodMs': 1000, 'SuccessThreshold': 1, 'FailureThreshold': 100},
    }
    return result


def novnc_url(host: str, token: str) -> str:
    # Authenticate both the document request and the subsequent WebSocket.
    ws_path = 'websockify' + ('?' + urlencode({'token': token}) if token else '')
    params = {'autoconnect': 'true', 'resize': 'scale', 'path': ws_path}
    if token:
        params['access_token'] = token
    return f'https://{host}/vnc.html?' + urlencode(params)


def snapshot_status(tool: dict) -> str | None:
    if tool.get('SnapshotStatus'):
        return tool['SnapshotStatus']
    # The public CAPI response currently carries this in StatusReason.
    match = re.search(r'\bSnapshotStatus=([A-Z_]+)\b', tool.get('StatusReason') or '')
    return match.group(1) if match else None


class Demo:
    def __init__(self, state_dir: Path | None = None, region: str | None = None):
        self.region = region or os.getenv('AGS_REGION', 'ap-guangzhou')
        self.path = (state_dir or ROOT / '.state' / self.region) / 'state.json'
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {}
        http = HttpProfile(endpoint='ags.tencentcloudapi.com', reqTimeout=180)
        profile = ClientProfile(httpProfile=http)
        secret_id = os.getenv('TENCENTCLOUD_SECRET_ID')
        secret_key = os.getenv('TENCENTCLOUD_SECRET_KEY')
        if not secret_id or not secret_key:
            raise ValueError('Set TENCENTCLOUD_SECRET_ID and TENCENTCLOUD_SECRET_KEY')
        # The SDK EnvironmentVariableCredential omits STS session tokens.
        credential = Credential(secret_id, secret_key, os.getenv('TENCENTCLOUD_TOKEN'))
        self.client = ags_client.AgsClient(credential, self.region, profile)

    def api(self, action: str, **params) -> dict:
        # call_json preserves recently added API fields even when typed models lag.
        return self.client.call_json(action, params)['Response']

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, indent=2) + '\n')

    def tool(self) -> dict:
        rows = self.api('DescribeSandboxToolList', ToolIds=[self.state['tool_id']], Limit=1).get('SandboxToolSet', [])
        if not rows:
            raise RuntimeError('Tool is missing. Run make clean before starting again.')
        tool = rows[0]
        tool['SnapshotStatus'] = snapshot_status(tool)
        return tool

    def create(self, image: str, *, cold: bool = False):
        if self.state.get('image') and self.state['image'] != image:
            raise RuntimeError('Existing state uses another image; run make clean first.')
        if not self.state.get('tool_id'):
            cfg = tool_config(image)
            name = self.state.setdefault('tool_name', 'osworld-' + ('cold-' if cold else 'auto-snapshot-') + uuid.uuid4().hex[:12])
            self.state.setdefault('create_token', uuid.uuid4().hex)
            self.state['image'] = image
            self.save()
            payload = dict(ToolName=name, ToolType='custom', Description='OSWorld custom OCI example',
                           DefaultTimeout='1h', NetworkConfiguration={'NetworkMode': 'PUBLIC'},
                           ClientToken=self.state['create_token'], CustomConfiguration=cfg)
            if os.getenv('ROLE_ARN'):
                payload['RoleArn'] = os.environ['ROLE_ARN']
            response = self.api('CreateSandboxTool', **payload)
            self.state.update(tool_id=response['ToolId'], tool_name=name, image=image)
            self.state.pop('create_token', None)
            self.save()  # Record ownership before any polling/network operation.
        deadline = time.monotonic() + 3600
        while time.monotonic() < deadline:
            tool = self.tool()
            print(f"Tool {self.state['tool_id']}: {tool.get('Status')}, snapshot={tool.get('SnapshotStatus', 'not reported')}", flush=True)
            if tool.get('Status') == 'ACTIVE':
                # CreateTool pins the resolved manifest. Verify that persisted
                # digest before starting; do not require a separate preheat API.
                if '@' in image:
                    expected = image.rsplit('@', 1)[1]
                    actual = (tool.get('CustomConfiguration') or {}).get('ImageDigest')
                    if actual != expected:
                        raise RuntimeError('Tool manifest digest is missing or differs from the expected digest; instance not started')
                return
            if tool.get('Status') in {'FAILED', 'ERROR', 'DELETED', 'INACTIVE'}:
                raise RuntimeError('Tool preparation failed: ' + str(tool.get('StatusReason', '')))
            time.sleep(10)
        raise TimeoutError('Tool preparation timed out; state retained for inspection/cleanup.')

    def start(self):
        if self.state.get('instance_id'):
            rows = self.api('DescribeSandboxInstanceList', InstanceIds=[self.state['instance_id']], Limit=1).get('InstanceSet', [])
            if rows and rows[0].get('Status') == 'RUNNING':
                return
            if rows and rows[0].get('Status') not in {'STOPPED', 'TERMINATED', 'DELETED', 'EXPIRED'}:
                raise RuntimeError('Existing instance is not running; inspect or clean it before starting another.')
            self.state.pop('instance_id', None)
            self.state.pop('start_token', None)
            self.save()
        mode = os.getenv('AUTH_MODE', 'token').upper()
        if mode not in {'TOKEN', 'NONE'}:
            raise ValueError('AUTH_MODE must be token or none')
        started = time.monotonic()
        # Persist the idempotency key so an ambiguous timeout can be retried safely.
        self.state.setdefault('start_token', uuid.uuid4().hex)
        self.save()
        try:
            r = self.api('StartSandboxInstance', ToolId=self.state['tool_id'], Timeout='1h',
                         AuthMode=mode, ClientToken=self.state['start_token'])
        except TencentCloudSDKException as exc:
            self.state['last_start_error'] = {'code': exc.get_code(), 'request_id': exc.get_request_id()}
            self.save()
            raise
        self.state.pop('last_start_error', None)
        self.state.update(instance_id=r['Instance']['InstanceId'], auth_mode=mode,
                          start_seconds=round(time.monotonic() - started, 3))
        self.save()
        print(f"Instance {self.state['instance_id']} created in {self.state['start_seconds']}s", flush=True)

    def token(self) -> str:
        if self.state.get('auth_mode') == 'NONE':
            return ''
        return self.api('AcquireSandboxInstanceToken', InstanceId=self.state['instance_id'])['Token']

    def host(self, port: int) -> str:
        return f"{port}-{self.state['instance_id']}.{self.region}.tencentags.com"

    def request(self, path: str, *, port: int = 5000, method='GET', **kwargs):
        token = self.token()
        headers = {'X-Access-Token': token} if token else {}
        r = requests.request(method, f'https://{self.host(port)}{path}', headers=headers,
                             timeout=kwargs.pop('timeout', 60), **kwargs)
        # Do not include request bodies or credential-bearing URLs in errors.
        if not r.ok:
            raise RuntimeError(f'OSWorld {method} :{port}{path}: HTTP {r.status_code}')
        return r

    def execute(self, command: list[str]) -> dict:
        result = self.request('/execute', method='POST', json={'command': command, 'shell': False}).json()
        if result.get('returncode') != 0:
            raise RuntimeError('OSWorld command failed (output omitted; may contain credentials)')
        return result

    def validate(self) -> dict:
        deadline = time.monotonic() + 180
        while True:
            try:
                platform = self.request('/platform', timeout=10).text
                png = self.request('/screenshot', timeout=20).content
                img = Image.open(io.BytesIO(png)).convert('RGB')
                spread = ImageStat.Stat(img).stddev
                if 'Linux' not in platform or img.size != (1920, 1080) or max(spread) < 5:
                    raise RuntimeError('Desktop is not ready')
                break
            except (RuntimeError, requests.RequestException, OSError):
                if time.monotonic() >= deadline:
                    raise RuntimeError('Desktop did not become ready within 180s') from None
                time.sleep(3)
        # The desktop/API and noVNC services start independently. Optional
        # smoke checks allow both to become ready within the same deadline.
        while True:
            try:
                self.request('/vnc.html', port=5910, timeout=10)
                token = self.token()
                ws_path = '/websockify' + ('?' + urlencode({'token': token}) if token else '')
                ws = websocket.create_connection('wss://' + self.host(5910) + ws_path, timeout=10)
                try:
                    banner = ws.recv()
                    if not (banner if isinstance(banner, bytes) else banner.encode()).startswith(b'RFB '):
                        raise RuntimeError('noVNC WebSocket did not return a VNC handshake')
                finally:
                    ws.close()
                break
            except (RuntimeError, requests.RequestException, websocket.WebSocketException, OSError):
                if time.monotonic() >= deadline:
                    raise RuntimeError('noVNC did not become ready within the desktop validation deadline') from None
                time.sleep(3)
        result = self.execute(['sh', '-c', 'set -eu; test "$(cat /proc/1/comm)" = systemd; test "$(stat -f -c %T /dev/shm)" = tmpfs; bytes=$(df -B1 --output=size /dev/shm | tail -n 1); test "$bytes" -ge 4294967296; printf "osworld-custom-ok %s" "$bytes"'])
        if 'osworld-custom-ok' not in result.get('output', ''):
            raise RuntimeError('Runtime check failed')
        report = {'platform': platform.strip(), 'screenshot_size': list(img.size), 'rgb_stddev': spread,
                  'pid1': 'systemd', 'shm_min_bytes': 4294967296,
                  'shm_size_bytes': int(result['output'].split()[-1]), 'shm_fs_type': 'tmpfs',
                  'novnc_websocket': 'RFB handshake passed',
                  'start_seconds': self.state.get('start_seconds'), 'tool_id': self.state['tool_id'],
                  'image': self.state.get('image'),
                  'instance_id': self.state['instance_id'], 'region': self.region,
                  'snapshot_status': self.tool().get('SnapshotStatus')}
        self.path.with_name('report.json').write_text(json.dumps(report, indent=2))
        self.path.with_name('screenshot.png').write_bytes(png)
        print(json.dumps(report, indent=2), flush=True)
        return report

    def preview(self):
        print('noVNC URL (contains an instance credential; do not share publicly):\n' + novnc_url(self.host(5910), self.token()))
        print('The interactive instance remains available for up to one hour. Run make clean when finished.')

    def claude(self):
        # Keep upload inside a private directory from its creation, not only chmod
        # after upload. The server executes as desktop user `user`.
        key = os.getenv('ANTHROPIC_API_KEY')
        if not key:
            raise ValueError('ANTHROPIC_API_KEY is required for make claude')
        self.execute(['sh', '-c', 'claude --version; install -d -m 0700 /run/user/1000/ags-claude'])
        env = {'ANTHROPIC_API_KEY': key, 'DISABLE_AUTOUPDATER': '1'}
        if os.getenv('ANTHROPIC_BASE_URL'):
            env['ANTHROPIC_BASE_URL'] = os.environ['ANTHROPIC_BASE_URL']
        if os.getenv('ANTHROPIC_MODEL'):
            env['ANTHROPIC_MODEL'] = os.environ['ANTHROPIC_MODEL']
        for name, content in [('credentials.json', json.dumps(env)), ('launch.py',
            'import json,os\nfrom pathlib import Path\n'
            'p=Path("/run/user/1000/ags-claude/credentials.json")\n'
            'env=dict(os.environ,**json.loads(p.read_text()))\n'
            'cfg=Path.home()/".claude.json"\n'
            'd=json.loads(cfg.read_text()) if cfg.exists() else {}\n'
            'd["hasCompletedOnboarding"]=True\ncfg.write_text(json.dumps(d))\n'
            'workspace=Path.home()/"claude-workspace"\nworkspace.mkdir(exist_ok=True)\nos.chdir(workspace)\n'
            'os.execve("/usr/local/bin/claude",["claude"],env)\n')]:
            self.request('/setup/upload', method='POST', data={'file_path': '/run/user/1000/ags-claude/' + name},
                         files={'file_data': (name, content.encode(), 'application/octet-stream')})
        self.execute(['chmod', '0600', '/run/user/1000/ags-claude/credentials.json', '/run/user/1000/ags-claude/launch.py'])
        self.request('/setup/launch', method='POST', json={'command': ['gnome-terminal', '--', 'python3', '/run/user/1000/ags-claude/launch.py'], 'shell': False})
        print('Claude Code launched in the desktop terminal. No model request is sent automatically.')

    def stop(self):
        if self.state.get('instance_id'):
            try:
                self.api('StopSandboxInstance', InstanceId=self.state['instance_id'])
            except TencentCloudSDKException as exc:
                if not (exc.get_code() or '').startswith('ResourceNotFound'):
                    raise
                rows = self.api('DescribeSandboxInstanceList', InstanceIds=[self.state['instance_id']], Limit=1).get('InstanceSet', [])
                if rows:
                    raise
            self.state.pop('instance_id', None)
            self.state.pop('start_token', None)
            self.save()

    def clean(self):
        self.stop()
        if self.state.get('create_token') and not self.state.get('tool_id'):
            raise RuntimeError('Tool creation result is unknown; retry the same command to recover its ID before cleanup.')
        if self.state.get('start_token') and not self.state.get('instance_id'):
            raise RuntimeError('Start result is unknown; state retained. Retry the same command or inspect instances before deleting the Tool.')
        if self.state.get('tool_id'):
            self.api('DeleteSandboxTool', ToolId=self.state['tool_id'])
            self.state = {}
            self.save()


def main():
    load_dotenv(ROOT / '.env', override=False)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['quickstart', 'custom', 'build', 'push', 'claude', 'snapshot', 'smoke', 'clean'])
    p.add_argument('--state-dir', type=Path)
    p.add_argument('--cold', action='store_true', help='Release validation only: disable the name trigger')
    args = p.parse_args()
    base = os.getenv('OSWORLD_BASE_IMAGE', '')
    custom = os.getenv('CUSTOM_IMAGE', '')
    if args.action in {'build', 'push'}:
        if not base or not custom:
            p.error('Set OSWORLD_BASE_IMAGE and CUSTOM_IMAGE in .env')
        if '/ags-image/' in custom:
            p.error('CUSTOM_IMAGE must point to your own repository')
        cmd = ['docker', 'push', custom] if args.action == 'push' else [
            'docker', 'build', '--platform=linux/amd64', '--build-arg', 'OSWORLD_BASE_IMAGE=' + base,
            '-f', str(ROOT / 'Dockerfile.claude-code'), '-t', custom, str(ROOT)]
        subprocess.run(cmd, check=True)
        return
    state_dir = args.state_dir
    if args.action in {'custom', 'claude'} and state_dir is None:
        state_dir = ROOT / '.state' / os.getenv('AGS_REGION', 'ap-guangzhou') / 'claude'
    if args.action == 'smoke' and state_dir is None:
        state_dir = ROOT / '.state' / ('smoke-' + uuid.uuid4().hex[:12])
    d = Demo(state_dir)
    if args.action == 'clean':
        d.clean()
        # Also clean the companion Claude Code example when using default state.
        if args.state_dir is None:
            Demo(ROOT / '.state' / d.region / 'claude').clean()
    elif args.action == 'snapshot':
        t = d.tool()
        print(json.dumps({k: t.get(k) for k in ['ToolId', 'Status', 'SnapshotStatus', 'StatusReason']}, indent=2))
    elif args.action == 'claude':
        d.claude()
        d.preview()
    else:
        image = custom if args.action == 'custom' else base
        if not image:
            p.error('Set OSWORLD_BASE_IMAGE or CUSTOM_IMAGE in .env')
        try:
            d.create(image, cold=args.cold)
            # Do not wait for snapshot READY. AGS may cold-start while making it.
            d.start()
            if args.action == 'smoke':
                d.validate()
            else:
                d.preview()
        finally:
            if args.action == 'smoke':
                d.stop()  # Retain the Tool; it may finish its automatic snapshot.


if __name__ == '__main__':
    main()
