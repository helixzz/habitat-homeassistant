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
| `bindRelayList` | **数组** | ✅（见 3.2） | 按键绑定了哪几路继电器；**空数组 = 按键不再驱动继电器** |
| `ownGroupList` | 数组 | ❌ 只上行 | 按键绑定的 Zigbee 组；要改只能通过 `/group/add` 重新下发 |
| `LCsetDirection` / `LCcurrentDirection` | int | ❌ 只上行 | 本地控制方向相关，实测两种工作模式下都是 `0`，与按键行为无关 |
| `levelMixColorTemp` / `stateOffset` / `sectionNums` | int | — | 描述性字段 |
| `devName` / `devRSSI` / `sceneState*` / `sceneLp*` | — | ❌ 只上行 | 状态上报 |

> 读取这些属性时，网关的 `getgatewaydevice` 对数组属性会**返回一个指针数值**（不是数组内容），别被误导 —— 数组真实值要从日志里的设备上报报文看。

---

## 4. 面板「按键切电」的机制（v0.3.7 解决的问题）

面板固件里一个按键有**两套彼此独立的绑定**：

| 绑定 | 字段 | 行为 |
|---|---|---|
| 组绑定 | `ownGroupList` | 按键向 Zigbee 组发**组播命令** |
| 继电器绑定 | `bindRelayList` | 按键**直接吸合面板自己的继电器**（纯本地行为） |

- 面板负载若是**独立智能灯控器**（常火线供电），继电器绑定多余且有害：按按键会切断灯控器供电，灯控器靠电容撑**约 7 分钟**后掉线并一直离线
- 面板负载若是**它自己的继电器输出**（普通灯），继电器绑定**必须保留** —— 切继电器是唯一能开关那盏灯的方式

**判据**：看该面板名下所有 Zigbee 组的成员里**有没有它自己**。
不含自己 → 解绑；含自己 → 保留。集成已实现自动分类与看护，见 [README](README.md#面板按键不让按键切断智能灯控器的供电-v037)。

---

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
