# 股海风云V2.2

适配真寻的炒股小游戏，使用金币为真寻经济系统的金币，使用的是真实数据

进行了严格的防风控处理，所有消息均为图片发送（windows下持仓依然为组消息）

注意：现阶段来说，这个插件对于玩过股市的人来说基本是必赚的，还请注意限制杠杆以控制盈利幅度

### 更新内容
v2.3
* 修正可以买超过当前金币数的躺平基金的问题

v2.2
* 修正因为不同人插件文件夹名字不同，导致配置文件不生效的问题
* 修正查询IXIC(纳斯达克指数)无法显示的问题

v2.11
* 修正ab股不显示的问题（之前都是好的，不是很明白原因，可能是收盘后网页不一样？总之暂时更新一下，明天再看看）

v2.1
* 添加日股买卖，日股代码均为J开头，可在https://histock.tw/jpstock找到
* 修正无法卖出小数位仓位的问题（如果卖的钱太少会被四舍五入掉，这是已知的）

* 
v2.0
* 将所有信息全部图片化（除了适配版的`我的持仓`指令，不过我觉得这个指令其实没人在用）
* 修正变更杠杆时剩余资金显示不正确的问题
* 持仓页面添加持仓所属人的信息

v1.99
* 添加`查看股票`指令，功能等同于之前的`买股票 代码 0`
* 股票k线默认改为东方财富通，更加专业，且支持基金显示，如果感觉不习惯的可以在配置内调回来
* 表格版查看持仓添加持仓收益总计功能
* 接下来7天内我都有事，有bug也修不了。所以这个版本不敢直接更新，放在名为`v1.99`的压缩包里了，代码仓库依然为1.96

v1.96
* 收益又被我搞坏了，已经修好

v1.95
* 修复了购买代码仅有2个字母的股票时，购买价格错误的设定为涨跌幅的问题
* 3天内没新问题的话，就更新到2.0并release

v1.9 
* 修复卖出躺平基金的恶性bug，以及躺平基金显示的Bug，以后再加新功能我会先内测
* 持仓表格添加盈亏百分比提示

v1.8
* 修正躺平基金无法购买的问题

v1.7
* 给小白新增了`躺平基金`，这是一个每持有一天就会指数增长1.5%的基金（小于1天不会赚钱）
* 参考指令：`买入躺平基金 x` `卖出躺平基金 x` x为仓位或金额，不填为满仓
* 曾经的windows适配代码`fit=False`代码被移动到了配置文件当中，之前查看持仓存在问题的，需要运行一次新插件后，到配置文件里面配好

v1.6
* 修正了5个字符的股票（如腾讯:TCEHY）会被当成港股的问题

v1.5
* 代码大范围重构
* 添加了超短线专用的`反转持仓`功能，可以快速将杠杆反转
* 继续优化使用细节
* 现在你可以直接用`买入601919`满仓满杠杆买入，`卖出601919`直接卖出，`买入601919 -5`直接做空
  (股票代码自行替换)
* 在涨停时做空将无法平仓

v1.4
* 修正1.3中使用仓位购买且余额为0时，购买0股股票导致持仓无法显示的Bug

v1.3
* 小更新，盈利的股票会显示为红色，亏损的则为绿色

v1.2 
* 增加查看持仓指令，可以看别人的持仓了
* 优化了股票显示
* 允许买入后更换杠杆（解析为一次卖出和一次买入操作）
* 
### 指令
`买股票 代码 金额 杠杆倍数(可不填)` 买入股票 例：买股票 600888 10000  (买入10000金币的仓位)

这是一个多功能指令，包括以下逻辑：

* 如果你只输入了买股票+股票代码，默认全仓最高杠杆梭哈

* 如果你不输入杠杆倍数，默认杠杆倍数是最大倍率

* 如果你不输入杠杆倍数但是之前买过了，默认杠杆倍数和之前一致

* 如果你的杠杆倍数大于最大倍数，买入数量却小于杠杆倍数，系统会认为你输入反了2个参数的位置并帮你纠正

* 如果你的杠杆倍数正常，买入数量却小于等于10，系统会认为你买入的单位是“仓位”而不是“金额”

* 如果你买入的金额是0，但是杠杆不是0，系统会认为你想修改杠杆

* 如果你买入的杠杆不一致，系统会认为你想修改杠杆的同时追加金额

* 如果你买入的金额是0，系统会认为你只是想看看这支股票

* 如果你买入的杠杆是0，不做特殊处理

* 如果你输入的金额是负数且大于杠杆倍率，比如-5，系统会认为你是满仓-5杠杆做空


`卖股票 代码 仓位(十分制）`卖出股票` 例：卖股票 600888 10 (卖出10层仓位)

`我的持仓`

`查看持仓@qq号` 偷看别人的持仓

`强制清仓 qq号` 管理专用指令！用来给爆仓的人平仓

### 支持范围
* A股 港股 美股 基金
* 做空 杠杆(最大倍率可配置)

### 不支持什么？
* 挂单，必须即时成交
* 爆仓后自动平仓，但是管理可以帮你强平

### 未来可能会添加的
* 持仓分析，请关注后续更新
* 现在的网页截图还是有点烂，但是我尝试截图其他页面都失败了

### 已知隐患
如果资金为负数的情况下进行卖股票以外的操作是可能出问题的

比如反转持仓实际上有一个先卖再买的动作，如果资金是负数就会买不起

### 安装
该插件与赛马插件都需要`nonebot_html_render`插件，之前配过赛马的用起来会比较轻松。
这个插件在windows系统下运行时可能有一些问题。

如果运行`我的持仓`指令出现错误（注意，如果仅仅是插件无法安装，和这个无关），请将插件里的win_fit配置改成true

将[nonebot_html_render](https://github.com/kexue-z/nonebot-plugin-htmlrender/tree/master/nonebot_plugin_htmlrender)
放置到真寻的extensive_plugins里（本插件与其同级），然后可能还需要安装一点依赖就可以运行了
（具体安装哪些看运行时是否报错）

* 注意放进去的是链接点进去时看到的子文件夹，不要把整个`nonebot_html_render`项目放进去
* 我已经把`nonebot_html_render`打包好了，你也可以解压就用
* 按理说会缺2个依赖：`Jinja2`和`markdown`，可以先提前装好

其他安装问题可以去看看[issue](https://github.com/RShock/zhenxun_plugin_stock_legend/issues?q=)

``` 
如果你的真寻不基于虚拟环境，应该尝试用这个
pip3 install Jinja2
pip3 install markdown

基于虚拟环境，应该尝试用这个
poetry add Jinja2
poetry add markdown

或者都尝试一下
```


