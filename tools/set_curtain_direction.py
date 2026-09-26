#!/usr/bin/env python3
"""栖息地网关：查看/修改窗帘电机方向 (curtainDir)。

背景
----
栖息地 App 没有暴露窗帘方向设置，但网关本地 HTTP API 的 `curtainDir` 属性
就是该参数（0=正常，1=反向）。它保存在窗帘电机内部，写入后电机会重新校准
行程：方向真正改变时通常会整程运行一次，方向未变时只会小幅抖动确认。

用法
----
    # 列出网关下所有窗帘及其属性
    python3 set_curtain_direction.py --host 172.16.33.27 --list

    # 把某窗帘设为反向（1）
    python3 set_curtain_direction.py --host 172.16.33.27 \
        --device B0FD0BE011051113 --direction 1

    # 恢复为正常（0）
    python3 set_curtain_direction.py --host 172.16.33.27 \
        --device B0FD0BE011051113 --direction 0

说明
----
* 网关的 `getgatewayproperties` 无需鉴权即可返回 `gatewayPwd`，脚本默认据此
  自动获取密码；如你不想依赖该行为，可用 `--pwd` 显式传入（见 README 获取凭证）。
* 网关 `curtainDir` 的回报值恒为 0（不回读电机内实际值），因此本脚本打印的
  “当前值”仅供参考，请以窗帘实际动作方向为准。
"""

import argparse
import json
import sys
import urllib.request

DEFAULT_ACCESS_ID = "FBee.key"
DEFAULT_KEY = "90ff179ea717b44e91ab31944cfc01a76f42fc612a44240aed1b8f8bc28a812a"
COVER_MODELS = {"ZT21LGJ", "EC02000001"}


def _post(host, path, payload, port=80):
    url = f"http://{host}:{port}{path}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)


def _auth(host, port, uid, key, pwd):
    return {
        "accessID": DEFAULT_ACCESS_ID,
        "key": key,
        "ver": "1.0",
        "uid": uid,
        "pwd": pwd,
    }


def resolve_credentials(host, port, uid, key, pwd):
    """若未显式提供 uid/pwd，则通过 getgatewayproperties 自动获取（该接口无需鉴权）。"""
    if uid and pwd:
        return uid, pwd
    props = _post(host, "/gateway/getgatewayproperties", {"accessID": DEFAULT_ACCESS_ID, "key": key, "ver": "1.0"}, port)
    params = props.get("params", {})
    uid = uid or params.get("gatewayId")
    pwd = pwd or params.get("gatewayPwd")
    return uid, pwd


def fetch_curtains(host, port, uid, key, pwd):
    resp = _post(host, "/gateway/getgatewaydevice", _auth(host, port, uid, key, pwd), port)
    devices = resp.get("params", {}).get("devices", []) or []
    curtains = []
    for dev in devices:
        if dev.get("model") not in COVER_MODELS:
            continue
        attrs = {a.get("name"): a.get("value") for a in dev.get("dev_attrs", [])}
        curtains.append(
            {
                "deviceUid": dev.get("deviceUid"),
                "devName": attrs.get("devName"),
                "childGatewayId": dev.get("childGatewayId"),
                "online": dev.get("online"),
                "curtainState": attrs.get("curtainState"),
                "curtainLevel": attrs.get("curtainLevel"),
                "curtainDir": attrs.get("curtainDir"),
            }
        )
    return curtains


def set_direction(host, port, uid, key, pwd, device_uid, child_gateway_id, value):
    params = {
        "childGatewayId": child_gateway_id or uid,
        "deviceUid": device_uid,
        "dev_attr": {"name": "curtainDir", "value": value},
    }
    body = _auth(host, port, uid, key, pwd)
    body["params"] = params
    return _post(host, "/gateway/setDeviceAttribute", body, port)


def main():
    parser = argparse.ArgumentParser(description="查看/修改栖息地窗帘电机方向 (curtainDir)")
    parser.add_argument("--host", required=True, help="网关 IP 或主机名")
    parser.add_argument("--port", type=int, default=80)
    parser.add_argument("--uid", help="网关 UID（如 2G01_25420142）；省略则自动获取")
    parser.add_argument("--key", default=DEFAULT_KEY, help="网关 key（同 Web 界面静态 key）")
    parser.add_argument("--pwd", help="网关密码；省略则自动从 getgatewayproperties 获取")
    parser.add_argument("--list", action="store_true", help="列出所有窗帘")
    parser.add_argument("--device", help="要修改的窗帘 deviceUid")
    parser.add_argument("--direction", type=int, choices=[0, 1], help="0=正常，1=反向")
    args = parser.parse_args()

    uid, pwd = resolve_credentials(args.host, args.port, args.uid, args.key, args.pwd)
    if not uid or not pwd:
        print("无法获取网关 UID/密码，请用 --uid/--pwd 显式传入。", file=sys.stderr)
        return 1

    curtains = fetch_curtains(args.host, args.port, uid, args.key, pwd)
    if args.list or args.device is None:
        print(f"网关 {uid}（{args.host}）下的窗帘：")
        for c in curtains:
            print(
                f"  {c['deviceUid']}  {c['devName']}  "
                f"online={c['online']} state={c['curtainState']} "
                f"level={c['curtainLevel']} dir(回报)={c['curtainDir']} "
                f"gw={c['childGatewayId']}"
            )
        if args.device is None:
            return 0

    if args.direction is None:
        print("请用 --direction 0|1 指定方向。", file=sys.stderr)
        return 1

    target = next((c for c in curtains if c["deviceUid"] == args.device), None)
    if target is None:
        print(f"未找到窗帘 {args.device}", file=sys.stderr)
        return 1

    resp = set_direction(
        args.host, args.port, uid, args.key, pwd,
        target["deviceUid"], target["childGatewayId"], args.direction,
    )
    print(json.dumps(resp, ensure_ascii=False))
    if resp.get("code") == 200:
        print(
            f"已写入 curtainDir={args.direction}（{'反向' if args.direction else '正常'}）。"
            "若方向真正改变，窗帘会整程运行一次以重新校准。"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
