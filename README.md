# eNSP Pro MCP

面向华为 eNSP Pro 单机版（V100R003C10SPC101）的 MCP server，提供拓扑构建、设备电源管理、控制台命令执行等自动化能力。WebUI 协议基于前端逆向分析获得，分析笔记见 `docs/API-NOTES.md`。

## 接入方式

ZCode 用户级 MCP 注册（`~/.zcode/cli/config.json` → `mcp.servers`）：

```json
"ensp-pro": {
  "command": "<python>",
  "args": ["<workspace>/ensp-pro-mcp/server/ensp_server.py"]
}
```

环境变量（可选）：`ENSP_BASE`（默认 `https://192.168.1.20:28443`）、
`ENSP_STATE`（状态文件路径，默认 `server/state.json`）。

前置条件：E5 服务器上 Hyper-V → Ubuntu 虚机 → QEMU appliance 链路处于运行状态
（虚机 `172.18.115.90`，E5 侧 portproxy 2222/28443；虚机 IP 由 DHCP 分配，宿主网络
重启后可能变化，变化时需同步修改 portproxy 规则）。

## 工具列表

共 10 个工具，统一按设备名称寻址，不使用设备 id：

| 工具 | 功能 |
|---|---|
| `ensp_status()` | 查看用户、沙箱列表与当前沙箱 |
| `ensp_lab(name)` | 按名称切换沙箱，沙箱不存在时自动创建 |
| `ensp_topology(sandbox?)` | 输出设备状态、启动进度与链路清单 |
| `ensp_add_devices([{name,type}])` | 批量创建设备，type 支持别名（LSW/AC/AP/STA/AR/CE/PC/SERVER/CLOUD） |
| `ensp_link([[A,ifA,B,ifB]])` | 批量创建链路，接口名直写（如 GE1/0/1），自动检查端口占用 |
| `ensp_power(action, [names])` | 设备开机/关机，命令立即返回 |
| `ensp_wait([names], timeout)` | 轮询启动状态，单次调用上限 110 秒，未完成时提示再次调用 |
| `ensp_remove([names])` | 删除设备 |
| `ensp_cli(device, [cmds])` | 在控制台自动执行命令：处理首登设密、重连验密、ENTER 确认与 screen-length |
| `ensp_console(device, send?, seconds?)` | 裸控制台访问：原样发送文本并读取输出流，适用于 PC 模拟器与交互场景 |

## 会话与认证

- standalone 模式下，`GET /api/login` 即可建立 admin 会话，无需口令。会话 Cookie
  持久化于 `server/state.cookies.json`（不纳入版本管理），客户端检测到会话失效后
  自动重新登录。
- 服务端对 admin 会话实施全局单实例限制：浏览器登录会使本工具的会话失效，
  本工具重新登录同样会使浏览器会话失效，二者不可同时使用。

## 控制台

- 控制台基于 SockJS（`/web.socket/{server}/{session}/websocket`）与 STOMP 1.2 实现。
  设备会话结束后，服务端会断开整条 WebSocket 连接，客户端对此自动检测并重建。
- VRP 设备首次开启控制台时强制要求设置登录密码（8–16 位），本工具统一设置为
  `Admin@123`；此后每次开启控制台需在 `Password:` 处重新输入该密码。
- 新设备的首登密码流程分为输入与确认两步。客户端引导流程偶有未能同步的情况，
  此时后续命令会被当作密码输入而丢失，且回显无异常表现；因此批量下发配置后，
  应通过 `display` 命令核对配置是否生效。

## 镜像语法差异

设备镜像为 YunShan OS（S6700 V600R025C10SPC500），与经典 VRP 存在以下差异：

- 无 `display vlan brief`，应使用 `display vlan`；
- `sys` 存在命令歧义（报 Ambiguous），应使用完整命令 `system-view`；
- mst-region 配置在退出视图时即生效，不存在 `active region-configuration` 命令；
- AAA 用户权限级别取值范围为 0–3，不支持 15。

## 目录结构

- `server/ensp_client.py` — 协议核心，REST 与 SockJS/STOMP 客户端
- `server/ensp_server.py` — FastMCP 工具面
- `prototype/` — 协议分析阶段的探测脚本，其中 `ensp_probe.py` 可独立运行
- `docs/` — 逆向分析笔记（API-NOTES）与官方文档摘录（PRODUCT-NOTES）
- `recon/` — 前端 bundle 原件，属第三方版权材料，仅保留于本地，不纳入仓库
