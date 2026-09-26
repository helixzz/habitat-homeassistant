# 设备列表 API 参考样本

本目录用于存放从栖息地 **App** 或 **网关** 获取设备/房间等数据的 API 响应样本，便于集成根据真实数据结构优化设备与实体命名。

---

## 一、网关 API（集成当前使用）

- **路径**: `/gateway/getgatewaydevice`
- **响应**: `{ "code": 200, "params": { "devices": [ ... ] } }`

每个 `devices[]` 中的设备对象（以 `getgatewaydevice.json` 实测为准）：

| 字段 | 说明 |
|------|------|
| `model` | 型号字符串，如 ZSW5HGJ、ZT21LGJ、ZBW4CGJ |
| `deviceUid` | 设备唯一 ID，如 B0FD0BE01105117C |
| `online` | 布尔，是否在线 |
| `dev_attrs` | 属性数组，每项 `{ "name": "属性名", "value": 值 }`（数值或字符串，未见 `valueStr`） |
| `childGatewayId` | 可选，设备当前所属子网关 UID；无则表示在主网关上。控制指令需发往该网关，集成在每次控制时按此字段解析 API，设备迁移网关后无需重载 |

**窗帘**：`curtainState`（0/1/2）、`curtainLevel`（0–255 整数，中间值如 155 表示约 61% 开）、`curtainDir`（**电机方向**，0=正常 / 1=反向，可写）。集成已按 0–255 解析并换算为 HA 的 0–100%。

- `curtainDir` 是本项目实测确认的**窗帘方向参数**：栖息地 App 未暴露该设置，但写入网关 `setDeviceAttribute` 即生效，参数保存在**电机内部**（网关不持久化、也不回读，回报值恒为 0）。写入后电机会重新校准行程：方向确实改变时整程运行一次，未变则小幅抖动确认。详见仓库 README「窗帘方向」一节。
- 网关到 Zigbee 的映射（由网关日志实测）：`curtainDir` → 窗帘簇 0x0102 厂商自定义命令 `0xf1`（1 字节）；`curtainState` 0/1/2 → 标准 Up/Open(0x00) / Down/Close(0x01) / Stop(0x02)；`curtainLevel` → Level Control 簇 0x0008 的 Move to Level。

**多键开关**：网关返回 `state0`、`state1`… 及 `devName`，**不返回** `state0Name` 等通道名；集成用 `const.py` 中按 `model` 配置的默认通道名（如 ZSW5HGJ 五合一面板对应 按键1～5）。

---

## 二、App API（searchDeviceConditionByHome）

样本文件 `*.json` 为 **手机 App** 与服务器通信时获取的「按家庭/房间的设备列表」，与网关 API 结构不同，但可用于对齐命名与型号。

### 顶层结构

```json
{
  "result_code": 0,
  "data": [
    { "type": "device", "deviceInfo": { ... } }
  ]
}
```

### deviceInfo 常用字段

| 字段 | 说明 |
|------|------|
| `device_number` | 设备编号，对应网关的 deviceUid |
| `product_model_code` | 型号，如 SHC-8W01-SW、SHC-8Q04-SW |
| `device_name` | 设备名称 |
| `room_name` | 房间名称（如 主卧、客餐厅） |
| `online` | 是否在线 |
| `list` | 节点列表，每项含 `node_name`、`index`、`productTypeNodeAttrInfoList` |

### 多键开关在 App 中的表示

- **list[]** 中每个元素对应一个按键/通道，**index** 为通道索引（0,1,2…）。
- **node_name** 即该通道在 App 中的名称，例如：
  - 四加一面板 SHC-8Q04-SW：`"单键开关"`(index 0)、`"场景按键1"`～`"场景按键4"`(index 1-4)
  - 4键情景 SHC-8W02-SW：`"场景按键0"`～`"场景按键3"`
  - 五合一面板 SHC-8W01-SW：可能为多个节点或单节点，网关侧用 state0～state4 表示 5 路
- **productTypeNodeAttrInfoList** 中 **describe** 为属性说明（如「灯开关(S1)」「单击」「长按」）；双键灯控为 S1/S2。

集成中多键开关的**默认通道名**已按上述 App 命名做了对齐（如 单键、情景1～4、S1/S2、按键1～5），网关若未返回 `state{i}Name` 等则使用这些默认名。

---

## 三、网关样本 getgatewaydevice.json

本目录中的 `getgatewaydevice.json` 为网关 `/gateway/getgatewaydevice` 的真实响应样本（已脱敏），用于对齐集成与网关实际字段。

- **窗帘**：`curtainLevel` 为 0–255 整数，中间值会正确显示为 HA 的 0–100% 开合度。
- **开关型号**：网关侧五合一面板为 `ZSW5HGJ`（state0～state4），与 App 的 SHC-8W01-SW 为同类设备，集成已为 ZSW5HGJ 配置相同默认通道名。

请勿提交包含网关 UID、Key、密码或家庭信息的真实凭证。

---

## 四、多网关

- 主网关与子网关使用**各自**的 UID/密码登录（集成配置中主网关为首次添加，子网关在「选项」里填写 host/端口/UID/key/密码）。
- 设备列表由主网关拉取，返回中可包含子网下的设备；此类设备带 `childGatewayId`。
- 在 HA 内设备配置（如窗帘反向）按**设备 ID**（deviceUid）保存，与设备当时连在哪个网关无关。
- 执行控制时，根据设备当前的 `childGatewayId` 向对应网关发送 API 请求；设备在网关间迁移后无需重载集成。

**网关 IP 变更**：配置中的「主机」可填 IP 或主机名。建议在路由器中为网关设置 DHCP 保留或固定主机名，并在此处填写主机名（如 `habitat-gateway` 或 `gateway.local`），这样 DHCP 分配新 IP 后无需修改配置即可自动连接（每次请求会解析主机名）。
