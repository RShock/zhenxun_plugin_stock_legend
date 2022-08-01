import platform

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, Message, Bot, MessageSegment
from nonebot.params import CommandArg, ArgPlainText, Arg
from nonebot.permission import SUPERUSER
from nonebot.typing import T_State
from nonebot.matcher import Matcher

from services.log import logger
from configs.config import Config
from .utils import get_stock_img, send_forward_msg_group, convert_stocks_to_md_table, fill_stock_id, get_stock_img_v2
from ..nonebot_plugin_htmlrender import text_to_pic, md_to_pic

from .data_source import (
    sell_stock_action,
    buy_stock_action,
    get_stock_list_action,
    force_clear_action,
    get_stock_list_action_for_win,
    revert_stock_action,
    buy_lazy_stock_action,
    sell_lazy_stock_action
)
from .utils import is_a_stock, get_stock_img, send_forward_msg_group, convert_stocks_to_md_table, fill_stock_id

__zx_plugin_name__ = "股海风云"
__plugin_usage__ = """
usage：
    简单股市小游戏，T+0 可做空 保证金无限 最高10倍杠杆 0手续费

    指令：
    买股票+代码+金额+杠杆倍数(可不填) 买入股票 例：买股票 600888 10000  (买入10000金币的仓位)
    卖股票+代码+仓位百分制 卖出股票 例：卖股票 600888 10 (卖出10层仓位，全卖可以省略这个参数)
        也支持使用仓位来买股票，如果什么都不填（比如只发送‘买股票600888’）会默认使用满仓满杠杆
        不指定杠杆都会默认加满杠杆！
    我的持仓
    查看持仓+atQQ 偷看别人的持仓
    反转持仓+股票代码 短线快捷指令，不卖出的情况下快速实现多转空 空转多
    清仓 直接把自己所有股票卖完（这个指令还在内测中）
    关于股海风云 可以看看这个插件有没有更新，会发一个github链接，当心风控哦
    ————————————————
    Q: 如何买基金
    A: 如果要买基金，为防止混淆，需要在基金前面加上"jj" 
     例：邯钢转债(110001) 易方达平稳增长混合(jj110001)
         如果你是新手，不需要在意细节，可以从入门的股票简单的玩
         
    Q: 杠杆是什么？
    A: 简单理解为加倍和超级加倍即可
         杠杆可以是负数（做空）
         如果买股票时忘记输入杠杆也没关系，可以再买一次来修改杠杆
     
    Q: 支持股票类型？
    A: 港股 美股 A股 基金
    
    Q: 不支持的东西？
    A: 分红 挂单
    
    Q: 我是超级新手，怎么玩？
    A: 可以先输入‘买入躺平基金 x’ x为仓位数 最高10 可不填
    
    Q: 股票代码是从哪里来的？
    A: 需要从现实中的股市提取
    
    Q: 为什么允许非整数的手数/是否应该加入汇率
    A: 当基金玩的
    ————————————————
    强制清仓+qq号(不是at是qq号)  管理专用指令，爆仓人不愿意清仓就对他使用这个吧
""".strip()
__plugin_des__ = "谁才是股市传奇？"
__plugin_type__ = ("群内小游戏",)
__plugin_cmd__ = ["买股票 代码 金额]", "卖股票 代码 仓位（十分制）", "我的持仓", "强制清仓"]
__plugin_version__ = 2.1
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
    },
    "TANG_PING": {
        "value": 0.015,
        "help": "躺平基金每日收益",
        "default_value": 0.015,
    },
    "WIN_FIT": {
        "value": False,
        "help": "如果我的持仓功能报错，且看了issue还是改不好，就把这个改成true",
        "default_value": False,
    },
    "IMAGE_MODE": {
        "value": 2,
        "help": "1:股票提示图为百度股市通，比较新人  2:股票提示图为分时+日k且支持基金",
        "default_value": 2,
    }
}

buy_stock = on_command("买股票", aliases={"买入", "建仓", "买入股票"}, priority=5, block=True)
sell_stock = on_command("卖股票", aliases={"卖出", "平仓", "卖出股票"}, priority=5, block=True)
my_stock = on_command("我的持仓", aliases={"我的股票", "我的仓位", "我的持股"}, priority=5, block=True)
clear_stock = on_command("强制清仓", priority=5, permission=SUPERUSER, block=True)
look_stock = on_command("查看持仓", aliases={"偷看持仓", "他的持仓"}, priority=5, block=True)
revert_stock = on_command("反转持仓", priority=5, block=True)
help_stock = on_command("关于股海风云", priority=5, block=True)
query_stock = on_command("查看股票", priority=5, block=True)
clear_my_stock = on_command("清仓", priority=5, block=True)


@buy_stock.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    if not isinstance(event, GroupMessageEvent):
        await buy_stock.finish(await to_pic_msg("这个游戏只能在群里玩哦"))
    msg = arg.extract_plain_text().strip().split()
    if len(msg) < 1:
        await buy_stock.finish(await to_pic_msg(
            f"格式错误，请输入\n买股票 股票代码 金额 杠杆层数(可选)\n如 买股票 600888 1000 5", width=300))
    if msg[0] == '躺平' or msg[0] == '躺平基金':  # 买入躺平基金的特殊逻辑
        await buy_lazy_handle(buy_stock, msg, event)
        return
    await buy_handle(buy_stock, msg, event)


async def buy_handle(bot, msg, event):
    if len(msg) == 1:
        cost = 10  # 10成仓位
    else:
        cost = int(msg[1])
    stock_id = fill_stock_id(msg[0])
    origin_stock_id = stock_id[2:]
    max_gearing = round(float(Config.get_config("stock_legend", "GEARING_RATIO", 5)), 1)
    gearing = None
    # 第三个参数是杠杆
    # 最大杠杆比率
    if cost == 0 and len(msg) == 2:  # 专门用来看行情，但是加上杠杆参数就是改杠杆了
        await bot.send(await to_pic_msg(f"你看了看，但没有买", width=300))
        await bot.finish(await get_stock_img_(origin_stock_id, stock_id))
    if cost < 0:
        if cost < -max_gearing:
            await bot.finish(await to_pic_msg(f"想做空的话\n请使用负数的杠杆率哦", width=300))
        else:  # 这个人输入了买股票xxxx -10 (-10应该是杠杆倍率而不是cost)
            gearing = cost
            cost = 10
    if len(msg) == 3:
        gearing = float(msg[2])
        if gearing > max_gearing:
            if -max_gearing <= cost <= max_gearing:  # 防呆，这人把输入参数顺序搞反了
                cost, gearing = gearing, cost
                await bot.send(await to_pic_msg(
                    f"你的杠杆和花费金币参数顺序反了，已经帮你修好了", width=300))
            else:
                await bot.send(await to_pic_msg(
                    f"最高杠杆只能到{max_gearing}倍,\n已经修正为{max_gearing}倍", width=300))
            gearing = max_gearing
        if gearing < -max_gearing:
            await bot.send(await to_pic_msg(
                f"最高杠杆只能到-{max_gearing}倍,\n已经修正为-{max_gearing}倍", width=300))
            gearing = -max_gearing
    result = await buy_stock_action(event.user_id, event.group_id, stock_id, gearing, cost)
    await bot.send(await to_pic_msg(result, width=300))
    await bot.finish(await get_stock_img_(origin_stock_id, stock_id))


@sell_stock.handle()
async def _(
        event: MessageEvent,
        arg: Message = CommandArg()):
    if not isinstance(event, GroupMessageEvent):
        await sell_stock.finish(await to_pic_msg("这个游戏只能在群里玩哦"))
    msg = arg.extract_plain_text().strip().split()
    if len(msg) < 1:
        await sell_stock.finish(await to_pic_msg(
            "格式错误，请输入\n卖股票 股票代码 [仓位(不填默认为十)]\n如 卖股票 601919 10", width=300))
    stock_id = fill_stock_id(msg[0])
    if len(msg) == 1:
        percent = 10
    else:
        percent = round(float(msg[1]), 2)
    if percent > 10:
        await sell_stock.send(await to_pic_msg("不能卖十成以上的仓位哦，已经帮你全卖了"))
        percent = 10
    if percent <= 0:
        await sell_stock.finish(await to_pic_msg("卖的仓位太低了！"))
    if msg[0] == '躺平' or msg[0] == '躺平基金':  # 卖出躺平基金的特殊逻辑
        await sell_lazy_handle(buy_stock, percent, event)
        return
    result = await sell_stock_action(event.user_id, event.group_id, stock_id, percent)
    await sell_stock.send(await to_pic_msg(result, width=300))
    origin_stock_id = stock_id[2:]
    await sell_stock.finish(await get_stock_img_(origin_stock_id, stock_id))


@my_stock.handle()
async def _(event: MessageEvent, bot: Bot):
    if not isinstance(event, GroupMessageEvent):
        await my_stock.finish(await to_pic_msg("这个游戏只能在群里玩哦"))
    username = await get_username(bot, event.group_id, event.user_id)

    if Config.get_config("stock_legend", "WIN_FIT", False):
        my_stocks = await get_stock_list_action_for_win(event.user_id, event.group_id)
        await send_forward_msg_group(bot, event, "真寻炒股小助手", my_stocks if my_stocks else ["你还什么都没买呢！"])
    else:
        my_stocks = await get_stock_list_action(event.user_id, event.group_id)
        if not my_stocks:
            await sell_stock.finish(await to_pic_msg(f"{username}你还什么都没买呢！", width=300))
        txt = convert_stocks_to_md_table(username, my_stocks)
        logger.info(txt)
        await sell_stock.finish(MessageSegment.image(await md_to_pic(f"{txt}", width=1000)))


@look_stock.handle()
async def _(event: MessageEvent, bot: Bot, args: Message = CommandArg()):
    if not isinstance(event, GroupMessageEvent):
        await look_stock.finish(await to_pic_msg("这个游戏只能在群里玩哦"))

    look_qq = event.user_id
    for arg in args:
        if arg.type == "at":
            look_qq = arg.data.get("qq", "")

    username = await get_username(bot, event.group_id, look_qq)
    if Config.get_config("stock_legend", "WIN_FIT", False):
        my_stocks = await get_stock_list_action_for_win(event.user_id, event.group_id)
        await send_forward_msg_group(bot, event, "真寻炒股小助手", my_stocks if my_stocks else ["仓位是空的"])
    else:
        my_stocks = await get_stock_list_action(look_qq, event.group_id)
        if not my_stocks:
            await sell_stock.finish(await to_pic_msg(f"{username}的仓位是空的", width=300))
        txt = convert_stocks_to_md_table(username, my_stocks)
        logger.info(txt)
        await sell_stock.finish(MessageSegment.image(await md_to_pic(f"{txt}", width=1200)))


# 这是一个测试用管理员指令，不能滥用
# 没有做太多容错处理
@clear_stock.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    if not isinstance(event, GroupMessageEvent):
        await clear_stock.finish(await to_pic_msg("这个游戏只能在群里玩哦"))

    msg = arg.extract_plain_text().strip().split()
    if len(msg) < 1:
        await buy_stock.finish(await to_pic_msg("格式错误，请输入强制清仓 qq号"))
    cnt, tmp = await force_clear_action(int(msg[0]), event.group_id)
    await buy_stock.finish(await to_pic_msg(f"{msg[0]}的{cnt}仓位都被卖了:\n{tmp}", width=300))


@clear_my_stock.handle()
async def _(event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        await clear_stock.finish(await to_pic_msg("这个游戏只能在群里玩哦"))

    cnt, tmp = await force_clear_action(event.user_id, event.group_id)
    await buy_stock.finish(await to_pic_msg(f"{cnt}个仓位都被卖了:\n{tmp}", width=300))


@revert_stock.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    if not isinstance(event, GroupMessageEvent):
        await revert_stock.finish(await to_pic_msg("这个游戏只能在群里玩哦"))

    msg = arg.extract_plain_text().strip().split()
    if len(msg) < 1:
        await revert_stock.finish(await to_pic_msg("格式错误，请输入反转持仓 股票代码"))
    stock_id = fill_stock_id(msg[0])
    msg = await revert_stock_action(event.user_id, event.group_id, stock_id)
    await revert_stock.finish(await to_pic_msg(msg))


async def to_pic_msg(msg, width=300):
    return MessageSegment.image(await text_to_pic(msg, width=width))


@help_stock.handle()
async def _():
    await help_stock.finish(
        """作者：小r
说明：这个插件可以帮多年后的你省很多钱！练习到每天盈利5%+就可以去玩真正的股市了
版本：v2.1
查看是否有更新：https://github.com/RShock/zhenxun_plugin_stock_legend""")


# 躺平基金是给不会炒股的人(以及周六日)玩的基金，每天收益为1.5%(默认)
# 虽然看起来很高但是实际上30天也就1.56倍，可以接受
async def buy_lazy_handle(bot, msg, event) -> None:
    cost = 10 if len(msg) <= 1 else float(msg[1])
    await bot.finish(MessageSegment.image(
        await text_to_pic(
            await buy_lazy_stock_action(event.user_id, event.group_id, cost), width=300)))


async def sell_lazy_handle(bot, percent, event) -> None:
    tmp = await sell_lazy_stock_action(event.user_id, event.group_id, percent)
    await bot.finish(await to_pic_msg(tmp, width=400))


@query_stock.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    if not isinstance(event, GroupMessageEvent):
        await revert_stock.finish(await to_pic_msg("这个游戏只能在群里玩哦"))

    msg = arg.extract_plain_text().strip().split()
    if len(msg) < 1:
        await revert_stock.finish(await to_pic_msg("格式错误，请输入查看股票 股票/基金代码", width=300))
    await query_stock.send(await to_pic_msg("正在查询...", width=200))
    stock_id = fill_stock_id(msg[0])
    await query_stock.finish(await get_stock_img_(msg[0], stock_id))


async def get_stock_img_(origin_stock_id, stock_id):
    if Config.get_config("stock_legend", "IMAGE_MODE", 2) == 2:
        return await get_stock_img_v2(origin_stock_id, stock_id)
    else:
        return await get_stock_img(origin_stock_id, stock_id)


async def get_username(bot, group_id, user_id):
    user_name = await bot.get_group_member_info(group_id=group_id, user_id=user_id)
    return user_name["card"] or user_name["nickname"]
