import asyncio
import json
import sqlite3
import time

import httpx
import pytest
from fastapi.testclient import TestClient

import gateway
from api_pool import APIPool, estimate_tokens, key_id, reset_time


@pytest.fixture
def setup(tmp_path, monkeypatch):
    providers = [{'provider': 'groq', 'base_url': 'https://provider.test/v1',
                  'api_keys': ['test-key-one', 'test-key-two'], 'models': ['model-a', 'model-b'],
                  'quota_limit_tokens': 1000, 'quota_limit_requests': 100}]
    monkeypatch.setattr(gateway, 'providers', providers)
    monkeypatch.setattr(gateway, 'CONFIG_PATH', str(tmp_path / 'config.json'))
    pool = APIPool(str(tmp_path / 'pool.db'), lambda: gateway.providers, gateway.is_chat_model)
    monkeypatch.setattr(gateway, 'pool', pool)
    return pool, providers, TestClient(gateway.app)


def mock_provider(monkeypatch, handler):
    client_class = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(gateway.httpx, 'AsyncClient', lambda **kwargs: client_class(transport=transport, **kwargs))


def event(data):
    return 'data: ' + json.dumps(data) + '\n\n'


def answer(tokens=100):
    return (event({'model': 'model-a', 'choices': [{'delta': {'content': 'Hello'}, 'finish_reason': None}]}) +
            event({'choices': [{'delta': {}, 'finish_reason': 'stop'}]}) +
            event({'choices': [], 'usage': {'total_tokens': tokens}}) + 'data: [DONE]\n\n')


def request(client, **options):
    return client.post('/v1/chat/completions', json={'model': 'model-a',
                       'messages': [{'role': 'user', 'content': 'Hello'}], 'max_tokens': 20,
                       'stream': True, **options})


def gateway_events(response):
    return [json.loads(line[5:].strip())['_gateway'] for line in response.text.splitlines()
            if line.startswith('data:') and '"_gateway"' in line]


def test_stream_counts_reported_tokens_and_persists(setup, monkeypatch):
    pool, providers, client = setup
    mock_provider(monkeypatch, lambda req: httpx.Response(200, text=answer(123)))
    response = request(client)
    assert response.status_code == 200 and '[DONE]' in response.text
    active = client.get('/status').json()['pool']['keys'][0]
    assert active['tokens'] == 123 and active['reported_tokens'] == 123
    assert active['requests'] == 1 and active['estimated_tokens'] == 0
    fresh = APIPool(pool.db_path, lambda: providers, gateway.is_chat_model)
    assert fresh.snapshot()['keys'][0]['tokens'] == 123
    assert not pool.reserved and not any(pool.pending.values())


def test_90_percent_switch_is_shared_across_models(setup, monkeypatch):
    pool, providers, client = setup
    calls = []
    def handler(req):
        calls.append((req.headers['authorization'], json.loads(req.content)['model']))
        return httpx.Response(200, text=answer(900 if len(calls) == 1 else 20))
    mock_provider(monkeypatch, handler)
    request(client)
    snapshot = client.get('/status').json()['pool']
    assert snapshot['keys'][0]['state'] == 'budget'
    assert snapshot['active_id'] == pool.entries()[1]['id']
    assert snapshot['switch_count'] == 1
    request(client, model='model-b')
    assert calls == [('Bearer test-key-one', 'model-a'), ('Bearer test-key-two', 'model-b')]


def test_429_preserves_full_history_and_cools_key(setup, monkeypatch):
    pool, providers, client = setup
    histories = []
    def handler(req):
        histories.append(json.loads(req.content)['messages'])
        if req.headers['authorization'] == 'Bearer test-key-one':
            return httpx.Response(429, headers={'retry-after': '10'}, text='private provider diagnostic')
        return httpx.Response(200, text=answer())
    mock_provider(monkeypatch, handler)
    history = [{'role': 'system', 'content': 'Keep context'}, {'role': 'user', 'content': 'Remember 7'},
               {'role': 'assistant', 'content': '7'}, {'role': 'user', 'content': 'What did I say?'}]
    response = request(client, messages=history)
    assert len(histories) == 2 and all(h == history for h in histories)
    assert 'private provider diagnostic' not in response.text
    assert pool.snapshot()['keys'][0]['state'] == 'cooldown'
    pool.load(pool.entries()[0])['cooldown_until'] = time.time() - 1
    assert pool.state(pool.entries()[0]) == 'standby'


def test_rate_headers_trigger_preemptive_rotation_and_expire(setup, monkeypatch):
    pool, providers, client = setup
    mock_provider(monkeypatch, lambda req: httpx.Response(200, text=answer(20), headers={
        'x-ratelimit-limit-tokens': '10000', 'x-ratelimit-remaining-tokens': '900',
        'x-ratelimit-reset-tokens': '1m5s'}))
    request(client)
    snapshot = pool.snapshot()
    assert snapshot['keys'][0]['state'] == 'cooldown'
    assert snapshot['active_id'] == pool.entries()[1]['id']
    window = pool.load(pool.entries()[0])['rate_limits']['tokens']
    window['reset_at'] = time.time() - 1
    assert pool.state(pool.entries()[0]) == 'standby'


class BrokenStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield event({'choices': [{'delta': {'content': 'Partial answer'}}]}).encode()
        raise httpx.ReadError('private connection details')


def test_partial_stream_never_replayed_into_another_answer(setup, monkeypatch):
    pool, providers, client = setup
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(200, stream=BrokenStream())
    mock_provider(monkeypatch, handler)
    response = request(client)
    assert len(calls) == 1
    assert 'Partial answer' in response.text and '"error"' in response.text
    assert 'private connection details' not in response.text
    usage = pool.load(pool.entries()[0])
    assert usage['requests'] == 1 and usage['estimated_tokens'] > 0
    assert not pool.reserved


def test_usage_missing_is_explicit_estimate(setup, monkeypatch):
    pool, providers, client = setup
    mock_provider(monkeypatch, lambda req: httpx.Response(200, text=event({
        'choices': [{'delta': {'content': 'Hello'}, 'finish_reason': 'stop'}]}) + 'data: [DONE]\n\n'))
    request(client)
    key = pool.snapshot()['keys'][0]
    assert key['reported_tokens'] == 0 and key['estimated_tokens'] > 0


def test_add_is_additive_and_response_hides_secrets(setup, monkeypatch):
    pool, providers, client = setup
    response = client.post('/pool/keys', json={'provider': 'groq', 'api_keys': ['test-key-three']})
    assert response.status_code == 200 and len(providers[0]['api_keys']) == 3
    assert all(secret not in response.text for secret in providers[0]['api_keys'])
    client.post('/pool/keys', json={'provider': 'groq', 'api_keys': ['test-key-three']})
    assert len(providers[0]['api_keys']) == 3
    assert client.post('/config', json=[]).status_code == 405


def test_settings_validation_disable_and_reset(setup):
    pool, providers, client = setup
    identity = pool.entries()[0]['id']
    assert client.patch(f'/pool/keys/{identity}', json={'token_budget': 0}).status_code == 422
    assert client.patch(f'/pool/keys/{identity}', json={'threshold': .2}).status_code == 422
    response = client.patch(f'/pool/keys/{identity}', json={'enabled': False})
    assert response.json()['pool']['keys'][0]['state'] == 'disabled'
    client.patch(f'/pool/keys/{identity}', json={'enabled': True})
    usage = pool.load(pool.entries()[0])
    usage['reported_tokens'] = 900
    pool.save(identity)
    client.post(f'/pool/keys/{identity}/reset')
    assert usage['reported_tokens'] == 0


def test_delete_key_removes_secret_usage_and_switches_active(setup):
    pool, providers, client = setup
    entry = pool.entries()[0]
    identity = entry['id']
    pool.load(entry)['requests'] = 3
    pool.save(identity)
    remaining = pool.entries()[1]['id']
    response = client.delete(f'/pool/keys/{identity}')
    assert response.status_code == 200
    assert providers[0]['api_keys'] == ['test-key-two']
    assert identity not in providers[0].get('key_settings', {})
    assert 'test-key-one' not in response.text and 'test-key-two' not in response.text
    data = response.json()
    assert [key['id'] for key in data['pool']['keys']] == [remaining]
    assert data['pool']['active_id'] == remaining
    assert client.delete(f'/pool/keys/{identity}').status_code == 404
    with sqlite3.connect(pool.db_path) as db:
        assert db.execute('SELECT COUNT(*) FROM pool_usage WHERE key_id=?', (identity,)).fetchone()[0] == 0


def test_all_exhausted_surface_error_without_upstream_call(setup, monkeypatch):
    pool, providers, client = setup
    for entry in pool.entries():
        pool.load(entry)['reported_tokens'] = 900
    mock_provider(monkeypatch, lambda req: pytest.fail('Exhausted key was used'))
    response = request(client)
    assert '"error"' in response.text and '"content"' not in response.text
    assert pool.snapshot()['active_id'] is None


def test_concurrent_reservations_cannot_overspend(setup):
    pool, providers, client = setup
    entry = pool.entries()[0]
    async def run():
        first, second = await asyncio.gather(pool.reserve(entry, 950), pool.reserve(entry, 100))
        assert first is not None and second is None
        await pool.finish(entry, first)
        assert not pool.reserved
    asyncio.run(run())


def test_legacy_counters_aggregate_once(setup):
    pool, providers, client = setup
    with sqlite3.connect(pool.db_path) as db:
        db.execute('CREATE TABLE quota (qkey TEXT, requests INTEGER, tokens INTEGER, errors INTEGER)')
        db.executemany('INSERT INTO quota VALUES (?,?,?,?)', [('0:0:model-a', 2, 50, 0), ('0:0:model-b', 3, 70, 1)])
    fresh = APIPool(pool.db_path, lambda: providers, gateway.is_chat_model)
    key = fresh.snapshot()['keys'][0]
    assert key['tokens'] == 120 and key['requests'] == 5
    fresh.reset(fresh.entries()[0])
    again = APIPool(pool.db_path, lambda: providers, gateway.is_chat_model)
    assert again.snapshot()['keys'][0]['tokens'] == 0


def test_nonstream_usage_and_unknown_model(setup, monkeypatch):
    pool, providers, client = setup
    mock_provider(monkeypatch, lambda req: httpx.Response(200, json={
        'choices': [{'message': {'role': 'assistant', 'content': 'OK'}}], 'usage': {'total_tokens': 55}}))
    assert request(client, stream=False).json()['choices'][0]['message']['content'] == 'OK'
    assert pool.snapshot()['keys'][0]['tokens'] == 55
    assert request(client, model='does-not-exist').status_code == 400


def test_provider_without_stream_usage_option(setup, monkeypatch):
    pool, providers, client = setup
    calls = []
    def handler(req):
        body = json.loads(req.content)
        calls.append(body)
        if 'stream_options' in body:
            return httpx.Response(400, json={'error': {'message': 'Unknown field stream_options'}})
        return httpx.Response(200, text=answer(10))
    mock_provider(monkeypatch, handler)
    response = request(client)
    assert 'Hello' in response.text and len(calls) == 2
    assert 'stream_options' not in calls[1]
    assert calls[0]['messages'] == calls[1]['messages']
    assert pool.snapshot()['keys'][0]['requests'] == 1


def test_request_threshold_and_model_switch_keep_active_account(setup, monkeypatch):
    pool, providers, client = setup
    entry = pool.entries()[0]
    pool.load(entry)['requests'] = 90
    pool.activate(entry['id'])
    assert pool.snapshot()['active_id'] == pool.entries()[1]['id']
    calls = []
    def handler(req):
        calls.append(req.headers['authorization'])
        return httpx.Response(200, text=answer(10))
    mock_provider(monkeypatch, handler)
    request(client, model='model-b')
    assert calls == ['Bearer test-key-two']


def test_disabled_key_is_rechecked_before_queued_dispatch(setup, monkeypatch):
    pool, providers, client = setup
    calls = []
    def handler(req):
        calls.append(req.headers['authorization'])
        identity = pool.entries()[1]['id']
        providers[0]['key_settings'] = {identity: {'enabled': False, 'token_budget': 1}}
        return httpx.Response(429, headers={'retry-after': '10'})
    mock_provider(monkeypatch, handler)
    response = request(client)
    assert calls == ['Bearer test-key-one'] and '"error"' in response.text


def test_requested_model_on_other_key_precedes_model_fallback(setup, monkeypatch):
    pool, providers, client = setup
    calls = []
    def handler(req):
        model = json.loads(req.content)['model']
        calls.append((req.headers['authorization'], model))
        if req.headers['authorization'] == 'Bearer test-key-one' and model == 'model-a':
            return httpx.Response(400)
        return httpx.Response(200, text=answer(10))
    mock_provider(monkeypatch, handler)
    request(client)
    assert calls == [('Bearer test-key-one', 'model-a'), ('Bearer test-key-two', 'model-a')]


def test_nested_groq_usage_is_reported(setup, monkeypatch):
    pool, providers, client = setup
    body = event({'choices': [{'delta': {'content': 'Hello'}}]}) + event({
        'choices': [{'delta': {}, 'finish_reason': 'stop'}], 'x_groq': {'usage': {'total_tokens': 21}}}) + 'data: [DONE]\n\n'
    mock_provider(monkeypatch, lambda req: httpx.Response(200, text=body))
    request(client)
    assert pool.snapshot()['keys'][0]['reported_tokens'] == 21


def test_nonstream_accepted_partial_body_is_counted(setup, monkeypatch):
    pool, providers, client = setup
    mock_provider(monkeypatch, lambda req: httpx.Response(200, stream=BrokenStream()))
    assert request(client, stream=False).status_code == 503
    assert all(pool.load(entry)['requests'] == 1 for entry in pool.entries())
    assert all(pool.load(entry)['estimated_tokens'] > 0 for entry in pool.entries())
    assert not pool.reserved


def test_asgi_disconnect_closes_suspended_generator(setup, monkeypatch):
    import anyio
    pool, providers, client = setup
    class WaitingStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield event({'choices': [{'delta': {'content': 'Partial'}}]}).encode()
            await anyio.sleep_forever()
    mock_provider(monkeypatch, lambda req: httpx.Response(200, stream=WaitingStream()))
    async def run():
        response = await gateway.chat(gateway.ChatRequest(model='model-a', messages=[{'role': 'user', 'content': 'Hello'}], max_tokens=20, stream=True))
        disconnected = anyio.Event()
        async def send(message):
            if message.get('type') == 'http.response.body' and b'Partial' in message.get('body', b''):
                disconnected.set()
                await anyio.sleep_forever()
        async def receive():
            await disconnected.wait()
            return {'type': 'http.disconnect'}
        await response({'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.3'}}, receive, send)
        assert not pool.reserved and not any(pool.pending.values())
        assert pool.load(pool.entries()[0])['requests'] == 1
    anyio.run(run)


def test_image_reservation_does_not_count_base64_as_text():
    message = {'role': 'user', 'content': [{'type': 'text', 'text': 'Describe'},
               {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + 'A' * 500000}}]}
    assert estimate_tokens([message]) < 2000


def test_rate_rotation_at_exactly_90_percent(setup):
    pool, providers, client = setup
    entry = pool.entries()[0]
    pool.headers(entry, httpx.Headers({'x-ratelimit-limit-tokens': '10000',
                                     'x-ratelimit-remaining-tokens': '1000', 'x-ratelimit-reset-tokens': '60'}))
    assert pool.state(entry) == 'cooldown'


def test_reset_header_duration():
    assert reset_time('7m12.5s', 100) == 532.5
    assert reset_time('250ms', 100) == 100.25
    assert reset_time('10', 100) == 110
    assert reset_time('2026-10-27T12:00:00+02:00', 0) == reset_time('2026-10-27T10:00:00Z', 0)
    assert key_id('groq', 'one') != key_id('groq', 'two')


def test_status_hides_providers_with_only_disabled_keys(setup):
    pool, providers, client = setup
    providers[0]['key_settings'] = {entry['id']: {'enabled': False} for entry in pool.entries()}
    data = client.get('/status').json()
    assert data['providers'] == []
    assert data['pool']['keys']


def test_probe_records_model_health(setup, monkeypatch):
    pool, providers, client = setup
    def handler(req):
        body = json.loads(req.content)
        assert body['stream'] is False and body['max_tokens'] == 1 and body['model'] == 'model-a'
        return httpx.Response(200, json={'model': 'model-a', 'choices': [{'message': {'content': 'p'}}],
                                         'usage': {'total_tokens': 2}})
    mock_provider(monkeypatch, handler)
    response = client.post('/models/probe', json={'model': 'model-a'})
    assert response.status_code == 200
    assert response.json()['ok'] is True
    health = client.get('/status').json()['model_health']['model-a']
    assert health['ok'] is True and health['latency_ms'] is not None
    fresh = APIPool(pool.db_path, lambda: providers, gateway.is_chat_model)
    assert fresh.model_health['model-a']['ok'] is True


def test_refresh_fetches_catalog_and_probes_models_in_parallel(setup, monkeypatch):
    pool, providers, client = setup
    catalogs, probes = [], []
    def handler(req):
        if req.method == 'GET' and req.url.path.endswith('/models'):
            catalogs.append(req.headers['authorization'])
            return httpx.Response(200, json={'data': [{'id': 'model-a'}, {'id': 'model-b'},
                                                     {'id': 'model-c'}, {'id': 'whisper-large'}]})
        model = json.loads(req.content)['model']
        probes.append(model)
        if model == 'model-a':
            return httpx.Response(200, json={'choices': [{'message': {'content': 'p'}}],
                                             'usage': {'total_tokens': 2}})
        if model == 'model-b':
            return httpx.Response(404, text='missing model')
        return httpx.Response(500, text='boom')
    mock_provider(monkeypatch, handler)
    data = client.post('/models/refresh', json={'model': 'model-b'}).json()
    assert catalogs == ['Bearer test-key-one']
    assert sorted(probes) == ['model-a', 'model-b', 'model-c']
    assert data['refresh'] == {'probed': 3, 'ok': 1, 'failed': 2, 'skipped': 0,
                               'deadline': False, 'providers': 1}
    assert providers[0]['models'] == ['model-a', 'model-b', 'model-c']
    assert 'whisper-large' not in providers[0]['models']
    assert data['model_health']['model-a']['ok'] is True
    assert data['model_health']['model-b']['status'] == 404
    assert data['model_health']['model-c']['status'] == 500
    saved = json.load(open(gateway.CONFIG_PATH, encoding='utf-8'))
    assert saved[0]['models'] == ['model-a', 'model-b', 'model-c']


def test_refresh_spreads_probes_across_keys(setup, monkeypatch):
    pool, providers, client = setup
    seen = []
    def handler(req):
        if req.method == 'GET':
            return httpx.Response(200, json={'data': [{'id': 'model-a'}, {'id': 'model-b'}]})
        seen.append(req.headers['authorization'])
        return httpx.Response(200, json={'choices': [{'message': {'content': 'p'}}],
                                         'usage': {'total_tokens': 2}})
    mock_provider(monkeypatch, handler)
    data = client.post('/models/refresh', json={}).json()
    assert data['refresh']['ok'] == 2
    assert sorted(seen) == ['Bearer test-key-one', 'Bearer test-key-two']


def test_refresh_retries_invalid_key_without_blaming_models(setup, monkeypatch):
    pool, providers, client = setup
    def handler(req):
        if req.method == 'GET':
            return httpx.Response(200, json={'data': [{'id': 'model-a'}, {'id': 'model-b'}]})
        if req.headers['authorization'] == 'Bearer test-key-one':
            return httpx.Response(400, json={'error': {'code': 400, 'status': 'INVALID_ARGUMENT',
                                                       'message': 'Invalid Auth key.'}})
        return httpx.Response(200, json={'choices': [{'message': {'content': 'p'}}],
                                         'usage': {'total_tokens': 2}})
    mock_provider(monkeypatch, handler)
    data = client.post('/models/refresh', json={}).json()
    assert data['refresh']['ok'] == 2 and data['refresh']['failed'] == 0
    assert data['model_health']['model-a']['ok'] is True
    assert data['model_health']['model-b']['ok'] is True
    key = pool.snapshot()['keys'][0]
    assert key['state'] == 'blocked' and key['last_error']['reason'] == 'credentials'


def test_chat_blocks_key_rejected_with_400_invalid_auth(setup, monkeypatch):
    pool, providers, client = setup
    def handler(req):
        if req.headers['authorization'] == 'Bearer test-key-one':
            return httpx.Response(400, json={'error': {'message': 'Invalid Auth key.'}})
        return httpx.Response(200, text=answer(5))
    mock_provider(monkeypatch, handler)
    response = request(client)
    assert response.status_code == 200
    keys = pool.snapshot()['keys']
    assert keys[0]['state'] == 'blocked' and keys[0]['last_error']['reason'] == 'credentials'
    assert keys[1]['state'] == 'active'


def test_refresh_rate_limit_does_not_cool_the_key(setup, monkeypatch):
    pool, providers, client = setup
    def handler(req):
        if req.method == 'GET':
            return httpx.Response(200, json={'data': [{'id': 'model-a'}, {'id': 'model-b'}]})
        if req.headers['authorization'] == 'Bearer test-key-one':
            return httpx.Response(429, headers={'retry-after': '30'}, text='slow down')
        return httpx.Response(200, json={'choices': [{'message': {'content': 'p'}}],
                                         'usage': {'total_tokens': 2}})
    mock_provider(monkeypatch, handler)
    data = client.post('/models/refresh', json={}).json()
    assert data['refresh']['ok'] == 2
    assert pool.snapshot()['keys'][0]['state'] in ('standby', 'active')


def test_refresh_clears_stale_request_failures(setup, monkeypatch):
    pool, providers, client = setup
    pool.record_model('model-a', False, 'upstream', 400)
    pool.record_model('model-c', False, 'upstream', 404)
    def handler(req):
        if req.method == 'GET':
            return httpx.Response(200, json={'data': [{'id': 'model-a'}, {'id': 'model-b'}]})
        return httpx.Response(429, text='slow down')
    mock_provider(monkeypatch, handler)
    data = client.post('/models/refresh', json={}).json()
    assert 'model-a' not in data['model_health']
    assert data['model_health']['model-c']['status'] == 404
    assert 'model-a' not in pool.model_health and 'model-c' in pool.model_health


def test_refresh_requires_a_key(setup):
    pool, providers, client = setup
    providers[0]['api_keys'] = []
    assert client.post('/models/refresh', json={}).status_code == 503


def test_failed_chat_marks_requested_model_unhealthy(setup, monkeypatch):
    pool, providers, client = setup
    mock_provider(monkeypatch, lambda req: httpx.Response(400, text='bad request'))
    response = request(client)
    assert '"error"' in response.text
    health = client.get('/status').json()['model_health']['model-a']
    assert health['ok'] is False and health['reason'] == 'upstream' and health['status'] == 400


def test_chat_fallback_does_not_mark_requested_model_healthy(setup, monkeypatch):
    pool, providers, client = setup
    def handler(req):
        model = json.loads(req.content)['model']
        if model == 'model-a':
            return httpx.Response(400, text='no such model')
        return httpx.Response(200, text=answer(10))
    mock_provider(monkeypatch, handler)
    response = request(client)
    assert response.status_code == 200
    health = client.get('/status').json()['model_health']['model-a']
    assert health['ok'] is False and health['reason'] == 'fallback'


def test_google_thought_deltas_are_forwarded_as_reasoning(setup, monkeypatch):
    pool, providers, client = setup
    def chunk(delta, finish=None):
        return event({'model': 'model-a', 'choices': [{'delta': delta, 'finish_reason': finish}]})
    stream = (chunk({'content': '<thought>let me think', 'extra_content': {'google': {'thought': True}}}) +
              chunk({'content': '</thought>the answer'}) +
              chunk({}, finish='stop') + event({'choices': [], 'usage': {'total_tokens': 10}}) + 'data: [DONE]\n\n')
    mock_provider(monkeypatch, lambda req: httpx.Response(200, text=stream))
    deltas = [json.loads(line[5:].strip())['choices'][0]['delta'] for line in request(client).text.splitlines()
              if line.startswith('data:') and '"choices"' in line and json.loads(line[5:].strip())['choices']]
    assert deltas[0] == {'reasoning': 'let me think', 'extra_content': {'google': {'thought': True}}}
    assert deltas[1]['content'] == 'the answer'


def test_round_robin_rotates_after_each_success(setup, monkeypatch):
    pool, providers, client = setup
    pool.set_strategy('round_robin')
    calls = []
    def handler(req):
        calls.append(req.headers['authorization'])
        return httpx.Response(200, text=answer(10))
    mock_provider(monkeypatch, handler)
    events = gateway_events(request(client))
    assert pool.snapshot()['active_id'] == pool.entries()[1]['id']
    # Routine rotation to the next account is not a failover, so it must not be flagged as a switch.
    assert [entry['switched'] for entry in events] == [False, False]
    request(client)
    assert calls == ['Bearer test-key-one', 'Bearer test-key-two']


def test_key_switch_inside_request_is_flagged(setup, monkeypatch):
    pool, providers, client = setup
    seen = []
    def handler(req):
        seen.append(req.headers['authorization'])
        if len(seen) == 1:
            return httpx.Response(429, text='rate limited')
        return httpx.Response(200, text=answer(10))
    mock_provider(monkeypatch, handler)
    events = gateway_events(request(client))
    assert seen == ['Bearer test-key-one', 'Bearer test-key-two']
    assert [entry['switched'] for entry in events] == [True, True]
    assert {entry['key_id'] for entry in events} == {pool.entries()[1]['id']}


def test_least_used_prefers_freshest_account(setup, monkeypatch):
    pool, providers, client = setup
    pool.set_strategy('least_used')
    pool.load(pool.entries()[0])['requests'] = 80
    calls = []
    def handler(req):
        calls.append(req.headers['authorization'])
        return httpx.Response(200, text=answer(10))
    mock_provider(monkeypatch, handler)
    request(client)
    assert calls == ['Bearer test-key-two']


def test_periodic_budget_resets_automatically(setup):
    pool, providers, client = setup
    entry = pool.entries()[0]
    providers[0].setdefault('key_settings', {})[entry['id']] = {'budget_period': 'daily'}
    usage = pool.load(entry)
    usage['reported_tokens'] = 900
    usage['period_start'] = time.time() - 86401
    pool.save(entry['id'])
    snapshot = pool.snapshot()
    key = next(item for item in snapshot['keys'] if item['id'] == entry['id'])
    assert key['tokens'] == 0 and key['state'] in ('standby', 'active')
    assert pool.load(entry)['period_start'] > time.time() - 5


def test_repeated_upstream_failures_back_off_progressively(setup):
    pool, providers, client = setup
    entry = pool.entries()[0]
    pool.failure(entry, 500)
    first = pool.load(entry)['cooldown_until'] - time.time()
    pool.failure(entry, 500)
    second = pool.load(entry)['cooldown_until'] - time.time()
    assert 10 < first <= 16 and 25 < second <= 31
    assert pool.load(entry)['failures'] == 2
    assert pool.load(entry)['last_error']['status'] == 500


def test_key_validation_rejects_explicit_credentials_failure(setup, monkeypatch):
    pool, providers, client = setup
    mock_provider(monkeypatch, lambda req: httpx.Response(401, json={'error': 'invalid api key'}))
    response = client.post('/pool/keys', json={'provider': 'groq', 'api_keys': ['definitely-bad-key']})
    assert response.status_code == 200
    data = response.json()
    assert data['validation'] == {'added': 0, 'rejected': 1, 'unverified': 0}
    assert len(providers[0]['api_keys']) == 2
    assert 'definitely-bad-key' not in response.text


def test_provider_models_can_be_edited_per_provider(setup, monkeypatch):
    pool, providers, client = setup
    response = client.patch('/pool/providers/groq/models', json={'models': ['model-a', 'model-c']})
    assert response.status_code == 200
    assert providers[0]['models'] == ['model-a', 'model-c']
    assert [item['id'] for item in client.get('/v1/models').json()['data']] == ['model-a', 'model-c']
    assert client.patch('/pool/providers/groq/models',
                        json={'models': ['mistral-embed']}).status_code == 400
    assert client.patch('/pool/providers/groq/models', json={'models': ['../../etc']}).status_code == 400
    assert client.patch('/pool/providers/nobody/models', json={'models': []}).status_code == 404
    assert client.patch('/pool/providers/groq/models', json={'models': []}).status_code == 200
    assert request(client).status_code == 400


def test_builtin_provider_can_be_removed_with_its_keys(setup, monkeypatch):
    pool, providers, client = setup
    mock_provider(monkeypatch, lambda req: httpx.Response(200, text=answer(10)))
    request(client)
    identities = [entry['id'] for entry in pool.entries()]
    assert client.delete('/pool/providers/groq').status_code == 200
    assert providers == []
    assert pool.entries() == []
    assert not any(identity in pool.usage for identity in identities)
    assert client.get('/status').json()['providers'] == []
    with open(gateway.CONFIG_PATH, encoding='utf-8') as saved:
        assert 'test-key-one' not in saved.read()


def test_custom_openai_compatible_provider_add_chat_and_delete(setup, monkeypatch):
    pool, providers, client = setup
    def handler(req):
        if req.method == 'GET':
            return httpx.Response(200, json={'data': [{'id': 'custom-model'}]})
        return httpx.Response(200, text=answer(10))
    mock_provider(monkeypatch, handler)
    response = client.post('/pool/providers', json={
        'name': 'localai', 'base_url': 'https://local.test/v1', 'models': ['custom-model']})
    assert response.status_code == 200
    custom = next(item for item in response.json()['providers'] if item['provider'] == 'localai')
    assert custom['custom'] is True
    response = client.post('/pool/keys', json={'provider': 'localai', 'api_keys': ['local-secret']})
    assert response.json()['validation']['added'] == 1
    assert 'local-secret' not in response.text
    assert request(client, model='custom-model').status_code == 200
    response = client.delete('/pool/providers/localai')
    assert response.status_code == 200
    assert not any(item['provider'] == 'localai' for item in providers)
    assert client.delete('/pool/keys/%s' % '0' * 24).status_code == 404


def test_preset_provider_adds_catalog_and_filters_non_chat(setup, monkeypatch):
    pool, providers, client = setup
    hosts = []
    def handler(req):
        hosts.append(req.url.host)
        return httpx.Response(200, json={'data': [{'id': 'mistral-small-latest'},
                                                 {'id': 'mistral-embed'}]})
    mock_provider(monkeypatch, handler)
    response = client.post('/pool/keys', json={'provider': 'mistral', 'api_keys': ['mistral-secret']})
    assert response.status_code == 200
    assert response.json()['validation']['added'] == 1
    assert 'mistral-secret' not in response.text
    added = next(item for item in providers if item['provider'] == 'mistral')
    assert added['base_url'] == 'https://api.mistral.ai/v1'
    assert added['models'] == ['mistral-small-latest']
    assert set(hosts) == {'api.mistral.ai'}


def test_long_conversation_is_trimmed_before_sending(setup, monkeypatch):
    pool, providers, client = setup
    providers[0]['quota_limit_tokens'] = 500000
    providers[0]['key_settings'] = {}
    seen = []
    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={'choices': [{'message': {'content': 'OK'}}],
                                         'usage': {'total_tokens': 10}})
    mock_provider(monkeypatch, handler)
    history = [{'role': 'user', 'content': f'message {index} ' + 'x' * 4000} for index in range(40)]
    history.append({'role': 'user', 'content': 'FINAL QUESTION'})
    response = request(client, stream=False, messages=history)
    assert response.status_code == 200
    assert seen[0]['messages'][-1]['content'] == 'FINAL QUESTION'
    assert len(seen[0]['messages']) < len(history)
    assert response.json()['_gateway']['context']['trimmed'] > 0


def test_probe_retries_reasoning_models_with_larger_token_budget(setup, monkeypatch):
    pool, providers, client = setup
    budgets = []
    def handler(req):
        body = json.loads(req.content)
        budgets.append(body['max_tokens'])
        if body['max_tokens'] == 1:
            return httpx.Response(400, json={'error': {'message': 'max_tokens must be at least 16'}})
        return httpx.Response(200, json={'model': 'model-a', 'choices': [{'message': {'content': 'p'}}],
                                         'usage': {'total_tokens': 2}})
    mock_provider(monkeypatch, handler)
    response = client.post('/models/probe', json={'model': 'model-a'})
    assert response.json()['ok'] is True
    assert budgets == [1, 16]


def test_health_endpoint_and_optional_token_guard(setup, monkeypatch):
    pool, providers, client = setup
    health = client.get('/health').json()
    assert health['status'] == 'ok' and health['version'] == gateway.GATEWAY_VERSION
    assert client.get('/status').json()['version'] == gateway.GATEWAY_VERSION
    monkeypatch.setattr(gateway, 'GATEWAY_TOKEN', 'secret-token')
    assert client.get('/status').status_code == 401
    assert client.get('/health').status_code == 200
    assert client.get('/app/').status_code == 404  # static shell stays public
    assert client.get('/status', headers={'Authorization': 'Bearer secret-token'}).status_code == 200


def test_workspace_root_sandbox_blocks_outside_paths(setup, monkeypatch, tmp_path):
    pool, providers, client = setup
    root = tmp_path / 'sandbox'
    root.mkdir()
    (root / 'inside.txt').write_text('visible', encoding='utf-8')
    outside = tmp_path / 'outside.txt'
    outside.write_text('secret', encoding='utf-8')
    monkeypatch.setattr(gateway, 'WORKSPACE_ROOT', str(root))

    assert client.post('/workspace/read', json={'path': str(root), 'filename': 'inside.txt'}).json()['content'] == 'visible'
    assert client.post('/workspace/read', json={'path': str(tmp_path), 'filename': 'outside.txt'}).status_code == 403
    assert client.post('/workspace/snapshot', json={'path': str(tmp_path)}).status_code == 403
    assert client.post('/workspace/list', json={'path': str(tmp_path)}).status_code == 403
    assert client.get('/workspace/root').json() == {'root': str(root)}


def test_workspace_snapshot_skips_secrets_binary_and_large_files(setup, monkeypatch, tmp_path):
    pool, providers, client = setup
    root = tmp_path / 'workspace'
    root.mkdir()
    (root / 'main.py').write_text('print(1)', encoding='utf-8')
    (root / '.env').write_text('TOKEN=secret', encoding='utf-8')
    (root / 'big.txt').write_text('x' * 400_001, encoding='utf-8')
    (root / 'blob.bin').write_bytes(b'\xff\xfe\x00')
    monkeypatch.setattr(gateway, 'WORKSPACE_ROOT', str(root))
    files = client.post('/workspace/snapshot', json={'path': str(root)}).json()['files']
    assert [item['path'] for item in files] == ['main.py']


def test_billing_402_blocks_key_and_reports_billing(setup, monkeypatch):
    pool, providers, client = setup
    mock_provider(monkeypatch, lambda req: httpx.Response(402, json={'error': 'insufficient credit'}))
    response = request(client)
    assert '"code": "billing"' in response.text
    pool_data = client.get('/status').json()['pool']
    assert [item['state'] for item in pool_data['keys']] == ['blocked', 'blocked']
    assert pool_data['keys'][0]['last_error']['reason'] == 'billing'
    client.post(f"/pool/keys/{pool_data['keys'][0]['id']}/reset")
    refreshed = client.get('/status').json()['pool']['keys'][0]
    assert refreshed['state'] in ('standby', 'active') and refreshed['last_error'] is None


def test_legacy_402_error_blocks_key_after_upgrade(setup):
    pool, providers, _ = setup
    entry = pool.entries()[0]
    legacy = {'requests': 5, 'reported_tokens': 10, 'estimated_tokens': 0, 'errors': 1,
              'cooldown_until': 0, 'blocked': False, 'rate_limits': {}, 'last_used': None,
              'failures': 1, 'period_start': 0,
              'last_error': {'status': 402, 'reason': 'request', 'at': time.time(), 'count': 1}}
    with sqlite3.connect(pool.db_path) as db:
        db.execute('INSERT OR REPLACE INTO pool_usage (key_id,data) VALUES (?,?)',
                   (entry['id'], json.dumps(legacy)))
    fresh = APIPool(pool.db_path, lambda: providers, gateway.is_chat_model)
    assert fresh.state(entry) == 'blocked'
    assert fresh.snapshot()['keys'][0]['last_error']['reason'] == 'billing'
    fresh.reset(entry)
    assert fresh.state(entry) in ('standby', 'active')


def test_missing_model_is_skipped_after_first_404(setup, monkeypatch):
    pool, providers, client = setup
    calls = []
    def handler(req):
        calls.append(json.loads(req.content)['model'])
        return httpx.Response(404, json={'error': 'model not found'})
    mock_provider(monkeypatch, handler)
    response = request(client)
    assert '"code": "model_unavailable"' in response.text
    assert calls == ['model-a', 'model-b']
    assert client.get('/status').json()['model_health']['model-a']['ok'] is False


def test_guard_models_are_never_offered_for_chat(setup):
    pool, providers, client = setup
    assert not gateway.is_chat_model('nvidia/nemotron-3.5-content-safety:free')
    assert not gateway.is_chat_model('meta-llama/llama-guard-4-12b')
    assert gateway.is_chat_model('nvidia/nemotron-3.5-super-vl')
    providers[0]['models'].append('nvidia/nemotron-3.5-content-safety:free')
    models = client.get('/status').json()['providers'][0]['models']
    assert 'nvidia/nemotron-3.5-content-safety:free' not in models


def test_gemini_model_prefixes_are_normalized_on_load(tmp_path, monkeypatch):
    config = tmp_path / 'config.json'
    config.write_text(json.dumps([{'provider': 'gemini',
                                   'base_url': 'https://generativelanguage.googleapis.com/v1beta/openai/',
                                   'api_keys': ['test-key'], 'models': ['models/gemini-2.5-flash', 'gemini-2.5-pro']}]),
                      encoding='utf-8')
    monkeypatch.setattr(gateway, 'CONFIG_PATH', str(config))
    loaded = gateway.load_config()
    assert loaded[0]['models'] == ['gemini-2.5-flash', 'gemini-2.5-pro']
    assert json.loads(config.read_text(encoding='utf-8'))[0]['models'] == ['gemini-2.5-flash', 'gemini-2.5-pro']
