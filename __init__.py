import platform
import time

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, Message, Bot, MessageSegment
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.typing import T_State
from services.log import logger
from configs.path_config import IMAGE_PATH
from utils.http_utils import AsyncPlaywright
from configs.config import Config
from ..nonebot_plugin_htmlrender import text_to_pic, md_to_pic


from .data_source import (
    sell_stock_action,
    buy_stock_action,
    is_a_stock,
    get_stock_list_action,
    force_clear_action,
    get_stock_list_action_for_win,
)

__zx_plugin_name__ = "股海风云"
__plugin_usage__ = """
usage：
    简单股市小游戏，T+0 可做空 保证金无限 最高10倍杠杆 0手续费
    如果你是新手，不需要在意细节，可以从入门的股票简单的玩
    指令：
    买股票+代码+金额+杠杆倍数(可不填) 买入股票 例：买股票 600888 10000  (买入10000金币的仓位)
    卖股票+代码+仓位百分制 卖出股票 例：卖股票 600888 10 (卖出10层仓位)
    我的持仓
    ————————————————
     如果要买基金，为防止混淆，需要在基金前面加上"jj" 
     例：邯钢转债(110001) 易方达平稳增长混合(jj110001)

     支持股票类型：港股 美股 A股 基金
     注意：该游戏不会计算分红
     杠杆：单纯的将盈利和亏损乘以指定的系数，杠杆值为负数即为做空
    ————————————————
    强制清仓+qq号  管理专用指令，爆仓人不愿意清仓就对他使用这个吧
    ————————————————
                                                       游戏制作人：小r
""".strip()
__plugin_des__ = "谁才是股市传奇？"
__plugin_cmd__ = ["买股票 代码 金额]", "卖股票 代码 仓位（十分制）", "我的持仓", "强制清仓"]
__plugin_version__ = 0.1
__plugin_author__ = "XiaoR"
__plugin_settings__ = {
    "level": 5,
    "default_status": True,
    "limit_superuser": True,
    "cmd": ["买股票", "买股票", "我的持仓"],
}
__plugin_configs__ = {
    "GEARING_RATIO": {
        "value": 5,
        "help": "最大杠杆比率",
        "default_value": 5,
    }
}
__plugin_type__ = ("群内小游戏",)


buy_stock = on_command("买股票", aliases={"买入", "建仓", "买入股票"}, priority=5, block=True)
sell_stock = on_command("卖股票", aliases={"卖出", "清仓", "平仓", "卖出股票"}, priority=5, block=True)
my_stock = on_command("我的持仓", aliases={"我的股票", "我的仓位"}, priority=5, block=True)
clear_stock = on_command("强制清仓", priority=5, permission=SUPERUSER, block=True)


# 查询接口时需要补全股票代码的所在地
def fill_stock_id(stock_id) -> str:
    # 玩家手动指定市场
    if stock_id.startswith("sh") or stock_id.startswith("sz") or stock_id.startswith("hk") \
            or stock_id.startswith("us") or stock_id.startswith("jj"):
        return stock_id
    if len(stock_id) == 5:  # 港股
        return "hk" + stock_id
    if stock_id.startswith("60") or stock_id.startswith("11") or stock_id.startswith("5"):  # 上海与上海可转债与上海场内基金
        return "sh" + stock_id
    # 深圳与深圳可转债(12)与深圳创业板与深圳场内基金(1)
    if stock_id.startswith("00") or stock_id.startswith("1") or stock_id.startswith("300"):
        return "sz" + stock_id
    if stock_id.startswith("4") or stock_id.startswith("8"):  # 北京
        return "bj" + stock_id
    # 其他一律当作美股
    return "us" + stock_id


@buy_stock.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    if not isinstance(event, GroupMessageEvent):
        await buy_stock.finish("这个游戏只能在群里玩哦")

    msg = arg.extract_plain_text().strip().split()
    if len(msg) < 2:
        await buy_stock.finish("格式错误，请输入买股票 股票代码 杠杆层数 金额 如 买股票 600888 1000 5")
    stock_id = fill_stock_id(msg[0])
    origin_stock_id = stock_id[2:]
    cost = int(msg[1])
    # 第三个参数是杠杆
    # 最大杠杆比率
    if cost == 0:
        await buy_stock.send(f"你看了看，但是没有买")
        await buy_stock.finish(await get_stock_img(origin_stock_id, stock_id))
    if cost < 0:
        await buy_stock.finish(f"想做空的话请使用负数的杠杆率哦")
    max_gearing = round(float(Config.get_config("stock_legend", "GEARING_RATIO", 5)), 1)
    if len(msg) == 3:
        gearing = float(msg[2])
        if gearing > max_gearing:
            await buy_stock.send(f"最高杠杆只能到{max_gearing}倍,已经修正为{max_gearing}倍")
            gearing = max_gearing
        if gearing < -max_gearing:
            await buy_stock.send(f"最高杠杆只能到-{max_gearing}倍,已经修正为-{max_gearing}倍")
            gearing = -max_gearing
    else:
        gearing = 1
    result = await buy_stock_action(event.user_id, event.group_id, stock_id, gearing, cost)

    await buy_stock.send(MessageSegment.image(await text_to_pic(result, width=300)))
    await buy_stock.finish(await get_stock_img(origin_stock_id, stock_id))


@sell_stock.handle()
async def _(
        event: MessageEvent,
        state: T_State,
        arg: Message = CommandArg()):
    if not isinstance(event, GroupMessageEvent):
        await buy_stock.finish("这个游戏只能在群里玩哦")
    msg = arg.extract_plain_text().strip().split()
    if len(msg) < 1:
        await sell_stock.finish("格式错误，请输入卖股票 股票代码 [仓位(不填默认为十)] 如 买股票 601919 7.5")
    stock_id = fill_stock_id(msg[0])
    percent = round(int(msg[1]), 2)
    if percent > 10:
        await sell_stock.finish("不能卖十成以上的仓位哦")
    if percent <= 0:
        await sell_stock.finish("卖的仓位太低了！")
    result = await sell_stock_action(event.user_id, event.group_id, stock_id, percent)
    await sell_stock.send(MessageSegment.image(await text_to_pic(result, width=300)))
    origin_stock_id = stock_id[2:]
    await sell_stock.finish(await get_stock_img(origin_stock_id, stock_id))


def convert_stocks_to_md_table(stocks):
    result = "|名称  |代码|持仓数量|现价|成本|杠杆比例|花费|当前价值|建仓时间|\n" \
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"

    def to_md(s):
        return f"|{s['name']}|{s['code']}|{s['number']}|{s['price_now']}|{s['price_cost']}|{s['gearing']}" \
               f"|{s['cost']}|{s['value']}|{s['create_time']}|\n"

    for stock in stocks:
        result += to_md(stock)
    return result


@my_stock.handle()
async def _(event: MessageEvent, bot: Bot, state: T_State, arg: Message = CommandArg()):
    if not isinstance(event, GroupMessageEvent):
        await buy_stock.finish("这个游戏只能在群里玩哦")

    # linux下使用这套逻辑
    if platform.system().lower() == 'linux':
        my_stocks = await get_stock_list_action(event.user_id, event.group_id)
        if not my_stocks:
            await sell_stock.send(MessageSegment.image(await text_to_pic("你还什么都没买呢！", width=300)))
        txt = convert_stocks_to_md_table(my_stocks)
        logger.info(txt)
        await sell_stock.finish(MessageSegment.image(await md_to_pic(f"{txt}", width=1200)))

    # windows下使用这套逻辑(风控差一点)
    if platform.system().lower() == 'windows':
        my_stocks = await get_stock_list_action_for_win(event.user_id, event.group_id)
        await send_forward_msg_group(bot, event, "真寻炒股小助手", my_stocks if my_stocks else ["你还什么都没买呢！"])


# 合并消息
async def send_forward_msg_group(
        bot: Bot,
        event: GroupMessageEvent,
        name: str,
        stocks: [],
):
    def to_json(stock):
        return {"type": "node", "data": {"name": name, "uin": bot.self_id, "content": stock}}

    messages = [to_json(stock) for stock in stocks]
    await bot.call_api(
        "send_group_forward_msg", group_id=event.group_id, messages=messages
    )


# 第一个参数是原始ID,第二个是加工后的
# 如果是A股 可以靠自己抓百度的截图 其他情况交给api截图（缺点：1小时只能对一个链接截图1张，而且页面不好看）
async def get_stock_img(origin_stock_id: str, stock_id: str):
    # 这些可以交给百度股市通
    if len(origin_stock_id) == 5:
        url = f"https://gushitong.baidu.com/stock/hk-{origin_stock_id}"
    elif stock_id.startswith("us"):
        url = f"https://gushitong.baidu.com/stock/us-{origin_stock_id}"
    else:
        url = f"https://gushitong.baidu.com/stock/ab-{origin_stock_id}"
    logger.info(url)
    return await AsyncPlaywright.screenshot(
        url,
        f"{IMAGE_PATH}/temp/stockImg_{stock_id}_{time.time()}.png",
        "#app",
        viewport_size=dict(width=1080, height=1800),
        wait_time=12
    )


# 这是一个测试用管理员指令，不能滥用
# 没有做太多容错处理
@clear_stock.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    if not isinstance(event, GroupMessageEvent):
        await buy_stock.finish("这个游戏只能在群里玩哦")

    msg = arg.extract_plain_text().strip().split()
    if len(msg) < 1:
        await buy_stock.finish("格式错误，请输入强制清仓 qq号")
    cnt = await force_clear_action(int(msg[0]), event.group_id)
    await buy_stock.finish(MessageSegment.image(await text_to_pic(f"{msg[0]}的{cnt}仓位都被卖了", width=300)))