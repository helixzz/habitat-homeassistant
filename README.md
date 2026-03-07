# 栖息地智能家庭 Home Assistant 集成

![Project](https://img.shields.io/badge/project-habitat-blue)
![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-green)
![Python](https://img.shields.io/badge/Python-3.10%2B-yellow)

简体中文 | [English](./README_EN.md)

## 功能支持

| 设备类型 | 功能 | 状态 |
|---------|------|------|
| 色温灯 (CCT Light) | 开/关、亮度、色温 | ✅ |
| 智能开关 | 开/关（多键/情景/五合一面板按键默认隐藏） | ✅ |
| 电动窗帘 | 开/关/停止、位置 | ✅ |
| 五合一环境传感器 | 温度、湿度、PM2.5、PM10、CO2、AQI | ✅ |
| 五合一面板 · 空调 | 气候实体：当前/目标温度、空调风速（关/1–6 档/自动） | ✅ |
| 五合一面板 · 加湿 | 加湿器实体：当前/目标湿度（新风按目标加湿） | ✅ |
| 五合一面板 · 新风 | 主面板：风扇实体（新风送风 0–6 档/自动） | ✅ |
| 五合一面板 · 地暖 | 主面板：地暖状态、滤芯/加湿器使用小时（只读） | ✅ |
| 空调 (水机室内机) | 当前温度、设定温度（只读传感器） | ✅ |
| 新风机 | 湿度、滤芯使用小时 | ✅ |
| 燃气报警器 | 气体状态、浓度 | ✅ |

五合一面板同时充当空调、新风（主面板可调全屋送风）、地暖控制器；温度/湿度目标与风速通过 HA 原生 **气候**、**加湿器**、**风扇** 实体控制。可选 Number 实体默认在实体注册表中隐藏，可在「设置 → 实体」中取消隐藏。

支持**多网关**：可在集成选项中配置主网关与子网关，设备按所属网关自动选用 API。

## 安装

### 方式一：手动安装

将本仓库以下内容复制到 Home Assistant 配置目录下的 `custom_components/habitat/`（若不存在请先创建 `habitat` 文件夹）：

**必需文件：**

- `__init__.py`、`config_flow.py`、`manifest.json`、`const.py`、`api.py`
- `helpers.py`
- `light.py`、`switch.py`、`cover.py`、`sensor.py`
- `number.py`、`climate.py`、`humidifier.py`、`fan.py`
- `translations/` 目录（含 `en.json`，用于英文界面实体名等）

**可选：**

- `brand/` 目录：若需在 HA 中显示集成 Logo（需 HA 2026.3+），请将 `assets/habitat-logo.webp` 转为 PNG 后保存为 `brand/logo.png`，并与 `brand/` 一并复制。详见 `brand/README.md`。

示例（将 `config` 替换为你的 HA 配置目录路径）：

```bash
mkdir -p config/custom_components/habitat
cp __init__.py config_flow.py manifest.json const.py api.py helpers.py \
   light.py switch.py cover.py sensor.py number.py climate.py humidifier.py fan.py \
   config/custom_components/habitat/
cp -r translations config/custom_components/habitat/
cp -r brand config/custom_components/habitat/ 2>/dev/null || true
```

然后重启 Home Assistant。

### 方式二：HACS（推荐）

> 即将支持 HACS 安装

## 配置

### 首次配置

1. 打开 Home Assistant
2. 进入 **设置** → **设备与服务**
3. 点击 **添加集成**
4. 搜索 **栖息地智能家庭**
5. 按提示填写：

| 字段 | 说明 | 示例 |
|------|------|------|
| 网关 IP 地址 | 栖息地网关的本地 IP | `172.16.33.72` |
| 网关 UID | 网关序列号 | `2G01_25420142` |
| API Key | 认证密钥 | （见下方获取方法） |
| 密码 | 认证密码 | （见下方获取方法） |

配置完成后，可在该集成的**选项**中添加子网关（多网关）。

### 获取 API 凭证

通过 HTTP 访问 Zigbee 网关的 Web 界面，使用浏览器开发者工具（F12）抓取登录请求中的参数：

```json
{
  "uid": "2G01_25420142",
  "key": "90ff179ea717b44e91ab3100000000006f42f0000000000ae0000000000a812a",
  "pwd": "FDCE1234567890123456710000000000"
}
```

## 设备与实体

集成会自动发现并创建设备与实体：

- **灯**：客厅筒灯、卧室灯带等
- **开关**：智能开关、情景面板、五合一面板上的按键（情景/五合一面板的开关实体默认隐藏，可在实体注册表中取消隐藏）
- **窗帘**：电动窗帘
- **传感器**：五合一环境（温湿度、PM2.5/PM10、CO2、AQI）、空调温度、新风机滤芯、燃气报警
- **五合一面板**：每块面板有**气候**（空调）、**加湿器**（湿度目标）；**主面板**另有**风扇**（新风送风）及地暖状态、滤芯/加湿器使用小时传感器。主面板由「滤芯或加湿器使用小时非零」自动判定。

## 故障排除

### 日志出现 “blocking call to import_module” 或集成目录为 habitat-homeassistant

集成在 Home Assistant 中的**目录名必须为 `habitat`**（与 manifest 的 domain 一致），不能使用 `habitat-homeassistant`。若日志仍出现 `custom_components.habitat-homeassistant`，说明 HA 仍在从旧目录加载。

**处理步骤**（需全部完成）：

1. **只保留正确目录**：在 `custom_components/` 下只保留 **`habitat`**（内含所有 .py、manifest.json、translations 等）。若存在 **`habitat-homeassistant`**，请**直接删除整个文件夹**（不要只改名）。
2. **重新添加集成**：**设置 → 设备与服务 → 集成**，删除「栖息地智能家庭」，再重新添加并填写网关信息。
3. **重启 Home Assistant**。

本集成已在 `manifest.json` 中设置 `"import_executor": true`，以减轻事件循环阻塞警告。

### 无法连接网关

1. 确认 Home Assistant 与栖息地网关在同一网络
2. 核对网关 IP
3. 尝试 `ping <网关IP>`

### 设备不在线

1. 在栖息地 App 中确认设备在线
2. 重启网关
3. 在集成中重新加载

## 开发

### 本地开发

将本仓库克隆或复制到 `custom_components/habitat/`，修改后重启 HA 或重新加载集成。建议开启 HA 开发者模式以便查看日志。

### 添加新设备类型

在 `const.py` 的 `MODEL_PLATFORMS` 及对应 `*_MODELS` 列表中添加新型号映射。

## 更新日志

### v0.1.0 (2026-03-07)

- 初始版本：灯光、开关、窗帘、传感器
- 后续：五合一面板 Climate/Humidifier/Fan/Number、地暖状态、多网关、情景/五合一开关默认隐藏、英文翻译（Fresh Air 等）

## 许可证

MIT License

---

*本集成与栖息地智能家庭无官方关联，仅为社区爱好者开发。*
