import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from paper_translator.config import Settings, ConfigStore
from paper_translator.providers import Translator, TranslationError
from paper_translator.state import RequestGate, SelectionDebouncer


@pytest.fixture
def api_server():
    requests = []
    replies = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            requests.append((self.path, body, dict(self.headers)))
            status, payload = replies.pop(0)
            encoded = json.dumps(payload).encode()
            self.send_response(status)
            if 300 <= status < 400:
                self.send_header('Location', payload['location'])
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            requests.append((self.path, b'', dict(self.headers)))
            encoded = json.dumps({'choices': [{'message': {'content': '{"translation":"redirected"}'}}]}).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}', requests, replies
    server.shutdown()
    server.server_close()
    thread.join()


def configured(url):
    return Settings(baidu_app_id='123', baidu_key='secret',
                    baidu_url=url + '/baidu', ai_url=url + '/v1',
                    ai_key='ai-secret', ai_model='test-model')


def test_daily_calls_baidu_with_utf8_signature(api_server):
    from urllib.parse import parse_qs
    url, requests, replies = api_server
    replies.append((200, {'trans_result': [{'src': 'attention机制', 'dst': '注意力机制'}]}))
    result = Translator().translate('attention机制', configured(url))
    assert result.translation == '注意力机制'
    assert result.reviewed is False
    fields = parse_qs(requests[0][1].decode())
    raw = '123attention机制' + fields['salt'][0] + 'secret'
    assert fields['sign'] == [hashlib.md5(raw.encode()).hexdigest()]
    assert len(requests) == 1


def test_paper_reviews_source_and_draft(api_server):
    url, requests, replies = api_server
    replies.extend([(200, {'trans_result': [{'dst': '注意'}]}),
                    (200, {'choices': [{'message': {'content': json.dumps({
                        'translation': '注意力机制', 'terms': [{'source': 'attention', 'target': '注意力', 'note': '机器学习术语'}],
                        'ambiguities': ['缺少上下文'], 'notes': '保留术语含义'})}}]})])
    settings = configured(url)
    settings.mode = 'paper'
    settings.discipline = '机器学习'
    result = Translator().translate('attention', settings)
    assert result.translation == '注意力机制'
    assert result.draft == '注意'
    assert result.reviewed is True
    assert result.ambiguities == ['缺少上下文']
    path, body, headers = requests[1]
    assert path == '/v1/chat/completions'
    payload = json.loads(body)
    user = json.loads(payload['messages'][1]['content'])
    assert user['source'] == 'attention'
    assert user['draft'] == '注意'
    assert user['discipline'] == '机器学习'
    assert headers['Authorization'] == 'Bearer ai-secret'


@pytest.mark.parametrize('payload', [
    {'choices': []},
    {'choices': [{'message': {'content': '这不是 JSON'}}]},
    {'choices': [{'message': {'content': '{"translation":""}'}}]},
    {'choices': [{'message': {'content': '{"translation":"译文","ambiguities":"字符串"}'}}]},
])
def test_bad_review_fails_without_presenting_draft(api_server, payload):
    url, requests, replies = api_server
    replies.extend([(200, {'trans_result': [{'dst': '初译'}]}), (200, payload)])
    settings = configured(url)
    settings.mode = 'paper'
    with pytest.raises(TranslationError, match='复核'):
        Translator().translate('term', settings)


def test_paper_review_reports_ai_http_failure_without_leaking_response(api_server):
    url, requests, replies = api_server
    replies.extend([(200, {'trans_result': [{'dst': '初译'}]}),
                    (401, {'message': 'private ai-secret'})])
    settings = configured(url)
    settings.mode = 'paper'
    with pytest.raises(TranslationError, match='AI 复核失败：API HTTP 401') as exc:
        Translator().translate('term', settings)
    assert 'private' not in str(exc.value)
    assert 'ai-secret' not in str(exc.value)
    assert len(requests) == 2


def test_paper_review_accepts_thinking_and_fenced_json(api_server):
    url, requests, replies = api_server
    content = '<think>核对术语</think>\n```json\n{"translation":"注意力机制","ambiguities":[]}\n```'
    replies.extend([(200, {'trans_result': [{'dst': '初译'}]}),
                    (200, {'choices': [{'message': {'content': content}}]})])
    settings = configured(url)
    settings.mode = 'paper'
    result = Translator().translate('attention mechanism', settings)
    assert result.reviewed and result.translation == '注意力机制'


def test_paper_review_explains_invalid_model_output(api_server):
    url, requests, replies = api_server
    replies.extend([(200, {'trans_result': [{'dst': '初译'}]}),
                    (200, {'choices': [{'message': {'content': '不是 JSON'}}]})])
    settings = configured(url)
    settings.mode = 'paper'
    with pytest.raises(TranslationError, match='AI 返回格式'):
        Translator().translate('term', settings)


def test_baidu_errors_never_become_empty_success(api_server):
    url, requests, replies = api_server
    replies.append((200, {'error_code': '54003', 'error_msg': 'limit'}))
    with pytest.raises(TranslationError, match='54003'):
        Translator().translate('term', configured(url))


def test_http_errors_do_not_echo_credentials(api_server):
    url, requests, replies = api_server
    replies.append((401, {'message': 'secret ai-secret'}))
    with pytest.raises(TranslationError) as exc:
        Translator().translate('term', configured(url))
    assert '401' in str(exc.value)
    assert 'secret' not in str(exc.value)


def test_missing_paper_credentials_fail_before_any_request(api_server):
    url, requests, replies = api_server
    settings = configured(url)
    settings.mode = 'paper'
    settings.ai_key = ''
    with pytest.raises(TranslationError):
        Translator().translate('term', settings)
    assert not requests


def test_pause_between_draft_and_review_prevents_second_request(api_server):
    url, requests, replies = api_server
    replies.append((200, {'trans_result': [{'dst': '初译'}]}))
    settings = configured(url)
    settings.mode = 'paper'
    with pytest.raises(TranslationError, match='取消'):
        Translator().translate('term', settings, cancelled=lambda: bool(requests))
    assert len(requests) == 1


def test_ai_redirect_is_rejected_without_forwarding_bearer_key(api_server):
    url, requests, replies = api_server
    replies.extend([(200, {'trans_result': [{'dst': '初译'}]}),
                    (302, {'location': url + '/other-service'})])
    settings = configured(url)
    settings.mode = 'paper'
    with pytest.raises(TranslationError, match='复核'):
        Translator().translate('term', settings)
    assert len(requests) == 2


def test_pause_and_settings_change_invalidate_results():
    gate = RequestGate()
    first = gate.issue()
    second = gate.issue()
    assert not gate.accepts(first)
    assert gate.accepts(second)
    gate.set_enabled(False)
    assert not gate.accepts(second)
    assert gate.issue() is None
    gate.set_enabled(True)
    third = gate.issue()
    gate.invalidate()
    assert not gate.accepts(third)


def test_selection_is_debounced_and_never_emitted_during_drag():
    d = SelectionDebouncer(delay_ms=450)
    assert d.feed('half', 0, dragging=True) is None
    assert d.feed('whole sentence', 100) is None
    assert d.feed('whole sentence', 549) is None
    assert d.feed('whole sentence', 550) == 'whole sentence'
    assert d.feed('whole sentence', 1000) is None
    d.feed('', 1100)
    d.feed('whole sentence', 1200)
    assert d.feed('whole sentence', 1650) == 'whole sentence'


def test_disabled_selection_does_not_replay_on_resume():
    d = SelectionDebouncer()
    d.feed('old', 0, enabled=False)
    assert d.feed('old', 1000, enabled=True) is None
    assert d.feed('old', 2000, enabled=True) is None
    d.feed('new', 2100)
    assert d.feed('new', 3100) == 'new'


def test_focus_return_primes_existing_selection_without_retranslating():
    d = SelectionDebouncer()
    d.feed('selected', 0)
    assert d.feed('selected', 1000) == 'selected'
    d.suspend()
    assert d.feed('selected', 1100) is None
    assert d.feed('selected', 1500) is None
    d.feed('new selection', 1600)
    assert d.feed('new selection', 2600) == 'new selection'


def test_copy_cancels_pending_selection_until_text_changes():
    d = SelectionDebouncer()
    d.feed('initial', 0)
    d.feed('copy candidate', 100)
    d.cancel_current()
    assert d.feed('copy candidate', 1500) is None
    d.feed('new selection', 1600)
    assert d.feed('new selection', 2599) is None
    assert d.feed('new selection', 2600) == 'new selection'


def test_same_text_can_translate_after_a_new_drag_even_after_copy():
    d = SelectionDebouncer()
    d.feed('same', 0)
    assert d.feed('same', 1000) == 'same'
    d.feed('', 1100, dragging=True)
    d.feed('same', 1200)
    assert d.feed('same', 2200) == 'same'
    d.feed('', 2300, dragging=True)
    d.feed('same', 2400)
    d.cancel_current()
    assert d.feed('same', 3400) is None
    d.feed('', 3500, dragging=True)
    d.feed('same', 3600)
    assert d.feed('same', 4600) == 'same'


class MemoryKeyring:
    def __init__(self, broken=False):
        self.data = {}
        self.broken = broken

    def get_password(self, service, name):
        if self.broken:
            raise RuntimeError('locked')
        return self.data.get(name)

    def set_password(self, service, name, value):
        if self.broken:
            raise RuntimeError('locked')
        self.data[name] = value

    def delete_password(self, service, name):
        self.data.pop(name, None)


def test_config_keeps_secrets_out_of_json_and_loads_keyring(tmp_path):
    ring = MemoryKeyring()
    store = ConfigStore(tmp_path / 'settings.json', ring)
    s = configured('https://example.com')
    assert store.save(s) == ''
    raw = store.path.read_text()
    assert 'secret' not in raw
    assert store.load().baidu_key == 'secret'
    assert store.load().ai_key == 'ai-secret'


def test_locked_keyring_preserves_only_session_credentials(tmp_path):
    store = ConfigStore(tmp_path / 'settings.json', MemoryKeyring(broken=True))
    assert store.save(configured('https://example.com'))
    assert 'secret' not in store.path.read_text()
    assert store.load().ai_key == 'ai-secret'


def test_hotkey_collision_rejected_before_save(tmp_path):
    store = ConfigStore(tmp_path / 'settings.json', MemoryKeyring())
    settings = Settings(screenshot_hotkey='Ctrl+Alt+S', toggle_hotkey='Ctrl+Alt+S')
    with pytest.raises(ValueError):
        store.save(settings)
    assert not store.path.exists()


@pytest.mark.parametrize('text,source,target', [
    ('这是测试。', 'zh', 'en'), ('This is a test.', 'en', 'zh'),
    ('使用 Transformer 提升翻译性能', 'zh', 'en'),
    ('This sentence mentions 中文 as an example.', 'en', 'zh'),
    ('𠀀繁體中文', 'zh', 'en'), ('123 + 456', 'auto', 'zh'),
])
def test_auto_direction_applies_to_daily_requests(api_server, text, source, target):
    from urllib.parse import parse_qs
    url, requests, replies = api_server
    replies.append((200, {'trans_result': [{'dst': 'translated'}]}))
    settings = configured(url)
    Translator().translate(text, settings)
    data = parse_qs(requests[0][1].decode())
    assert data['from'] == [source]
    assert data['to'] == [target]
    assert settings.source_language == 'auto' and settings.target_language == 'zh'


def test_paper_review_uses_detected_direction(api_server):
    from urllib.parse import parse_qs
    url, requests, replies = api_server
    replies.extend([(200, {'trans_result': [{'dst': 'draft'}]}),
                    (200, {'choices': [{'message': {'content': '{"translation":"reviewed"}'}}]})])
    settings = configured(url)
    settings.mode = 'paper'
    Translator().translate('注意力机制', settings)
    assert parse_qs(requests[0][1].decode())['to'] == ['en']
    user = json.loads(json.loads(requests[1][1])['messages'][1]['content'])
    assert (user['source_language'], user['target_language']) == ('zh', 'en')


def test_manual_direction_can_override_detection(api_server):
    from urllib.parse import parse_qs
    url, requests, replies = api_server
    replies.append((200, {'trans_result': [{'dst': 'manual'}]}))
    settings = configured(url)
    settings.auto_direction = False
    settings.target_language = 'fra'
    Translator().translate('中文', settings)
    assert parse_qs(requests[0][1].decode())['to'] == ['fra']


def test_paper_context_is_for_review_only_and_not_explanations(api_server):
    url, requests, replies = api_server
    replies.extend([(200, {'trans_result': [{'dst': 'draft'}]}),
                    (200, {'choices': [{'message': {'content': '{"translation":"最终译文","terms":[{"source":"x","target":"y","note":"explanation"}],"notes":"explanation"}'}}]})])
    settings = configured(url)
    settings.mode = 'paper'
    result = Translator().translate('attention', settings, context='In neural networks, attention weights the values.')
    user = json.loads(json.loads(requests[1][1])['messages'][1]['content'])
    assert user['context'].startswith('In neural networks')
    assert result.terms == [] and result.notes == ''
    assert result.translation == '最终译文' and result.reviewed
    from urllib.parse import parse_qs
    assert parse_qs(requests[0][1].decode())['q'] == ['attention']
