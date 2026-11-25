"""Constants for 栖息地智能家庭 integration."""

from homeassistant.const import Platform

DOMAIN = "habitat"
PLATFORMS = [
    Platform.LIGHT,
    Platform.SWITCH,
    Platform.COVER,
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.CLIMATE,
    Platform.HUMIDIFIER,
    Platform.FAN,
    Platform.SELECT,
]

# Default configuration
DEFAULT_HOST = "172.16.33.72"
DEFAULT_PORT = 80

# 轮询间隔（秒）。网关没有推送/长轮询接口（除 getgatewaydevice 外本地端点都是 404），
# 所以所有状态都靠轮询整个设备列表获得 —— 间隔越短，由物理开关/面板/栖息地 App
# 引起的变更在 HA 里出现得越快，代价是更多局域网流量（设备列表约 85 KB / 次）。
CONF_POLL_INTERVAL = "poll_interval"
DEFAULT_POLL_INTERVAL = 15
POLL_INTERVAL_CHOICES = [5, 10, 15, 30, 60, 120]

# 兼容旧引用
UPDATE_INTERVAL_SEC = DEFAULT_POLL_INTERVAL

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
# 窗帘电机方向参数（存在电机内，App 未暴露；网关本地 API 可写）
# 网关属性名 curtainDir：0=正常，1=反向；写入后电机会重新校准行程（可能整程运行一次）
CURTAIN_DIR_ATTR = "curtainDir"
CURTAIN_DIR_NORMAL = 0
CURTAIN_DIR_REVERSED = 1
# 网关**不持久化** curtainDir（只把它转发给电机，不写数据库），所以方向可能被
# 网关重启/云端同步重置。为让方向「存得住」，集成把期望值记在 config entry
# options 里，并在网关重连、集成启动时自动重新下发：
#   curtain_dir_overrides: {"<deviceUid>": 0|1}
CONF_CURTAIN_DIR_OVERRIDES = "curtain_dir_overrides"
CONF_CURTAIN_DIR_WATCHDOG = "curtain_dir_watchdog"
SERVICE_REAPPLY_CURTAIN_DIR = "reapply_curtain_direction"

# --- 云端（App）账号 -------------------------------------------------------------
# 有些设备**不在 Zigbee 网关上**，只存在于厂商云端（实测：四合一水处理器
# SHX-ECL1-V1，设备号以 YD 开头）。这类设备只能通过云端 API 读取。
# 云端登录只有短信验证码一种方式，且**没有 token 刷新接口** —— 过期后必须重新
# 走一次短信登录（集成会触发 HA 的「重新认证」流程）。
CONF_CLOUD_ENABLED = "cloud_enabled"
CONF_CLOUD_MOBILE = "cloud_mobile"
CONF_CLOUD_TOKEN = "cloud_token"
CONF_CLOUD_HOME_ID = "cloud_home_id"
CONF_CLOUD_POLL_INTERVAL = "cloud_poll_interval"
# 云端前面有 WAF：请求必须伪装成 App 的 User-Agent，否则验证码根本不会发出
CLOUD_AUTH_HOST = "habitat-app-cloud.nanshe-tech.com"
CLOUD_APP_USER_AGENT = "qi xi de/2.7.1 (iPhone; iOS 26.5.1; Scale/3.00)"
# 云端设备变化很慢（TDS、滤芯寿命），没必要频繁轮询
DEFAULT_CLOUD_POLL_INTERVAL = 60
CLOUD_POLL_INTERVAL_CHOICES = [30, 60, 120, 300]
# 目前只接「水处理」：其余云端设备（空调/新风/地暖/传感器）都是五合一面板的
# 虚拟子设备，网关侧已经能拿到，走云端反而会重复。
CLOUD_WATER_TYPE = "WT"

# --- 面板「按键直控继电器」解绑 -------------------------------------------------
# 面板固件里有两套彼此独立的绑定：
#   ① 组绑定     按键 → 向 Zigbee 组发组播命令（ownGroupList）
#   ② 继电器绑定 bindRelayList，按键 → 吸合面板自己的继电器（本地行为）
# 当某面板名下所有组的成员**都不包含它自己**时，说明它的负载是**独立的智能灯控器**
# （常火供电），按键只需发组播；此时如果继电器绑定还在，按键会额外切断灯控器的
# 供电 —— 灯控器靠电容撑几分钟后掉线（表现为「灯忽然不可用」）。
# 把 bindRelayList 写成空数组即可解绑。注意：网关**值没变化就不下发**，所以必须先
# 写一个非空值制造变化，再写空值。
BIND_RELAY_LIST_ATTR = "bindRelayList"
# 解绑要下发「空数组」。注意必须传**字符串** "[]" 而不是 Python 列表：
#   * 传列表：网关能正确下发，但拼 HTTP 响应时会崩（返回 500）——反复触发会把
#     网关的 HTTP 服务压死（实测出现过一分钟不可用）。
#   * 传字符串：返回 200 不崩，同样下发 zgb_val:0，而且**不受「值没变就跳过」
#     限制**（列表写法在数据库里已经是 [] 时会静默不下发）。
# 所以这里用字符串形式。
BIND_RELAY_LIST_NONE = "[]"
CONF_DECOUPLE_PANEL_BUTTONS = "decouple_panel_buttons"
SERVICE_REAPPLY_PANEL_DECOUPLE = "reapply_panel_decouple"
# 诊断：面板的按键分组是否建在它自己所属的网关上（云端/实际网关不一致会导致配置静默失败）
SERVICE_DIAGNOSE_PANEL_BINDINGS = "diagnose_panel_bindings"
# 面板解绑继电器绑定的等待时间（等 Zigbee 网络稳定）
DECOUPLE_DELAY = 20.0
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
# 按模型为多键开关提供的默认通道名（索引 0 对应 state0；与 App/网关 对齐）
# 网关返回的 model 可能与 App 不同，如五合一面板网关为 ZSW5HGJ、App 为 SHC-8W01-SW
SWITCH_MODEL_CHANNEL_LABELS: dict[str, list[str]] = {
    "SHC-8Q04-SW": ["单键", "情景1", "情景2", "情景3", "情景4"],   # 四加一面板
    "SHC-8W02-SW": ["情景1", "情景2", "情景3", "情景4"],           # 4键快充/情景
    "SHC-8W01-SW": ["按键1", "按键2", "按键3", "按键4", "按键5"],   # 五合一面板 (App 型号)
    "ZSW5HGJ": ["按键1", "按键2", "按键3", "按键4", "按键5"],       # 五合一面板 (网关型号，state0-4)
    "SHC-8Q03-SW": ["S1", "S2"],                                   # 双键
    "SHC-8Q02-SW": ["开关"],                                       # 单键
    "CUN01GJ": ["情景"],                                           # 情景开关
}
# 无匹配时的通用后缀
SWITCH_CHANNEL_FALLBACK = "按键{i}"

# 五合一面板：空调/新风/地暖控制；主面板判定为滤芯或加湿器使用小时非零
PANEL_5IN1_MODELS = frozenset({"ZSW5HGJ", "SHC-4J01-SW"})
PANEL_5IN1_MAIN_ATTRS = ("newWindFilterelementServicehours", "newWindHumidifierServicehours")
FAN_LEVEL_AUTO = 7  # 空调/新风风速 0=关 1-6=档位 7=自动

# 情景/五合一/多合一面板：其上“开关”实体默认在实体注册表中隐藏，用户可在 设置→实体 中取消隐藏
SWITCH_MODELS_HIDDEN_BY_DEFAULT = frozenset({
    "ZSW5HGJ",      # 五合一面板 (网关型号)
    "SHC-8W01-SW",  # 五合一面板 (App 型号)
    "SHC-8W02-SW",  # 4 键情景
    "SHC-8Q04-SW",  # 四加一面板 (单键+情景1-4)
    "CUN01GJ",      # 情景开关
})
