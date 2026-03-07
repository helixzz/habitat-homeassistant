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
