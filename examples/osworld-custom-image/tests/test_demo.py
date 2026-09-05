import importlib.util
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('demo', Path(__file__).parents[1] / 'scripts/demo.py')
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def test_sts_session_token_is_passed_to_sdk(tmp_path, monkeypatch):
    monkeypatch.setenv('TENCENTCLOUD_SECRET_ID', 'test-id')
    monkeypatch.setenv('TENCENTCLOUD_SECRET_KEY', 'test-key')
    monkeypatch.setenv('TENCENTCLOUD_TOKEN', 'test-session-token')
    captured = []
    monkeypatch.setattr(demo.ags_client, 'AgsClient', lambda cred, *args: captured.append(cred))
    demo.Demo(tmp_path, region='ap-guangzhou')
    assert captured[0].token == 'test-session-token'


def test_preview_authenticates_page_and_websocket_without_mangling_token():
    token = 'a+b/c?d=e&f%20'
    url = demo.novnc_url('5910-example.ap-guangzhou.tencentags.com', token)
    query = parse_qs(urlsplit(url).query)
    assert query['access_token'] == [token]
    assert parse_qs(urlsplit(query['path'][0]).query)['token'] == [token]


def test_unauthenticated_preview_has_no_credential_parameters():
    q = parse_qs(urlsplit(demo.novnc_url('example.test', '')).query)
    assert q['path'] == ['websockify']
    assert 'access_token' not in q


def test_tool_does_not_bake_application_secrets(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'must-not-be-baked')
    cfg = demo.tool_config('ccr.ccs.tencentyun.com/example/image:v1')
    assert 'must-not-be-baked' not in str(cfg)
    assert 'Env' not in cfg
    assert cfg['Command'] == ['/sbin/init']


def test_snapshot_status_supports_public_api_status_reason():
    assert demo.snapshot_status({'Status': 'ACTIVE', 'StatusReason': 'SnapshotStatus=BUILDING'}) == 'BUILDING'
    assert demo.snapshot_status({'SnapshotStatus': 'READY', 'StatusReason': 'old'}) == 'READY'
    assert demo.snapshot_status({'Status': 'ACTIVE', 'StatusReason': ''}) is None


def test_tool_digest_reference_is_compatible_with_snapshot_converter():
    digest = 'sha256:' + 'a' * 64
    cfg = demo.tool_config('registry.example:5000/team/image:v1@' + digest)
    assert cfg['Image'] == 'registry.example:5000/team/image@' + digest
    personal = demo.tool_config('ccr.ccs.tencentyun.com/team/image:v1@' + digest)
    assert personal['Image'] == 'ccr.ccs.tencentyun.com/team/image:v1'
    assert 'ImageDigest' not in personal


def test_failed_guest_command_is_not_reported_as_success():
    d = object.__new__(demo.Demo)
    class Response:
        def json(self):
            return {'returncode': 1, 'output': 'secret-value'}
    d.request = lambda *a, **kw: Response()
    with pytest.raises(RuntimeError) as error:
        d.execute(['false'])
    assert 'secret-value' not in str(error.value)


@pytest.mark.parametrize('actual', ['sha256:' + 'a' * 64, 'sha256:' + 'b' * 64, None])
def test_pinned_ccr_uses_direct_creation_and_verifies_saved_digest(tmp_path, actual):
    d = object.__new__(demo.Demo)
    d.state = {}
    d.path = tmp_path / 'state.json'
    calls = []
    def api(action, **params):
        calls.append(action)
        assert action == 'CreateSandboxTool'
        assert params['CustomConfiguration']['Image'] == 'ccr.ccs.tencentyun.com/team/image:v1'
        return {'ToolId': 'owned-tool'}
    d.api = api
    d.tool = lambda: {'Status': 'ACTIVE', 'CustomConfiguration': {'ImageDigest': actual}}
    image = 'ccr.ccs.tencentyun.com/team/image:v1@sha256:' + 'a' * 64
    if actual == 'sha256:' + 'a' * 64:
        d.create(image)
    else:
        with pytest.raises(RuntimeError, match='digest'):
            d.create(image)
    assert calls == ['CreateSandboxTool']
    assert d.state['tool_id'] == 'owned-tool'


def test_smoke_waits_for_novnc_without_restarting_instance(tmp_path, monkeypatch):
    d = object.__new__(demo.Demo)
    d.path = tmp_path / 'state.json'
    d.region = 'ap-shanghai'
    d.state = {'tool_id': 'tool', 'instance_id': 'instance', 'start_seconds': 0.5}
    calls = []
    def request(path, **kwargs):
        calls.append(path)
        if path == '/vnc.html' and calls.count(path) == 1:
            raise RuntimeError('OSWorld GET :5910/vnc.html: HTTP 502')
        return SimpleNamespace(text='Linux', content=b'png-fixture')
    d.request = request
    d.token = lambda: 'test-token'
    d.host = lambda port: 'localhost'
    d.execute = lambda cmd: {'output': 'osworld-custom-ok 4294967296'}
    d.tool = lambda: {'SnapshotStatus': 'READY'}
    monkeypatch.setattr(demo.Image, 'open', lambda data: SimpleNamespace(convert=lambda mode: SimpleNamespace(size=(1920,1080))))
    monkeypatch.setattr(demo.ImageStat, 'Stat', lambda img: SimpleNamespace(stddev=[20,20,20]))
    monkeypatch.setattr(demo.websocket, 'create_connection', lambda *a, **kw: SimpleNamespace(recv=lambda: b'RFB 003.008\n', close=lambda: None))
    monkeypatch.setattr(demo.time, 'sleep', lambda n: None)
    report = d.validate()
    assert calls.count('/vnc.html') == 2
    assert report['start_seconds'] == 0.5


def test_cleanup_preserves_ownership_if_stop_fails(tmp_path):
    d = object.__new__(demo.Demo)
    d.state = {'tool_id': 'owned-tool', 'instance_id': 'owned-instance'}
    d.path = tmp_path / 'state.json'
    calls = []
    def api(action, **params):
        calls.append(action)
        raise RuntimeError('temporary failure')
    d.api = api
    with pytest.raises(RuntimeError):
        d.clean()
    assert calls == ['StopSandboxInstance']
    assert d.state['instance_id'] == 'owned-instance'


def test_cleanup_does_not_delete_tool_after_ambiguous_start(tmp_path):
    d = object.__new__(demo.Demo)
    d.state = {'tool_id': 'owned-tool', 'start_token': 'retry-key'}
    d.path = tmp_path / 'state.json'
    d.api = lambda *a, **kw: pytest.fail('No deletion while start result is unknown')
    with pytest.raises(RuntimeError, match='unknown'):
        d.clean()
    assert d.state['start_token'] == 'retry-key'


@pytest.mark.parametrize('action', ['quickstart', 'custom'])
def test_interactive_start_does_not_force_optional_checks(monkeypatch, action):
    calls = []
    class Stub:
        def __init__(self, *a, **kw): pass
        def create(self, *a, **kw): calls.append('create')
        def start(self): calls.append('start')
        def preview(self): calls.append('preview')
        def validate(self): pytest.fail('Interactive validation must be optional')
    monkeypatch.setattr(demo, 'Demo', Stub)
    monkeypatch.setattr(demo, 'load_dotenv', lambda *a, **kw: None)
    monkeypatch.setenv('OSWORLD_BASE_IMAGE', 'registry.example/base:v1')
    monkeypatch.setenv('CUSTOM_IMAGE', 'registry.example/custom:v1')
    monkeypatch.setattr('sys.argv', ['demo.py', action])
    demo.main()
    assert calls == ['create', 'start', 'preview']


def test_tool_creation_reuses_idempotency_key_after_timeout(tmp_path):
    d = object.__new__(demo.Demo)
    d.state = {}
    d.path = tmp_path / 'state.json'
    tokens = []
    def api(action, **params):
        assert action == 'CreateSandboxTool'
        tokens.append(params['ClientToken'])
        raise demo.TencentCloudSDKException('RequestTimeout', 'timeout', 'request-id')
    d.api = api
    for _ in range(2):
        with pytest.raises(demo.TencentCloudSDKException):
            d.create('ccr.ccs.tencentyun.com/ags-image/example:v1')
    assert tokens[0] == tokens[1]
    assert d.path.exists()
    with pytest.raises(RuntimeError, match='unknown'):
        d.clean()


def test_expired_instance_is_replaced_with_new_start_token(tmp_path):
    d = object.__new__(demo.Demo)
    d.state = {'tool_id': 'tool', 'instance_id': 'expired', 'start_token': 'old'}
    d.path = tmp_path / 'state.json'
    def api(action, **params):
        if action == 'DescribeSandboxInstanceList':
            return {'InstanceSet': []}
        assert action == 'StartSandboxInstance'
        assert params['ClientToken'] != 'old'
        return {'Instance': {'InstanceId': 'new'}}
    d.api = api
    d.start()
    assert d.state['instance_id'] == 'new'
