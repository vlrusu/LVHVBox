"""Remote on-demand telemetry client; no Pi dependencies or LV/HV connection."""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


class RS485Connection:
    def __init__(self, host='127.0.0.1', port=12004, timeout=30.0):
        self.host, self.port, self.timeout = host, port, timeout

    def _get(self, path, params=None):
        url = f'http://{self.host}:{self.port}{path}'
        if params:
            url += '?' + urlencode(params)
        try:
            with urlopen(url, timeout=self.timeout) as response:
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

    def read(self, address, name):
        text = str(address)
        if text.upper().startswith('MN'):
            text = text[2:]
        address = int(text)
        if not 0 <= address <= 511:
            raise ValueError('ROC/MN address must be 0..511')
        return self._get('/read', {'address': address, 'name': name})
