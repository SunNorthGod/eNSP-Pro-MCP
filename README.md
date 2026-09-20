# eNSP Pro MCP

对华为 eNSP Pro(V100R003C10SPC101 standalone)做程序化自动化的 MCP server。
前端协议逆向笔记见 `docs/API-NOTES.md`,原始 bundle 与提取结果在 `recon/`。

## 接入

ZCode 用户级 MCP 注册(`~/.zcode/cli/config.json` → `mcp.servers`):

```json
"ensp-pro": {
  "command": "<python>",
  "args": ["<workspace>/ensp-pro-mcp/server/ensp_server.py"]
}
```

环境变量(可选):`ENSP_BASE`(默认 `https://192.168.1.20:28443`)、
`ENSP_STATE`(状态文件,默认 `server/state.json`)。

前置条件:E5 服务器上 Hyper-V → Ubuntu VM → QEMU appliance 链路在跑
(虚机 `172.18.115.90`,E5 侧 portproxy 2222/28443;虚机 IP 随宿主网络重启会变,变了要改 portproxy)。

## 工具面(10 个,全部吃设备名,不吃 id)

| 工具 | 用途 |
|---|---|
| `ensp_status()` | 用户/沙箱列表/当前沙箱 |
| `ensp_lab(name)` | 按名切换沙箱,不存在则创建 |
| `ensp_topology(sandbox?)` | 设备(状态/启动进度)+ 链路清单 |
| `ensp_add_devices([{name,type}])` | 批量建设备,type 用别名(LSW/AC/AP/STA/AR/CE/PC/SERVER/CLOUD) |
| `ensp_link([[A,ifA,B,ifB]])` | 批量连线,接口名直写(如 GE1/0/1),自动查占用 |
| `ensp_power(action, [names])` | start/stop,立即返回 |
| `ensp_wait([names], timeout)` | 轮询启动状态,单次最多 110s,未完成会提示重调 |
| `ensp_remove([names])` | 删设备 |
| `ensp_cli(device, [cmds])` | 控制台自动跑命令:自动处理首登设密/重连验密/ENTER 门/screen-length |
| `ensp_console(device, send?, seconds?)` | 裸控制台:原样发送 + 收割输出(PC 模拟器/交互场景用) |

## 实现要点

- 认证:standalone 模式 `GET /api/login` 即建立 admin 会话,无需口令;会话 Cookie 持久化到
  `server/state.cookies.json`(不入仓库),进程内检测会话失效自动重登。
  注意:appliance 对 admin 会话全局单实例,浏览器正式登录会踢掉本工具、反之亦然。
- 控制台:SockJS(`/web.socket/{server}/{session}/websocket`)+ STOMP 1.2,
  SUB `/user/topic/console/message/{sandboxId}/{deviceId}`,
  SEND `/app/console/{connect,message,heartbeat,close}/...`;
  服务端在设备会话结束后会断开整条 WebSocket,客户端检测死连接自动重建。
- 首次开 VRP 设备控制台会要求设置登录密码(8-16 位),本工具自动以 `Admin@123`
  设置并保存;此后每次重开控制台需在 `Password:` 处重输该密码,bootstrap 状态机自动处理。
  新设备首登是「输入 + 确认」两步密码流程,bootstrap 偶发跟不上时会吞掉后续命令,
  批量灌配置后务必 `display` 核对落地。
- 镜像为 YunShan OS(S6700 V600R025C10SPC500),个别经典 VRP 语法不同:
  无 `display vlan brief`(用 `display vlan`)、`sys` 歧义要用 `system-view`、
  mst-region 配置无 `active region-configuration`(quit 即生效)、AAA 权限级只有 0-3。
- 单条 STOMP/SockJS 连接承载全部设备的控制台会话;`_consoles` 按设备缓存状态。

## 目录

- `server/ensp_client.py` — REST + SockJS/STOMP 客户端(协议核心)
- `server/ensp_server.py` — FastMCP 工具面
- `prototype/` — 逆向期的探测脚本(`ensp_probe.py` 可独立敲 REST/控制台)
- `docs/` — 前端协议逆向笔记(API-NOTES)与官方文档摘录(PRODUCT-NOTES)
- `recon/` — 前端 bundle 等逆向原始材料,含华为版权代码,仅本地保留,不入仓库
