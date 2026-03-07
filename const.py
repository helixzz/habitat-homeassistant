"""Constants for 栖息地智能家庭 integration."""

from homeassistant.const import Platform

DOMAIN = "habitat"
PLATFORMS = [Platform.LIGHT, Platform.SWITCH, Platform.COVER, Platform.SENSOR]

# Default configuration
DEFAULT_HOST = "172.16.33.72"
DEFAULT_PORT = 80

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

# Model to platform mapping
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
