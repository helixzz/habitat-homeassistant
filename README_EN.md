# Habitat Smart Home – Home Assistant Integration

![Project](https://img.shields.io/badge/project-habitat-blue)
![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-green)
![Python](https://img.shields.io/badge/Python-3.10%2B-yellow)

[简体中文](./README.md) | English

## Supported features

| Device type | Features | Status |
|------------|----------|--------|
| CCT Light | On/off, brightness, color temperature | ✅ |
| Smart switch | On/off (multi‑key / scene / 5‑in‑1 panel buttons hidden by default) | ✅ |
| Motorized curtain | Open/close/stop, position | ✅ |
| Motorized curtain · direction | Normal/reversed (`curtainDir`, not exposed in the App — see below) | ✅ |
| 5‑in‑1 environment sensor | Temperature, humidity, PM2.5, PM10, CO2, AQI | ✅ |
| 5‑in‑1 panel · AC | Climate entity: current/target temperature, AC fan (off / 1–6 / auto) | ✅ |
| 5‑in‑1 panel · Humidifier | Humidifier entity: current/target humidity (Fresh Air humidification) | ✅ |
| 5‑in‑1 panel · Fresh Air | Main panel only: Fan entity (Fresh Air supply 0–6 / auto) | ✅ |
| 5‑in‑1 panel · Floor heating | Main panel only: floor heating state, filter/humidifier service hours (read‑only) | ✅ |
| AC (water unit indoor) | Current temperature, set temperature (read‑only sensors) | ✅ |
| Fresh Air unit | Humidity, filter service hours | ✅ |
| Gas alarm | Gas state, concentration | ✅ |

The 5‑in‑1 panel acts as AC, Fresh Air (main panel controls whole‑house supply), and floor heating controller. Target temperature, humidity, and fan speeds are exposed as native **Climate**, **Humidifier**, and **Fan** entities. Optional Number entities are hidden by default in the entity registry; you can enable them under **Settings → Entities**.

**Multiple gateways** are supported: you can add primary and child gateways in the integration options; devices use the API of their assigned gateway.

## Installation

### Option 1: Manual installation

Copy the following from this repository into your Home Assistant config directory under `custom_components/habitat/` (create the `habitat` folder if it does not exist).

**Required files:**

- `__init__.py`, `config_flow.py`, `manifest.json`, `const.py`, `api.py`
- `helpers.py`
- `light.py`, `switch.py`, `cover.py`, `sensor.py`
- `number.py`, `climate.py`, `humidifier.py`, `fan.py`, `select.py`
- `services.yaml` (UI descriptions for the `reapply_curtain_direction` service)
- The `translations/` directory (including `en.json` for English entity names)

**Optional:**

- `brand/` directory: for integration logo in HA (requires HA 2026.3+). See `brand/README.md`.

Example (replace `config` with your HA config path):

```bash
mkdir -p config/custom_components/habitat
cp __init__.py config_flow.py manifest.json const.py api.py helpers.py \
   light.py switch.py cover.py sensor.py number.py climate.py humidifier.py fan.py select.py \
   services.yaml \
   config/custom_components/habitat/
cp -r translations config/custom_components/habitat/
cp -r brand config/custom_components/habitat/ 2>/dev/null || true
```

Then restart Home Assistant.

### Option 2: HACS (recommended)

> HACS support coming soon

## Configuration

### First-time setup

1. Open Home Assistant
2. Go to **Settings** → **Devices & services**
3. Click **Add integration**
4. Search for **栖息地智能家庭** (Habitat Smart Home)
5. Enter:

| Field | Description | Example |
|-------|-------------|--------|
| Gateway IP | Local IP of the Habitat gateway | `172.16.33.72` |
| Gateway UID | Gateway serial / UID | `2G01_25420142` |
| API Key | Authentication key | (see below) |
| Password | Authentication password | (see below) |

After setup, you can add child gateways in the integration **Options** (multiple gateways).

### Getting API credentials

Use your browser’s developer tools (F12) to capture the login request when accessing the Zigbee gateway’s web interface over HTTP. Use the parameters from that request:

```json
{
  "uid": "2G01_25420142",
  "key": "90ff179ea717b44e91ab3100000000006f42f0000000000ae0000000000a812a",
  "pwd": "FDCE1234567890123456710000000000"
}
```

## Devices and entities

The integration discovers and creates:

- **Lights**: ceiling lights, strips, etc.
- **Switches**: smart switches, scene panels, 5‑in‑1 panel keys (switch entities for scene/5‑in‑1 panels are hidden by default; you can unhide them in the entity registry)
- **Covers**: motorized curtains (each curtain device also gets a **direction** select entity, see below)
- **Sensors**: 5‑in‑1 environment (temp, humidity, PM2.5/PM10, CO2, AQI), AC temperature, Fresh Air filter hours, gas alarm
- **5‑in‑1 panel**: each panel has a **Climate** (AC) and **Humidifier** (humidity target) entity; the **main panel** also has a **Fan** (Fresh Air supply) and floor heating state plus filter/humidifier service hour sensors. The main panel is detected automatically (filter or humidifier service hours non‑zero).

## Curtain direction: fixing a curtain installed the wrong way

A curtain motor's direction (normal/reversed) is stored **inside the motor**. Neither the Habitat App nor the hardware panels expose it — but the gateway's local API attribute `curtainDir` is exactly that parameter:

| Attribute | Meaning | Values |
|-----------|---------|--------|
| `curtainDir` | Motor direction | `0` = normal, `1` = reversed |

The write takes effect immediately and the motor re-calibrates its travel: if the direction actually changes it usually performs **one full run**; if it does not change, it only jogs slightly to acknowledge.

> ⚠️ **Important: the gateway does not persist this value.** It merely forwards `curtainDir` to the motor (`gm_down_dev_set_attr` → `attr_set_curtain_dir` → Zigbee `0xf1`) and **never writes it to its database**; the gateway's own attribute cache (`prevDevAttrList`) only tracks `curtainState` / `curtainLevel`. So a **gateway restart, power loss, or a same-named cloud push can reset the direction back to 0**. Since v0.2.1 the integration solves this with a direction watchdog (below).

**From HA**: every curtain device gets a “窗帘方向” (curtain direction) select entity with Normal/Reversed options.

- The gateway **always reports `curtainDir` as 0** (it does not read the motor's stored value), so the entity state reflects the last write.
- This is a **hardware-level** fix; the integration option “反向 - curtain” is a **software-level** fix. Enabling both cancels out — normally you want only one, preferably the direction entity so the App and hardware panels become correct too.

### Direction watchdog (persistence, v0.2.1+)

Because the gateway cannot store the value, the integration keeps the desired direction in the config entry options (`curtain_dir_overrides`) as the source of truth and re-sends it automatically:

- **on integration setup / HA restart** (after a 45 s grace period for the Zigbee network)
- **when the gateway comes back online** (a poll going from failure to success means it restarted)

It can be turned off in the integration **Options** (`方向看护`), or triggered manually:

```yaml
service: habitat.reapply_curtain_direction
# optional: only one curtain
data:
  device_uid: B0FD0BE011051113
```

Re-sending when the direction is already correct makes the motor **jog slightly** to acknowledge — that is expected.

**Outside HA** (script shipped in this repo):

```bash
# list all curtains on the gateway
python3 tools/set_curtain_direction.py --host 172.16.33.27 --list

# set reversed (1) / restore normal (0)
python3 tools/set_curtain_direction.py --host 172.16.33.27 \
    --device B0FD0BE011051113 --direction 1
```

The script reads `gatewayPwd` from the gateway's `getgatewayproperties` (that endpoint needs no authentication — see the security note below).

**How it works**: the gateway maps `curtainDir` to manufacturer-specific command `0xf1` of the Zigbee Window Covering cluster (0x0102); `curtainState` maps to the standard Up/Open(0x00)/Down/Close(0x01)/Stop(0x02) commands and `curtainLevel` to Level Control Move to Level. The open/close direction is decided by `curtainDir` inside the motor, independent of the App/gateway — which is why a software-only inversion in HA cannot fix the App or the panels.

> ⚠️ **Security note**: the gateway's `/gateway/getgatewayproperties` returns `gatewayPwd` with no authentication, and `/gateway/setDeviceAttribute` only needs the static key plus that password to control devices. In other words, **anyone on the same LAN can read the password and control your Habitat devices**. If that matters to you, put the gateway on a separate VLAN / IoT network.

## Troubleshooting

### Log shows “blocking call to import_module” or integration path is habitat-homeassistant

The integration **folder name must be `habitat`** (same as the manifest domain), not `habitat-homeassistant`. If logs still reference `custom_components.habitat-homeassistant`, HA is loading from the old path.

**Fix (do all steps):**

1. **Use only the correct folder**: Under `custom_components/` keep only **`habitat`** with all .py files, manifest.json, translations, etc. If **`habitat-homeassistant`** exists, **delete that entire folder** (do not just rename).
2. **Re-add the integration**: **Settings → Devices & services → Integrations**, remove “栖息地智能家庭”, then add it again and enter gateway details.
3. **Restart Home Assistant.**

The integration sets `"import_executor": true` in `manifest.json` to reduce event loop blocking warnings.

### Cannot connect to gateway

1. Ensure the Home Assistant host and Habitat gateway are on the same network
2. Check the gateway IP
3. Try `ping <gateway-ip>`

### Device not online

1. Confirm the device is online in the Habitat app
2. Restart the gateway
3. Reload the integration

## Development

### Local development

Clone or copy this repo into `custom_components/habitat/`, then restart HA or reload the integration after changes. Enabling HA developer mode helps with logs.

### Adding new device types

Add new model mappings in `const.py` in `MODEL_PLATFORMS` and the relevant `*_MODELS` lists.

## Changelog

### v0.2.2 (2026-09-27)

- Migration: a direction that only lived in the entity state (v0.2.0) is back-filled into the config entry options, so the watchdog works right after upgrading without re-selecting

### v0.2.1 (2026-09-27)

- **Curtain direction persistence**: the gateway does not store `curtainDir` (it only forwards it to the motor), so the direction can be reset by a gateway restart / power loss / cloud push. The integration now keeps the desired direction in the config entry options and re-sends it **on setup** and **when the gateway comes back online**
- New `habitat.reapply_curtain_direction` service (optionally for a single `device_uid`) and a `方向看护` watchdog toggle in the integration options
- Docs: the full evidence chain for the non-persistence and the cloud-override analysis

### v0.2.0 (2026-09-27)

- New “curtain direction” select entity: writes the gateway `curtainDir` attribute, a **hardware-level** fix for curtains installed the wrong way (the app and the hardware panels become correct too)
- New `tools/set_curtain_direction.py`: standalone CLI to list curtains and read/write the motor direction
- Docs: how the direction works, the gateway → Zigbee mapping (`curtainDir` → Window Covering 0x0102 manufacturer command `0xf1`) and the gateway password exposure note

### v0.1.0 (2026-03-07)

- Initial release: lights, switches, covers, sensors
- Later: 5‑in‑1 Climate/Humidifier/Fan/Number, floor heating state, multiple gateways, scene/5‑in‑1 switches hidden by default, English translations (e.g. Fresh Air)

## License

MIT License

---

*This integration is not officially affiliated with Habitat Smart Home; it is developed by the community.*
