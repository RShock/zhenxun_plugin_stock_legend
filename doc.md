# 股海风云 需求文档

## 账户系统
- 配置项 `跨群合并账户` 默认开启，开启后同一 QQ 在不同群共用一个股海风云账户，账户键只使用 QQ
- 关闭 `跨群合并账户` 时恢复旧行为，账户键使用 `QQ:群号`
- 开启后用户触发买卖、查看、清仓、取消委托等操作时，会自动把旧 `QQ:群号` 持仓迁移到 QQ 账户
- 旧持仓同 QQ 同股票合并时，数量与成本累加，杠杆沿用合并前成本最高的那条记录
- 旧委托单会迁移为 QQ 账户；迁移后的新格式不再包含群号，定时执行和退款正常，但无法定位群聊发送执行通知

## 委托单系统
- 美股：非交易时段创建委托单，等到开盘执行
- 港股：T+0但延迟15分钟成交，创建委托单
- A股：实时成交，不走委托单
- 买入委托单：创建时**立即扣款**，定时任务执行时 (`skip_order=True`) **不再校验余额**
- 卖出委托单：创建时不扣款，定时任务执行时直接卖出并返款

## 定时任务 (`check_and_execute_orders`)
- 每60秒检查一次待执行委托单
- 买入委托单调用 `buy_stock_action(..., skip_order=True)`，已预先扣款，禁止重复余额检查
- 卖出委托单调用 `sell_stock_action(..., skip_order=True)`
- 执行失败标记 `failed`，买入委托单失败时退还已扣金额
- 超时3小时以上的失败委托单由 `check_timeout_failed_orders` 退款

## 关键函数参数说明
- `buy_stock_action(skip_order=False)`：`skip_order=True` 时跳过所有余额检查，直接执行买入（委托单专用）
- `sell_stock_action(skip_order=False)`：`skip_order=True` 时跳过委托单创建，直接执行卖出

## 数据库列类型
- `stock_game.number` 和 `stock_game.cost` 必须是 `NUMERIC(20,3)`（模型 `max_digits=20`）。如果旧表是 `NUMERIC(10,3)`，值超过 9,999,999 时会溢出导致金币丢失。启动时 `_run_script` 会自动 ALTER COLUMN 修复。
- `stock_order.cost` 同理，模型 `max_digits=20`，迁移脚本已加入。

## 容易犯错的 Bug 模式
- **委托单余额重复检查**：`buy_stock_action` 中两处余额检查（`have_gold < cost`、`have_gold == 0`）必须受 `if not skip_order:` 守卫，否则定时任务执行已扣款委托单时会因余额不足而误判失败
- **躺平基金先扣款后写库**：`buy_lazy_stock_action` 先 `reduce_gold` 再 `buy_stock`，若 `buy_stock` 抛异常（如数值溢出），钱已扣但没买成，必须 catch 后 `add_gold` 退款