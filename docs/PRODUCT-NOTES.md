# eNSP Pro 产品文档摘录(V100R003C10 产品文档 + 缺省账号和密码)

来源:`C:\Users\29596\Downloads\ENSP-Pro\产品说明书\`。全文已抽至 `recon/product-doc-fulltext.txt`。

## 设备资源规格(3.3 节,决定沙箱容量规划)

| 设备 | 内存/台 | CPU/台 |
|---|---|---|
| NE 路由器 | 1.6 GB | 1 |
| CE 交换机 | 1.7 GB | 1 |
| S 交换机 | 1.7 GB | 1 |
| AR 路由器 | 1.7 GB | 1 |
| USG 防火墙 | 2.6 GB | 1.5 |
| AntiDDOS | 3.5 GB | 2 |
| IPS | 2.5 GB | 1.5 |
| AC | 1.7 GB | 1 |
| AP | 1.5 GB | 2.5 |
| PC 终端 | 250 MB | 0.2 |
| STA 终端 | 250 MB | 0.2 |
| CLOUD | 250 MB | 0.2 |

官方口径:8 核 16G 宿主机跑 3~5 台;当前 E5 appliance 配 80 vCPU/12G,教材实验
(1×S + 1×AC + 2×AP + STA + CLOUD ≈ 7GB)余量充足。

## CLOUD 模拟器(2.3.13 / 4.3.13 / 4.8.5,仅单机版支持)

- 特性:Ethernet 端口转发(经 eNSP 虚机网卡转发网元以太网流量)、UDP 隧道转发、
  **远程网元管理(Telnet/SSH/HTTP(s) 访问网元管理端口)**。
- 双击已启动的 CLOUD 弹窗配置:Ethernet 添加以太口;UDP 页开 UDP 端口
  (端口范围 5000~5999,"本地 IP"取 CLOUD UDP 页显示值);Remote 页配 Telnet/HTTP(S)
  远程地址,配好 Telnet 后"命令行"直达系统 Telnet 工具。
- 官方不建议云网元用 NAT/桥接网卡(会导致 UDP 通信失效)。

## 命令行(4.3.4)

- 仅"启动成功"的设备可开命令行;单次输入不能超过 **8KB**;支持复制粘贴。

## 导入/导出配置(4.3.14 / 4.3.15)

- **导入配置要求设备未启动**(启动中/已启动不能导入)。
- 编辑配置文件**不要改动文件前四行**,否则导入失败。
- 对应 REST:`/service/ensp/configuration/importFile`(上传)、`/downloadFile`、
  `/getConfigurations`、`/dealConfiguration`(尚未在 MCP 中封装,备用)。

## 缺省账号(缺省账号和密码文档)

- OS/容器内部账号(root/ensplite/pc 等)全部"外部无法访问、不可登录"——
  与实测的 standalone WebUI 免登录(会话即 admin)一致,产品本就无 WebUI 口令。
- 各模拟器缺省账号指向华为外网文档:《CloudEngine S系列交换机缺省帐号与密码(V600版本)》
  《WLAN缺省帐号与密码》等(需网站权限)。
- 实测补充(S 系列,YunShan OS V600R025C10SPC500):首次开控制台强制设置登录密码
  (8-16 位),之后每次重开控制台要输该密码;MCP 已自动以 `Admin@123` 处理。

## 与实验相关的版本事实

- S 交换机镜像实为 YunShan OS(S6700 V600R025C10SPC500),经典 VRP 个别语法不同:
  无 `display vlan brief`(直接 `display vlan`),`display vlan ?` 可见合法子参数。
- WLAN 特性(2.3.8-2.3.9、5xxx 行):CAPWAP、WAC 组网、WLAN 用户管理(STA)、
  射频管理、WLAN 漫游均有,HCIA-WLAN 认证特性可用 → 教材任务 3.2(AP 上线/WLAN 模板/STA)
  在该版本可做。
- CLOUD 仅单机版(standalone)可用,本部署即单机版。
