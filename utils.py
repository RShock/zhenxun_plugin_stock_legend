import time
import urllib.request
from pathlib import Path

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from playwright.async_api import async_playwright
from rfc3986.compat import to_str

from configs.config import Config
from configs.path_config import IMAGE_PATH
from utils.message_builder import image
from .stock_model import StockDB
from services import logger
from utils.http_utils import AsyncPlaywright

import re


# 股票名称: infolist[1]
# 股票代码: infolist[2]
# 当前价格: infolist[3]
# 涨    跌: infolist[4]
# 涨   跌%: infolist[5],'%'
# 成交量(手):infolist[6]
# 成交额(万):infolist[7]
# 第一个参数是股票原始ID,第二个是加工后的（增加了2个字母的前缀）
# 百度股市通能获取所有截图
def get_stock_info(stock_id: str) -> list:
    if stock_id == '躺平基金':
        return ['躺平基金', '躺平基金', 1, 1, 1, 1, 1, 1]
    if not stock_id.isascii() or not stock_id.isprintable():
        return []
    p = re.compile(r'[j|J]\d+')  # 日股代码正则
    if p.match(stock_id):
        return get_jp_stock_info(stock_id)
    f = urllib.request.urlopen('http://qt.gtimg.cn/q=s_' + to_str(stock_id))
    # return like: v_s_sz000858="51~五 粮 液~000858~18.10~0.01~0.06~94583~17065~~687.07";
    strGB: str = f.readline().decode('gb2312')
    f.close()
    infolist = strGB[strGB.find("\""):-3]
    return infolist.split('~')


def get_jp_stock_info(jp_stock_id):
    url = 'https://histock.tw/stock/module/stockdata.aspx?no=J7951'
    # Request Data
    data = dict(
        # 参数
        no='J7951'
    )
    response = requests.post(url, data)
    print(response)  # 请求状态
    print(response.content)  # 返回结果


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
    if stock.stock_id == '躺平基金':
        _, rate, earned = get_tang_ping_earned(stock, 10)
        rate = round(earned * 100 / stock.cost - 100, 2)
        rate = f"📈+{rate}%" if rate >= 0 else f"📉{rate}%"
        return {
            "name": infolist[1],
            "code": "---",
            "number": round(stock.number, 2),
            "price_now": "---",
            "price_cost": "---",
            "gearing": "---",
            "cost": round(stock.cost),
            "value": earned,
            "rate": rate,
            "create_time": time
        }
    value = round((stock.number * float(price) - stock.cost) * stock.gearing + stock.cost, 2)
    rate = round(value * 100 / stock.cost - 100, 2)
    rate = f"📈+{rate}%" if rate >= 0 else f"📉{rate}%"
    return {
        "name": infolist[1],
        "code": stock.stock_id,
        "number": round(stock.number / 100, 2),
        "price_now": price,
        "price_cost": round(stock.cost / stock.number, 2),
        "gearing": stock.gearing,
        "cost": round(stock.cost),
        "value": value,
        "rate": rate,
        "create_time": time
    }


def to_txt(stock):
    if stock["name"] == "躺平基金":
        return f"""{stock["name"]}
持仓数 {stock["number"]}手
花费 {stock["cost"]}金
价值 {stock["value"]}({stock["rate"]})
建仓时间 {stock["create_time"]}
"""
    return f"""{stock["name"]} 代码{stock["code"]}
持仓数 {stock["number"]}手
现价 {stock["price_now"]}亓
成本 {stock["price_cost"]}亓
⚖比例 {stock["gearing"]}
花费 {stock["cost"]}金
当前价值 {stock["value"]}({stock["rate"]})
建仓时间 {stock["create_time"]}"""


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


def convert_stocks_to_md_table(username, stocks):
    result = f'### {username}的持仓\n'\
        '|名称|代码|持仓数量|现价|成本|杠杆比例|花费|当前价值|建仓时间|\n' \
             '| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n'

    def to_md(s):
        # 染色
        if s['value'] > s['cost']:
            s['value'] = f"<font color=\"#dd0000\">{s['value']}</font>"
        elif s['value'] < s['cost']:
            s['value'] = f"<font color=\"#00dd00\">{s['value']}</font>"

        return f"|{s['name']}|{s['code']}|{s['number']}|{s['price_now']}|{s['price_cost']}|{s['gearing']}" \
               f"|{s['cost']}|{s['value']}({s['rate']})|{s['create_time']}|\n"

    total_value = 0
    total_cost = 0
    for stock in stocks:
        total_value += float(stock['value'])
        total_cost += float(stock['cost'])
        result += to_md(stock)
    dif = round(total_value - total_cost, 1)
    if dif >= 0:
        dif = f"<font color=\"#dd0000\">{dif}</font>"
    else:
        dif = f"<font color=\"#00dd00\">{dif}</font>"
    total_value = round(total_value, 2)
    total_cost = round(total_cost, 2)
    result += f"|总计||||||{total_cost}|{total_value}|{dif}|"
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
    if len(stock_id) == 4 and stock_id.isdigit():  # 港股
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


def get_tang_ping_earned(stock: StockDB, percent: float) -> (int, float, int):
    day = (time.time() - time.mktime(stock.buy_time.timetuple())) // 60 // 60 // 24
    tang_ping = float(Config.get_config("stock_legend", "TANG_PING", 5))
    rate = ((1 + tang_ping) ** day)  # 翻倍数
    return day, rate, round(stock.number * rate * percent / 10)


# 采用东财 图像更专业
async def get_stock_img_v2(origin_stock_id: str, stock_id: str, is_detail: bool = False):
    is_fund = False  # 基金特判
    if len(origin_stock_id) == 5 and origin_stock_id.isdigit():
        url = f"http://quote.eastmoney.com/hk/{origin_stock_id}.html"
        tar = "//div[contains(@class,'quote3l')][2]//div[@class='quote3l_c']"
    elif stock_id.startswith("us"):
        url = f"http://quote.eastmoney.com/us/{origin_stock_id}.html"
        tar = "//div[contains(@class,'quote3l')][2]//div[@class='quote3l_c']"
    elif origin_stock_id == "IXIC":  # 纳斯达克指数 还有很多同类指数实在是搞不过来 建议直接去买对应基金
        url = "https://gushitong.baidu.com/index/us-IXIC"
        tar = ".fac"
    # 国债r001系列(购买这个系列完全是作弊，不禁止的原因是，希望有人能通过这个游戏学习股市，最后发现这个(直接看这段文字的不算数))
    # 真发现了，可以先约定不许买
    elif origin_stock_id.startswith('13'):
        url = f"http://quote.eastmoney.com/bond/{stock_id}.html"
        tar = "//div[contains(@class,'quote2l_cr2_m')]"
    elif stock_id.startswith('jj'):  # 基金
        url = f"https://fund.eastmoney.com/{stock_id[2:]}.html"
        is_fund = True
    else:  # 其他ab股
        url = f"http://quote.eastmoney.com/{stock_id}.html"
        tar = "//div[@id='js_box']"
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
        )

        page = await browser.new_page()
        logger.info(url)
        await page.goto(url)

        path = f"{IMAGE_PATH}/stock_legend/stockImg_{stock_id}_{time.time()}.png"
        if is_fund:
            viewport_size = dict(width=1200, height=3400)
            await page.set_viewport_size(viewport_size)
            tmp = page.locator("#hq_ip_tips >> text=立即开启")
            if tmp:
                await tmp.click()
                await page.wait_for_timeout(1000)
            await page.screenshot(path=path, timeout=10000, clip={"x": 0, "width": 780, "y": 700, "height": 2400})
        else:
            page = await page.wait_for_selector(tar, timeout=10000)
            await page.screenshot(path=path, timeout=10000)

        await browser.close()
    return image(Path(path))
