import asyncio
import hashlib
import json
import math
import re
import sqlite3
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def key_id(provider, key):
    return hashlib.sha256((provider + ':' + key).encode()).hexdigest()[:24]


PERIODS = {'never': 0, 'daily': 86400, 'weekly': 7 * 86400, 'monthly': 30 * 86400}
STRATEGIES = ('sticky', 'round_robin', 'least_used')


def estimate_tokens(messages, output=''):
    characters = len(output)
    image_tokens = 0
    for message in messages:
        content = message.get('content')
        characters += 16
        if isinstance(content, str):
            characters += len(content)
        elif isinstance(content, list):
            for part in content:
                if part.get('type') == 'text':
                    characters += len(part.get('text', ''))
                elif part.get('type') == 'image_url':
                    image_tokens += 1536
        elif content is not None:
            characters += len(json.dumps(content, ensure_ascii=False))
    return max(1, math.ceil(characters / 4) + image_tokens)


def reset_time(value, now):
    if not value:
        return now + 60
    try:
        number = float(value)
        return number if number > 1000000000 else now + max(0, number)
    except ValueError:
        pass
    parts = re.findall(r'(\d+(?:\.\d+)?)(ms|d|h|m|s)', value)
    if parts:
        factors = {'ms': .001, 's': 1, 'm': 60, 'h': 3600, 'd': 86400}
        return now + sum(float(n) * factors[unit] for n, unit in parts)
    try:
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return (date if date.tzinfo else date.replace(tzinfo=timezone.utc)).timestamp()
    except ValueError:
        try:
            return parsedate_to_datetime(value).timestamp()
        except (ValueError, TypeError):
            return now + 60


class APIPool:
    def __init__(self, db_path, get_providers, is_chat_model):
        self.db_path = db_path
        self.get_providers = get_providers
        self.is_chat_model = is_chat_model
        self.lock = asyncio.Lock()
        self.active_id = None
        self.switch_count = 0
        self.last_switch = None
        self.usage = {}
        self.reserved = {}
        self.pending = {}
        self.model_health = {}
        self.settings = {'strategy': 'sticky'}
        with sqlite3.connect(db_path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS pool_usage (key_id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS model_health (model TEXT PRIMARY KEY, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS pool_settings (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
            row = db.execute("SELECT value FROM pool_settings WHERE name='routing'").fetchone()
            if row:
                try:
                    stored = json.loads(row[0])
                except (TypeError, ValueError):
                    stored = {}
                if isinstance(stored, dict) and stored.get('strategy') in STRATEGIES:
                    self.settings['strategy'] = stored['strategy']
            cutoff = time.time() - 7 * 86400
            for model, data in db.execute('SELECT model, data FROM model_health').fetchall():
                try:
                    record = json.loads(data)
                except (TypeError, ValueError):
                    continue
                if isinstance(record, dict) and record.get('at', 0) >= cutoff:
                    self.model_health[model] = record

    def record_model(self, model, ok, reason=None, status=None, latency_ms=None):
        if not model:
            return
        record = {'ok': bool(ok), 'at': time.time(), 'reason': reason, 'status': status, 'latency_ms': latency_ms}
        self.model_health[model] = record
        with sqlite3.connect(self.db_path) as db:
            db.execute('INSERT OR REPLACE INTO model_health (model, data) VALUES (?,?)',
                       (model, json.dumps(record)))

    def model_health_snapshot(self):
        cutoff = time.time() - 7 * 86400
        return {model: record for model, record in self.model_health.items() if record.get('at', 0) >= cutoff}

    def clear_model_failures(self, statuses=(400,)):
        """Forget request-level rejections before a refresh retests the catalog.

        A 400 can come from one bad key (some providers say 400, not 401), so it must
        not stay hidden for a week after the key itself has been retired.
        """
        removed = [model for model, record in self.model_health.items()
                   if record.get('ok') is False and record.get('status') in statuses]
        if not removed:
            return 0
        with sqlite3.connect(self.db_path) as db:
            db.executemany('DELETE FROM model_health WHERE model=?', [(model,) for model in removed])
        for model in removed:
            self.model_health.pop(model, None)
        return len(removed)

    def set_strategy(self, strategy):
        if strategy not in STRATEGIES:
            raise ValueError('Unknown routing strategy')
        self.settings['strategy'] = strategy
        with sqlite3.connect(self.db_path) as db:
            db.execute('INSERT OR REPLACE INTO pool_settings (name,value) VALUES (?,?)',
                       ('routing', json.dumps({'strategy': strategy})))
        return self.settings['strategy']

    def entries(self):
        result = []
        seen = set()
        for pi, provider in enumerate(self.get_providers()):
            for ki, key in enumerate(provider.get('api_keys', [])):
                identity = key_id(provider['provider'], key)
                if identity in seen:
                    continue
                seen.add(identity)
                settings = provider.get('key_settings', {}).get(identity, {})
                result.append({'id': identity, 'pi': pi, 'ki': ki, 'key': key, 'config': provider,
                               'provider': provider['provider'],
                               'label': settings.get('label', f"{provider['provider']} · {ki + 1:02}"),
                               'enabled': settings.get('enabled', True),
                               'token_budget': settings.get('token_budget', provider.get('quota_limit_tokens') or 100000),
                               'request_budget': settings.get('request_budget', provider.get('quota_limit_requests') or 1000),
                               'threshold': settings.get('threshold', .9),
                               'budget_period': settings.get('budget_period', 'never')
                               if settings.get('budget_period', 'never') in PERIODS else 'never'})
        return result

    def load(self, entry):
        identity = entry['id']
        if identity not in self.usage:
            with sqlite3.connect(self.db_path) as db:
                row = db.execute('SELECT data FROM pool_usage WHERE key_id=?', (identity,)).fetchone()
                legacy = None
                if row is None:
                    exists = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='quota'").fetchone()
                    if exists:
                        legacy = db.execute('SELECT SUM(requests),SUM(tokens),SUM(errors) FROM quota WHERE qkey LIKE ?',
                                            (f"{entry['pi']}:{entry['ki']}:%",)).fetchone()
            self.usage[identity] = json.loads(row[0]) if row else {
                'requests': (legacy[0] or 0) if legacy else 0,
                'reported_tokens': (legacy[1] or 0) if legacy else 0,
                'estimated_tokens': 0, 'errors': (legacy[2] or 0) if legacy else 0,
                'cooldown_until': 0, 'blocked': False, 'rate_limits': {}, 'last_used': None}
            if row is None:
                self.save(identity)
            usage = self.usage[identity]
            changed = False
            for field, default in (('failures', 0), ('last_error', None), ('period_start', 0)):
                if field not in usage:
                    usage[field] = default
                    changed = True
            # Older versions recorded a 402 as a generic request error. The evidence is still
            # definitive: keep the account blocked with an accurate reason after an upgrade.
            last_error = usage.get('last_error')
            if not usage.get('blocked') and isinstance(last_error, dict) and last_error.get('status') == 402:
                usage['blocked'] = True
                usage['last_error'] = {**last_error, 'reason': 'billing'}
                changed = True
            if changed:
                self.save(identity)
        return self.usage[identity]

    def refresh_period(self, entry, now=None):
        now = now or time.time()
        seconds = PERIODS.get(entry.get('budget_period', 'never'), 0)
        if not seconds:
            return False
        usage = self.load(entry)
        if not usage.get('period_start'):
            usage['period_start'] = now
            self.save(entry['id'])
            return False
        if now - usage['period_start'] < seconds:
            return False
        usage.update(requests=0, reported_tokens=0, estimated_tokens=0, period_start=now)
        self.save(entry['id'])
        return True

    def save(self, identity):
        with sqlite3.connect(self.db_path) as db:
            db.execute('INSERT OR REPLACE INTO pool_usage (key_id,data) VALUES (?,?)',
                       (identity, json.dumps(self.usage[identity])))

    def state(self, entry, now=None):
        now = now or time.time()
        self.refresh_period(entry, now)
        usage = self.load(entry)
        if not entry['enabled']:
            return 'disabled'
        if usage['blocked']:
            return 'blocked'
        if usage['cooldown_until'] > now:
            return 'cooldown'
        tokens = usage['reported_tokens'] + usage['estimated_tokens']
        if tokens >= entry['token_budget'] * entry['threshold'] or usage['requests'] >= entry['request_budget'] * entry['threshold']:
            return 'budget'
        for window in usage['rate_limits'].values():
            if window['reset_at'] > now and window['limit'] - window['remaining'] >= window['limit'] * entry['threshold']:
                return 'cooldown'
        if not any(self.is_chat_model(m) for m in entry['config'].get('models', [])):
            return 'blocked'
        return 'standby'

    def ordered(self, model=None):
        entries = self.entries()

        def preferred(entry):
            return 0 if model and model in entry['config'].get('models', []) else 1

        if self.settings.get('strategy') == 'least_used':
            def score(entry):
                usage = self.load(entry)
                used = usage['requests'] + (usage['reported_tokens'] + usage['estimated_tokens']) / max(1, entry['token_budget'])
                return (preferred(entry), used, 0 if entry['id'] == self.active_id else 1)
            entries.sort(key=score)
        else:
            entries.sort(key=lambda e: (preferred(e), 0 if e['id'] == self.active_id else 1))
        return entries

    def activate(self, identity):
        if self.active_id == identity:
            return False
        previous = self.active_id
        self.active_id = identity
        if previous:
            self.switch_count += 1
            self.last_switch = {'from': previous, 'to': identity, 'at': time.time()}
        return bool(previous)

    def rotate(self, entry):
        """Advance to the next healthy account after a successful round-robin request."""
        if self.settings.get('strategy') != 'round_robin':
            return False
        entries = self.entries()
        if len(entries) < 2:
            return False
        ids = [item['id'] for item in entries]
        start = ids.index(entry['id']) if entry['id'] in ids else 0
        rotated = entries[start + 1:] + entries[:start + 1]
        upcoming = next((item for item in rotated
                         if item['id'] != entry['id'] and self.state(item) == 'standby'), None)
        return self.activate(upcoming['id']) if upcoming else False

    def snapshot(self, model=None):
        entries = self.entries()
        eligible = [e for e in self.ordered(model) if self.state(e) == 'standby']
        active = next((e for e in entries if e['id'] == self.active_id), None)
        if not active or (not self.reserved.get(active['id']) and self.state(active) != 'standby'):
            self.activate(eligible[0]['id'] if eligible else None)
        elif model and model not in active['config'].get('models', []) and eligible and not self.reserved.get(active['id']):
            self.activate(eligible[0]['id'])
        upcoming = next((e for e in eligible if e['id'] != self.active_id), None)
        keys = []
        now = time.time()
        for entry in entries:
            usage = self.load(entry)
            pending = self.pending.get(entry['id'], 0)
            tokens = usage['reported_tokens'] + usage['estimated_tokens'] + pending
            state = self.state(entry, now)
            if entry['id'] == self.active_id and state == 'standby':
                state = 'active'
            rate_limits = {name: window for name, window in usage['rate_limits'].items() if window['reset_at'] > now}
            cooldown = max([usage['cooldown_until']] + [w['reset_at'] for w in rate_limits.values()
                           if w['limit'] - w['remaining'] >= w['limit'] * entry['threshold']])
            keys.append({k: entry[k] for k in ('id', 'provider', 'label', 'enabled', 'token_budget',
                                                       'request_budget', 'threshold', 'budget_period')} |
                        {'masked_key': '••••' + entry['key'][-4:], 'state': state,
                         'tokens': tokens, 'reported_tokens': usage['reported_tokens'],
                         'estimated_tokens': usage['estimated_tokens'] + pending, 'requests': usage['requests'],
                         'token_percent': min(100, round(tokens / entry['token_budget'] * 100, 2)),
                         'request_percent': min(100, round(usage['requests'] / entry['request_budget'] * 100, 2)),
                         'cooldown_until': cooldown if cooldown > now else 0, 'rate_limits': rate_limits,
                         'errors': usage['errors'], 'failures': usage.get('failures', 0),
                         'last_error': usage.get('last_error'), 'last_used': usage['last_used']})
        return {'keys': keys, 'active_id': self.active_id, 'next_id': upcoming['id'] if upcoming else None,
                'switch_count': self.switch_count, 'last_switch': self.last_switch, 'scope': 'local_budget',
                'strategy': self.settings.get('strategy', 'sticky')}

    async def reserve(self, entry, tokens):
        async with self.lock:
            current = next((e for e in self.entries() if e['id'] == entry['id']), None)
            if current is None:
                return None
            entry.update(current)
            usage = self.load(entry)
            reserved = self.reserved.get(entry['id'], {'tokens': 0, 'requests': 0})
            if self.state(entry) != 'standby':
                return None
            consumed = usage['reported_tokens'] + usage['estimated_tokens'] + reserved['tokens']
            if consumed >= entry['token_budget'] * entry['threshold'] or usage['requests'] + reserved['requests'] >= entry['request_budget'] * entry['threshold']:
                return None
            if consumed + tokens > entry['token_budget']:
                return None
            if usage['requests'] + reserved['requests'] + 1 > entry['request_budget']:
                return None
            now = time.time()
            for name, window in usage['rate_limits'].items():
                needed = tokens + reserved['tokens'] if name == 'tokens' else 1 + reserved['requests']
                if window['reset_at'] > now and needed > window['remaining']:
                    return None
            self.reserved[entry['id']] = {'tokens': reserved['tokens'] + tokens, 'requests': reserved['requests'] + 1}
            return {'tokens': tokens, 'observed': 0, 'accepted': False, 'usage': None}

    def observe(self, entry, reservation, tokens):
        delta = tokens - reservation['observed']
        self.pending[entry['id']] = self.pending.get(entry['id'], 0) + delta
        reservation['observed'] = tokens

    def headers(self, entry, headers):
        usage = self.load(entry)
        now = time.time()
        for name in ('tokens', 'requests'):
            limit = headers.get(f'x-ratelimit-limit-{name}')
            remaining = headers.get(f'x-ratelimit-remaining-{name}')
            if limit is None or remaining is None:
                continue
            try:
                usage['rate_limits'][name] = {'limit': float(limit), 'remaining': float(remaining),
                                             'reset_at': reset_time(headers.get(f'x-ratelimit-reset-{name}'), now)}
            except ValueError:
                continue
        self.save(entry['id'])

    def failure(self, entry, code, headers=None):
        usage = self.load(entry)
        now = time.time()
        usage['errors'] += 1
        usage['failures'] = usage.get('failures', 0) + 1
        reason = 'request'
        if code in (401, 403):
            usage['blocked'] = True
            reason = 'credentials'
        elif code == 402:
            # The account itself has no credit left; other keys stay usable.
            usage['blocked'] = True
            reason = 'billing'
        elif code == 404:
            reason = 'model_missing'
        elif code == 429:
            deadline = reset_time((headers or {}).get('retry-after'), now)
            deadlines = [w['reset_at'] for w in usage['rate_limits'].values() if w['remaining'] <= 0]
            usage['cooldown_until'] = max([deadline] + deadlines)
            reason = 'rate_limit'
        elif code in (408, 504):
            usage['cooldown_until'] = now + 20
            reason = 'timeout'
        elif code >= 500:
            # Circuit breaker: repeated upstream failures back off progressively (15s → 5m).
            delay = min(300, 15 * 2 ** min(usage['failures'] - 1, 4))
            usage['cooldown_until'] = now + delay
            reason = 'upstream'
        usage['last_error'] = {'status': code, 'reason': reason, 'at': now, 'count': usage['failures']}
        self.save(entry['id'])

    async def finish(self, entry, reservation):
        async with self.lock:
            identity = entry['id']
            usage = self.load(entry)
            if reservation['accepted']:
                usage['requests'] += 1
                if reservation['usage'] is not None:
                    usage['reported_tokens'] += reservation['usage']
                else:
                    usage['estimated_tokens'] += reservation['observed']
                usage['last_used'] = time.time()
                usage['failures'] = 0
                usage['last_error'] = None
                self.save(identity)
            self.pending[identity] = max(0, self.pending.get(identity, 0) - reservation['observed'])
            reserved = self.reserved[identity]
            reserved['tokens'] -= reservation['tokens']
            reserved['requests'] -= 1
            if not reserved['requests']:
                del self.reserved[identity]

    def reset(self, entry):
        usage = self.load(entry)
        usage.update(requests=0, reported_tokens=0, estimated_tokens=0, failures=0,
                     last_error=None, blocked=False, cooldown_until=0)
        self.save(entry['id'])

    def forget(self, identity):
        self.usage.pop(identity, None)
        self.reserved.pop(identity, None)
        self.pending.pop(identity, None)
        if self.active_id == identity:
            self.active_id = None
        with sqlite3.connect(self.db_path) as db:
            db.execute('DELETE FROM pool_usage WHERE key_id=?', (identity,))
