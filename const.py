"""Constants for 栖息地智能家庭 integration."""

from homeassistant.const import Platform

DOMAIN = "habitat"
PLATFORMS = [Platform.LIGHT, Platform.SWITCH, Platform.COVER, Platform.SENSOR]

# Default configuration
DEFAULT_HOST = "172.16.33.72"
DEFAULT_PORT = 80

# Coordinator polling interval for device list
UPDATE_INTERVAL_SEC = 60

# API configuration
API_GET_DEVICES = "/gateway/getgatewaydevice"
API_SET_DEVICE = "/gateway/setDeviceAttribute"

# Device type mapping
DEVICE_TYPE_LIGHT = "LI"       # 灯
DEVICE_TYPE_SWITCH = "SW"      # 开关
DEVICE_TYPE_COVER = "EC"       # 窗帘
DEVICE_TYPE_SENSOR = "SE"      # 传感器
DEVICE_TYPE_AC = "AC"          # 空调
DEVICE_TYPE_UH = "UH"          # 地暖
DEVICE_TYPE_FA = "FA"          # 新风
DEVICE_TYPE_GA = "GA"          # 燃气报警器

# Model to platform mapping (legacy; prefer *_MODELS below)
MODEL_PLATFORMS = {
    "ZBW4CGJ": Platform.LIGHT,  # 色温灯
    "SHC-6D01-SW": Platform.LIGHT,  # 色温灯 (App)
    "SHC-8Q02-SW": Platform.SWITCH, # 单键开关
    "SHC-8Q03-SW": Platform.SWITCH, # 双键开关
    "SHC-8W01-SW": Platform.SWITCH, # 五合一面板
    "SHC-8W02-SW": Platform.SWITCH, # 4键情景开关
    "SHC-8Q04-SW": Platform.SWITCH, # 4+1开关面板
    "CUN01GJ": Platform.SWITCH,     # 情景开关
    "ZT21LGJ": Platform.COVER,      # 电动窗帘
    "EC02000001": Platform.COVER,   # 电动窗帘 (App)
    "SHC-4J01-SW": Platform.SENSOR, # 五合一传感器
    "FP_1020R": Platform.SENSOR,    # 水机室内机 (空调)
    "FP_510R": Platform.SENSOR,     # 水机室内机
    "FP_510L": Platform.SENSOR,     # 水机室内机
    "8DO": Platform.SWITCH,         # 地暖控制器
    "XF-430": Platform.SENSOR,      # 全热净化新风机
    "JT-HS8CG": Platform.SENSOR,    # 燃气报警器
}

# Single source of truth: model lists per platform (gateway returns these model strings)
LIGHT_MODELS = ["ZBW4CGJ", "SHC-6D01-SW"]
SWITCH_MODELS = [
    "ZSW5BGJ", "ZSW5GGJ", "ZSW5HGJ", "ZWN04GJ", "CUN01GJ", "8DO",
    "SHC-8Q02-SW", "SHC-8Q03-SW", "SHC-8W01-SW", "SHC-8W02-SW", "SHC-8Q04-SW",
]
COVER_MODELS = ["ZT21LGJ", "EC02000001"]
# 五合一传感器 (environmental)
SENSOR_MODELS = ["ZSW5HGJ", "SHC-4J01-SW"]
# 空调、新风、燃气
AC_MODELS = ["FP_1020R", "FP_510R", "FP_510L"]
FA_MODEL = "XF-430"
GA_MODEL = "JT-HS8CG"

# 多键开关：API 中可能表示“第 N 路/按键名称”的 dev_attrs 属性名（{i} 为通道索引，按优先级尝试）
SWITCH_CHANNEL_NAME_ATTR_PATTERNS = [
    "state{i}Name",
    "channel{i}Name",
    "key{i}Name",
    "buttonName{i}",
    "name{i}",
    "channelName{i}",
]
# 按模型为多键开关提供的默认通道名（索引 0 对应 state0；与 App 中 node_name/describe 对齐）
SWITCH_MODEL_CHANNEL_LABELS: dict[str, list[str]] = {
    "SHC-8Q04-SW": ["单键", "情景1", "情景2", "情景3", "情景4"],   # 四加一面板：单键 + 场景按键1-4
    "SHC-8W02-SW": ["情景1", "情景2", "情景3", "情景4"],           # 4键快充/情景：场景按键0-3
    "SHC-8W01-SW": ["按键1", "按键2", "按键3", "按键4", "按键5"],   # 五合一面板
    "SHC-8Q03-SW": ["S1", "S2"],                                   # 双键：与 App「灯开关(S1)/(S2)」一致
    "SHC-8Q02-SW": ["开关"],                                       # 单键
    "CUN01GJ": ["情景"],                                           # 情景开关
}
# 无匹配时的通用后缀
SWITCH_CHANNEL_FALLBACK = "按键{i}"
