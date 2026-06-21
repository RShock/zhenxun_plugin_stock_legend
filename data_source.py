import asyncio
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytz

# from .stock_log_model import StockLogDB
from zhenxun.configs.config import Config
from zhenxun.models.user_console import UserConsole
from zhenxun.services.log import logger
from zhenxun.utils.enum import GoldHandle

from .stock_model import (
    StockDB,
    StockOrderDB,
    build_stock_account_key,
    parse_stock_account_key,
)
from .utils import (
    get_stock_info,
    get_tang_ping_earned,
    get_total_value,
    is_a_stock,
    is_st_stock,
    to_obj,
    to_txt,
)

plugin_name = re.split(r"[\\/]", __file__)[-2]


def is_global_account_enabled() -> bool:
    return bool(Config.get_config(plugin_name, "跨群合并账户", True))


async def get_stock_uid(user_id: int, group_id: int) -> str:
    if not is_global_account_enabled():
        return f"{user_id}:{group_id}"
    uid = build_stock_account_key(user_id)
    await StockDB.merge_legacy_user_stocks(user_id)
    await StockOrderDB.migrate_legacy_user_orders(user_id)
    return uid


# 时区设置
TZ = timezone(timedelta(hours=8))  # 东八区
US_EASTERN_TZ = pytz.timezone("America/New_York")  # 美国东部时区


def get_us_trading_hours_beijing() -> tuple[int, int, int, int]:
    """获取美股交易时间（北京时间）
    根据当前美国东部时区的夏令时状态返回对应的北京时间
    返回: (开盘小时, 开盘分钟, 收盘小时, 收盘分钟)
    """
    # 获取当前美国东部时间
    us_now = datetime.now(US_EASTERN_TZ)

    # 判断是否是夏令时
    is_dst = us_now.dst() != timedelta(0)

    if is_dst:
        # 夏令时：美股 09:30-16:00 (美东) -> 北京时间 21:30-04:00
        return 21, 30, 4, 0
    else:
        # 冬令时：美股 09:30-16:00 (美东) -> 北京时间 22:30-05:00
        return 22, 30, 5, 0


def is_us_trading_time(now: datetime) -> bool:
    """判断当前是否在美股交易时段内"""
    open_hour, open_minute, close_hour, close_minute = get_us_trading_hours_beijing()

    current_time = now.hour * 60 + now.minute
    open_time = open_hour * 60 + open_minute
    close_time = close_hour * 60 + close_minute

    # 美股交易时间跨越午夜
    if close_time < open_time:
        # 交易时段：21:30/22:30 - 24:00 或 00:00 - 04:00/05:00
        return current_time >= open_time or current_time < close_time
    else:
        return open_time <= current_time < close_time


# 美股开盘时间（夏令时）
US_OPEN_HOUR = 21
US_OPEN_MINUTE = 30

# 港股开盘时间
HK_OPEN_HOUR = 9
HK_OPEN_MINUTE = 30

# 港股延迟时间（15分钟）
HK_DELAY_MINUTES = 15


async def buy_stock_action(
    user_id: int,
    group_id: int,
    stock_id: str,
    gearing: float,
    cost: int,
    force_price: float = 0,
    platform: str | None = None,
    skip_order: bool = False,
) -> str | None:
    infolist = await get_stock_info(stock_id)
    if len(infolist) <= 7:
        return "未找到对应股票，提示：请使用股票代码而不是名字"
    if force_price:
        price = force_price
    else:
        price = float(infolist[3])
    name = infolist[1]
    lock = asyncio.Lock()
    # 担心遇到线程问题，加了把锁（不知道有没有用）
    async with lock:
        user = await UserConsole.get_user(str(user_id), platform)
        have_gold = user.gold
        if not skip_order:
            if have_gold <= 0 and gearing is None:  # 先筛选一种情况
                return "你没有钱买股票"
            if 0 < cost <= 10:  # 如果花费小于10，认为他说的是仓位而不是花费
                cost = int(have_gold * cost / 10)
            elif have_gold < cost:
                return f"你当前只有{have_gold},买不起{cost}的股票哦"
        if price == 0:
            return f"{name}停牌了，不能买哦"

        uid = await get_stock_uid(user_id, group_id)
        stock = await StockDB.get_stock(uid, stock_id)
        # 先理清楚杠杆到底是多少
        if stock:
            if not gearing:
                gearing = float(stock.gearing)
        if not gearing:
            max_gearing = round(
                float(Config.get_config(plugin_name, "最大杠杆比率", 5)), 1
            )
            gearing = max_gearing
        gearing = round(gearing, 1)
        if not skip_order:
            if (stock and have_gold == 0 and gearing == stock.gearing) or (
                stock is None and have_gold == 0
            ):
                return "你没有钱买股票"
        # 涨停的股票不能买可以做空 跌停的股票反之（A股特供，防止打板战术）
        if is_a_stock(stock_id):
            if is_st_stock(name):
                if float(infolist[5]) > 4.93 and gearing >= 0:
                    return "该股票涨停了，不能买哦"
                if float(infolist[5]) < -4.93 and gearing < 0:
                    return "该股票跌停了，不能做空哦"
            if float(infolist[5]) > 9.9 and gearing >= 0:
                return "该股票涨停了，不能买哦"
            if float(infolist[5]) < -9.9 and gearing < 0:
                return "该股票跌停了，不能做空哦"

        # 检查是否需要创建委托单
        now = datetime.now(TZ)
        execute_time = now
        need_order = False

        # 如果是执行委托单，跳过委托检查，直接执行
        if not skip_order:
            # 美股处理：需要等到开盘后才能成交
            if stock_id.startswith("us"):
                # 判断当前是否在交易时段内
                if is_us_trading_time(now):
                    # 当前在交易时段内，立即执行
                    need_order = False
                else:
                    # 不在交易时段，计算下一次开盘时间
                    open_hour, open_minute, _, _ = get_us_trading_hours_beijing()
                    open_time = now.replace(
                        hour=open_hour, minute=open_minute, second=0, microsecond=0
                    )

                    # 如果当前时间已经过了今天的开盘时间，说明是收盘后，设置为明天开盘时间
                    current_time = now.hour * 60 + now.minute
                    open_time_minutes = open_hour * 60 + open_minute

                    if current_time >= open_time_minutes:
                        # 已经过了开盘时间，设置为明天
                        open_time = open_time + timedelta(days=1)

                    execute_time = open_time
                    need_order = True

            # 港股处理：需要延迟15分钟成交
            elif stock_id.startswith("hk"):
                execute_time = now + timedelta(minutes=HK_DELAY_MINUTES)
                need_order = True

        if need_order:
            # 调试：如果是特定用户，强制设为1分钟后执行
            if user_id == 418648118:
                execute_time = now + timedelta(minutes=1)

            # 创建委托单
            try:
                await StockOrderDB.create_order(
                    uid=uid,
                    stock_id=stock_id,
                    order_type="buy",
                    gearing=gearing,
                    cost=cost,
                    percent=0,
                    execute_time=execute_time,
                    group_id=group_id,
                )
                # 扣除资金
                await UserConsole.reduce_gold(
                    str(user_id), int(cost), GoldHandle.PLUGIN, plugin_name, platform
                )
            except Exception as e:
                logger.error(f"创建买入委托单或扣款失败: {e}")
                return f"创建委托单失败: {e}"
            return (
                f"委托买入 {name}\n"
                f"委托金额: {cost} 金币\n"
                f"杠杆比率: {gearing}\n"
                f"将于 {execute_time.strftime('%H:%M')} 执行\n"
                f"剩余资金: {round(have_gold - cost)}"
            )
        else:
            # 立即执行
            num = cost / price
            origin_cost = cost
            if stock and stock.gearing != gearing:  # 杠杆改变的逻辑
                # 先把旧股票全卖了
                earned = await fast_clear_stock(price, group_id, stock, user_id)
                # 加上当前本金
                cost = int(earned + cost)
                # 算出当前股数
                num = cost / price
            # 再买
            query = await StockDB.buy_stock(
                uid,
                stock_id,
                gearing,
                Decimal.from_float(num),
                Decimal.from_float(cost),
            )
            # await StockLogDB.buy_stock_log(uid, stock_id, gearing, num, price, cost)
            # 如果不是执行委托单，才扣钱（委托单在创建时已经扣钱了）
            if not skip_order:
                await UserConsole.reduce_gold(
                    str(user_id), int(cost), GoldHandle.PLUGIN, plugin_name, platform
                )
    if query:
        price = Decimal.from_float(price).quantize(Decimal("0.001"))
        if stock and stock.gearing != gearing:
            return (
                f"给{name}追加仓位{origin_cost},修改杠杆为{gearing}\n"
                f"因为杠杆的调整，持仓被重新计算了\n"
                f"现价 {price}块\n"
                f"当前持仓 {round(query.number / 100, 2)}手\n"
                f"当前持仓价值 {round((query.number * price - query.cost) * query.gearing + query.cost, 2)}\n"
                f"当前持仓成本 {round(query.cost, 2)}\n"
                f"杠杆比率 {query.gearing}\n"
                f"剩余资金 {round(have_gold - origin_cost)}"
            )
        else:
            return (
                f"成功购买了 {round(num / 100, 2)} 手 {name}\n"
                f"现价 {price}块\n"
                f"当前持仓 {round(query.number / 100, 2)}手\n"
                f"当前持仓价值 {round((query.number * price - query.cost) * query.gearing + query.cost, 2)}\n"
                f"当前持仓成本 {round(query.cost, 2)}\n"
                f"杠杆比率 {query.gearing}\n"
                f"剩余资金 {round(have_gold - cost)}"
            )


# 快速清仓指令
async def fast_clear_stock(
    price, group_id, stock, user_id, platform: str | None = None
):
    v = round(get_total_value(price, stock), 0)
    # await StockLogDB.sell_stock_log(
    #     uid=f"{user_id}:{group_id}",
    #     stock_id=stock.stock_id,
    #     number=stock.number,
    #     price=price,
    #     get=v,
    #     profit=v - stock.cost)
    await stock.delete()
    await UserConsole.add_gold(str(user_id), int(v), GoldHandle.GET, platform)
    return v


async def sell_stock_action(
    user_id: int,
    group_id: int,
    stock_id: str,
    percent: float,
    force_price: float = 0,
    platform: str | None = None,
    skip_order: bool = False,
):
    infolist = await get_stock_info(stock_id)
    if len(infolist) <= 7:
        return "未找到对应股票，提示：请使用股票代码而不是名字"
    logger.info(str(infolist))

    if force_price:
        price = force_price
    else:
        price = float(infolist[3])
    name = infolist[1]
    uid = await get_stock_uid(user_id, group_id)
    lock = asyncio.Lock()
    # 担心遇到线程问题，加了把锁（不知道有没有用）
    async with lock:
        stock = await StockDB.get_stock(uid, stock_id)
        if not stock:
            return "你还没有买这个股票哦"
        # 跌停的股票不能卖
        if is_a_stock(stock_id):
            if is_st_stock(name):
                if float(infolist[5]) > 4.93 and stock.gearing > 0:
                    return f"{name}看起来跌停了，不能卖哦"
                if float(infolist[5]) > 4.93 and stock.gearing < 0:
                    return f"{name}看起来涨停了，不能平仓哦"
            if float(infolist[5]) < -9.9 and stock.gearing > 0:
                return f"{name}看起来跌停了，不能卖哦"
            if float(infolist[5]) > 9.9 and stock.gearing < 0:
                return f"{name}看起来涨停了，不能平仓哦"

        # 检查是否需要创建委托单
        now = datetime.now(TZ)
        execute_time = now
        need_order = False

        # 如果是执行委托单，跳过委托检查，直接执行
        if not skip_order:
            # 港股处理：需要延迟15分钟成交
            if stock_id.startswith("hk"):
                execute_time = now + timedelta(minutes=HK_DELAY_MINUTES)
                need_order = True

        if need_order:
            # 调试：如果是特定用户，强制设为1分钟后执行
            if user_id == 418648118:
                execute_time = now + timedelta(minutes=1)

            # 计算卖出金额 = 当前价格 * 持仓数量 * 卖出比例
            current_value = float(price) * float(stock.number) * percent / 10
            await StockOrderDB.create_order(
                uid=uid,
                stock_id=stock_id,
                order_type="sell",
                gearing=float(stock.gearing),
                cost=current_value,
                percent=percent,
                execute_time=execute_time,
                group_id=group_id,
            )
            return (
                f"委托卖出 {name}\n"
                f"委托金额: {current_value:.0f} 金币\n"
                f"委托仓位: {percent}成\n"
                f"将于 {execute_time.strftime('%H:%M')} 执行"
            )
        else:
            # 立即执行
            await StockDB.sell_stock(uid, stock_id, percent)
            if stock.cost <= 0:  # 正常情况不会出现，但是一旦出现需要异常修复
                stock.cost = Decimal.from_float(1)
            total_value = get_total_value(price, stock)
            return_money = round(total_value * percent / 10, 0)
            earned_percent = round(
                (total_value - float(stock.cost)) / float(stock.cost) * 100, 2
            )
            # await StockLogDB.sell_stock_log(
            #     uid=uid,
            #     stock_id=stock_id,
            #     number=stock.number * percent / 10,
            #     price=price,
            #     get=return_money,
            #     profit=(total_value - stock.cost) * percent * stock.gearing)
            await UserConsole.add_gold(
                str(user_id), int(return_money), GoldHandle.GET, platform
            )
    if earned_percent < -100:
        lajihua = f"亏了{-earned_percent}%，只能去当三和大神了！"
    elif earned_percent < -10:
        lajihua = f"亏了{-earned_percent}%，好伤心！"
    elif earned_percent < 0:
        lajihua = f"小亏了{-earned_percent}%"
    elif earned_percent == 0:
        lajihua = "没亏没赚"
    elif earned_percent < 5:
        lajihua = f"小赚了{earned_percent}%"
    elif earned_percent < 10:
        lajihua = f"赚了{earned_percent}%，真开心！"
    elif earned_percent < 50:
        lajihua = f"赚了{earned_percent}%，赢麻了！"
    elif earned_percent < 100:
        lajihua = f"赚了{earned_percent}%，会所嫩模！"
    else:
        lajihua = f"赚了{earned_percent}%，正在通知管理员！"
    return (
        f"卖掉了 {name} {percent}成仓位, {lajihua}\n"
        f"成交价 {price}块\n"
        f"卖了 {return_money} 块钱\n"
        f"剩余仓位 {round(float(stock.number) * (1 - percent / 10) / 100, 2)} 手\n"
        f"剩余仓位当前价值 {round(float(total_value) * (1 - percent / 10), 2)}"
    )


async def get_stock_list_action(uid: int, group_id: int):
    stock_uid = await get_stock_uid(uid, group_id)
    my_stocks = await StockDB.get_my_stock(stock_uid)
    my_orders = await StockOrderDB.get_user_orders(stock_uid)

    stock_list = [await to_obj(stock) for stock in my_stocks]
    order_list = []

    for order in my_orders:
        infolist = await get_stock_info(order.stock_id)
        if len(infolist) > 7:
            name = infolist[1]
            order_info = {
                "name": name,
                "stock_id": order.stock_id,
                "type": "买入" if order.type == "buy" else "卖出",
                "gearing": float(order.gearing),
                "cost": float(order.cost) if order.cost else 0,
                "percent": float(order.percent) if order.percent else 0,
                "execute_time": order.execute_time.strftime("%Y-%m-%d %H:%M"),
                "status": "待执行",
            }
            order_list.append(order_info)

    return stock_list, order_list


async def get_stock_list_action_for_win(uid: int, group_id: int):
    stock_uid = await get_stock_uid(uid, group_id)
    my_stocks = await StockDB.get_my_stock(stock_uid)
    my_orders = await StockOrderDB.get_user_orders(stock_uid)

    stock_list = [to_txt(await to_obj(stock)) for stock in my_stocks]
    order_list = []

    for order in my_orders:
        infolist = await get_stock_info(order.stock_id)
        if len(infolist) > 7:
            name = infolist[1]
            order_text = f"委托{'买入' if order.type == 'buy' else '卖出'} {name}\n"
            order_text += f"执行时间: {order.execute_time.strftime('%H:%M')}"
            order_list.append(order_text)

    return stock_list + order_list


async def force_clear_action(user_id: int, group_id: int):
    uid = await get_stock_uid(user_id, group_id)
    stocks = await StockDB.get_stocks_by_uid(uid)
    tmp = ""
    for stock in stocks:
        if stock.stock_id == "躺平基金":
            tmp += await sell_lazy_stock_action(user_id, group_id, 10)
        else:
            tmp += await sell_stock_action(user_id, group_id, stock.stock_id, 10)
        tmp += "\n\n"
    return len(stocks), tmp


async def revert_stock_action(
    user_id: int, group_id: int, stock_id: str, platform: str | None = None
):
    infolist = await get_stock_info(stock_id)
    if len(infolist) <= 7:
        return "未找到对应股票，提示：请使用股票代码而不是名字"
    price = float(infolist[3])
    name = infolist[1]
    lock = asyncio.Lock()
    # 担心遇到线程问题，加了把锁（不知道有没有用）
    async with lock:
        uid = await get_stock_uid(user_id, group_id)
        stock = await StockDB.get_stock(uid, stock_id)
        if not stock:
            return f"你还没买{name}(当前价格:{price})呢！"
        gearing = -stock.gearing
        if is_a_stock(stock_id):
            if is_st_stock(name):
                if float(infolist[5]) > 4.93 or float(infolist[5]) < -4.93:
                    return "该功能在涨跌停时关闭！"

            if float(infolist[5]) > 9.9 or float(infolist[5]) < -9.9:
                return "该功能在涨跌停时关闭！"
        total_value = await fast_clear_stock(price, group_id, stock, user_id, platform)
        await buy_stock_action(
            user_id,
            group_id,
            stock_id,
            float(gearing),
            int(total_value),
            price,
            platform,
        )
    return f"""反转{name}仓位成功！
当前股票价格{price}
当前杠杆{gearing}
当前仓位价值{total_value}
"""


async def buy_lazy_stock_action(
    user_id: int, group_id: int, cost: float, platform: str | None = None
):
    lock = asyncio.Lock()
    # 担心遇到线程问题，加了把锁（不知道有没有用）
    async with lock:
        user = await UserConsole.get_user(str(user_id), platform)
        have_gold = user.gold
        if cost <= 0:
            return "买入数量必须是正数哦(0-10:仓位 10+:价格)"
        cost = cost if cost > 10 else round(have_gold * cost / 10, 0)
        if cost <= 0 or have_gold - cost < 0 or have_gold <= 0:
            return "虽然你很想躺平，但是你没有足够的钱"
        uid = await get_stock_uid(user_id, group_id)
        stock = await StockDB.get_stock(uid, "躺平基金")
        # 如果一个人在10天前买了躺平，现在又买了10块钱，放进去会直接变成10/1.015^10块钱
        if stock:
            _, scale, _ = get_tang_ping_earned(stock, 10)
            real_cost = cost / scale
        else:
            real_cost = cost
        await UserConsole.reduce_gold(
            str(user_id), round(cost), GoldHandle.PLUGIN, plugin_name, platform
        )
        try:
            t = await StockDB.buy_stock(
                uid,
                "躺平基金",
                1,
                Decimal.from_float(real_cost),
                Decimal.from_float(cost),
            )
        except Exception as e:
            logger.error(f"买入躺平基金失败，退款: {e}")
            await UserConsole.add_gold(
                str(user_id), round(cost), GoldHandle.GET, platform
            )
            return f"买入躺平基金失败，已退款 {round(cost)} 金币。\n错误: {e}"
        # await StockLogDB.buy_stock_log(uid, "躺平基金", 1, real_cost, 1, cost)
        return (
            f"欢迎认购躺平基金！您认购了💰{cost}的躺平基金，每待满一天就会获得"
            f"{round(float(Config.get_config(plugin_name, '躺平基金每日收益', 0.015) * 100), 1)}%的收益！一定要待满才有哦"
        )


async def sell_lazy_stock_action(
    user_id: int, group_id: int, percent: float, platform: str | None = None
):
    lock = asyncio.Lock()
    # 担心遇到线程问题，加了把锁（不知道有没有用）
    async with lock:
        uid = await get_stock_uid(user_id, group_id)
        stock = await StockDB.get_stock(uid, "躺平基金")
        if not stock:
            return "你之前不在躺平哦"
        day, rate, earned = get_tang_ping_earned(stock, percent)

        await stock.sell_stock(uid, "躺平基金", percent)
        await UserConsole.add_gold(str(user_id), int(earned), GoldHandle.GET, platform)
        # await StockLogDB.sell_stock_log(uid, "躺平基金", stock.number * percent / 10, 1, earned, earned / (1 + rate))
        msg = (
            f"坚持持有了{day}天所以翻了{round(rate, 2)}倍！(该倍率指最早一批买入资金的倍率）"
            if day > 0
            else "没有坚持持有，只能把钱原路退给你了！"
        )
        return f"""卖出了{percent}成仓位的躺平基金
{msg}
得到了{earned}块钱
        """.strip()


async def check_and_execute_orders():
    """检查并执行到期的委托单"""
    from nonebot import get_bot
    from nonebot.adapters.onebot.v11 import MessageSegment

    now = datetime.now(TZ)
    logger.info(
        f"[委托任务] 开始检查委托单，当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    pending_orders = await StockOrderDB.get_pending_orders(now)
    logger.info(f"[委托任务] 找到 {len(pending_orders)} 个待执行的委托单")

    for order in pending_orders:
        try:
            logger.info(
                f"[委托任务] 开始执行委托单 ID:{order.id}, "
                f"类型:{order.type}, 股票:{order.stock_id}, "
                f"用户:{order.uid}, 执行时间:{order.execute_time}"
            )

            user_id, _ = parse_stock_account_key(order.uid)
            group_id = order.group_id
            if group_id is None:
                _, group_id = parse_stock_account_key(order.uid)
            logger.info(f"[委托任务] 解析用户ID:{user_id}, 群组ID:{group_id}")

            result = None
            if order.type == "buy":
                logger.info(
                    f"[委托任务] 执行买入: 股票:{order.stock_id}, "
                    f"金额:{order.cost}, 杠杆:{order.gearing}"
                )
                result = await buy_stock_action(
                    user_id=user_id,
                    group_id=group_id or 0,
                    stock_id=order.stock_id,
                    gearing=float(order.gearing),
                    cost=int(order.cost),
                    force_price=0,
                    platform=None,
                    skip_order=True,
                )
                logger.info(f"[委托任务] 买入结果: {result}")
            elif order.type == "sell":
                logger.info(
                    f"[委托任务] 执行卖出: 股票:{order.stock_id}, "
                    f"仓位:{order.percent}成"
                )
                result = await sell_stock_action(
                    user_id=user_id,
                    group_id=group_id or 0,
                    stock_id=order.stock_id,
                    percent=float(order.percent),
                    force_price=0,
                    platform=None,
                    skip_order=True,
                )
                logger.info(f"[委托任务] 卖出结果: {result}")

            is_order_failed = result and (
                "买不起" in result or ("卖" in result and "还没有买" in result)
            )
            if is_order_failed:
                await StockOrderDB.fail_order(order.id)
                logger.info(f"[委托任务] 委托单 ID:{order.id} 执行失败，已标记为failed")
                if order.type == "buy" and order.cost:
                    await UserConsole.add_gold(
                        str(user_id), int(order.cost), GoldHandle.GET, None
                    )
                    logger.info(f"[委托任务] 已返还用户 {user_id} 金币: {order.cost}")
                    result = f"{result}\n已返还委托金额: {int(order.cost)} 金币"
            else:
                await StockOrderDB.execute_order(order.id)
                logger.info(f"[委托任务] 委托单 ID:{order.id} 执行完成")

            try:
                if group_id is None:
                    logger.info(f"[委托任务] 委托单 ID:{order.id} 无群号，跳过群通知")
                else:
                    bot = get_bot()
                    from nonebot_plugin_htmlrender import text_to_pic

                    result_img = await text_to_pic(
                        f"委托单执行结果:\n{result}", width=300
                    )
                    await bot.send_group_msg(
                        group_id=group_id, message=MessageSegment.image(result_img)
                    )
                    logger.info(f"[委托任务] 已发送执行结果给群:{group_id}")
            except Exception as e:
                logger.error(f"[委托任务] 发送执行结果失败: {e}")

        except Exception as e:
            logger.error(
                f"[委托任务] 执行委托单失败 ID:{order.id}, 错误类型:{type(e)}, 错误信息:{e}"
            )
            import traceback

            logger.error(f"[委托任务] 详细错误:\n{traceback.format_exc()}")

            try:
                await StockOrderDB.fail_order(order.id)
                logger.info(f"[委托任务] 委托单 ID:{order.id} 因异常标记为failed")
                if order.type == "buy" and order.cost:
                    refund_user_id, _ = parse_stock_account_key(order.uid)
                    await UserConsole.add_gold(
                        str(refund_user_id), int(order.cost), GoldHandle.GET, None
                    )
                    logger.info(
                        f"[委托任务] 已返还用户 {refund_user_id} 金币: {order.cost}"
                    )
            except Exception as refund_error:
                logger.error(f"[委托任务] 返还资金失败: {refund_error}")


async def check_timeout_failed_orders():
    """检查超时的失败委托单并退款（超过执行时间3小时的失败委托单）"""
    from nonebot import get_bot
    from nonebot.adapters.onebot.v11 import MessageSegment

    now = datetime.now(TZ)
    logger.info(
        f"[超时委托检查] 开始检查超时失败委托单，当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    timeout_orders = await StockOrderDB.get_timeout_failed_orders(now, timeout_hours=3)
    logger.info(f"[超时委托检查] 找到 {len(timeout_orders)} 个超时失败委托单")

    for order in timeout_orders:
        try:
            logger.info(
                f"[超时委托检查] 处理超时委托单 ID:{order.id}, "
                f"类型:{order.type}, 股票:{order.stock_id}, "
                f"用户:{order.uid}, 执行时间:{order.execute_time}"
            )

            user_id, _ = parse_stock_account_key(order.uid)
            group_id = order.group_id
            if group_id is None:
                _, group_id = parse_stock_account_key(order.uid)

            if order.type == "buy" and order.cost:
                await UserConsole.add_gold(
                    str(user_id), int(order.cost), GoldHandle.GET, None
                )
                logger.info(f"[超时委托检查] 已返还用户 {user_id} 金币: {order.cost}")

                order.status = "cancelled"
                await order.save()
                logger.info(f"[超时委托检查] 委托单 ID:{order.id} 已标记为cancelled")

                try:
                    bot = get_bot()
                    from nonebot_plugin_htmlrender import text_to_pic

                    msg = (
                        f"委托单超时退款通知:\n"
                        f"委托单ID: {order.id}\n"
                        f"股票: {order.stock_id}\n"
                        f"类型: 买入\n"
                        f"金额: {int(order.cost)} 金币\n"
                        f"执行时间: {order.execute_time.strftime('%Y-%m-%d %H:%M')}\n"
                        f"状态: 超时失败，已退款"
                    )
                    if group_id is None:
                        logger.info(
                            f"[超时委托检查] 委托单 ID:{order.id} 无群号，跳过群通知"
                        )
                    else:
                        result_img = await text_to_pic(msg, width=300)
                        await bot.send_group_msg(
                            group_id=group_id, message=MessageSegment.image(result_img)
                        )
                        logger.info(f"[超时委托检查] 已发送退款通知给群:{group_id}")
                except Exception as e:
                    logger.error(f"[超时委托检查] 发送退款通知失败: {e}")

        except Exception as e:
            logger.error(f"[超时委托检查] 处理超时委托单失败 ID:{order.id}, 错误:{e}")
