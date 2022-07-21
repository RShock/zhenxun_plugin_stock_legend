import time
import urllib.request

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from rfc3986.compat import to_str


# 股票名称: infolist[1]
# 股票代码: infolist[2]
# 当前价格: infolist[3]
# 涨    跌: infolist[4]
# 涨   跌%: infolist[5],'%'
# 成交量(手):infolist[6]
# 成交额(万):infolist[7]
from configs.path_config import IMAGE_PATH
from extensive_plugin.stock_legend.stock_model import StockDB
from services import logger
from utils.http_utils import AsyncPlaywright


# 第一个参数是股票原始ID,第二个是加工后的（增加了2个字母的前缀）
# 百度股市通能获取所有截图
def get_stock_info(num) -> list:
    f = urllib.request.urlopen('http://qt.gtimg.cn/q=s_' + to_str(num))
    # return like: v_s_sz000858="51~五 粮 液~000858~18.10~0.01~0.06~94583~17065~~687.07";
    strGB = f.readline().decode('gb2312')
    f.close()
    infolist = strGB[14:-3]
    return infolist.split('~')


# 判断是不是a股，因为上海深圳股票有涨跌停
def is_a_stock(stock_id):
    return stock_id.startswith("sh") or stock_id.startswith("sz")


def is_st_stock(stock_name: str):
    return stock_name.startswith("ST") or stock_name.startswith("*ST")


# 计算当前持仓值多少钱
def get_total_value(price, stock):
    return (stock.number * price - stock.cost) * stock.gearing + stock.cost


def to_obj(stock: StockDB):
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


async def get_stock_img(origin_stock_id: str, stock_id: str, is_long: bool = False):
    # 这些可以交给百度股市通
    if len(origin_stock_id) == 5 and origin_stock_id.isdigit():
        url = f"https://gushitong.baidu.com/stock/hk-{origin_stock_id}"
    elif stock_id.startswith("us"):
        url = f"https://gushitong.baidu.com/stock/us-{origin_stock_id}"
    elif origin_stock_id == "IXIC":  # 纳斯达克指数
        url = "https://gushitong.baidu.com/index/us-IXIC"
    else:
        url = f"https://gushitong.baidu.com/stock/ab-{origin_stock_id}"

    logger.info(url)
    if is_long:
        tmp = "#app"
    else:
        tmp = ".fac"
    return await AsyncPlaywright.screenshot(
        url,
        f"{IMAGE_PATH}/temp/stockImg_{stock_id}_{time.time()}.png",
        tmp,
        wait_time=12
    )


async def send_forward_msg_group(
        bot: Bot,
        event: GroupMessageEvent,
        name: str,
        stocks: [],
):
    """
    合并消息
    @param bot: 机器人的引用
    @param event: 用来获取群id
    @param name: 发消息的人的名字
    @param stocks: 股票信息
    @return:
    """
    def to_json(stock):
        return {"type": "node", "data": {"name": name, "uin": bot.self_id, "content": stock}}

    messages = [to_json(stock) for stock in stocks]
    await bot.call_api(
        "send_group_forward_msg", group_id=event.group_id, messages=messages
    )


def convert_stocks_to_md_table(stocks):
    result = "|名称  |代码|持仓数量|现价|成本|杠杆比例|花费|当前价值|建仓时间|\n" \
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"

    def to_md(s):
        # 染色
        if s['value'] > s['cost']:
            s['value'] = f"<font color=\"#dd0000\">{s['value']}</font>"
        elif s['value'] < s['cost']:
            s['value'] = f"<font color=\"#00dd00\">{s['value']}</font>"
        return f"|{s['name']}|{s['code']}|{s['number']}|{s['price_now']}|{s['price_cost']}|{s['gearing']}" \
               f"|{s['cost']}|{s['value']}|{s['create_time']}|\n"

    for stock in stocks:
        result += to_md(stock)
    return result


def fill_stock_id(stock_id: str) -> str:
    """
    补全股票ID
    @param stock_id: 原始ID
    @return: 补全后的ID
    """
    # 玩家手动指定市场
    if stock_id.startswith("sh") or stock_id.startswith("sz") or stock_id.startswith("hk") \
            or stock_id.startswith("us") or stock_id.startswith("jj"):
        return stock_id
    if len(stock_id) == 4 and stock_id.isdigit():    # 港股
        return "hk0" + stock_id
    if len(stock_id) == 5 and stock_id.isdigit():  # 港股
        return "hk" + stock_id
    if stock_id.startswith("60") or stock_id.startswith("11") or stock_id.startswith("5"):  # 上海与上海可转债与上海场内基金
        return "sh" + stock_id
    # 深圳与深圳可转债(12)与深圳创业板与深圳场内基金(1)
    if stock_id.startswith("00") or stock_id.startswith("1") or stock_id.startswith("30"):
        return "sz" + stock_id
    if stock_id.startswith("4") or stock_id.startswith("8"):  # 北京
        return "bj" + stock_id
    # 其他一律当作美股
    return "us" + stock_id
