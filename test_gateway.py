"""One-off script to verify gateway API: get devices and optional control.
Run from repo root: python test_gateway.py
Uses credentials from your capture (host, uid, key, pwd)."""
import asyncio
import json
import sys
sys.path.insert(0, ".")
from api import HabitatAPI

HOST = "172.16.33.72"
UID = "2G01_25420142"
KEY = "90ff179ea717b44e91ab31944cfc01a76f42fc612a44240aed1b8f8bc28a812a"
PWD = "FDCE15C3AD9EC6C3FE10E16429711826"

async def main():
    api = HabitatAPI(host=HOST, access_id="FBee.key", key=KEY, uid=UID, pwd=PWD)
    print("1. get_devices() ...")
    devices = await api.get_devices()
    if not devices:
        print("   FAIL: no devices returned (check network, host, uid/key/pwd)")
        return
    print(f"   OK: {len(devices)} devices")
    for i, d in enumerate(devices[:5]):
        name = d.get("deviceUid", "?")
        for a in d.get("dev_attrs", []):
            if a.get("name") == "devName":
                name = a.get("value", name)
                break
        print(f"   [{i}] model={d.get('model')} online={d.get('online')} name={name} deviceUid={d.get('deviceUid')}")
    if len(devices) > 5:
        print(f"   ... and {len(devices) - 5} more")
    # Save sample for reference (attr names, model list)
    try:
        with open("devices_sample.json", "w", encoding="utf-8") as f:
            json.dump(devices[:3], f, ensure_ascii=False, indent=2)
        print("   Sample written to devices_sample.json")
    except Exception as e:
        print(f"   Skip sample file: {e}")

    # Optional: try set attribute on first device that might support state0 (e.g. light/switch)
    device_uid = "B0FD0BE011049085"  # from your capture
    if not any(d.get("deviceUid") == device_uid for d in devices):
        device_uid = None
        for d in devices:
            uid = d.get("deviceUid")
            model = d.get("model", "")
            if uid and (model in ("ZBW4CGJ", "ZSW5BGJ", "ZSW5GGJ", "ZWN04GJ", "CUN01GJ", "8DO") or "SW" in model or "LI" in model):
                device_uid = uid
                break
    if device_uid:
        print("\n2. set_device_attribute(..., 'state0', 0) then 1 ...")
        ok0 = await api.set_device_attribute(device_uid, "state0", 0)
        print(f"   state0=0: {ok0}")
        ok1 = await api.set_device_attribute(device_uid, "state0", 1)
        print(f"   state0=1: {ok1}")
    else:
        print("\n2. Skip control test (no suitable device Uid)")

if __name__ == "__main__":
    asyncio.run(main())
