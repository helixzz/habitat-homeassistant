# 栖息地 / 飞比（FBee）网关本地 API 参考

本文件记录在逆向与调试过程中实测确认的网关行为，供后续维护参考。
对应网关：`SHC-2G01-SW`（飞比 FBee 方案，南社科技 / 栖息地贴牌），固件 `DS1.5.3`。
所有结论均来自抓取网关自身日志（`/gateway/loggerpush`）与逐条实验，**不是厂商文档**。

> ⚠️ 本文件里的地址、UID、密钥都是示例，请以你自己的网关注册信息为准。

---

## 1. 本地 HTTP 接口

网关 `80` 端口是**无鉴权**的本地控制接口（[见第 6 节](#6-安全注意)）。请求体统一为：

```json
{
  "accessID": "FBee.key",
  "key": "<应用 key，固定值>",
  "ver": "1.0",
  "uid": "2G01_25420142",
  "pwd": "<网关密码>",
  "params": { }
}
```

接口按**基址**分成四组：

| 基址 | 接口 | 说明 |
|---|---|---|
| `/gateway/` | `getgatewayproperties` | 网关属性（含 `gatewayPwd`、`gatewayId`） |
| | `login` | 登录（实际不校验） |
| | `getgatewaydevice` | **全部设备 + 全部属性**（约 85 KB） |
| | `setDeviceAttribute` | 写设备属性（见第 3 节） |
| | `loggerpush` | 拉取网关内部日志压缩包（最重要的调试手段） |
| | `setpermitjoin` | 允许设备入网 |
| | `deldevice` | 删除设备 |
| | `find` / `reboot` / `enablessh` / `localupgrade` / `triggerUpgrade` / `checkUpgrade` | 寻找 / 重启 / 开 SSH / 升级 |
| | `setbase` / `setnetwork` / `setother` | 网关自身配置 |
| `/group/` | `getall` / `add` / `del` / `exec` | Zigbee 分组 |
| `/autoscene/` | `getall` / `add` / `del` / `exec` / `setstate` | 自动化场景 |
| `/defense/` | `getall` / `setstate` | 安防 |

**注意**：`/gateway/group_getall` 不存在（404），分组必须走 `/group/getall`。
`/group/*` 用 JSON 提交正常，用表单编码会 500（`'NoneType' object has no attribute 'get'`）。

### 允许设备入网

```bash
curl -s -X POST http://<网关IP>/gateway/setpermitjoin \
  -H 'Content-Type: application/json' \
  -d '{"accessID":"FBee.key","key":"<key>","ver":"1.0","uid":"<uid>","pwd":"<pwd>",
       "params":{"childGatewayId":"<uid>","state":1,"time":60}}'
```

- 不带 `params` 会返回 **403 Forbidden**（看起来像鉴权失败，其实是缺参数）
- `time` 被固件**钳死在 60 秒**，要长时间配网必须每 <60 秒续开一次
- 是否生效看网关日志：`permit join status` 与 `permit time 60`

---

## 2. 属性名 → 设备侧的映射

网关用**两套互不相干的处理器命名**，判断「某个属性能不能真正下发到设备」时必须两套都找：

| 命名 | 所在文件 | 含义 | 例子 |
|---|---|---|---|
| `privAttr_<名字>_down` | `privAttr_*.c` | 厂商私有属性下行 | `privAttr_state0_down` |
| `attr_set_<名字>` | `mAttr_down.c` | **模型属性下行** | `attr_set_curtain_dir`、`attr_set_bindRelayList` |

> 只搜 `privAttr_*` 会得出「该属性不可写」的**错误结论** —— 我在 `bindRelayList` 上就栽过这个跟头。

判断某个属性是否有下发能力，还可以看日志里有没有这行：

```
(model.c:3752) the dev index for attr <名字> is <索引>
```

`-1` 表示模型层没有该属性的设备侧映射。

---

## 3. `setDeviceAttribute` 的行为

```bash
curl -s -X POST http://<网关IP>/gateway/setDeviceAttribute \
  -H 'Content-Type: application/json' \
  -d '{"accessID":"FBee.key","key":"<key>","ver":"1.0","uid":"<uid>","pwd":"<pwd>",
       "params":{"childGatewayId":"<uid>","deviceUid":"<设备IEEE>",
                 "dev_attr":{"name":"<属性名>","value":<值>}}}'
```

### 3.1 值没变化就不下发

**网关会拿新值和数据库里已有的值比较，相同则不产生任何下行**（日志里连 `attr_set_*` 都不会出现）。
所以「写一个等于当前值的值」是**静默无效**的 —— 调试时极易误判。

### 3.2 传数组会让网关崩

以 `bindRelayList`（取值是数组）为例：

| 传法 | HTTP 响应 | 是否下发 | 备注 |
|---|---|---|---|
| JSON 数组 `[]` / `[1,2,3,4]` | **500** | ✅ 会 | 网关解析正确、也真的下发了，但**拼响应时崩**；反复触发会**压死 HTTP 服务**（实测约 1 分钟完全无响应、之后自愈）。而且受 3.1 影响，值没变就静默跳过 |
| 字符串 `"[]"` | **200** | ✅ 会 | 解析路径不同（日志出现 `wrong json array data!`），**固定下发 `zgb_val:0`**，不受 3.1 限制，一条请求即可 ✅ |
| 字符串 `"[1,2,3,4]"` | **200** | ⚠️ 下发的是 `0` | 字符串形式无法表达非空数组 |

**结论**：需要把数组属性清零时，传字符串 `"[]"`；需要设成非空数组时无安全写法（用数组形式但控制频率）。

日志证据：

```
(mAttr_down.c:3419) attr_set_bindRelayList starts...
(mAttr_down.c:3442) buf: []
(mAttr_down.c:3447) zgb_val:0
(common.c:189) Gw[2G01_25420142]Sd[13] Send:15 00 42 01 42 25 FE 8D 0C 02 4F 68 01 00 FB 05 00 02 20 01 00
```

### 3.3 关键属性清单（实测）

| 属性 | 类型 | 可下发 | 说明 |
|---|---|---|---|
| `state0`…`state6` | int | ✅ | 面板各路继电器 / 开关通道 |
| `curtainDir` | int | ✅ | 窗帘电机方向（0 正常 / 1 反向），**电机内**存储，网关不持久化 |
| `curtainLevel` | int | ✅ | 窗帘位置，**原始 0–255**，0=全开、255=全关（与 HA 语义相反） |
| `bindRelayList` | **数组** | ✅（见 3.2） | **按键输出绑定表** —— 按键有没有输出、输出到哪几路。⚠️ **空数组 = 按键完全没有输出**（不只是不驱动继电器，连 Zigbee 组播控灯也一起失效，按键变死键，只能恢复出厂设置恢复）。它**不是**「按键→继电器」的独立开关 |
| `ownGroupList` | 数组 | ❌ 只上行 | 按键绑定的 Zigbee 组；要改只能通过 `/group/add` 重新下发 |
| `LCsetDirection` / `LCcurrentDirection` | int | ❌ 只上行 | 本地控制方向相关，实测两种工作模式下都是 `0`，与按键行为无关 |
| `levelMixColorTemp` / `stateOffset` / `sectionNums` | int | — | 描述性字段 |
| `devName` / `devRSSI` / `sceneState*` / `sceneLp*` | — | ❌ 只上行 | 状态上报 |

> 读取这些属性时，网关的 `getgatewaydevice` 对数组属性会**返回一个指针数值**（不是数组内容），别被误导 —— 数组真实值要从日志里的设备上报报文看。

---

## 4. 面板按键为什么会切断智能灯控器的供电

部分面板型号（如双键开关 `ZSW5GGJ`）的按键**在硬件上直连自己的继电器**。当这类面板的负载是
**独立智能灯控器**（常火线供电）时，按下按键会顺带切断灯控器的供电 —— 灯控器靠电容能撑
**约 7 分钟**才被网关判为离线，然后一直离线（用户看到的就是「灯忽然不可用」）。

`bindRelayList` 是**按键输出绑定表**（按键有没有输出、输出到哪几路），**不是**「按键→继电器」
的独立开关：

- 写空数组 → 按键**完全没有输出**（连 Zigbee 组播控灯也失效，按键变死键）✗
- 集成 v0.3.7 曾据此实现「自动解绑」，**实测是错的**，v0.3.8 起默认关闭

**正确做法**：改接线（把灯控器挪到常火线）、换用按键不直连继电器的面板（五合一面板、
情景开关），或接受该面板按键失效。详见 [README](README.md#-面板按键与智能灯控器的供电重要更正)。

### 4.1 实测确认：出厂默认就是「按键直连继电器」

把双键开关**恢复出厂设置**再让它重新入网后，按键立刻回到「直连继电器」的行为。
也就是说这**不是**某个被改坏的配置，而是**设备出厂行为**；面板重新入网时网关只会把它名下
的 Zigbee 组绑定推回去（`ownGroupList` 可见），**不会**改变按键与继电器的耦合。

### 4.2 实测确认：栖息地 App 的「按键绑定」保存是坏的（云端侧）

App 里确实有完整的按键绑定界面（每个按键的 **单击 / 双击 / 长按** 可分别设置，例如
「单击 → 色温灯」「长按 → 由暗到明」），但**保存一律失败**（App 只弹「保存失败」，无更多信息）。

抓取网关日志可以确认**保存请求根本没到网关**：

| 你操作 App 的那一分钟里，云端对网关的请求 | 次数 |
|---|---|
| `gm_down_request_get_devs`（读设备列表） | 19 |
| `gm_down_request_gm_info`（读网关信息） | 7 |
| `gm_down_group_request_all`（读全部分组） | 1 |
| **`gm_down_dev_set_attr`（写设备属性）** | **0** |
| **任何绑定/分组写入** | **0** |

即：**App 能正常读，但保存被云端直接拒绝**，命令从未下发到网关。这解释了「保存成功过一次
但按键毫无作用」——那次很可能也只是写进了云端，没有下发。

**结论**：通过 App 改变按键绑定这条路**走不通**（属于厂商后端问题，需向楠社科技/栖息地反馈，
或由装机商使用其工程工具）。

### 4.3 错配点：云端缺少该设备的「普通灯连接」记录

同一型号（`SHC-8Q03-SW`）的三台双键开关，在 App 里的表现不同，根因是**云端设备记录结构不同**：

| 设备 | 云端记录 | App 渲染 | 保存按键绑定 |
|---|---|---|---|
| 主卫 `…C17E` | 含 `普通灯(双键S1连接)`、`普通灯(双键S2连接)` | 普通灯开关 | ✅ 3–5 秒成功 |
| 中厨 `…B5F5` | 含 `普通灯(双键S2连接)` | 普通灯开关 | ✅ 正常 |
| **主卧 `…C11A`** | **只有一条 `双键开关`，无任何普通灯记录** | **智能开关**（可编辑灯具亮度） | ❌ **转圈 10s+ 后失败** |

而**网关侧三台设备的字段完全相同**（`deviceType=0x0000000A`、`model=ZSW5GGJ`、
`snid=FZT56-ZSW5GGJ5.1`）—— 说明那两条「普通灯连接」记录是**云端/装机商在配置时创建的**，
不是网关上报的。

**保存失败的瞬间取证**（覆盖操作的 2 分钟日志）：

| 云端对网关的请求 | 次数 |
|---|---|
| `gm_down_request_get_devs` | **32 次**（约每 4 秒一次，在轮询等待变更） |
| `gm_down_request_gm_info` | 9 次 |
| 写入设备属性 / 绑定 / 分组 | **0 次** |
| 该设备的任何活动、网关发出的 Zigbee 帧 | **0** |

即：云端把配置写进自己的库之后，**未能构造/下发任何命令**，反复轮询网关 10 秒后超时失败。
**这解释了「保存失败 + 按键无作用」**：云端认为它是智能开关，设备实际运行在本地继电器模式，
两边协议对不上。

**修复只能由厂商在云端完成**（补齐/重建该设备记录），或由装机商使用工程工具。

## 5. 分组（Zigbee 组）

```json
{
  "name": "gn_<homeId>_<roomId>_<序号>",
  "order": 1,
  "imgOrder": 0,
  "members": [ { "childGatewayId": "...", "deviceUid": "..." } ],
  "belongToDevSection": { "deviceUid": "<面板IEEE>", "sectionOrder": 1 }
}
```

- `POST /group/add` 用来**新建或重存**分组；重存时会**把绑定重新下发给面板** —— 这也是「固件更新清掉面板本地组绑定」后唯一能修复的手段
- **必须带 `belongToDevSection`**：漏掉会把该按键的归属清空（我在调试时踩过，把主卧的绑定弄丢过）
- 组名格式：`gn_<homeId>_<roomId>_<sectionOrder>`
- 面板上报的 `ownGroupList` 形如 `[{"sectionOrder":1,"groupName":"gn_..."}]`，`groupName` 为空串表示该按键**没有组绑定**

---

## 6. 安全注意

- **本地 API 没有真正的鉴权**：`pwd` 填错、甚至不填，`getgatewaydevice` 依然返回完整设备列表（含设备密钥类字段）
- `getgatewayproperties` 会直接返回 `gatewayPwd` 明文
- `enablessh` 可开启网关 SSH
- 因此**不要把网关暴露到公网**；如需远程访问请走 VPN / 反向代理 + 额外鉴权

---

## 7. 云端连接（仅记录，未使用）

| 用途 | 地址 |
|---|---|
| 主网关长连接 | `v2.fbeecloud.com:18090`（`Account=<网关ID> Passwd=<网关密码>`） |
| 子网关长连接 | `zzz.com:18090` |
| MQTT | `iot-mqtts-cn-north-1.nanshe-tech.com` |
| OTA | `https://ota.nanshe-tech.com/ota/fiveinone/<型号>/update.json` |

云端下行与本地 API 走**同一个属性处理器**（`gm_down_dev_set_attr`），所以云端理论上能改任何一个本地能改的属性 —— 包括 `curtainDir`。

---

## 8. 调试方法

网关自带日志推送，是最有效的排障手段：

```bash
curl -s -X POST http://<网关IP>/gateway/loggerpush \
  -H 'Content-Type: application/json' \
  -d '{"accessID":"FBee.key","key":"<key>","ver":"1.0","uid":"<uid>","pwd":"<pwd>","params":{}}' \
  -o log.gz && tar tzf log.gz
```

关键日志文件：

| 文件 | 内容 |
|---|---|
| `tmp/elog_py/elog_py.log` | 网关主逻辑（属性下行、Zigbee 帧收发、上报） |
| `tmp/elog_GM.log` | 设备模型层 |
| `tmp/elog_sm/elog_sm.log` | Zigbee 协议栈（配网、组、绑定） |

常用检索关键词：

```
attr_set_<属性名>        # 属性下行处理器被调用
privAttr_<属性名>_down   # 私有属性下行处理器
the dev index for attr   # 该属性是否有设备侧映射（-1 = 没有）
Send:15                  # 发往 Zigbee 模块的帧
zgb_up_<属性名>          # 属性上行
permit join              # 配网状态
```

---

## 9. 其它实测坑

- `pkill -f` 会误杀自己的 shell，杀进程请用 PID
- 大量并发写属性（例如穷举 7000 个候选属性名）会把网关 HTTP 服务压到无响应，通常一分钟左右自愈
- 主网关的 `getgatewaydevice` **已经包含子网关下的设备**，遍历两台网关时要按 `deviceUid` 去重
- 网关判设备离线有明显延迟（面板继电器断开供电后，灯控器约 **7 分钟**才变 `online=false`），短时间采样会得出错误结论

---

## 10. ⚠️ 不要把网关的 HTTP API 拉太频繁 —— 会让**全屋开关「失灵」**

**实测（本项目的真实事故）**：高频/并发调用 `getgatewaydevice`（每次约 85 KB）会占满网关 CPU，
进而**饿死它的 Zigbee 协调器**。表现是：

- **全屋面板按键、开关全部没有反应**（按键后灯不响应，但设备在网关里显示 `online=True`）
- 同时 HA 侧出现大量 `Connection reset by peer` / `Cannot connect to host 172.16.33.27:80` /
  `API request timeout`（实测一次事故里积累了 **93 次**，另一次 `Gateway returned no devices`）

**这不是设备损坏，负载一撤就自动恢复。**

复现条件（事故当时的实际负载）：3 秒一次的轮询脚本 × 双网关各拉一遍 ≈ **3.3 MB/分钟**，
再叠加一次 3900 条属性的写入穷举；持续十几分钟即出现上述现象，脚本停掉后立即恢复。

**安全做法**：

| 做法 | 说明 |
|---|---|
| 轮询间隔 ≥ **15 秒** | 集成默认值。选项里的 **5 秒档属于激进设置**，不建议长期使用 |
| 不要同时开多个「轮询设备列表」的脚本 | 每个脚本都在拉完整的 85 KB 设备表 |
| 需要高频观测时缩小范围 | 只查你关心的少数设备，而不是每次拉全表 |
| 调试脚本之间留出间隔 | 写完属性后 sleep 几秒再拉状态 |

> 排查此类问题时，先看 HA 日志里有没有 `Connection reset by peer` / `Gateway returned no devices`
> —— 有的话基本可以确定是网关被 HTTP 请求压住了，而不是 Zigbee 设备或配置出了问题。

