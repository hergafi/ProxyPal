import os
import tempfile

# The gateway always requires a token; pin it before test modules import gateway.
os.environ['GATEWAY_TOKEN'] = 'test-gateway-token'
_state = tempfile.mkdtemp(prefix='proxypal-tests-')
os.environ.setdefault('GATEWAY_CONFIG', os.path.join(_state, 'gateway_config.json'))
os.environ.setdefault('DB_PATH', os.path.join(_state, 'gateway.db'))
