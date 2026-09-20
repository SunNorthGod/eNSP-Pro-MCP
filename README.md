# eNSP Pro MCP

操作华为 eNSP Pro 单机版(V100R003C10SPC101)的 MCP server:建拓扑、连线、开关机、
进设备敲命令行,都在对话里完成。协议是自己逆向出来的,笔记在 `docs/API-NOTES.md`。

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

前置:E5 服务器上 Hyper-V → Ubuntu VM → QEMU appliance 链路在跑
(虚机 `172.18.115.90`,E5 侧 portproxy 2222/28443;虚机 IP 随宿主网络重启会变,变了要改 portproxy)。

## 工具面

10 个工具,全部按设备名寻址,不碰 id:

| 工具 | 用途 |
|---|---|
| `ensp_status()` | 用户/沙箱列表/当前沙箱 |
| `ensp_lab(name)` | 按名切换沙箱,不存在则创建 |
| `ensp_topology(sandbox?)` | 设备(状态/启动进度)+ 链路清单 |
| `ensp_add_devices([{name,type}])` | 批量建设备,type 用别名(LSW/AC/AP/STA/AR/CE/PC/SERVER/CLOUD) |
| `ensp_link([[A,ifA,B,ifB]])` | 批量连线,接口名直写(如 GE1/0/1),自动查占用 |
| `ensp_power(action, [names])` | start/stop,立即返回 |
| `ensp_wait([names], timeout)` | 轮询启动状态,单次最多 110s,没起完会提示重调 |
| `ensp_remove([names])` | 删设备 |
| `ensp_cli(device, [cmds])` | 控制台自动跑命令:处理首登设密/重连验密/ENTER 门/screen-length |
| `ensp_console(device, send?, seconds?)` | 裸控制台:原样发送 + 收割输出(PC 模拟器/交互场景用) |

## 踩过的坑

- appliance 对 admin 会话全局单实例:浏览器一登录,本工具就掉线;本工具重登,
  浏览器那边也被踢。两边只能活一个。
- 控制台走 SockJS(`/web.socket/{server}/{session}/websocket`)+ STOMP 1.2。
  设备会话结束后服务端会把整条 WebSocket 掐掉,客户端得自己检测重连。
- VRP 设备第一次开控制台强制设密码,这里统一用 `Admin@123`;之后每次重开
  都要在 `Password:` 处重输。
- 新设备首登密码要输两遍(输入 + 确认)。bootstrap 偶尔跟不上这个节奏,会把后面
  发的命令当密码吃掉,回显还看不出异常——批量灌完配置必须 `display` 核对。
- 镜像是 YunShan OS(S6700 V600R025C10SPC500),跟经典 VRP 有出入:
  没有 `display vlan brief`,用 `display vlan`;`sys` 有歧义报 Ambiguous,要写
  `system-view`;mst-region 配好 quit 就生效,没有 `active region-configuration`
  这条命令;AAA 权限级只有 0-3,没有 15。

## 目录

- `server/ensp_client.py` — 协议核心:REST + SockJS/STOMP
- `server/ensp_server.py` — FastMCP 工具面
- `prototype/` — 逆向时的探测脚本,`ensp_probe.py` 可单独跑
- `docs/` — 逆向笔记(API-NOTES)和官方文档摘录(PRODUCT-NOTES)
- `recon/` — 前端 bundle 原件,华为的版权代码,只留在本地,不进仓库
