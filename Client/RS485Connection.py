"""Remote on-demand telemetry client; no Pi dependencies or LV/HV connection."""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class RS485Connection:
    def __init__(self, host='127.0.0.1', port=12004, timeout=30.0):
        self.host, self.port, self.timeout = host, port, timeout

    def _get(self, path, params=None, body=None, *, timeout=None):
        url = f'http://{self.host}:{self.port}{path}'
        if params:
            url += '?' + urlencode(params)
        request = url if body is None else Request(url, data=json.dumps(body).encode(),
                                                   headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urlopen(request, timeout=self.timeout if timeout is None else timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            try:
                detail = json.load(exc).get('error', str(exc))
            except (ValueError, AttributeError):
                detail = str(exc)
            finally:
                exc.close()
            raise RuntimeError(f'RS485 server: {detail}') from exc
        except (URLError, OSError, ValueError) as exc:
            raise RuntimeError(f'RS485 query failed at {url}: {exc}') from exc

    def get_health(self):
        return self._get('/health')

    def get_parameters(self):
        return self._get('/parameters')

    def get_panels(self):
        return self._get('/panels')

    def discover(self, start=0, end=300):
        def address(value):
            text = str(value)
            return int(text[2:] if text.upper().startswith('MN') else text)
        start, end = address(start), address(end)
        if not 0 <= start <= end <= 511:
            raise ValueError('discovery range must satisfy 0 <= start <= end <= 511')
        # A full 512-address scan plus an outstanding legacy reply window can
        # exceed the normal per-variable HTTP timeout. No HTTP retries.
        return self._get('/discover', {'start': start, 'end': end}, timeout=max(60, self.timeout))

    def direct_read(self, address, name):
        return self.read(address, name, direct=True)

    def read(self, address, name, *, direct=False):
        text = str(address)
        if text.upper().startswith('MN'):
            text = text[2:]
        address = int(text)
        if not 0 <= address <= 511:
            raise ValueError('ROC/MN address must be 0..511')
        return self._get('/direct-read' if direct else '/read', {'address': address, 'name': name})

    def recovery(self, address, *, activate=False):
        text = str(address)
        if text.upper().startswith('MN'):
            text = text[2:]
        address = int(text)
        if not 1 <= address <= 511:
            raise ValueError('recovery address must be 1..511')
        if activate:
            return self._get('/recover-golden', body={'address': address, 'action': 'activate-golden'})
        return self._get('/recovery-status', {'address': address})

    def panel_id(self, address):
        text = str(address)
        if text.upper().startswith('MN'):
            text = text[2:]
        address = int(text)
        if not 0 <= address <= 511:
            raise ValueError('panel address must be 0..511')
        return self._get('/panel-id', {'address': address})
