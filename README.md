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
| 电动窗帘 · 方向 | 正常/反向（`curtainDir`，App 未暴露，见下文） | ✅ |
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
- `number.py`、`climate.py`、`humidifier.py`、`fan.py`、`select.py`
- `services.yaml`（`reapply_curtain_direction` 服务的界面描述）
- `translations/` 目录（含 `en.json`，用于英文界面实体名等）

**可选：**

- `brand/` 目录：若需在 HA 中显示集成 Logo（需 HA 2026.3+），请将 `assets/habitat-logo.webp` 转为 PNG 后保存为 `brand/logo.png`，并与 `brand/` 一并复制。详见 `brand/README.md`。

示例（将 `config` 替换为你的 HA 配置目录路径）：

```bash
mkdir -p config/custom_components/habitat
cp __init__.py config_flow.py manifest.json const.py api.py helpers.py \
   light.py switch.py cover.py sensor.py number.py climate.py humidifier.py fan.py select.py \
   services.yaml \
   config/custom_components/habitat/
cp -r translations config/custom_components/habitat/
cp -r brand config/custom_components/habitat/ 2>/dev/null || true
```

然后重启 Home Assistant。

### 方式二：HACS 自定义仓库（推荐）

本集成**没有上架 HACS 默认商店**，但仓库已按 HACS 规范配置好（`hacs.json` + `brand/icon.png`），可以直接作为**自定义仓库**添加，之后就能一键更新：

1. 打开 **HACS** → 右上角 **⋮** → **自定义仓库**
2. 仓库填 `https://github.com/helixzz/habitat-homeassistant`
3. 类别选 **集成 (Integration)** → **添加**
4. 回到 HACS 搜索「栖息地」→ 进入后点 **下载**，选择版本（如 `v0.3.0`）
5. **重启 Home Assistant**

之后有新版本时 HACS 会提示更新。

> 说明：HACS 会把整个仓库下载到 `custom_components/habitat/`（因此 `tools/`、`assets/`、文档也会一并进去）。这不影响运行，只是目录里会多一些非必需文件。

### 升级（重要）

集成会随 Home Assistant 一起加载，**升级后必须重启 HA**（或在「设置 → 设备与服务」里重载集成）才会生效。

- **HACS 安装**：HACS → 栖息地 → **更新** → 重启 HA。
- **手动安装**：覆盖 `custom_components/habitat/` 下的文件 → 重启 HA。

> ⚠️ v0.2.1 起新增了 **`services.yaml`**，v0.3.0 起新增了 **`hacs.json`**。手动升级时别漏了这两个文件（`hacs.json` 是 HACS 用的，手动安装不放也不影响运行）。

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
- **窗帘**：电动窗帘（每个窗帘设备下另有**方向**选择实体，见下文）
- **传感器**：五合一环境（温湿度、PM2.5/PM10、CO2、AQI）、空调温度、新风机滤芯、燃气报警
- **五合一面板**：每块面板有**气候**（空调）、**加湿器**（湿度目标）；**主面板**另有**风扇**（新风送风）及地暖状态、滤芯/加湿器使用小时传感器。主面板由「滤芯或加湿器使用小时非零」自动判定。

## 窗帘方向：把装反的窗帘改回来

电动窗帘电机的方向（正转/反转）保存在**电机内部**，栖息地 App 与硬件面板都没有暴露该设置；但网关本地 API 的属性 `curtainDir` 就是它：

| 属性 | 含义 | 取值 |
|------|------|------|
| `curtainDir` | 电机方向 | `0` = 正常，`1` = 反向 |

写入后立即生效，电机会重新校准行程：方向确实改变时通常**整程运行一次**，方向未变时只小幅抖动确认。

> ⚠️ **重要：网关不会持久化这个值。** 网关只是把 `curtainDir` 转发给电机（调用链 `gm_down_dev_set_attr` → `attr_set_curtain_dir` → Zigbee `0xf1`），**全程不写数据库**；网关自己的属性缓存（`prevDevAttrList`）也只跟踪 `curtainState` / `curtainLevel`，不含 `curtainDir`。因此**网关重启、断电，或云端下发同名字段都可能把方向重置回 0**。v0.2.1 起集成用「方向看护」解决这个问题（见下）。

**在 HA 内修改**：每个窗帘设备下会多出一个「窗帘方向」选择实体（正常/反向），切换即可。

- 网关对 `curtainDir` 的**回报值恒为 0**（不回读电机内实际值），因此实体状态以「最近一次写入」为准。
- 该实体是**硬件级**修正；集成选项里的「反向 - 窗帘」是**软件级**修正。两者同时开启会互相抵消，通常只需其一 —— 建议用「窗帘方向」把硬件调正，这样 App 与硬件面板也会一起变正确。

### 方向看护（持久化，v0.2.1+）

因为网关存不住这个值，集成把它**记在 config entry options**（`curtain_dir_overrides`）里，作为真值源，并在下列时机自动重新下发：

- **集成启动 / HA 重启后**（等 45 秒让 Zigbee 网络稳定）
- **检测到网关重新上线时**（轮询由失败转为成功 = 网关重启/重连过）

可在集成**选项**中关闭（`方向看护` 复选框）。也可以手动触发：

```yaml
service: habitat.reapply_curtain_direction
# 可选：只处理某一个窗帘
data:
  device_uid: B0FD0BE011051113
```

### ⚠️ 修好硬件方向后，必须同步调整 HA 的「反向 - 窗帘」

这个电机的方向设置会**同时**翻转「电机转向」和「位置值方向」。实测（ZT21LGJ）：

| `curtainDir` | 面板/App 点「打开」 | 网关 `curtainLevel` |
|---|---|---|
| `0`（装反时） | 物理**关闭** ✗ | `0` = 物理关闭 |
| `1`（修正后） | 物理**打开** ✓ | `0` = 物理打开 |

所以：

- 栖息地 App 按 `(255 - level) / 255` **反转显示**，修好后 App 的开关与百分比都是对的；
- 本集成**默认不做反转**，因此**修好硬件方向之后，HA 的位置与开关会整体反过来（开 = 0%）**。
- 解决：在集成**选项**里给这些窗帘勾上「反向 - 窗帘」。也就是说，硬件修正与 HA 软件反向**不是二选一，而是修好硬件后必须开启 HA 反向**（在改方向之前，两者是反过来的关系）。

> 实测数据：`curtainState=0`（关闭）→ level 254 → 物理全关；`curtainState=1`（打开）→ level 0 → 物理全开。

如果不想依赖 HA，也可以用脚本（`tools/set_curtain_direction.py`）配合 cron / 计划任务定期执行。注意：重新下发时若方向本来就是对的，电机会**小幅抖动确认**一下，属正常现象。

**在 HA 外修改**（仓库内附带脚本）：

```bash
# 列出网关下所有窗帘
python3 tools/set_curtain_direction.py --host 172.16.33.27 --list

# 设为反向（1）/ 恢复正常（0）
python3 tools/set_curtain_direction.py --host 172.16.33.27 \
    --device B0FD0BE011051113 --direction 1
```

脚本会自动从网关 `getgatewayproperties` 读取 `gatewayPwd`（该接口无需鉴权，见下方安全提示）。

**原理**：网关把 `curtainDir` 映射到 Zigbee 窗帘簇（0x0102）的厂商自定义命令 `0xf1`；`curtainState` 映射到标准 Up/Open(0x00)/Down/Close(0x01)/Stop(0x02)，`curtainLevel` 映射到 Level Control 簇的 Move to Level。窗帘的开关方向由电机内的 `curtainDir` 决定，与 App/网关无关，因此只在 HA 内做软件反向无法修正 App 与面板。

> ⚠️ **安全提示**：网关的 `/gateway/getgatewayproperties` 无需任何鉴权即可返回 `gatewayPwd`，而 `/gateway/setDeviceAttribute` 只需静态 key + 该密码即可控制设备。也就是说，**同一局域网内任何人都能读取密码并控制你的栖息地设备**。如在意，建议把网关放入独立 VLAN / IoT 网段。

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

### v0.3.5 (2026-09-27)

**修复：设备离线期间集成不创建实体 → 设备恢复后 HA 里永远「不可用」（必须重载集成才行）**

所有平台在创建实体时都按 `online` 过滤：

```python
if model in LIGHT_MODELS and online:      # light.py，switch/cover/sensor/… 同样
    ...创建实体...
```

后果（真实案例）：用户房间里「四合一面板」的固件更新后，面板把灯控器（`ZBW4CGJ` 灯带）的**电断掉了**；网关随即把这些灯标为 `online=false`。此时集成重载 → 这些灯**根本没被创建** → HA 只保留一个 `restored` 占位状态。等用户重新按键给灯控器上电、灯恢复在线后，HA 里**仍然是「不可用」**，除非再重载一次集成。

另外所有实体都**没有定义 `available`**，所以「可用性」完全由创建那一刻是否在线决定。

修复：

- 所有平台**无条件创建实体**（不再在创建阶段按 `online` 过滤）
- 新增 `helpers.HabitatAvailabilityMixin`，统一提供动态 `available`：

  ```python
  @property
  def available(self) -> bool:
      return bool((self._device_data or {}).get("online", True))
  ```

  设备离线时如实显示 `unavailable`，**重新上线后下一次轮询就会自动恢复**，不再需要重载集成。

### v0.3.4 (2026-09-27)

**新增：可配置的轮询间隔（默认 60s → 15s），改善灯光/开关状态滞后**

网关本地 API **没有推送/长轮询接口**（探测 `subscribe`/`notify`/`poll`/`getevent` 等 20 个候选端点全部 404，只有 `getgatewaydevice` 可用），所以由**物理开关、面板或栖息地 App** 引起的变更，HA 只能靠轮询发现。原来的间隔是固定的 60 秒，平均滞后 30 秒、最坏 60 秒 —— 这就是「灯明明亮着、HA 显示关闭，半分钟后又对了」。

现在可以在集成选项里选轮询间隔（**5 / 10 / 15 / 30 / 60 / 120 秒**，默认 **15 秒**）。设备列表约 85 KB/次、耗时约 0.26 秒，所以 15 秒完全不吃力；想更省流量可以调大。

### v0.3.3 (2026-09-27)

**修复：`curtainLevel <= 100` 时被误当成百分比，位置算错**

`cover.py` 里有一句启发式：

```python
if 0 <= level <= 100:
    level = int((level / 100) * 255)
```

但实测网关下发的 `curtainLevel` 就是**原始 0-255**（观测到 0 / 5 / 7 / 122 / 191 / 254 / 255），本地 API 与栖息地 App 也都用 0-255。结果任何 ≤ 100 的原始值都会被缩放，位置全错：

| 网关 level | 物理开度 | 旧显示 | 正确 |
|---|---|---|---|
| 5 | 98% | 95% | 98% |
| 50 | 80% | **50%** | 80% |
| 100 | 61% | **0%** | 61% |

已移除该启发式，直接按 0-255 处理。

### v0.3.2 (2026-09-27)

**修复：窗帘全开后 HA 永远显示「全关」（`curtainLevel = 0` 被当成属性缺失）**

网关的 `curtainLevel` 只有 `value` 字段（没有 `valueStr`），而 `cover.py` 写的是：

```python
raw = attr.get("value") or attr.get("valueStr")
```

`curtainLevel = 0` 表示**全开**，但 `0` 是 falsy → `raw` 变成 `None` → `continue` **跳过更新** → 实体保留旧的 `_level`。结果就是：窗帘一旦全开，HA 的位置/开关就永远停在旧值（通常表现为「物理全开、HA 显示全关」）。

实测证据（书房，方向正常的窗帘）：命令「关闭」→ 网关 level = **254**；命令「打开」→ level = **0**。即厂商 level 语义（0=开 / 255=关）与 HA position 语义（0=关 / 100=开）**天生相反**。

修复：

- `cover.py` 改用 `is None` 判断（`light.py` 早就是正确写法，`switch.py` 的通道名解析同步修正）
- 附带确认：因为厂商 level 语义与 HA 相反，**每一个窗帘都需要在集成选项里勾选「反向 - 窗帘」**，与电机方向 `curtainDir` 无关（那是另一个设置，只有装反的房间需要改）

### v0.3.1 (2026-09-27)

**修复：集成加载后所有实体只更新一次就再也不刷新（严重 bug）**

`DataUpdateCoordinator._async_refresh()` 只在「存在监听者」时才会安排下一次刷新：

```python
if not auth_failed and self._listeners and not self.hass.is_stopping:
    self._schedule_refresh()
```

本集成的实体是普通实体（自己在 `async_update` 里读 `coordinator.data`），从不调用 `async_add_listener`，于是 `_listeners` 恒为空 —— **协调器只做一次首次拉取，之后就永久停摆**。表现为：集成加载/重载后所有传感器、开关、灯的状态都停在那一刻，只有被操作过的设备（例如窗帘）因为命令路径会 `async_request_refresh()` 才偶尔更新。

这是长期存在的架构问题，与本次窗帘方向改动无关。修复方式是在 setup 时挂一个空监听者，把周期性轮询真正打开。

其他修复：

- 卸载集成时调用 `coordinator.async_shutdown()`，避免残留定时器；`hass.data` 清理改为 `pop(..., None)` 容错
- `via_device` 弃用告警 → 改用 `via_device_id`（HA 2027.8 会移除旧参数）
- `CONCENTRATION_PARTS_PER_MILLION` 弃用 → 改用等值字符串 `"ppm"`

### v0.3.0 (2026-09-27)

- **支持 HACS 自定义仓库**：新增 `hacs.json`（`content_in_root`）、品牌图 `brand/icon.png`、manifest 补 `issue_tracker`；README 增加 HACS 安装与升级说明

### v0.2.3 (2026-09-27)

- 文档：明确 `curtainDir` 会同时翻转「电机转向」与「位置值方向」，因此**修好硬件方向后必须在集成选项里勾上「反向 - 窗帘」**，否则 HA 的位置与开关会整体反过来（附实测映射表）

### v0.2.2 (2026-09-27)

- 迁移：旧版本只在实体状态里记录的方向（v0.2.0）会自动补写进 config entry options，升级后方向看护立即生效，无需手动重选

### v0.2.1 (2026-09-27)

- **窗帘方向持久化**：网关不保存 `curtainDir`（只转发给电机），方向会在网关重启/断电/云端同步后被重置。集成现在把期望方向记在 config entry options，并在**集成启动**与**检测到网关重新上线**时自动重新下发
- 新增服务 `habitat.reapply_curtain_direction`（可只处理指定 `device_uid`）与集成选项「方向看护」开关
- 文档：补充网关不持久化 `curtainDir` 的完整证据链与云端可能覆盖的分析

### v0.2.0 (2026-09-27)

- 新增「窗帘方向」选择实体：写入网关 `curtainDir`，**硬件级**纠正装反的电动窗帘（App 与硬件面板也会一起变正确）
- 新增 `tools/set_curtain_direction.py`：不依赖 HA 的独立脚本，可列出窗帘并查看/修改电机方向
- 文档：补充窗帘方向的原理、网关到 Zigbee 的属性映射（`curtainDir` → 窗帘簇 0x0102 厂商命令 `0xf1`）与网关密码暴露的安全提示

### v0.1.0 (2026-03-07)

- 初始版本：灯光、开关、窗帘、传感器
- 后续：五合一面板 Climate/Humidifier/Fan/Number、地暖状态、多网关、情景/五合一开关默认隐藏、英文翻译（Fresh Air 等）

## 许可证

MIT License

---

*本集成与栖息地智能家庭无官方关联，仅为社区爱好者开发。*
