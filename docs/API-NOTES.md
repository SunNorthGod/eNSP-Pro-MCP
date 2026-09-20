# eNSP Pro V100R003C10SPC101 WebUI API 逆向笔记

来源:`https://192.168.1.20:28443` 前端 bundle 静态分析(recon/ 目录)。
所有结论未经服务器实测标注前均为静态推断,以 `prototype/ensp_probe.py` 实测为准。

## 1. HTTP 层

- Base URL: `https://192.168.1.20:28443`(自签证书,客户端需 `verify=False`)。
- 前端所有请求 `credentials: include` → **会话认证走 Cookie**,登录后服务端 Set-Cookie。
- 请求头:`Content-Type: application/json`、`Cache-Control: no-cache`、`Pragma: no-cache`、
  `Accept-Language: zh`(或 en)。
- 若 cookie `csrfToken` 存在 → 附 `X-CSRF-TOKEN` 头。
- `fetchWithToken()` 模式:先 `GET /service/attack/key`,取响应 `data` 作为 `token` 请求头再发目标请求。
  哪些接口走该模式待实测(可能为登录)。
- 响应包络:JSON `code === 0` 或 `status === 200` 为成功;`code ∈ {50010005, 50070014}` → 会话失效。
  失败体含 `message` / 错误码(错误码表在前端 i18n `enspNg.pcServerErrorCode`)。

## 2. REST 端点全集(前端实际调用)

### 认证/用户
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/standalone/isRegistered?home={origin}` | standalone 部署注册状态(本部署为 standalone) |
| POST | `/api/login` | 登录,字段含 username/password(完整形状待实测) |
| GET | `/api/login?service={origin}` | 页面级 CAS 式跳转(header 里那个 login 按钮) |
| GET | `/api/login/sandboxUser?ticket={t}` | 沙箱用户票据登录 |
| GET | `/api/logout`, `/service/user/logout` | 登出 |
| GET | `/api/keepalive` | 会话保活 |
| GET | `/api/getUserInfo`, `/service/user/getUserInfoById` | 用户信息 |
| GET | `/service/attack/key` | 取 token(配合 `token` 请求头) |
| POST | `/api/register`, `/api/register/checkCaptcha`, GET `/api/register/getCaptcha` | 注册 |

### 工程/沙箱
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/service/project` | 当前工程 |
| POST | `/service/user/changeDefaultProject?projectId={id}` | 切默认工程 |
| GET | `/service/ensp/project/getUserProjects` | 用户工程列表 |
| POST | `/api/getAllProject` | 全部工程(body 待实测) |
| POST | `/service/ensp/sandbox/create` | 建沙箱;表单字段:name, isPublic(number, 私有/公开), maxVms(必填), 描述类可选 |
| POST | `/service/ensp/sandbox/update` | 改沙箱 |
| POST | `/service/ensp/sandbox/getByPage` | 分页列沙箱(body 待实测,常规 pageNum/pageSize) |
| GET | `/service/ensp/sandbox/getOneSandbox?sandboxId={id}` | **拓扑全量**:返回含 devices/links/graphicsVOList/textBoxs/status |
| POST | `/service/ensp/sandbox/batchDeleteSandbox` | 删沙箱 |
| GET | `/service/ensp/sandbox/getAvailableDevice?sandboxId={id}` | 该沙箱可用设备面板 |
| GET | `/service/ensp/sandbox/getAvailableDevices` | 全部设备模板 |
| POST | `/service/ensp/sandbox/getTemplateDeviceInfo` | FormData,模板详情 |
| POST | `/service/ensp/sandbox/importSandbox`、`exportSandbox`、`batchExportSandbox`、`batchDownload`、`batchUploadSandbox` | 导入导出 |
| POST | `/service/ensp/sandbox/recycle?sandboxId={id}` | 回收 |
| POST | `/service/ensp/sandbox/renewalResource?sandboxId={id}&keepTime={t}` | 资源续期 |
| GET | `/service/ensp/sandbox/getRenewalResourceInterval`、`/service/ensp/sandbox/getTime` | 辅助 |
| POST | `/service/ensp/sandbox/demo/getByPage`、`/service/ensp/sandbox/demo/importSandboxByDemo` | 官方 demo 模板 |
| GET | `/service/ensp/sandbox/getLatestUsedSandbox` | 最近使用 |
| GET | `/api/getDeviceMaxNumber` | 沙箱资源上限(对应 UI 弹窗"2.0U/3.4G"那类配额) |

### 设备 `/service/ensp/device`
| 方法 | 路径 | body |
|---|---|---|
| POST | `/batchCreate` | `{devices: [device...], sandboxId}`;device = 设备模板对象克隆 + `deviceTypeId`(模板的 deviceType.id) + `devicePosition:{positionX, positionY}`(万分比、以画布中心为 0,POSITION_ACCURACY=10000) + `sandboxId` |
| POST | `/batchDelete` | `{sandboxId, deviceIds:[id...]}`
| POST | `/batchStart` | `{deviceIds:[id...], sandboxId}` |
| POST | `/batchStop` | 同上 |
| POST | `/batchReboot` | 同上 |
| POST | `/modifyComponent` | `{sandboxId, devices:[{id, positionX, positionY...}]}` |
| POST | `/checkDeviceName?sandboxId={id}&deviceName={n}` | — |
| GET | `/downloadLog?deviceId={id}` | 设备日志下载 |
| POST | `/service/ensp/device-image/import-{NATIVE\|CUSTOM}?deviceType={t}` | 自定义镜像上传 |
| GET/POST | `/service/ensp/device-type`, `/service/ensp/device/property` | 类型/属性 |

### 连线 `/service/ensp/link`
| 方法 | 路径 | body |
|---|---|---|
| POST | `/create` | `{leftDeviceId, leftIfId, rightDeviceId, rightIfId, linkTypeId: 1, sandboxId}`(LINK_TEMPLATE + linkTypeId=1) |
| POST | `/deleteLink` | `{linkId}` |

接口 id 来源:`getOneSandbox` 返回的 `devices[].deviceIfs[]`(有 id/name/displayName/serialId)。

### 配置文件 `/service/ensp/configuration`
| 方法 | 路径 |
|---|---|
| POST | `/dealConfiguration` |
| POST | `/getConfigurations` |
| POST | `/downloadFile`;GET `/download/{...}` |
| POST | `/importFile` |

### 其他
`/service/ensp/wlan`(WLAN 相关)、`/service/ensp/pcap`、`/service/ensp/auditLog`、`/service/ensp/cmd/setting`(命令行终端设置)、`/service/ensp/cmd/setting/resize`、`/service/ensp/cmd/log`、`/service/ensp/graphics`、`/service/ensp/textBox`、`/service/ensp/position`、`/service/ensp/stmVersion`、`/service/ensp/system`、`/service/env/system`。

## 3. 状态枚举(TOPO_COMPOMENT_STATUS)

- Sandbox.TOPO: `CREATING:0, READY:1, CREATE_FAIL:2, DELETE:3, DELETE_FAIL:4, FULL_DELETE_FAIL:5, DELETE_SUCCESS:6, NO_CREATING:7, DELETE_FAIL_TIME:8`
- DEVICE: `STOPPED:0, VM_READY:1, VM_PENDING_ADD:2, VM_PENDING_ADD_ERROR:3, CONTAINER_READY:4, CONTAINER_PENDING_ADD_ERROR:5, CONTAINER_PENDING_ADD:6, DISPLAY_PENDING_DELETING:7...`
  → 运行态 = `VM_READY(1)` 或 `CONTAINER_READY(4)`;1/2/6 为中间态。

## 4. STOMP over WebSocket

- 端点:`wss://{host}:{port}/web.socket`(浏览器带会话 cookie 完成握手)。
- 库:@stomp/stompjs v7,`accept-version: 1.2`,`heart-beat: 30000,30000`。
- 目的地前缀约定(应用封装 `os.defaultClient`):
  - `subscribe(t)` → 实际 SUB `/user/topic{t}`
  - `send(t, body)` → 实际 PUBLISH `/app{t}`
- **会话级心跳**:每 3s PUBLISH `/user/topic/ping` body=`ping`(绕过 /app 前缀,直接发 Kb+ping)。

### 设备控制台(sandboxId + nodeId 复合 id,记 `cid = {sandboxId}/{nodeId}`)
| 方向 | 目的地 | body |
|---|---|---|
| SUB | `/user/topic/console/message/{cid}` | 设备回显(原始终端字节流,xterm 直写,含 `\r\n`) |
| SUB | `/user/topic/console/heartbeat/{cid}` | 心跳回执 |
| SEND | `/app/console/connect/{cid}` | (空)开启会话 |
| SEND | `/app/console/message/{cid}` | 键入文本(含 `\r` 回车;前端是逐键+整行混合) |
| SEND | `/app/console/heartbeat/{cid}` | (空)定期 |
| SEND | `/app/console/close/{cid}` | (空)关会话 |
| SEND | `/app/console/log/{nodeId}` | 命令记录(可选,isRecord 开关) |

### 拓扑事件订阅(`/sandboxes/{id}/...`)
`updated`, `removed`, `devices/updated`, `devices/removed`, `links/updated`, `links/removed`,
`graphics/updated`, `graphics/removed`, `textBoxes/updated`, `textBoxes/removed` — body 为变更对象 JSON。

## 5. 杂项

- 前端构建:Vite + Vue3 + Pinia;主 bundle `index-4e14d765.js`,拓扑页 `sandbox-63dabefb.js`(含 xterm.js + xterm fit/serialize 插件)。
- `device.extProps` 中有 `name:"remote.url"` 属性(设备控制台直连地址,standalone 模式由 `updateNodeRemoteUrl` 维护)——备用通道,主通道走上述 STOMP。
- 路由前缀 `/ensp-emulation/console/...` 是前端 Vue Router 路径,不是后端 API。
- PC 模拟器走同一 console 通道(输出 banner "Welcome to use PC Simulators!")。
