"""API for 栖息地智能家庭 gateway."""

import logging
import urllib.request
import json

_LOGGER = logging.getLogger(__name__)


class HabitatAPI:
    """Client for interacting with Habitat gateway."""

    def __init__(self, host: str, access_id: str, key: str, uid: str, pwd: str):
        """Initialize API client."""
        self.host = host
        self.access_id = access_id
        self.key = key
        self.uid = uid
        self.pwd = pwd
        self.base_url = f"http://{host}"

    def _request(self, endpoint: str, params: dict) -> dict:
        """Make request to gateway."""
        url = f"{self.base_url}{endpoint}"
        data = {
            "accessID": self.access_id,
            "key": self.key,
            "ver": "1.0",
            "uid": self.uid,
            "pwd": self.pwd,
            **params
        }
        
        _LOGGER.debug(f"Request to {url}: {data}")
        
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode('utf-8'))
                _LOGGER.debug(f"Response: {result}")
                return result
        except Exception as e:
            _LOGGER.error(f"API request failed: {e}")
            return {"code": 500, "status": str(e)}

    def get_devices(self) -> list:
        """Get all devices from gateway."""
        result = self._request("/gateway/getgatewaydevice", {})
        
        if result.get("code") == 200:
            return result.get("params", {}).get("devices", [])
        return []

    def set_device_attribute(self, device_uid: str, attr_name: str, value) -> bool:
        """Set device attribute."""
        params = {
            "childGatewayId": self.uid,
            "deviceUid": device_uid,
            "dev_attr": {
                "name": attr_name,
                "value": value
            }
        }
        
        result = self._request("/gateway/setDeviceAttribute", params)
        return result.get("code") == 200

    def set_light(self, device_uid: str, state: int, level: int = None, color_temp: int = None) -> bool:
        """Control light device."""
        if state is not None:
            if not self.set_device_attribute(device_uid, "state", state):
                return False
        if level is not None:
            if not self.set_device_attribute(device_uid, "level", level):
                return False
        if color_temp is not None:
            if not self.set_device_attribute(device_uid, "colorTemp", color_temp):
                return False
        return True

    def set_switch(self, device_uid: str, state: int, switch_index: int = 0) -> bool:
        """Control switch device."""
        attr_name = f"state{switch_index}" if switch_index > 0 else "state0"
        return self.set_device_attribute(device_uid, attr_name, state)

    def set_cover(self, device_uid: str, state: int = None, level: int = None) -> bool:
        """Control cover (curtain) device."""
        if state is not None:
            if not self.set_device_attribute(device_uid, "curtainState", state):
                return False
        if level is not None:
            if not self.set_device_attribute(device_uid, "curtainLevel", level):
                return False
        return True
