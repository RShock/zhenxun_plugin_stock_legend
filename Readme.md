# 股海风云V1.0

适配真寻的炒股小游戏，使用金币为真寻经济系统的金币，使用的是真实数据

进行了严格的防风控处理，所有消息均为图片发送（windows下持仓依然为组消息）

注意：现阶段来说，这个插件对于玩过股市的人来说基本是必赚的，还请注意限制杠杆以控制盈利幅度

### 指令
`买股票 代码 金额 杠杆倍数(可不填)` 买入股票 例：买股票 600888 10000  (买入10000金币的仓位)

`卖股票 代码 仓位(十分制）`卖出股票` 例：卖股票 600888 10 (卖出10层仓位)

`我的持仓`

`强制清仓 qq号` 管理专用指令！用来给爆仓的人平仓

### 支持范围
* A股 港股 美股 基金
* 做空 杠杆(最大倍率可配置)

### 不支持什么？
* 挂单，必须即时成交
* 爆仓后自动平仓，但是管理可以帮你强平

### 未来可能会添加的
* 持仓分析，请关注后续更新

### 已知隐患
* 美股盘前交易 A股集合竞价阶段，插件可能获取不到盘前价格从而产生未来视（待验证），如果真的存在该bug，会考虑在这段时间禁止交易

### 安装
该插件与赛马插件都需要`nonebot_html_render`插件，之前配过赛马的用起来会比较轻松。
这个插件在windows系统下运行时可能有一些问题。
因此推荐linux系统使用该插件。

（开发方面，具体表现为markdown转图片不可用，无法启用debug模式。
因为我是新手，无法解决该问题，只编写了兼容代码让它在我的windows上
硬跑起来，但是无法保证别的windows也能成功启动）

将[nonebot_html_render](https://github.com/kexue-z/nonebot-plugin-htmlrender/tree/master/nonebot_plugin_htmlrender)
放置到真寻的extensive_plugins里（本插件与其同级），然后可能还需要安装一点依赖就可以运行了
（具体安装哪些看运行时是否报错）


