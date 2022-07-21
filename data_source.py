import asyncio

from models.bag_user import BagUser
from .stock_model import StockDB
from .stock_log_model import StockLogDB
from configs.config import Config
from .utils import get_stock_info, get_total_value, to_obj, to_txt, is_a_stock, is_st_stock


async def buy_stock_action(user_id: int, group_id: int, stock_id: str, gearing: float, cost: int,
                           force_price: float = None) -> str:
    infolist = get_stock_info(stock_id)
    if len(infolist) <= 7:

        return f"未找到对应股票，提示：请使用股票代码而不是名字"
    if force_price:
        price = force_price
    else:
        price = float(infolist[3])
    name = infolist[1]
    lock = asyncio.Lock()
    # 担心遇到线程问题，加了把锁（不知道有没有用）
    async with lock:
        have_gold = await BagUser.get_gold(user_id, group_id)
        if have_gold <= 0 and gearing is None:  # 先筛选一种情况
            return f"你没有钱买股票"
        if 0 < cost <= 10:  # 如果花费小于10，认为他说的是仓位而不是花费
            cost = have_gold * cost / 10
        elif have_gold < cost:
            return f"你当前只有{have_gold},买不起{cost}的股票哦"
        if price == 0:
            return f"{name}停牌了，不能买哦"

        uid = f"{user_id}:{group_id}"
        stock = await StockDB.get_stock(uid, stock_id)
        # 先理清楚杠杆到底是多少
        if stock:
            if not gearing:
                gearing = stock.gearing
        if not gearing:
            max_gearing = round(float(Config.get_config("stock_legend", "GEARING_RATIO", 5)), 1)
            gearing = max_gearing
        gearing = round(gearing, 1)
        if (stock and have_gold == 0 and gearing == stock.gearing) or (stock is None and have_gold == 0):
            return f"你没有钱买股票"
        # 涨停的股票不能买可以做空 跌停的股票反之（A股特供，防止打板战术）
        if is_a_stock(stock_id):
            if is_st_stock(name):
                if float(infolist[5]) > 4.93 and gearing >= 0:
                    return f"该股票涨停了，不能买哦"
                if float(infolist[5]) < -4.93 and gearing < 0:
                    return f"该股票跌停了，不能做空哦"
            if float(infolist[5]) > 9.9 and gearing >= 0:
                return f"该股票涨停了，不能买哦"
            if float(infolist[5]) < -9.9 and gearing < 0:
                return f"该股票跌停了，不能做空哦"

        num = cost / price
        origin_cost = cost
        if stock and stock.gearing != gearing:  # 杠杆改变的逻辑
            # 先把旧股票全卖了
            earned = await fast_clear_stock(price, group_id, stock, user_id)
            # 加上当前本金
            cost = earned + cost
            # 算出当前股数
            num = cost / price
        # 再买
        query = await StockDB.buy_stock(
            uid, stock_id, gearing, num, cost
        )
        await StockLogDB.buy_stock_log(uid, stock_id, gearing, num, price, cost, query.buy_time)
        await BagUser.spend_gold(user_id, group_id, cost)
    if query:
        if stock and stock.gearing != gearing:
            return f'给{name}追加仓位{origin_cost},修改杠杆为{gearing}\n' \
                   f'因为杠杆的调整，持仓被重新计算了\n' \
                   f'现价 {price}亓\n' \
                   f'当前持仓 {round(query.number / 100, 2)}手\n' \
                   f'当前持仓价值 {round((query.number * price - query.cost) * query.gearing + query.cost, 2)}\n' \
                   f'当前持仓成本 {round(query.cost, 2)}\n' \
                   f'杠杆比率 {query.gearing}\n' \
                   f'剩余资金 {have_gold - cost}'
        else:
            return f"成功购买了 {round(num / 100, 2)} 手 {name}\n" \
                   f"现价 {price}亓\n" \
                   f"当前持仓 {round(query.number / 100, 2)}手\n" \
                   f"当前持仓价值 {round((query.number * price - query.cost) * query.gearing + query.cost, 2)}\n" \
                   f"当前持仓成本 {round(query.cost, 2)}\n" \
                   f"杠杆比率 {query.gearing}\n" \
                   f"剩余资金 {have_gold - cost}"


# 快速清仓指令
async def fast_clear_stock(price, group_id, stock, user_id):
    await stock.delete()
    v = round(get_total_value(price, stock), 0)
    await BagUser.add_gold(user_id, group_id, v)
    return v


async def sell_stock_action(user_id: int, group_id: int, stock_id: str, percent: float):
    infolist = get_stock_info(stock_id)
    if len(infolist) <= 7:
        return f"未找到对应股票，提示：请使用股票代码而不是名字"
    price = float(infolist[3])
    name = infolist[1]
    uid = f"{user_id}:{group_id}"
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
        await StockDB.sell_stock(
            uid, stock_id, percent
        )
        if stock.cost <= 0:  # 正常情况不会出现，但是一旦出现需要异常修复
            stock.cost = 1
        total_value = get_total_value(price, stock)
        return_money = round(total_value * percent / 10, 0)
        earned_percent = round((total_value - stock.cost) / stock.cost * 100, 2)
        await StockLogDB.sell_stock_log(
            uid=uid,
            stock_id=stock_id,
            number=stock.number * percent / 10,
            price=price,
            get=return_money,
            profit=(total_value - stock.cost) * percent * stock.gearing)
        await BagUser.add_gold(user_id, group_id, return_money)
    if earned_percent < -100:
        lajihua = f"亏了{-earned_percent}%，只能去当三和大神了！"
    elif earned_percent < -10:
        lajihua = f"亏了{-earned_percent}%，好伤心！"
    elif earned_percent < 0:
        lajihua = f"小亏了{-earned_percent}%"
    elif earned_percent == 0:
        lajihua = f"没亏没赚"
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
    return f"卖掉了 {name} {percent}成仓位, {lajihua}\n" \
           f"成交价 {price}亓\n" \
           f"卖了 {return_money} 块钱\n" \
           f"剩余仓位 {round(stock.number * (1 - percent / 10) / 100, 2)} 手\n" \
           f"剩余仓位当前价值 {round(total_value * (1 - percent / 10), 2)}"


async def get_stock_list_action(uid: int, group_id: int):
    my_stocks = await StockDB.get_my_stock(f"{uid}:{group_id}")

    return [to_obj(stock) for stock in my_stocks]


async def get_stock_list_action_for_win(uid: int, group_id: int):
    my_stocks = await StockDB.get_my_stock(f"{uid}:{group_id}")

    return [to_txt(stock) for stock in my_stocks]


async def force_clear_action(user_id: int, group_id: int):
    uid = f"{user_id}:{group_id}"
    stocks = await StockDB.get_stocks_by_uid(uid)
    for stock in stocks:
        await sell_stock_action(user_id, group_id, stock.stock_id, 10)
    return len(stocks)


async def revert_stock_action(user_id: int, group_id: int, stock_id: str):
    infolist = get_stock_info(stock_id)
    if len(infolist) <= 7:
        return f"未找到对应股票，提示：请使用股票代码而不是名字"
    price = float(infolist[3])
    name = infolist[1]
    lock = asyncio.Lock()
    # 担心遇到线程问题，加了把锁（不知道有没有用）
    async with lock:
        uid = f"{user_id}:{group_id}"
        stock = await StockDB.get_stock(uid, stock_id)
        if not stock:
            return f"你还没买{name}(当前价格:{price})呢！"
        gearing = -stock.gearing
        if is_a_stock(stock_id):
            if is_st_stock(name):
                if float(infolist[5]) > 4.93 or float(infolist[5]) < -4.93:
                    return f"该功能在涨跌停时关闭！"

            if float(infolist[5]) > 9.9 or float(infolist[5]) < -9.9:
                return f"该功能在涨跌停时关闭！"

        total_value = await fast_clear_stock(price, group_id, stock, user_id)
        await buy_stock_action(user_id, group_id, stock_id, gearing, total_value, price)
    return f"""反转{name}仓位成功！
当前股票价格{price}
当前杠杆{gearing}
当前仓位价值{total_value}
"""
