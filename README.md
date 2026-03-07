# 栖息地智能家庭 Home Assistant 集成

![Project](https://img.shields.io/badge/project-habitat-blue)
![HA Version](https://img.shields.io/badge/Home-Assistant-2024.1%2B-green)
![Python](https://img.shields.io/badge/Python-3.10%2B-yellow)

简体中文 | [English](./README_EN.md)

## 功能支持

| 设备类型 | 功能 | 状态 |
|---------|------|------|
| 色温灯 (CCT Light) | 开/关、亮度、色温 | ✅ |
| 智能开关 | 开/关 | ✅ |
| 电动窗帘 | 开/关/停止 | ✅ |
| 五合一传感器 | 温度、湿度、PM2.5、PM10、CO2、AQI | ✅ |
| 空调 | 温度监控 | ✅ |
| 新风机 | 滤芯小时数 | ✅ |
| 燃气报警器 | 气体状态、浓度 | ✅ |

## 安装

### 方式一：手动安装

本仓库根目录即为集成代码所在目录。请将以下文件复制到 Home Assistant 配置目录下的 `custom_components/habitat/` 中（若不存在请先创建 `habitat` 文件夹）：

- `__init__.py`、`config_flow.py`、`manifest.json`、`const.py`、`api.py`
- `light.py`、`switch.py`、`cover.py`、`sensor.py`

例如在仓库根目录执行（将 `config` 替换为你的 HA 配置目录路径）：

```bash
mkdir -p config/custom_components/habitat
cp __init__.py config_flow.py manifest.json const.py api.py light.py switch.py cover.py sensor.py config/custom_components/habitat/
```

然后重启 Home Assistant。

### 方式二：使用 HACS (推荐)

> 即将支持 HACS 安装

## 配置

### 首次配置

1. 打开 Home Assistant
2. 进入 **设置** → **设备与服务**
3. 点击 **添加集成**
4. 搜索 **栖息地智能家庭**
5. 按照提示填写配置信息：

| 字段 | 说明 | 示例 |
|------|------|------|
| 网关 IP 地址 | 栖息地网关的本地 IP | `172.16.33.72` |
| 网关 UID | 网关序列号 | `2G01_25420142` |
| API Key | 认证密钥 | (见下方获取方法) |
| 密码 | 认证密码 | (见下方获取方法) |

### 获取 API 凭证

使用 HTTP 方式登录到 Zigbee 网关设备的 Web 界面，利用浏览器 F12 工具可抓取前后端交互的请求数据。

```json
{
  "uid": "2G01_25420142",
  "key": "90ff179ea717b44e91ab3100000000006f42f0000000000ae0000000000a812a",
  "pwd": "FDCE1234567890123456710000000000"
}
```

## 设备清单

本集成会自动发现并添加以下设备：

- **灯**: 客厅筒灯、卧室灯带、书房灯等
- **开关**: 智能开关、情景面板、五合一面板
- **窗帘**: 各房间的电动窗帘
- **传感器**: 各房间的五合一环境传感器

## 故障排除

### 日志提示 “blocking call to import_module” 或集成目录为 habitat-homeassistant

集成在 Home Assistant 中的**目录名必须为 `habitat`**（与 manifest 的 domain 一致），不能使用带连字符的 `habitat-homeassistant`。若日志里仍出现 `custom_components.habitat-homeassistant`，说明 HA 还在从旧目录加载。

**处理方式**（需全部做完）：

1. **只保留正确目录**：在 `custom_components/` 下只保留文件夹 **`habitat`**（内含本集成的所有 .py 和 manifest.json）。若还存在 **`habitat-homeassistant`** 文件夹，请**直接删除整个文件夹**（不要只改名，避免 HA 仍从旧路径加载）。
2. **重新添加集成**：在 HA 中进入 **设置 → 设备与服务 → 集成**，找到「栖息地智能家庭」，删除该集成（会移除已配置的网关）。再点击「添加集成」，重新搜索并添加「栖息地智能家庭」，重新填写网关信息。
3. **重启 HA**：完成上述步骤后重启 Home Assistant。

同时本集成已在 `manifest.json` 中设置 `"import_executor": true`，以减少事件循环阻塞警告。

### 无法连接网关

1. 确认 Home Assistant 主机和栖息地网关在同一网络
2. 检查网关 IP 地址是否正确
3. 尝试 ping 网关: `ping 172.16.33.72`

### 设备不在线

1. 检查设备是否在栖息地 App 中在线
2. 重启网关
3. 重新加载集成

## 开发

### 本地开发

```bash
# 进入开发目录
cd custom_components/habitat

# 启用开发者模式后，在 HA 中配置:
# http://your-ha-ip:8123
```

### 添加新设备类型

在 `const.py` 中的 `MODEL_PLATFORMS` 字典添加新的设备类型映射。

## 更新日志

### v0.1.0 (2026-03-07)
- 初始版本
- 支持灯光、开关、窗帘、传感器

## 许可证

MIT License

---

*本集成与栖息地智能家庭无官方关联，仅为社区爱好者开发。*
