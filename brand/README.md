# 集成 Logo / 品牌图（可选）

自 **Home Assistant 2026.3** 起，自定义集成可以在本目录下放置品牌图，用于在 HA 界面（如集成列表、设备页）显示 Logo。

## 放置方式

将图片放在 **`brand/`** 目录下，并使用以下文件名（均为 **PNG** 格式）：

| 文件名       | 用途           |
|-------------|----------------|
| `logo.png`  | 品牌/产品 Logo（推荐） |
| `icon.png`  | 方形图标（可选）     |

若你在项目根目录的 `assets/` 下已有 `habitat-logo.webp`，请先转换为 PNG，再复制或重命名为 `brand/logo.png`。例如：

- 用在线工具或本地软件将 `habitat-logo.webp` 转为 PNG；
- 将得到的 PNG 保存为 `brand/logo.png`。

手动安装集成时，请将整个 `brand/` 目录一并复制到 `custom_components/habitat/` 下，这样 HA 才能加载到 Logo。
