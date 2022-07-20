import asyncio
import urllib.request

from rfc3986.compat import to_str

from models.bag_user import BagUser
from .stock_model import StockDB
from .stock_log_model import StockLogDB
from configs.config import Config


def get_stock_info(num) -> list:
    f = urllib.request.urlopen('http://qt.gtimg.cn/q=s_' + to_str(num))
    # return like: v_s_sz000858="51~五 粮 液~000858~18.10~0.01~0.06~94583~17065~~687.07";
    strGB = f.readline().decode('gb2312')
    f.close()
    infolist = strGB[14:-3]
    return infolist.split('~')


# 股票名称: infolist[1]
# 股票代码: infolist[2]
# 当前价格: infolist[3]
# 涨    跌: infolist[4]
# 涨   跌%: infolist[5],'%'
# 成交量(手):infolist[6]
# 成交额(万):infolist[7]

async def buy_stock_action(user_id: int, group_id: int, stock_id: str, gearing: float, cost: int) -> str:
    infolist = get_stock_info(stock_id)
    if len(infolist) <= 7:
        return f"未找到对应股票，提示：请使用股票代码而不是名字"
    price = float(infolist[3])
    name = infolist[1]
    lock = asyncio.Lock()
    # 担心遇到线程问题，加了把锁（不知道有没有用）
    async with lock:
        have_gold = await BagUser.get_gold(user_id, group_id)
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
        # 涨停的股票不能买可以做空 跌停的股票反之（A股特供，防止打板战术）
        if is_a_stock(stock_id):
            if float(infolist[5]) > 9.9 and gearing >= 0:
                return f"该股票涨停了，不能买哦"
            if float(infolist[5]) < -9.9 and gearing < 0:
                return f"该股票跌停了，不能做空哦"

        num = cost / price
        origin_cost = cost
        if stock and stock.gearing != gearing:  # 杠杆改变的逻辑
            # 先把旧股票全卖了
            earned = round((stock.number * price - stock.cost) * stock.gearing + stock.cost, 0)
            # 加上当前本金
            cost = earned + cost
            # 算出当前股数
            num = cost / price
            await sell_stock_action(user_id, group_id, stock_id, 10)
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


# 上海深圳股票有涨跌停
def is_a_stock(stock_id):
    return stock_id.startswith("sh") or stock_id.startswith("sz")


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
            if float(infolist[5]) < -9.9 and stock.gearing > 0:
                return f"{name}看起来跌停了，不能卖哦"
            if float(infolist[5]) < -9.9 and stock.gearing < 0:
                return f"{name}看起来涨停了，不能平仓哦"
        await StockDB.sell_stock(
            uid, stock_id, percent
        )
        total_value = (stock.number * price - stock.cost) * stock.gearing + stock.cost
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

    def to_txt(stock: StockDB):
        infolist = get_stock_info(stock.stock_id)
        price = infolist[3]
        time = stock.buy_time.strftime("%Y-%m-%d %H:%M:%S")
        result = {
            "name": infolist[1],
            "code": stock.stock_id,
            "number": round(stock.number / 100, 2),
            "price_now": price,
            "price_cost": round(stock.cost / stock.number, 2),
            "gearing": stock.gearing,
            "cost": stock.cost,
            "value": round((stock.number * float(price) - stock.cost) * stock.gearing + stock.cost, 2),
            "create_time": time
        }
        return result

    return [to_txt(stock) for stock in my_stocks]


async def get_stock_list_action_for_win(uid: int, group_id: int):
    my_stocks = await StockDB.get_my_stock(f"{uid}:{group_id}")

    def to_txt(stock: StockDB):
        infolist = get_stock_info(stock.stock_id)
        price = infolist[3]
        time = stock.buy_time.strftime("%Y-%m-%d %H:%M:%S")
        return f"{infolist[1]} 代码{stock.stock_id}\n" \
               f"持仓数 {round(stock.number / 100, 2)}手\n" \
               f"现价 {price}亓\n" \
               f"成本 {round(stock.cost / stock.number, 2)}亓\n" \
               f"⚖比例 {stock.gearing}\n" \
               f"花费 {stock.cost}金\n" \
               f"当前价值 {round((stock.number * float(price) - stock.cost) * stock.gearing + stock.cost, 2)}金\n" \
               f"建仓时间 {time}"

    return [to_txt(stock) for stock in my_stocks]


async def force_clear_action(user_id: int, group_id: int):
    uid = f"{user_id}:{group_id}"
    stocks = await StockDB.get_stocks_by_uid(uid)
    for stock in stocks:
        await sell_stock_action(user_id, group_id, stock.stock_id, 10)
    return len(stocks)
