import asyncio
import fnmatch
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import socket
import time
from contextlib import asynccontextmanager
from typing import Any, List, Literal, Optional
from urllib.parse import quote, urlparse

import anyio
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api_pool import APIPool, estimate_tokens, key_id

load_dotenv()
CONFIG_PATH = os.getenv('GATEWAY_CONFIG') or os.path.join(os.path.dirname(__file__), 'gateway_config.json')
DB_PATH = os.getenv('DB_PATH') or os.path.join(os.path.dirname(__file__), 'gateway.db')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO),
                    format='%(asctime)s %(levelname)s %(name)s %(message)s')
logger = logging.getLogger('proxypal')
STARTED_AT = time.time()
GATEWAY_VERSION = 6  # Keep in sync with modern-workspace/src/App.jsx and run.bat.
TOKEN_PATH = os.getenv('GATEWAY_TOKEN_FILE') or os.path.join(os.path.dirname(__file__), 'data', '.gateway_token')


def restrict_permissions(path):
    """Keep runtime secrets readable only by the account running the gateway."""
    if os.name == 'posix':
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def load_gateway_token():
    """A loopback gateway still needs a secret so other local pages cannot drive it."""
    configured = os.getenv('GATEWAY_TOKEN', '').strip()
    if configured:
        return configured
    try:
        with open(TOKEN_PATH, encoding='utf-8') as file:
            saved = file.read().strip()
        if saved:
            return saved
    except OSError:
        pass
    token = secrets.token_urlsafe(32)
    try:
        os.makedirs(os.path.dirname(TOKEN_PATH) or '.', exist_ok=True)
        descriptor = os.open(TOKEN_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as file:
            file.write(token)
        restrict_permissions(TOKEN_PATH)
        logger.info('Gateway token created; it is stored in %s', TOKEN_PATH)
    except OSError:
        logger.warning('Could not persist the gateway token in %s; it will change on restart', TOKEN_PATH)
    return token


GATEWAY_TOKEN = load_gateway_token()


def load_config():
    try:
        with open(CONFIG_PATH, encoding='utf-8') as file:
            data = json.load(file)
    except FileNotFoundError:
        logger.warning('Config file %s is missing; starting with an empty provider list', CONFIG_PATH)
        return []
    data = data if isinstance(data, list) else [data]
    changed = False
    for provider in data:
        if not isinstance(provider, dict) or 'generativelanguage.googleapis.com' not in str(provider.get('base_url')):
            continue
        models = provider.get('models')
        if not isinstance(models, list):
            continue
        # Gemini's native listing returns "models/<id>", but its OpenAI-compatible endpoint expects "<id>".
        normalized = [model[len('models/'):] if isinstance(model, str) and model.startswith('models/') else model
                      for model in models]
        if normalized != models:
            provider['models'] = normalized
            changed = True
    if changed:
        save_config(data)
        logger.info('Normalized Gemini model identifiers in %s', CONFIG_PATH)
    return data


def save_config(data):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as file:
        json.dump(data, file, indent=2)
    restrict_permissions(CONFIG_PATH)


providers = load_config()
_NON_CHAT_PATTERNS = ('whisper', 'tts', 'orpheus', 'guard', 'safety', 'moderation', 'classifier',
                      'embed', 'rerank', 'audio', 'speech', 'ocr-', 'dall-e', 'stable-diffusion',
                      'flux', 'midjourney', 'image', 'imagen', 'veo', 'music', 'live-', 'batch')
REFRESH_MAX_MODELS = 60
REFRESH_CONCURRENCY = 12
REFRESH_DEADLINE = 45


def is_chat_model(model):
    return bool(model) and not any(part in model.lower() for part in _NON_CHAT_PATTERNS)


_CREDENTIAL_HINTS = ('api key not valid', 'api_key_invalid', 'invalid api key', 'invalid auth key',
                     'api key expired', 'api key is invalid', 'incorrect api key')


def credential_failure(status, detail=''):
    """Some providers reject an invalid key with HTTP 400 instead of 401."""
    if status in (401, 403):
        return True
    text = str(detail or '').lower()
    return status == 400 and any(hint in text for hint in _CREDENTIAL_HINTS)


pool = APIPool(DB_PATH, lambda: providers, is_chat_model)
restrict_permissions(DB_PATH)


@asynccontextmanager
async def lifespan(app):
    await startup()
    yield


app = FastAPI(title='ProxyPal', lifespan=lifespan)
app.add_middleware(CORSMiddleware,
                   allow_origins=os.getenv('ALLOWED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(','),
                   allow_methods=['GET', 'POST', 'PATCH', 'DELETE'], allow_headers=['Content-Type', 'Authorization'])
STATIC_DIR = os.getenv('STATIC_DIR') or os.path.join(os.path.dirname(__file__), 'static')
if os.path.isdir(STATIC_DIR):
    app.mount('/app', StaticFiles(directory=STATIC_DIR, html=True), name='static')
WORKSPACE_ROOT = os.path.realpath(os.getenv('WORKSPACE_ROOT')) if os.getenv('WORKSPACE_ROOT') else None


def token_matches(request):
    supplied = request.headers.get('authorization', '')
    return hmac.compare_digest(supplied, 'Bearer ' + GATEWAY_TOKEN)


@app.middleware('http')
async def require_token(request, call_next):
    # The app shell itself stays reachable; its API calls still need the token.
    public = request.url.path in ('/', '/health') or request.url.path.startswith('/app')
    if request.method != 'OPTIONS' and not public and not token_matches(request):
        return JSONResponse({'detail': 'Unauthorized: missing or invalid gateway token'}, status_code=401)
    return await call_next(request)


class ChatMessage(BaseModel):
    role: Literal['system', 'user', 'assistant', 'tool']
    content: Any


class ChatRequest(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessage] = Field(min_length=1)
    temperature: float = Field(default=.7, ge=0, le=2)
    top_p: float = Field(default=1, gt=0, le=1)
    max_tokens: int = Field(default=2048, ge=1, le=32768)
    stream: bool = False
    reasoning_effort: Optional[str] = None


class ProbeRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)


class RefreshRequest(BaseModel):
    model: Optional[str] = Field(default=None, max_length=200)


class AddKeys(BaseModel):
    provider: str = Field(min_length=2, max_length=32)
    api_keys: List[str] = Field(min_length=1, max_length=50)
    label: Optional[str] = Field(default=None, max_length=80)
    token_budget: int = Field(default=100000, ge=1)
    request_budget: int = Field(default=1000, ge=1)


class NewProvider(BaseModel):
    name: str = Field(min_length=2, max_length=32)
    base_url: str = Field(min_length=8, max_length=300)
    models: List[str] = Field(default_factory=list, max_length=200)


class ProviderModels(BaseModel):
    models: List[str] = Field(default_factory=list, max_length=200)


class RoutingSettings(BaseModel):
    strategy: Literal['sticky', 'round_robin', 'least_used']


class KeySettings(BaseModel):
    enabled: Optional[bool] = None
    label: Optional[str] = Field(default=None, max_length=80)
    token_budget: Optional[int] = Field(default=None, ge=1)
    request_budget: Optional[int] = Field(default=None, ge=1)
    threshold: Optional[float] = Field(default=None, ge=.5, le=1)
    budget_period: Optional[Literal['never', 'daily', 'weekly', 'monthly']] = None


PROVIDER_URLS = {'groq': 'https://api.groq.com/openai/v1',
                 'openrouter': 'https://openrouter.ai/api/v1',
                 'gemini': 'https://generativelanguage.googleapis.com/v1beta/openai',
                 'openai': 'https://api.openai.com/v1',
                 'anthropic': 'https://api.anthropic.com/v1',
                 'mistral': 'https://api.mistral.ai/v1',
                 'deepseek': 'https://api.deepseek.com/v1',
                 'moonshot': 'https://api.moonshot.ai/v1',
                 'llama': 'https://api.llama.com/compat/v1',
                 'github': 'https://models.github.ai/inference',
                 'xai': 'https://api.x.ai/v1',
                 'together': 'https://api.together.xyz/v1',
                 'fireworks': 'https://api.fireworks.ai/inference/v1',
                 'cerebras': 'https://api.cerebras.ai/v1'}

# Providers whose catalog route needs different auth still get a starting list;
# every model is probed before use, so stale entries are hidden automatically.
PROVIDER_MODELS = {
    'anthropic': ['claude-sonnet-4-5', 'claude-haiku-4-5', 'claude-opus-4-1'],
    'github': ['openai/gpt-4.1', 'openai/gpt-4o',
               'meta/Llama-4-Scout-17B-16E-Instruct', 'deepseek/DeepSeek-V3-0324'],
}

# Conservative context windows for the chat models the pool commonly routes to.
CONTEXT_LIMITS = (
    ('gemini', 1000000), ('gemma3', 131072), ('gemma2', 8192), ('gemma-2', 8192),
    ('claude', 200000), ('gpt-4.1', 1000000), ('gpt-4o', 128000), ('gpt-5', 400000),
    ('o3', 200000), ('o4', 200000), ('llama-4', 131072), ('llama-3.3', 131072),
    ('llama-3.1', 131072), ('llama-3.2', 131072), ('qwen', 131072), ('deepseek', 131072),
    ('mistral-large', 131072), ('mixtral', 32768), ('command-r', 128000),
    ('kimi', 131072), ('minimax', 1000000),
)


def context_limit(model):
    name = (model or '').lower()
    for marker, limit in CONTEXT_LIMITS:
        if marker in name:
            return limit
    return 32768


def fit_messages(messages, model, max_tokens):
    """Keep a conversation inside the model window without losing the newest turns."""
    limit = context_limit(model)
    adjusted = max(256, min(int(max_tokens), limit // 2))
    system = [dict(message) for message in messages if message.get('role') == 'system']
    rest = [dict(message) for message in messages if message.get('role') != 'system']
    trimmed = 0

    def size():
        return estimate_tokens(system + rest) + adjusted

    while size() > limit and len(rest) > 1:
        rest.pop(0)
        trimmed += 1
        if rest and rest[0].get('role') == 'assistant' and len(rest) > 1:
            rest.pop(0)
            trimmed += 1
        if not any(message.get('role') == 'user' for message in rest):
            break

    truncated = False
    if size() > limit:
        adjusted = max(128, min(adjusted, limit - estimate_tokens(system + rest) - 64))
    if size() > limit:
        for message in reversed(rest):
            if message.get('role') != 'user':
                continue
            content = message.get('content')
            others = [item for item in system + rest if item is not message]
            budget = max(400, (limit - estimate_tokens(others) - adjusted - 128) * 4)
            if isinstance(content, str) and len(content) > budget:
                message['content'] = content[-budget:]
                truncated = True
            elif isinstance(content, list):
                text = ''.join(part.get('text', '') for part in content if part.get('type') == 'text')
                if len(text) > budget:
                    message['content'] = [{'type': 'text', 'text': text[-budget:]}]
                    truncated = True
            break

    return system + rest, {'limit': limit, 'trimmed': trimmed, 'truncated': truncated,
                           'max_tokens': adjusted}


async def fetch_models(base_url, api_key, timeout=20):
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(base_url.rstrip('/') + '/models',
                                        headers={'Authorization': 'Bearer ' + api_key})
        if response.status_code != 200:
            return []
        data = response.json()
        return [item.get('id') or item.get('name') for item in data.get('data', data.get('models', []))
                if item.get('id') or item.get('name')]
    except (httpx.HTTPError, ValueError):
        return []


async def startup():
    changed = False
    for provider in providers:
        if not provider.get('models') and provider.get('api_keys'):
            provider['models'] = await fetch_models(provider['base_url'], provider['api_keys'][0])
            changed = True
    if changed:
        save_config(providers)
    pool.snapshot()


def loopback_request(request):
    host = (request.headers.get('host') or '')
    if host.startswith('['):
        host = host.split(']', 1)[0] + ']'
    else:
        host = host.split(':', 1)[0]
    return host.strip('[]').lower() in ('127.0.0.1', 'localhost', '::1')


@app.get('/')
async def root(request: Request):
    if os.path.isdir(STATIC_DIR):
        # Only the browser on this machine gets the token handed to it once; remote
        # clients still have to present it themselves.
        return RedirectResponse('/app/?token=' + quote(GATEWAY_TOKEN, safe='') if loopback_request(request) else '/app/')
    return {'name': 'ProxyPal', 'status': 'running', 'providers': len(providers)}


def safe_status(model=None):
    safe = []
    for provider in providers:
        settings = provider.get('key_settings', {})
        keys = provider.get('api_keys', [])
        custom = provider['provider'] not in PROVIDER_URLS
        enabled = any(settings.get(key_id(provider['provider'], key), {}).get('enabled', True) for key in keys)
        if not enabled and not (custom and not keys):
            continue
        safe.append({'provider': provider['provider'], 'key_count': len(keys),
                     'models': [m for m in provider.get('models', []) if is_chat_model(m)],
                     'custom': custom, 'base_url': provider.get('base_url')})
    return {'version': GATEWAY_VERSION, 'providers': safe, 'pool': pool.snapshot(model),
            'model_health': pool.model_health_snapshot()}


@app.get('/status')
async def status(model: Optional[str] = None):
    return safe_status(model)


@app.get('/health')
async def health():
    entries = pool.entries()
    states = [pool.state(entry) for entry in entries]
    return {'status': 'ok', 'version': GATEWAY_VERSION, 'uptime_s': round(time.time() - STARTED_AT),
            'providers': len(providers), 'keys': len(entries),
            'available': sum(1 for state in states if state in ('standby', 'active')),
            'blocked': sum(1 for state in states if state in ('blocked', 'disabled'))}


@app.get('/settings')
async def read_settings():
    return {'strategy': pool.settings.get('strategy', 'sticky')}


@app.patch('/settings')
async def update_settings(body: RoutingSettings):
    pool.set_strategy(body.strategy)
    logger.info('routing strategy=%s', body.strategy)
    return safe_status()


LOOPBACK_HOSTS = {'localhost', '127.0.0.1', '::1'}
BLOCKED_ADDRESSES = (ipaddress.ip_network('169.254.0.0/16'), ipaddress.ip_network('fd00:ec2::254/128'))


def blocked_address(value):
    try:
        address = ipaddress.ip_address(value.split('%', 1)[0])
    except ValueError:
        return False
    return address.is_link_local or any(address in network for network in BLOCKED_ADDRESSES)


async def resolves_to_blocked(host):
    if blocked_address(host):
        return True
    try:
        infos = await anyio.to_thread.run_sync(socket.getaddrinfo, host, None)
    except OSError:
        return False
    return any(blocked_address(info[4][0]) for info in infos)


async def validate_provider_url(url):
    """A custom provider receives the user's key, so never send it over cleartext
    to a remote host or to link-local/cloud-metadata addresses."""
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password:
        raise HTTPException(400, 'Base URL must be an http(s) URL without embedded credentials')
    host = (parsed.hostname or '').lower()
    if not host:
        raise HTTPException(400, 'Base URL must include a host')
    if parsed.scheme == 'http' and host not in LOOPBACK_HOSTS:
        raise HTTPException(400, 'Remote providers must use https:// (http:// is allowed only for localhost)')
    if await resolves_to_blocked(host):
        raise HTTPException(400, 'This host address is not allowed (link-local or cloud metadata)')


@app.post('/pool/providers')
async def add_provider(body: NewProvider):
    name = body.name.strip().lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{1,31}', name):
        raise HTTPException(400, 'Provider names use lowercase letters, digits, - and _')
    if name in PROVIDER_URLS:
        raise HTTPException(400, 'This provider name is reserved')
    if any(provider['provider'] == name for provider in providers):
        raise HTTPException(409, 'Provider already exists')
    url = body.base_url.strip().rstrip('/')
    await validate_provider_url(url)
    models = list(dict.fromkeys(model.strip() for model in body.models if model.strip() and is_chat_model(model)))
    if not models:
        raise HTTPException(400, 'Add at least one chat model id')
    providers.append({'provider': name, 'base_url': url, 'models': models, 'api_keys': []})
    save_config(providers)
    logger.info('provider add name=%s models=%d', name, len(models))
    return safe_status()


@app.delete('/pool/providers/{name}')
async def delete_provider(name: str):
    provider = next((item for item in providers if item['provider'] == name), None)
    if provider is None:
        raise HTTPException(404, 'Provider not found')
    if any(pool.reserved.get(key_id(name, key)) for key in provider.get('api_keys', [])):
        raise HTTPException(409, 'Wait for this provider to finish its current response')
    for key in provider.get('api_keys', []):
        pool.forget(key_id(name, key))
    providers.remove(provider)
    save_config(providers)
    logger.info('provider delete name=%s keys=%d', name, len(provider.get('api_keys', [])))
    return safe_status()


@app.patch('/pool/providers/{name}/models')
async def set_provider_models(name: str, body: ProviderModels):
    provider = next((item for item in providers if item['provider'] == name), None)
    if provider is None:
        raise HTTPException(404, 'Provider not found')
    models = list(dict.fromkeys(model.strip() for model in body.models if model.strip()))
    if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,199}', model) for model in models):
        raise HTTPException(400, 'Model ids may only contain letters, digits and . _ : / @ + -')
    rejected = [model for model in models if not is_chat_model(model)]
    if rejected:
        raise HTTPException(400, 'Not chat models: ' + ', '.join(rejected[:3]))
    if any(pool.reserved.get(key_id(name, key)) for key in provider.get('api_keys', [])):
        raise HTTPException(409, 'Wait for this provider to finish its current response')
    provider['models'] = models
    save_config(providers)
    logger.info('provider models name=%s count=%d', name, len(models))
    return safe_status()


@app.get('/v1/models')
async def list_models():
    seen = set()
    models = []
    for provider in providers:
        for model in provider.get('models', []):
            if is_chat_model(model) and model not in seen:
                seen.add(model)
                models.append({'id': model, 'object': 'model', 'provider': provider['provider'],
                               'context_window': context_limit(model)})
    return {'object': 'list', 'data': models}


async def validate_key(base_url, key):
    """Reject credentials the provider explicitly refuses; network failures stay unverified."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12, connect=5)) as client:
            response = await client.get(base_url.rstrip('/') + '/models',
                                        headers={'Authorization': 'Bearer ' + key})
    except (httpx.HTTPError, ValueError):
        return 'unverified'
    if credential_failure(response.status_code, response.text):
        return 'invalid'
    if 200 <= response.status_code < 300:
        return 'valid'
    return 'unverified'


@app.post('/pool/keys')
async def add_keys(body: AddKeys):
    provider_name = body.provider.strip().lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{1,31}', provider_name):
        raise HTTPException(400, 'Provider names use lowercase letters, digits, - and _')
    keys = list(dict.fromkeys(key.strip() for key in body.api_keys))
    if any(not key or len(key) > 4096 or any(char.isspace() for char in key) for key in keys):
        raise HTTPException(400, 'Keys must be nonempty values without whitespace')
    provider = next((p for p in providers if p['provider'] == provider_name), None)
    if provider is None:
        if provider_name not in PROVIDER_URLS:
            raise HTTPException(404, 'Create this custom provider first')
        provider = {'provider': provider_name, 'base_url': PROVIDER_URLS[provider_name],
                    'models': list(PROVIDER_MODELS.get(provider_name, [])), 'api_keys': []}
        providers.append(provider)
    fresh = [key for key in keys if key not in provider['api_keys']]
    semaphore = asyncio.Semaphore(5)

    async def check(key):
        async with semaphore:
            return await validate_key(provider['base_url'], key)

    verdicts = dict(zip(fresh, await asyncio.gather(*(check(key) for key in fresh)))) if fresh else {}
    for index, key in enumerate(fresh):
        if verdicts.get(key) == 'invalid':
            continue
        provider['api_keys'].append(key)
        settings = {'token_budget': body.token_budget, 'request_budget': body.request_budget,
                    'threshold': .9, 'budget_period': 'never'}
        if body.label and body.label.strip():
            settings['label'] = body.label.strip() + (f' · {index + 1}' if len(keys) > 1 else '')
        provider.setdefault('key_settings', {})[key_id(provider_name, key)] = settings
    added = sum(1 for key in fresh if verdicts.get(key) != 'invalid')
    validation = {'added': added, 'rejected': len(fresh) - added,
                  'unverified': sum(1 for key in fresh if verdicts.get(key) == 'unverified')}
    save_config(providers)
    if added and not provider.get('models'):
        provider['models'] = [model for model in await fetch_models(provider['base_url'], provider['api_keys'][0])
                              if is_chat_model(model)]
        save_config(providers)
    logger.info('keys add provider=%s added=%d rejected=%d unverified=%d', provider_name,
                validation['added'], validation['rejected'], validation['unverified'])
    return safe_status() | {'validation': validation}


def find_key(identity):
    entry = next((e for e in pool.entries() if e['id'] == identity), None)
    if not entry:
        raise HTTPException(404, 'Key not found')
    if pool.reserved.get(identity):
        raise HTTPException(409, 'Wait for this key to finish its current response')
    return entry


@app.patch('/pool/keys/{identity}')
async def update_key(identity: str, body: KeySettings):
    entry = find_key(identity)
    settings = entry['config'].setdefault('key_settings', {}).setdefault(identity, {})
    settings.update(body.model_dump(exclude_none=True))
    if body.enabled is True:
        pool.load(entry)['blocked'] = False
        pool.save(identity)
    save_config(providers)
    return safe_status()


@app.post('/pool/keys/{identity}/reset')
async def reset_key(identity: str):
    pool.reset(find_key(identity))
    return safe_status()


@app.delete('/pool/keys/{identity}')
async def delete_key(identity: str):
    entry = find_key(identity)
    provider = entry['config']
    provider['api_keys'] = [key for key in provider.get('api_keys', [])
                            if key_id(provider['provider'], key) != identity]
    provider.get('key_settings', {}).pop(identity, None)
    save_config(providers)
    pool.forget(identity)
    return safe_status()


@app.post('/config')
async def replace_config():
    raise HTTPException(405, 'Use /pool/keys to add keys without replacing existing accounts')


@app.post('/health/refresh')
async def refresh_health():
    return {'pool': pool.snapshot(), 'message': 'Passive monitoring; model tests run on demand'}


@app.post('/models/probe')
async def probe_model(body: ProbeRequest):
    requested = body.model
    if not any(p.get('api_keys') for p in providers):
        raise HTTPException(503, 'Add an API key in settings first')
    if not any(requested in p.get('models', []) for p in providers):
        raise HTTPException(400, 'Selected model is not available in this pool')
    messages = [{'role': 'user', 'content': 'ping'}]
    reserve_tokens = estimate_tokens(messages) + 1
    started = time.perf_counter()
    last = None
    candidates = [entry for entry in pool.entries() if requested in entry['config'].get('models', [])]
    for entry in candidates:
        reservation = await pool.reserve(entry, reserve_tokens)
        if reservation is None:
            continue
        data = None
        failed = False
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=8)) as client:
                # Reasoning models may reject max_tokens=1; retry once with a small budget.
                for budget in (1, 16):
                    upstream = {'model': requested, 'messages': messages, 'temperature': 0,
                                'max_tokens': budget, 'stream': False}
                    async with upstream_stream(client, entry, upstream) as response:
                        pool.headers(entry, response.headers)
                        if response.status_code != 200:
                            detail = (await response.aread()).decode('utf-8', errors='replace').lower()
                            last = {'reason': 'upstream', 'status': response.status_code}
                            if budget == 1 and response.status_code in (400, 422) and (
                                    'max_tokens' in detail or 'max tokens' in detail or 'length' in detail):
                                continue
                            pool.failure(entry, response.status_code, response.headers)
                            failed = True
                            break
                        reservation['accepted'] = True
                        pool.observe(entry, reservation, estimate_tokens(messages))
                        await response.aread()
                        data = response.json()
                        break
            if failed:
                continue
            if data.get('error') or not data.get('choices'):
                raise ValueError('Invalid response')
            reservation['usage'] = usage_tokens(data)
        except (httpx.HTTPError, ValueError):
            pool.failure(entry, 502)
            last = {'reason': 'upstream', 'status': 502}
            data = None
        finally:
            with anyio.CancelScope(shield=True):
                await pool.finish(entry, reservation)
        if data is not None:
            latency = round((time.perf_counter() - started) * 1000)
            pool.record_model(requested, True, latency_ms=latency)
            switched = pool.activate(entry['id'])
            return {'model': requested, 'ok': True, 'latency_ms': latency,
                    'gateway': metadata(entry, requested, switched)}
    latency = round((time.perf_counter() - started) * 1000)
    failure = last or {'reason': 'no_key'}
    pool.record_model(requested, False, failure['reason'], failure.get('status'), latency)
    return JSONResponse({'model': requested, 'ok': False, 'latency_ms': latency,
                         'reason': failure['reason'], 'status': failure.get('status')})


@app.post('/models/refresh')
async def refresh_models(body: RefreshRequest):
    """Fetch each provider's current catalog, then verify models in parallel.

    One usable key per provider is enough: a model that is missing from the account
    fails the same way on every key. The short timeout and the cap keep an update
    bounded even when a provider lists hundreds of models.
    """
    if not any(p.get('api_keys') for p in providers):
        raise HTTPException(503, 'Add an API key in settings first')

    # Retest request-level rejections instead of keeping a possibly key-caused 400 hidden.
    pool.clear_model_failures()

    fetches = []
    for provider in providers:
        keys = provider.get('api_keys') or []
        settings = provider.get('key_settings', {})
        key = next((candidate for candidate in keys
                    if settings.get(key_id(provider['provider'], candidate), {}).get('enabled', True)), None)
        if key:
            fetches.append((provider, key, fetch_models(provider.get('base_url', ''), key, timeout=15)))

    updated = 0
    verified = {}
    if fetches:
        results = await asyncio.gather(*(task for _, _, task in fetches), return_exceptions=True)
        changed = False
        for (provider, key, _), found in zip(fetches, results):
            if not isinstance(found, list) or not found:
                continue
            # A successful catalog fetch proves this key works; reuse it for probes so
            # an unrelated stale key cannot mark every model as broken.
            verified[provider['provider']] = key
            discovered = []
            gemini = 'generativelanguage.googleapis.com' in str(provider.get('base_url'))
            for raw in found:
                model = raw[len('models/'):] if gemini and isinstance(raw, str) and raw.startswith('models/') else raw
                if isinstance(model, str) and is_chat_model(model) and model not in discovered:
                    discovered.append(model)
            if not discovered:
                continue
            if provider['provider'] in PROVIDER_URLS:
                merged = discovered
            else:
                # A custom provider may expose extra aliases the user added by hand.
                merged = list(dict.fromkeys(list(provider.get('models') or []) + discovered))
            if merged != provider.get('models'):
                provider['models'] = merged
                changed = True
            updated += 1
        if changed:
            save_config(providers)

    entries = pool.entries()
    usable = {}
    for entry in entries:
        if not entry['enabled']:
            continue
        try:
            if pool.state(entry) not in ('standby', 'active'):
                continue
        except (KeyError, TypeError):
            continue
        usable.setdefault(entry['provider'], []).append(entry)

    selected = body.model
    plans = []
    seen = set()
    by_provider = {}
    for provider in providers:
        candidates = usable.get(provider['provider']) or []
        if not candidates:
            continue
        # Spread probes across accounts so one free-tier limit cannot stop the update,
        # but retry through the key that just proved itself against the catalog first.
        candidates.sort(key=lambda item: (item['key'] != verified.get(provider['provider']),
                                          pool.load(item)['requests']))
        by_provider[provider['provider']] = candidates
        models = [model for model in provider.get('models', []) if is_chat_model(model)]
        if selected in models:
            models = [selected] + [model for model in models if model != selected]
        for index, model in enumerate(models):
            if model in seen:
                continue
            seen.add(model)
            plans.append((candidates[index % len(candidates)], model))
    plans = plans[:REFRESH_MAX_MODELS]

    stats = {'probed': 0, 'ok': 0, 'failed': 0, 'skipped': 0, 'deadline': False}
    stopped = set()
    dead_keys = set()
    semaphore = asyncio.Semaphore(REFRESH_CONCURRENCY)
    timeout = httpx.Timeout(12, connect=5)

    async with httpx.AsyncClient(timeout=timeout) as client:
        async def check(entry, model):
            async with semaphore:
                alternatives = [entry] + [item for item in by_provider.get(entry['provider'], [])
                                          if item['id'] != entry['id']]
                attempts = 0
                for candidate in alternatives:
                    if candidate['provider'] in stopped:
                        break
                    if candidate['id'] in dead_keys:
                        continue
                    reservation = await pool.reserve(candidate, 16)
                    if reservation is None:
                        continue
                    attempts += 1
                    started = time.perf_counter()
                    retry = False
                    try:
                        response = await client.post(
                            candidate['config']['base_url'].rstrip('/') + '/chat/completions',
                            headers={'Authorization': 'Bearer ' + candidate['key'],
                                     'Content-Type': 'application/json'},
                            json={'model': model, 'messages': [{'role': 'user', 'content': 'ping'}],
                                  'max_tokens': 16, 'stream': False})
                        pool.headers(candidate, response.headers)
                        latency = round((time.perf_counter() - started) * 1000)
                        if response.status_code == 200:
                            try:
                                data = response.json()
                            except ValueError:
                                data = {}
                            if data.get('error') or not data.get('choices'):
                                raise ValueError('Invalid response')
                            reservation['accepted'] = True
                            reservation['usage'] = usage_tokens(data)
                            pool.record_model(model, True, latency_ms=latency)
                            stats['ok'] += 1
                            stats['probed'] += 1
                            return
                        if credential_failure(response.status_code, response.text):
                            # A bad key says nothing about the model; retire it and retry elsewhere.
                            pool.failure(candidate, 401, response.headers)
                            dead_keys.add(candidate['id'])
                            retry = True
                        elif response.status_code == 429:
                            # Probe bursts can hit a per-model window. That is not proof the
                            # account is exhausted, so never cool the key and block chat.
                            retry = True
                        else:
                            pool.record_model(model, False, 'upstream', response.status_code, latency)
                            stats['failed'] += 1
                            stats['probed'] += 1
                            if response.status_code in (401, 402, 403):
                                stopped.add(candidate['provider'])
                                pool.failure(candidate, response.status_code, response.headers)
                            return
                    except (httpx.HTTPError, ValueError):
                        pool.record_model(model, False, 'upstream', 502,
                                          round((time.perf_counter() - started) * 1000))
                        stats['failed'] += 1
                        stats['probed'] += 1
                        return
                    finally:
                        with anyio.CancelScope(shield=True):
                            await pool.finish(candidate, reservation)
                    if not retry or attempts >= 2:
                        break
                # No verdict: rate limits or unusable credentials, not a model failure.
                stats['skipped'] += 1

        if plans:
            try:
                await asyncio.wait_for(asyncio.gather(*(check(entry, model) for entry, model in plans)),
                                       timeout=REFRESH_DEADLINE)
            except asyncio.TimeoutError:
                stats['deadline'] = True

    logger.info('models refresh providers=%d probed=%d ok=%d failed=%d skipped=%d deadline=%s',
                updated, stats['probed'], stats['ok'], stats['failed'], stats['skipped'], stats['deadline'])
    response = safe_status(selected)
    response['refresh'] = {**stats, 'providers': updated}
    return response


def payload(req, model, messages, max_tokens):
    body = {'model': model, 'messages': messages,
            'temperature': req.temperature, 'top_p': req.top_p, 'max_tokens': max_tokens,
            'stream': req.stream}
    if req.reasoning_effort:
        body['reasoning_effort'] = req.reasoning_effort
    if req.stream:
        body['stream_options'] = {'include_usage': True}
    return body


def usage_tokens(data):
    usage = data.get('usage') or (data.get('x_groq') or {}).get('usage') or {}
    total = usage.get('total_tokens')
    if total is None and 'prompt_tokens' in usage and 'completion_tokens' in usage:
        total = usage['prompt_tokens'] + usage['completion_tokens']
    return max(0, int(total)) if isinstance(total, (int, float)) else None


def candidate_list(requested):
    entries = pool.ordered(requested)
    preferred = [(entry, requested) for entry in entries if requested in entry['config'].get('models', [])]
    fallback = []
    for entry in entries:
        models = [m for m in entry['config'].get('models', []) if m != requested and is_chat_model(m)]
        healthy = [m for m in models if pool.model_health.get(m, {}).get('ok') is True]
        model = (healthy or models or [None])[0]
        if model:
            fallback.append((entry, model))
    return preferred + fallback


def note_failure(state, entry, model, status, requested):
    state.update(reason='upstream', status=status, provider=entry['provider'], model=model)
    if status == 402:
        state['billing'] = True
    elif status == 404 and model == requested:
        state['model_missing'] = True
    elif status in (408, 504):
        state['timeout'] = True


def final_error(state, requested):
    if state.get('billing'):
        code = 'billing'
    elif not state.get('attempts'):
        code = 'no_key'
    elif state.get('model_missing'):
        code = 'model_unavailable'
    elif state.get('timeout'):
        code = 'timeout'
    elif state.get('status') in (400, 422):
        code = 'request'
    else:
        code = 'upstream'
    status = state.get('status')
    messages = {
        'no_key': 'No key is available right now. Check budgets, cooldowns and credentials in settings.',
        'billing': 'The provider refused the request because the account has no remaining credit (HTTP 402). Top up or use another account.',
        'model_unavailable': 'The selected model is not available from the configured providers (HTTP 404). Pick another model.',
        'timeout': 'The provider did not respond in time. Try again or use another key.',
        'request': f'The provider rejected the request (HTTP {status}). Check the model and parameters.',
        'upstream': f'Every available key failed at the provider (last HTTP {status}). Try again or check the keys.',
    }
    return {'error': {'code': code, 'status': status, 'provider': state.get('provider'),
                      'model': state.get('model'), 'message': messages[code]}}


class PoolStreamingResponse(StreamingResponse):
    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await self.body_iterator.aclose()


def metadata(entry, model, switched, context=None):
    result = {'key_id': entry['id'], 'provider': entry['provider'], 'label': entry['label'],
              'model': model, 'switched': switched, 'pool': pool.snapshot()}
    if context and (context['trimmed'] or context['truncated']):
        result['context'] = {'limit': context['limit'], 'trimmed': context['trimmed'],
                             'truncated': context['truncated'], 'max_tokens': context['max_tokens']}
    return result


def sse(data):
    return 'data: ' + json.dumps(data, ensure_ascii=False) + '\n\n'


@asynccontextmanager
async def upstream_stream(client, entry, body):
    url = entry['config']['base_url'].rstrip('/') + '/chat/completions'
    headers = {'Authorization': 'Bearer ' + entry['key'], 'Content-Type': 'application/json'}
    async with client.stream('POST', url, headers=headers, json=body) as response:
        retry = False
        if response.status_code == 400 and 'stream_options' in body:
            diagnostic = (await response.aread()).decode('utf-8', errors='replace').lower()
            retry = 'stream_options' in diagnostic or 'include_usage' in diagnostic
        if not retry:
            yield response
            return
    body = {key: value for key, value in body.items() if key != 'stream_options'}
    async with client.stream('POST', url, headers=headers, json=body) as response:
        yield response


@app.post('/v1/chat/completions')
async def chat(req: ChatRequest):
    if not any(p.get('api_keys') for p in providers):
        raise HTTPException(503, 'Add an API key in settings first')
    if req.model and not any(req.model in p.get('models', []) for p in providers):
        raise HTTPException(400, 'Selected model is not available in this pool')
    if req.model and not is_chat_model(req.model):
        raise HTTPException(400, 'Selected model is not a chat model')
    messages = [m.model_dump() for m in req.messages]
    candidates = candidate_list(req.model)
    requested = req.model
    last_failure = {'reason': 'no_key', 'attempts': 0}
    unavailable = set()
    # Round-robin already moves the active key between requests, so pool.activate() cannot report
    # a mid-request failover. The first candidate is the key the user was expected to be served by.
    first_candidate = candidates[0][0]['id'] if candidates else None

    async def responses():
        for entry, model in candidates:
            if model in unavailable:
                continue
            fitted, context = fit_messages(messages, model, req.max_tokens)
            reserve_tokens = estimate_tokens(fitted) + context['max_tokens']
            reservation = await pool.reserve(entry, reserve_tokens)
            if reservation is None:
                continue
            last_failure['attempts'] += 1
            emitted = False
            complete = False
            output = ''
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(90, connect=15)) as client:
                    async with upstream_stream(client, entry, payload(req, model, fitted, context['max_tokens'])) as response:
                        pool.headers(entry, response.headers)
                        if response.status_code != 200:
                            detail = (await response.aread()).decode('utf-8', errors='replace')
                            code = 401 if credential_failure(response.status_code, detail) else response.status_code
                            note_failure(last_failure, entry, model, code, requested)
                            if response.status_code == 404:
                                unavailable.add(model)
                            pool.failure(entry, code, response.headers)
                            logger.warning('chat upstream provider=%s model=%s status=%s', entry['provider'], model,
                                           response.status_code)
                            continue
                        reservation['accepted'] = True
                        pool.observe(entry, reservation, estimate_tokens(fitted))
                        pool.activate(entry['id'])
                        switched = entry['id'] != first_candidate
                        yield sse({'_gateway': metadata(entry, model, switched, context)})
                        data_lines = []
                        async for line in response.aiter_lines():
                            if line.startswith('data:'):
                                data_lines.append(line[5:].lstrip())
                                continue
                            if line or not data_lines:
                                continue
                            event = '\n'.join(data_lines)
                            data_lines = []
                            if event == '[DONE]':
                                complete = True
                                break
                            try:
                                data = json.loads(event)
                            except ValueError:
                                continue
                            if data.get('error'):
                                raise ValueError('Upstream streaming error')
                            tokens = usage_tokens(data)
                            if tokens is not None:
                                reservation['usage'] = tokens
                            for choice in data.get('choices', []):
                                delta = choice.get('delta') or {}
                                # Google thinking models stream their deliberation inside content with a thought
                                # flag; the UI shows that under reasoning, never as the answer.
                                if ((delta.get('extra_content') or {}).get('google') or {}).get('thought') is True and delta.get('content'):
                                    delta['reasoning'] = (delta.get('reasoning') or '') + delta.pop('content')
                                for field in ('content', 'reasoning'):
                                    if delta.get(field):
                                        delta[field] = delta[field].replace('<thought>', '').replace('</thought>', '')
                                text = (delta.get('content') or '') + (delta.get('reasoning') or delta.get('reasoning_content') or '')
                                text += ''.join(item.get('text', '') for item in delta.get('reasoning_details', []) if isinstance(item, dict))
                                if text:
                                    emitted = True
                                    output += text
                                    pool.observe(entry, reservation, estimate_tokens(fitted, output))
                                if choice.get('finish_reason') is not None:
                                    complete = True
                            yield sse(data)
                        if data_lines and data_lines != ['[DONE]']:
                            try:
                                trailing = json.loads('\n'.join(data_lines))
                                tokens = usage_tokens(trailing)
                                if tokens is not None:
                                    reservation['usage'] = tokens
                            except ValueError:
                                pass
                        if not complete or not emitted:
                            raise ValueError('Incomplete or empty response')
            except (httpx.HTTPError, ValueError):
                pool.failure(entry, 502)
                last_failure.update(reason='stream')
                logger.warning('chat stream failed provider=%s model=%s emitted=%s', entry['provider'], model, emitted)
                if emitted:
                    if requested:
                        pool.record_model(requested, False, 'stream')
                    yield sse({'error': {'code': 'stream_interrupted',
                                         'message': 'The stream was interrupted. The received part was kept; retry without losing the conversation.'}})
                    return
            finally:
                with anyio.CancelScope(shield=True):
                    await pool.finish(entry, reservation)
            if complete and emitted:
                if requested:
                    pool.record_model(requested, model == requested, None if model == requested else 'fallback')
                else:
                    pool.record_model(model, True)
                pool.rotate(entry)
                logger.info('chat ok provider=%s model=%s trimmed=%d tokens=%s', entry['provider'], model,
                            context['trimmed'], reservation.get('usage'))
                yield sse({'_gateway': metadata(entry, model, switched, context)})
                yield 'data: [DONE]\n\n'
                return
        if requested:
            pool.record_model(requested, False, last_failure.get('reason'), last_failure.get('status'))
        yield sse(final_error(last_failure, requested))
        yield 'data: [DONE]\n\n'

    if req.stream:
        return PoolStreamingResponse(responses(), media_type='text/event-stream',
                                     headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
    for entry, model in candidates:
        if model in unavailable:
            continue
        fitted, context = fit_messages(messages, model, req.max_tokens)
        reserve_tokens = estimate_tokens(fitted) + context['max_tokens']
        reservation = await pool.reserve(entry, reserve_tokens)
        if reservation is None:
            continue
        last_failure['attempts'] += 1
        data = None
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                async with upstream_stream(client, entry, payload(req, model, fitted, context['max_tokens'])) as response:
                    pool.headers(entry, response.headers)
                    if response.status_code != 200:
                        note_failure(last_failure, entry, model, response.status_code, requested)
                        if response.status_code == 404:
                            unavailable.add(model)
                        pool.failure(entry, response.status_code, response.headers)
                        continue
                    reservation['accepted'] = True
                    pool.observe(entry, reservation, estimate_tokens(fitted))
                    await response.aread()
                    data = response.json()
            if data.get('error') or not data.get('choices'):
                raise ValueError('Invalid response')
            reservation['usage'] = usage_tokens(data)
            pool.observe(entry, reservation, estimate_tokens(fitted, json.dumps(data.get('choices'), ensure_ascii=False)))
            pool.activate(entry['id'])
            switched = entry['id'] != first_candidate
        except (httpx.HTTPError, ValueError):
            pool.failure(entry, 502)
            last_failure.update(reason='upstream', status=502)
            data = None
        finally:
            with anyio.CancelScope(shield=True):
                await pool.finish(entry, reservation)
        if data is not None:
            if requested:
                pool.record_model(requested, model == requested, None if model == requested else 'fallback')
            else:
                pool.record_model(model, True)
            pool.rotate(entry)
            logger.info('chat ok provider=%s model=%s trimmed=%d tokens=%s', entry['provider'], model,
                        context['trimmed'], reservation.get('usage'))
            data['_gateway'] = metadata(entry, model, switched, context)
            return JSONResponse(data)
    if requested:
        pool.record_model(requested, False, last_failure.get('reason'), last_failure.get('status'))
    return JSONResponse(final_error(last_failure, requested), status_code=503)


class WorkspaceReq(BaseModel):
    path: str
    filename: Optional[str] = None
    content: Optional[str] = None


SNAPSHOT_MAX_FILES = 40
SNAPSHOT_SKIP_DIRS = {'node_modules', '.git', '__pycache__', '.venv', 'venv', 'dist', 'build',
                      '.ssh', '.aws', '.gnupg', '.docker'}
SNAPSHOT_SKIP_NAMES = {'.npmrc', '.pypirc', '.netrc', '.git-credentials'}
SNAPSHOT_SKIP_PATTERNS = ('id_rsa*', 'id_ed25519*', 'id_ecdsa*', '*.pem', '*.key', '*.p12', '*.pfx',
                          '*.kdbx', '*.keystore', 'credentials*', '*secret*', '*token*',
                          '*password*', '*.tfstate')
HOME_ROOT = os.path.realpath(os.path.expanduser('~'))
SYSTEM_ROOTS = tuple(os.path.realpath(path) for path in (
    '/etc', '/usr', '/bin', '/sbin', '/lib', '/lib64', '/boot', '/dev', '/proc', '/sys', '/root',
    'C:\\Windows', 'C:\\Program Files', 'C:\\Program Files (x86)', 'C:\\ProgramData',
))


def is_sensitive_root(root):
    """The workspace snapshot sends file contents to a provider, so refuse folders
    that hold the whole system or the user's entire profile."""
    if root == HOME_ROOT:
        return True
    drive, tail = os.path.splitdrive(root)
    if drive and not tail.strip('\\/'):
        return True
    if os.path.dirname(root) == root:
        return True
    for system in SYSTEM_ROOTS:
        try:
            if root == system or os.path.commonpath([system, root]) == system:
                return True
        except ValueError:
            continue
    return False


def snapshot_skip_name(name):
    lowered = name.lower()
    if lowered.startswith('.env') or lowered in ('gateway_config.json', 'gateway.db', '.gateway_token'):
        return True
    if lowered in SNAPSHOT_SKIP_NAMES:
        return True
    return any(fnmatch.fnmatch(lowered, pattern) for pattern in SNAPSHOT_SKIP_PATTERNS)


def looks_like_private_key(text):
    return '-----BEGIN' in text and 'PRIVATE KEY' in text


def workspace_root(path):
    root = os.path.realpath(path)
    if is_sensitive_root(root):
        raise HTTPException(403, 'This folder cannot be used as a workspace')
    if WORKSPACE_ROOT:
        try:
            allowed = os.path.commonpath([WORKSPACE_ROOT, root]) == WORKSPACE_ROOT
        except ValueError:
            allowed = False
        if not allowed:
            raise HTTPException(403, 'Workspace path is outside WORKSPACE_ROOT')
    return root


def workspace_file(req):
    if not req.filename:
        raise HTTPException(400, 'filename required')
    root = workspace_root(req.path)
    full = os.path.realpath(os.path.join(root, req.filename))
    try:
        contained = os.path.commonpath([root, full]) == root
    except ValueError:
        contained = False
    if not contained:
        raise HTTPException(403, 'Path traversal blocked')
    return full


@app.post('/workspace/list')
async def ws_list(req: WorkspaceReq):
    root = workspace_root(req.path)
    if not os.path.isdir(root):
        raise HTTPException(400, 'Not a directory')
    return {'root': root, 'entries': [{'name': name, 'type': 'dir' if os.path.isdir(os.path.join(root, name)) else 'file',
                                      'path': os.path.join(root, name)} for name in sorted(os.listdir(root))]}


@app.post('/workspace/read')
async def ws_read(req: WorkspaceReq):
    full = workspace_file(req)
    if not os.path.isfile(full):
        raise HTTPException(404, 'File not found')
    with open(full, encoding='utf-8', errors='replace') as file:
        return {'path': full, 'content': file.read()}


@app.post('/workspace/write')
async def ws_write(req: WorkspaceReq):
    if not WORKSPACE_ROOT:
        raise HTTPException(403, 'Workspace writes require WORKSPACE_ROOT')
    full = workspace_file(req)
    if req.content is None:
        raise HTTPException(400, 'content required')
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w', encoding='utf-8') as file:
        file.write(req.content)
    return {'ok': True, 'path': full}


@app.get('/workspace/root')
async def ws_root():
    return {'root': WORKSPACE_ROOT or ''}


@app.post('/workspace/snapshot')
async def ws_snapshot(req: WorkspaceReq):
    root = workspace_root(req.path)
    if not os.path.isdir(root):
        raise HTTPException(400, 'Not a directory')
    files = []
    skipped = 0
    for directory, subdirs, names in os.walk(root):
        subdirs[:] = [d for d in subdirs if d not in SNAPSHOT_SKIP_DIRS]
        for name in names:
            if snapshot_skip_name(name):
                skipped += 1
                continue
            full = os.path.join(directory, name)
            try:
                if not os.path.isfile(full) or os.path.getsize(full) > 400_000:
                    skipped += 1
                    continue
                if os.path.commonpath([root, os.path.realpath(full)]) != root:
                    skipped += 1
                    continue
                with open(full, encoding='utf-8') as file:
                    content = file.read(4000)
            except (OSError, UnicodeError, ValueError):
                skipped += 1
                continue
            if looks_like_private_key(content):
                skipped += 1
                continue
            files.append({'path': os.path.relpath(full, root), 'content': content})
            if len(files) >= SNAPSHOT_MAX_FILES:
                return {'root': root, 'files': files, 'skipped': skipped}
    return {'root': root, 'files': files, 'skipped': skipped}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host=os.getenv('GATEWAY_HOST', '127.0.0.1'), port=int(os.getenv('GATEWAY_PORT', '8790')))
