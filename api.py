"""API for 栖息地智能家庭 gateway."""

import logging

import aiohttp

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=10)


class HabitatAPIError(Exception):
    """Raised when gateway returns a business error (e.g. auth failure)."""
    def __init__(self, message: str, code: int = None):
        self.code = code
        super().__init__(message)


class HabitatAPI:
    """Client for interacting with Habitat gateway."""

    def __init__(
        self,
        host: str,
        access_id: str,
        key: str,
        uid: str,
        pwd: str,
        port: int = 80,
    ):
        """Initialize API client."""
        self.host = host
        self.port = port
        self.access_id = access_id
        self.key = key
        self.uid = uid
        self.pwd = pwd
        if port == 80:
            self.base_url = f"http://{host}"
        else:
            self.base_url = f"http://{host}:{port}"

    async def _request(self, endpoint: str, params: dict) -> dict:
        """Make request to gateway. Returns dict with 'code' and optional 'params'/'message'.
        On network/timeout errors returns {'code': 500, 'message': str}.
        On gateway business error returns response as-is (code != 200)."""
        url = f"{self.base_url}{endpoint}"
        data = {
            "accessID": self.access_id,
            "key": self.key,
            "ver": "1.0",
            "uid": self.uid,
            "pwd": self.pwd,
            **params
        }
        _LOGGER.debug("Request to %s: %s", url, data)
        try:
            async with aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT) as session:
                async with session.post(
                    url, json=data, headers={"Content-Type": "application/json"}
                ) as response:
                    result = await response.json()
                    _LOGGER.debug("Response: %s", result)
                    return result
        except aiohttp.ClientError as e:
            _LOGGER.error("API request failed (network): %s", e)
            return {"code": 500, "message": "无法连接到网关，请检查网络和地址"}
        except TimeoutError as e:
            _LOGGER.error("API request timeout: %s", e)
            return {"code": 500, "message": "连接超时，请检查网络"}
        except Exception as e:
            _LOGGER.exception("Unexpected error")
            return {"code": 500, "message": str(e)}

    async def get_devices(self) -> list:
        """Get all devices from gateway. Raises HabitatAPIError on auth/business error."""
        result = await self._request("/gateway/getgatewaydevice", {})
        code = result.get("code")
        if code == 200:
            devices = result.get("params", {}).get("devices", [])
            return devices if devices is not None else []
        if code == 500:
            raise ConnectionError(result.get("message", "无法连接到网关"))
        raise HabitatAPIError(
            result.get("message", "认证失败，请检查 UID、Key 和密码"),
            code=code,
        )

    async def set_device_attribute(
        self, device_uid: str, attr_name: str, value
    ) -> bool:
        """Set device attribute. Gateway expects device payload under top-level 'params'."""
        params = {
            "params": {
                "childGatewayId": self.uid,
                "deviceUid": device_uid,
                "dev_attr": {"name": attr_name, "value": value},
            }
        }
        result = await self._request("/gateway/setDeviceAttribute", params)
        return result.get("code") == 200

    async def get_groups(self) -> list:
        """读取网关全部 Zigbee 组（/group 是独立于 /gateway 的 API 基址）。"""
        result = await self._request("/group/getall", {})
        return (result.get("params") or {}).get("groups") or []

    async def set_device_attribute_raw(
        self, device_uid: str, attr_name: str, value
    ) -> int:
        """同 set_device_attribute，但返回原始 code。

        bindRelayList 是**数组**属性：网关能正确解析并下发给设备，但在拼响应时
        会崩（回 HTTP 500）。所以这里必须把「真失败」和「成功了但响应崩了」区分开
        —— 调用方通过返回的 code 判断，并配合「先写非空值再写空值」保证真的下发。
        """
        params = {
            "params": {
                "childGatewayId": self.uid,
                "deviceUid": device_uid,
                "dev_attr": {"name": attr_name, "value": value},
            }
        }
        result = await self._request("/gateway/setDeviceAttribute", params)
        return int(result.get("code") or 0)

    async def set_light(
        self,
        device_uid: str,
        state: int = None,
        level: int = None,
        color_temp: int = None,
    ) -> bool:
        """Control light device."""
        if state is not None:
            if not await self.set_device_attribute(device_uid, "state", state):
                return False
        if level is not None:
            if not await self.set_device_attribute(device_uid, "level", level):
                return False
        if color_temp is not None:
            if not await self.set_device_attribute(
                device_uid, "colorTemp", color_temp
            ):
                return False
        return True

    async def set_switch(
        self, device_uid: str, state: int, switch_index: int = 0
    ) -> bool:
        """Control switch device."""
        attr_name = (
            f"state{switch_index}" if switch_index > 0 else "state0"
        )
        return await self.set_device_attribute(device_uid, attr_name, state)

    async def set_cover(
        self, device_uid: str, state: int = None, level: int = None
    ) -> bool:
        """Control cover (curtain) device."""
        if state is not None:
            if not await self.set_device_attribute(
                device_uid, "curtainState", state
            ):
                return False
        if level is not None:
            if not await self.set_device_attribute(
                device_uid, "curtainLevel", level
            ):
                return False
        return True
