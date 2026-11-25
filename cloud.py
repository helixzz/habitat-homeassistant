"""栖息地云端（App / 云）REST API 客户端。

为什么需要它
------------
有些设备**不在 Zigbee 网关上**，只存在于厂商云端 —— 例如四合一水处理器
（型号 ``SHX-ECL1-V1``，设备号以 ``YD`` 开头）。本地网关 API 完全看不到它们
（``getgatewaydevice`` 只返回 Zigbee 设备），云端 API 是唯一的数据来源。

实测要点
--------
* 登录只有**短信验证码**一种方式：没有密码登录，也**没有 token 刷新接口**
  （实测文档与接口均确认），过期后必须重新走一次短信登录。
* 云端前面有阿里云 WAF，请求必须伪装成 App 的 User-Agent，否则接口会
  「看起来成功」（返回 ``result_code: 0``）但验证码**根本不会发出**。
  第一次实测时就踩了这个坑。
* 证书有效（DigiCert，``*.nanshe-tech.com``），不需要关闭 TLS 校验。
* token 放在**响应头** ``token`` 里，之后每次请求放在请求头 ``token``。
* 业务错误统一返回 ``result_code != 0`` 并带 ``message``；鉴权失败是 HTTP 401。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    CLOUD_APP_USER_AGENT,
    CLOUD_AUTH_HOST,
    CLOUD_WATER_TYPE,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10)


class HabitatCloudError(Exception):
    """云端请求失败（网络 / 业务错误）。"""


class HabitatCloudAuthError(HabitatCloudError):
    """云端鉴权失败（token 缺失或已过期）。"""


class HabitatCloudAPI:
    """栖息地云端 API 的极简异步客户端。"""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        token: str | None = None,
        home_id: str | None = None,
        host: str = CLOUD_AUTH_HOST,
    ) -> None:
        self._session = session
        self._token = token
        self.home_id = home_id
        self._host = host

    @property
    def token(self) -> str | None:
        return self._token

    def _headers(self, auth: bool) -> dict[str, str]:
        headers = {
            # 必须伪装成 App，否则会被 WAF 静默拦掉（验证码不会真的发出）
            "User-Agent": CLOUD_APP_USER_AGENT,
            "Accept": "application/json",
            "caller": "iOS",
        }
        if auth:
            if not self._token:
                raise HabitatCloudAuthError("尚未登录云端账号")
            headers["token"] = self._token
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> tuple[dict[str, Any], Any]:
        """发起请求，返回 (JSON, 响应对象)。"""
        url = f"https://{self._host}{path}"
        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers(auth),
                json=body,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                if resp.status == 401:
                    raise HabitatCloudAuthError(
                        "云端登录状态已失效，需要重新用短信验证码登录"
                    )
                if resp.status >= 400:
                    raise HabitatCloudError(
                        f"云端返回 HTTP {resp.status}（{path}）"
                    )
                try:
                    data = await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError) as err:
                    raise HabitatCloudError(
                        f"云端返回内容不是 JSON（{path}）"
                    ) from err
                # 登录接口的 token 在响应头里
                if isinstance(data, dict):
                    code = data.get("result_code")
                    if code not in (0, "0", None):
                        message = str(data.get("message") or "未知错误")
                        if "登录" in message or "token" in message.lower():
                            raise HabitatCloudAuthError(message)
                        raise HabitatCloudError(message)
                return data, resp
        except HabitatCloudError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise HabitatCloudError(f"无法连接云端：{err}") from err

    # --- 登录 -------------------------------------------------------------

    async def async_request_sms_code(self, mobile: str) -> None:
        """请求短信验证码（不需要 token）。"""
        await self._request(
            "GET", f"/app-apis/user/v1/im/sms_code?mobile={mobile}", auth=False
        )

    async def async_login(self, mobile: str, code: str) -> str:
        """用短信验证码登录，返回并记住 token。"""
        data, resp = await self._request(
            "POST",
            "/app-apis/user/v1/login/sms_code_login",
            body={"credential": code, "identifier": mobile},
            auth=False,
        )
        token = resp.headers.get("token")
        if not token:
            raise HabitatCloudAuthError("登录成功但没有返回 token")
        payload = data.get("data") or {}
        self._token = token
        self.home_id = str(payload.get("current_home_id") or "") or self.home_id
        return token

    # --- 设备 -------------------------------------------------------------

    async def async_search_devices(
        self, product_types: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """一次拉取整个家庭下的设备（可按产品类型过滤）。"""
        if not self.home_id:
            raise HabitatCloudError("缺少 home_id，无法查询云端设备")
        data, _ = await self._request(
            "POST",
            f"/app-apis/user/v1/search/{self.home_id}/searchDeviceConditionByHome",
            body={"room_ids": [], "product_type_list": product_types or []},
        )
        payload = data.get("data")
        items = payload if isinstance(payload, list) else (payload or {}).get("list") or []
        devices: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            # 列表里既有设备，也有分组/网关等条目
            info = item.get("deviceInfo") or item
            if isinstance(info, dict) and info.get("device_id"):
                devices.append(info)
        return devices

    async def async_get_device_info(
        self, device_id: str, room_id: str | int
    ) -> dict[str, Any]:
        """查询单台设备的详情（含全部属性）。"""
        if not self.home_id:
            raise HabitatCloudError("缺少 home_id，无法查询云端设备")
        data, _ = await self._request(
            "GET",
            f"/app-apis/device/v1/{self.home_id}/{room_id}/{device_id}/getDeviceInfo",
        )
        return data.get("data") or {}


def _normalize_device(raw: dict[str, Any]) -> dict[str, Any]:
    """把云端设备记录压平成便于实体读取的结构。"""
    attrs: dict[str, Any] = {}
    describes: dict[str, str] = {}
    for node in raw.get("list") or []:
        if not isinstance(node, dict):
            continue
        for attr in node.get("productTypeNodeAttrInfoList") or []:
            if not isinstance(attr, dict):
                continue
            name = attr.get("node_attr_name")
            if not name:
                continue
            value = attr.get("value")
            # 云端把空值表示成 "" 或字符串 "None"
            if value in ("", "None"):
                value = None
            attrs[name] = value
            describes[name] = str(attr.get("describe") or "")
    return {
        "device_id": str(raw.get("device_id") or ""),
        "device_number": str(raw.get("device_number") or ""),
        "name": raw.get("device_name") or raw.get("product_model_name") or "栖息地设备",
        "model": raw.get("product_model_code") or "",
        "model_name": raw.get("product_model_name") or "",
        "room": raw.get("room_name") or "",
        "room_id": raw.get("roomId"),
        "type_code": raw.get("product_type_code") or "",
        "sub_type_code": raw.get("product_sub_type_code") or "",
        "online": str(raw.get("online")) == "1",
        "attrs": attrs,
        "describes": describes,
    }


class HabitatCloudCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """轮询云端设备（目前用于 Zigbee 网关上没有的设备，如水处理器）。"""

    def __init__(
        self,
        hass: HomeAssistant,
        api: HabitatCloudAPI,
        update_interval: int,
        config_entry=None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="habitat_cloud",
            update_method=self._async_update_data,
            update_interval=timedelta(seconds=update_interval),
            config_entry=config_entry,
        )
        self.api = api
        # 只关心「网关看不到、只能从云端拿」的设备类型
        self.product_types = [CLOUD_WATER_TYPE]

    async def _async_update_data(self) -> list[dict[str, Any]]:
        try:
            raw_devices = await self.api.async_search_devices(self.product_types)
        except HabitatCloudAuthError as err:
            # 让 HA 启动重新认证流程（token 没有刷新接口，只能重新短信登录）
            raise ConfigEntryAuthFailed(str(err)) from err
        except HabitatCloudError as err:
            raise UpdateFailed(str(err)) from err

        devices = [_normalize_device(d) for d in raw_devices]
        _LOGGER.debug("云端返回 %s 台设备", len(devices))
        return devices
