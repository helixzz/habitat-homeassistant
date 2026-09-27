"""共享辅助：设备属性读取、五合一面板主面板判定。"""

from .const import PANEL_5IN1_MAIN_ATTRS


def get_attr_value(dev_attrs: list, attr_name: str):
    """从 dev_attrs 中取第一个匹配 name 的 value。"""
    for a in dev_attrs:
        if a.get("name") == attr_name:
            return a.get("value")
    return None


def is_main_panel(dev_attrs: list) -> bool:
    """五合一面板主面板：滤芯或加湿器使用小时任一项存在且非零。"""
    for name in PANEL_5IN1_MAIN_ATTRS:
        v = get_attr_value(dev_attrs, name)
        if v is not None:
            try:
                if int(v) != 0:
                    return True
            except (TypeError, ValueError):
                pass
    return False


class HabitatAvailabilityMixin:
    """设备在网关上离线时把实体标记为 unavailable（设备恢复后自动变回可用）。

    ⚠️ 实体必须在 setup 时**无条件创建**。如果按 `online` 在创建阶段就过滤掉，
    设备离线期间集成根本不会创建实体，HA 只保留一个 `restored` 占位状态；
    等设备重新上线，实体也不会自动回来 —— 必须重载集成才会恢复。
    （现实中很常见：面板固件更新后把灯控器断电、网关重启导致 Zigbee 设备暂时掉线。）
    """

    _device_data: dict

    @property
    def available(self) -> bool:
        """网关上报 online=false 时不可用；实体本身始终存在。"""
        data = getattr(self, "_device_data", None) or {}
        return bool(data.get("online", True))
