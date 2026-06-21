import re

from nonebot import get_driver
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    MessageEvent,
    MessageSegment,
)
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Match, on_alconna
from nonebot_plugin_htmlrender import md_to_pic, text_to_pic
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.config import Config
from zhenxun.configs.utils import Command, PluginExtraData, RegisterConfig
from zhenxun.models.user_console import UserConsole
from zhenxun.services.log import logger
from zhenxun.utils.enum import GoldHandle
from zhenxun.utils.platform import PlatformUtils

from .data_source import (
    buy_lazy_stock_action,
    buy_stock_action,
    check_and_execute_orders,
    check_timeout_failed_orders,
    force_clear_action,
    get_stock_list_action,
    get_stock_list_action_for_win,
    get_stock_uid,
    revert_stock_action,
    sell_lazy_stock_action,
    sell_stock_action,
)
from .stock_model import StockOrderDB
from .utils import (
    convert_orders_to_md_table,
    convert_stocks_to_md_table,
    fill_stock_id,
    get_stock_img,
    get_stock_img_v2,
    get_stock_img_sina,
    get_stock_img_netease,
    get_stock_img_tencent,
    get_stock_img_auto,
    is_a_stock,
    send_forward_msg_group,
)

__plugin_meta__ = PluginMetadata(
    name="股海风云",
    description="谁才是股市传奇？",
    usage="""
    简单股市小游戏，T+0 可做空 保证金无限 最高10倍杠杆 0手续费

    指令：
    买股票+代码+金额+杠杆倍数(可不填) 买入股票 例：买股票 600888 10000  (买入10000金币的仓位)
    卖股票+代码+仓位百分制 卖出股票 例：卖股票 600888 10 (卖出10层仓位，全卖可以省略这个参数)
        也支持使用仓位来买股票，如果什么都不填（比如只发送'买股票600888'）会默认使用满仓满杠杆
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
    A: 可以先输入'买入躺平基金 x' x为仓位数 最高10 可不填
    
    Q: 股票代码是从哪里来的？
    A: 需要从现实中的股市提取
    
    Q: 为什么允许非整数的手数/是否应该加入汇率
    A: 当基金玩的
    ————————————————
    强制清仓+qq号(不是at是qq号)  管理专用指令，爆仓人不愿意清仓就对他使用这个吧
    """.strip(),
    extra=PluginExtraData(
        author="XiaoR",
        version="3.0",
        commands=[
            Command(command="买股票", params=["代码", "金额", "杠杆"]),
            Command(command="卖股票", params=["代码", "仓位"]),
            Command(command="我的持仓"),
            Command(command="强制清仓"),
        ],
        menu_type="群内小游戏",
        configs=[
            RegisterConfig(
                key="最大杠杆比率",
                value=5,
                help="最大杠杆比率",
                default_value=5,
                type=int,
            ),
            RegisterConfig(
                key="躺平基金每日收益",
                value=0.015,
                help="躺平基金每日收益",
                default_value=0.015,
                type=float,
            ),
            RegisterConfig(
                key="WIN_FIT",
                value=False,
                help="如果我的持仓功能报错，且看了issue还是改不好，就把这个改成true",
                default_value=False,
                type=bool,
            ),
            RegisterConfig(
                key="跨群合并账户",
                value=True,
                help="开启后同一QQ在不同群使用同一个股海风云账户，并自动兼容旧群账户数据",
                default_value=True,
                type=bool,
            ),
            RegisterConfig(
                key="股票提示图模式",
                value=3,
                help="1:百度股市通 2:东方财富(可能遇到验证码) 3:新浪财经(推荐,速度快) 4:网易财经 5:腾讯财经 6:自动选择(依次尝试新浪>网易>腾讯)",
                default_value=3,
                type=int,
            ),
        ],
    ).to_dict(),
)

buy_stock = on_alconna(
    Alconna("买股票", Args["stock_code?", str]["amount?", str]["gearing?", str]),
    priority=5,
    block=True,
)

buy_stock.shortcut(
    r"(买股票|买入|建仓|买入股票)(?P<stock_code>\S+)(\s+(?P<amount>\S+))?(\s+(?P<gearing>\S+))?",
    arguments=["{stock_code}", "{amount}", "{gearing}"],
    prefix=True,
)

sell_stock = on_alconna(
    Alconna("卖股票", Args["stock_code?", str]["percent?", str]),
    priority=5,
    block=True,
)

sell_stock.shortcut(
    r"(卖股票|卖出|平仓|卖出股票)(?P<stock_code>\S+)(\s+(?P<percent>\S+))?",
    arguments=["{stock_code}", "{percent}"],
    prefix=True,
)

my_stock = on_alconna(
    Alconna("我的持仓"),
    priority=5,
    block=True,
)

my_stock.shortcut(
    r"(我的持仓|我的股票|我的仓位|我的持股)",
    arguments=[],
    prefix=True,
)

clear_stock = on_alconna(
    Alconna("强制清仓", Args["qq_number?", str]),
    priority=5,
    permission=SUPERUSER,
    block=True,
)

clear_stock.shortcut(
    r"强制清仓(?P<qq_number>\d+)?",
    arguments=["{qq_number}"],
    prefix=True,
)

cancel_order = on_alconna(
    Alconna("取消委托"),
    priority=5,
    permission=SUPERUSER,
    block=True,
)

cancel_order.shortcut(
    r"取消委托",
    arguments=[],
    prefix=True,
)

look_stock = on_alconna(
    Alconna("查看持仓"),
    priority=5,
    block=True,
)

look_stock.shortcut(
    r"(查看持仓|偷看持仓|他的持仓)",
    arguments=[],
    prefix=True,
)

revert_stock = on_alconna(
    Alconna("反转持仓", Args["stock_code?", str]),
    priority=5,
    block=True,
)

revert_stock.shortcut(
    r"反转持仓(?P<stock_code>\S+)?",
    arguments=["{stock_code}"],
    prefix=True,
)

help_stock = on_alconna(
    Alconna("关于股海风云"),
    priority=5,
    block=True,
)

query_stock = on_alconna(
    Alconna("查看股票", Args["stock_code?", str]),
    priority=5,
    block=True,
)

query_stock.shortcut(
    r"查看股票(?P<stock_code>\S+)?",
    arguments=["{stock_code}"],
    prefix=True,
)

clear_my_stock = on_alconna(
    Alconna("清仓"),
    priority=5,
    block=True,
)

plugin_name = re.split(r"[\\/]", __file__)[-2]

# 启动定时任务检查委托单
driver = get_driver()


@driver.on_startup
async def _():
    import asyncio

    await StockOrderDB.migrate_all_legacy_group_ids()

    async def check_orders_task():
        logger.info("[委托定时任务] 委托检查任务已启动，每60秒检查一次")
        while True:
            try:
                await check_and_execute_orders()
            except Exception as e:
                logger.error(f"[委托定时任务] 检查委托单失败: {e}")
                import traceback

                logger.error(f"[委托定时任务] 详细错误:\n{traceback.format_exc()}")
            await asyncio.sleep(60)

    async def check_timeout_task():
        logger.info("[超时委托定时任务] 超时委托检查任务已启动，每60秒检查一次")
        while True:
            try:
                await check_timeout_failed_orders()
            except Exception as e:
                logger.error(f"[超时委托定时任务] 检查超时委托单失败: {e}")
                import traceback

                logger.error(f"[超时委托定时任务] 详细错误:\n{traceback.format_exc()}")
            await asyncio.sleep(60)

    asyncio.create_task(check_orders_task())
    asyncio.create_task(check_timeout_task())


@buy_stock.handle()
async def _(
    bot: Bot,
    event: MessageEvent,
    session: Uninfo,
    stock_code: Match[str],
    amount: Match[str],
    gearing: Match[str],
):
    if not isinstance(event, GroupMessageEvent):
        await buy_stock.finish(await to_pic_msg("这个游戏只能在群里玩哦"))

    msg = []
    if stock_code.available:
        msg.append(stock_code.result)
    if amount.available:
        msg.append(amount.result)
    if gearing.available:
        msg.append(gearing.result)

    if len(msg) < 1:
        await buy_stock.finish(
            await to_pic_msg(
                "格式错误，请输入\n买股票 股票代码 金额 杠杆层数(可选)\n如 买股票 600888 1000 5",
                width=300,
            )
        )
    if msg[0] == "躺平" or msg[0] == "躺平基金":
        await buy_lazy_handle(buy_stock, msg, event, session)
        return
    await buy_handle(bot, msg, event, session)


async def buy_handle(bot, msg, event, session: Uninfo):
    if len(msg) == 1:
        cost = 10  # 10成仓位
    else:
        cost = int(msg[1])
    stock_id = fill_stock_id(msg[0])
    origin_stock_id = stock_id[2:]
    max_gearing = round(float(Config.get_config(plugin_name, "最大杠杆比率", 5)), 1)
    gearing = 0
    # 第三个参数是杠杆
    # 最大杠杆比率
    if cost == 0 and len(msg) == 2:  # 专门用来看行情，但是加上杠杆参数就是改杠杆了
        await buy_stock.send(await to_pic_msg("你看了看，但没有买", width=300))
        await PlatformUtils.send_message(
            bot,
            None,
            str(event.group_id),
            await get_stock_img_(origin_stock_id, stock_id),
        )
    if cost < 0:
        if cost < -max_gearing:
            await buy_stock.finish(
                await to_pic_msg("想做空的话\n请使用负数的杠杆率哦", width=300)
            )
        else:  # 这个人输入了买股票xxxx -10 (-10应该是杠杆倍率而不是cost)
            gearing = cost
            cost = 10
    if len(msg) == 3:
        gearing = float(msg[2])
        if gearing > max_gearing:
            if -max_gearing <= cost <= max_gearing:  # 防呆，这人把输入参数顺序搞反了
                cost, gearing = gearing, cost
                await buy_stock.send(
                    await to_pic_msg(
                        "你的杠杆和花费金币参数顺序反了，已经帮你修好了", width=300
                    )
                )
            else:
                await buy_stock.send(
                    await to_pic_msg(
                        f"最高杠杆只能到{max_gearing}倍,\n已经修正为{max_gearing}倍",
                        width=300,
                    )
                )
            gearing = max_gearing
        if gearing < -max_gearing:
            await buy_stock.send(
                await to_pic_msg(
                    f"最高杠杆只能到-{max_gearing}倍,\n已经修正为-{max_gearing}倍",
                    width=300,
                )
            )
            gearing = -max_gearing
    result = await buy_stock_action(
        int(session.user.id),
        event.group_id,
        stock_id,
        float(gearing),
        int(cost),
        0,
        PlatformUtils.get_platform(session),
    )
    await buy_stock.send(await to_pic_msg(result, width=300))
    await PlatformUtils.send_message(
        bot, None, str(event.group_id), await get_stock_img_(origin_stock_id, stock_id)
    )


@sell_stock.handle()
async def _(
    bot: Bot,
    event: MessageEvent,
    session: Uninfo,
    stock_code: Match[str],
    percent: Match[str],
):
    if not isinstance(event, GroupMessageEvent):
        await sell_stock.finish(await to_pic_msg("这个游戏只能在群里玩哦"))

    msg = []
    if stock_code.available:
        msg.append(stock_code.result)
    if percent.available:
        msg.append(percent.result)

    if len(msg) < 1:
        await sell_stock.finish(
            await to_pic_msg(
                "格式错误，请输入\n卖股票 股票代码 [仓位(不填默认为十)]\n如 卖股票 601919 10",
                width=300,
            )
        )
    stock_id = fill_stock_id(msg[0])
    if len(msg) == 1:
        sell_percent = 10
    else:
        sell_percent = round(float(msg[1]), 2)
    if sell_percent > 10:
        await sell_stock.send(
            await to_pic_msg("不能卖十成以上的仓位哦，已经帮你全卖了")
        )
        sell_percent = 10
    if sell_percent <= 0:
        await sell_stock.finish(await to_pic_msg("卖的仓位太低了！"))
    if msg[0] == "躺平" or msg[0] == "躺平基金":
        await sell_lazy_handle(buy_stock, sell_percent, event, session)
        return
    result = await sell_stock_action(
        int(session.user.id),
        event.group_id,
        stock_id,
        sell_percent,
        0,
        PlatformUtils.get_platform(session),
    )
    await sell_stock.send(await to_pic_msg(result, width=300))
    origin_stock_id = stock_id[2:]
    await PlatformUtils.send_message(
        bot, None, str(event.group_id), await get_stock_img_(origin_stock_id, stock_id)
    )


@my_stock.handle()
async def _(event: MessageEvent, bot: Bot):
    if not isinstance(event, GroupMessageEvent):
        await my_stock.finish(await to_pic_msg("这个游戏只能在群里玩哦"))
    username = await get_username(bot, event.group_id, event.user_id)

    if Config.get_config(plugin_name, "WIN_FIT", False):
        my_stocks = await get_stock_list_action_for_win(event.user_id, event.group_id)
        await send_forward_msg_group(
            bot,
            event,
            "真寻炒股小助手",
            my_stocks if my_stocks else ["你还什么都没买呢！"],
        )
    else:
        my_stocks, my_orders = await get_stock_list_action(
            event.user_id, event.group_id
        )
        txt = convert_stocks_to_md_table(username, my_stocks)

        if my_orders:
            txt += "\n\n" + convert_orders_to_md_table(my_orders)

        if not my_stocks and not my_orders:
            await my_stock.finish(
                await to_pic_msg(f"{username}你还什么都没买呢！", width=300)
            )
        await my_stock.finish(
            MessageSegment.image(await md_to_pic(f"{txt}", width=1000))
        )


@look_stock.handle()
async def _(event: MessageEvent, bot: Bot):
    if not isinstance(event, GroupMessageEvent):
        await look_stock.finish(await to_pic_msg("这个游戏只能在群里玩哦"))

    look_qq = event.user_id
    username = await get_username(bot, event.group_id, look_qq)
    if Config.get_config(plugin_name, "WIN_FIT", False):
        my_stocks = await get_stock_list_action_for_win(look_qq, event.group_id)
        await send_forward_msg_group(
            bot, event, "真寻炒股小助手", my_stocks if my_stocks else ["仓位是空的"]
        )
    else:
        my_stocks, my_orders = await get_stock_list_action(look_qq, event.group_id)
        txt = convert_stocks_to_md_table(username, my_stocks)

        if my_orders:
            txt += "\n\n" + convert_orders_to_md_table(my_orders)

        if not my_stocks and not my_orders:
            await look_stock.finish(
                await to_pic_msg(f"{username}的仓位是空的", width=300)
            )
        logger.info(txt)
        await look_stock.finish(
            MessageSegment.image(await md_to_pic(f"{txt}", width=1200))
        )


# 这是一个测试用管理员指令，不能滥用
# 没有做太多容错处理
@clear_stock.handle()
async def _(event: MessageEvent, qq_number: Match[str]):
    if not isinstance(event, GroupMessageEvent):
        await clear_stock.finish(await to_pic_msg("这个游戏只能在群里玩哦"))

    if not qq_number.available:
        await clear_stock.finish(await to_pic_msg("格式错误，请输入强制清仓 qq号"))

    cnt, tmp = await force_clear_action(int(qq_number.result), event.group_id)
    await clear_stock.finish(
        await to_pic_msg(f"{qq_number.result}的{cnt}仓位都被卖了:\n{tmp}", width=300)
    )


@cancel_order.handle()
async def _(event: MessageEvent, session: Uninfo):
    if not isinstance(event, GroupMessageEvent):
        await cancel_order.finish(await to_pic_msg("这个游戏只能在群里玩哦"))

    uid = await get_stock_uid(event.user_id, event.group_id)
    count, refund = await StockOrderDB.cancel_user_orders(uid)

    if count == 0:
        await cancel_order.finish(await to_pic_msg("你没有待执行的委托单", width=300))

    if refund > 0:
        await UserConsole.add_gold(
            str(event.user_id), int(refund), GoldHandle.GET, session
        )

    await cancel_order.finish(
        await to_pic_msg(
            f"已取消 {count} 个委托单\n返还金额: {refund:.0f} 金币", width=300
        )
    )


@clear_my_stock.handle()
async def _(event: MessageEvent):
    if not isinstance(event, GroupMessageEvent):
        await clear_my_stock.finish(await to_pic_msg("这个游戏只能在群里玩哦"))

    cnt, tmp = await force_clear_action(event.user_id, event.group_id)
    await clear_my_stock.finish(
        await to_pic_msg(f"{cnt}个仓位都被卖了:\n{tmp}", width=300)
    )


@revert_stock.handle()
async def _(event: MessageEvent, stock_code: Match[str]):
    if not isinstance(event, GroupMessageEvent):
        await revert_stock.finish(await to_pic_msg("这个游戏只能在群里玩哦"))

    if not stock_code.available:
        await revert_stock.finish(await to_pic_msg("格式错误，请输入反转持仓 股票代码"))

    stock_id = fill_stock_id(stock_code.result)
    msg = await revert_stock_action(event.user_id, event.group_id, stock_id)
    await revert_stock.finish(await to_pic_msg(msg))


async def to_pic_msg(msg, width=300):
    return MessageSegment.image(await text_to_pic(msg, width=width))


@help_stock.handle()
async def _():
    await help_stock.finish(
        """作者：小r
说明：这个插件可以帮多年后的你省很多钱！练习到每天盈利5%+就可以去玩真正的股市了
版本：v2.4
查看是否有更新：https://github.com/RShock/zhenxun_plugin_stock_legend"""
    )


# 躺平基金是给不会炒股的人(以及周六日)玩的基金，每天收益为1.5%(默认)
# 虽然看起来很高但是实际上30天也就1.56倍，可以接受
async def buy_lazy_handle(bot, msg, event, session: Uninfo) -> None:
    cost = 10 if len(msg) <= 1 else float(msg[1])
    await bot.finish(
        MessageSegment.image(
            await text_to_pic(
                await buy_lazy_stock_action(
                    int(session.user.id),
                    event.group_id,
                    cost,
                    PlatformUtils.get_platform(session),
                ),
                width=300,
            )
        )
    )


async def sell_lazy_handle(bot, percent, event, session: Uninfo) -> None:
    tmp = await sell_lazy_stock_action(
        int(session.user.id),
        event.group_id,
        percent,
        PlatformUtils.get_platform(session),
    )
    await bot.finish(await to_pic_msg(tmp, width=400))


@query_stock.handle()
async def _(bot: Bot, event: MessageEvent, stock_code: Match[str]):
    if not isinstance(event, GroupMessageEvent):
        await query_stock.finish(await to_pic_msg("这个游戏只能在群里玩哦"))

    if not stock_code.available:
        await query_stock.finish(
            await to_pic_msg("格式错误，请输入查看股票 股票/基金代码", width=300)
        )

    await query_stock.send(await to_pic_msg("正在查询...", width=200))
    stock_id = fill_stock_id(stock_code.result)
    await PlatformUtils.send_message(
        bot,
        None,
        str(event.group_id),
        await get_stock_img_(stock_code.result, stock_id),
    )


async def get_stock_img_(origin_stock_id, stock_id):
    mode = Config.get_config(plugin_name, "股票提示图模式", 3)
    if mode == 1:
        return await get_stock_img(origin_stock_id, stock_id)
    elif mode == 2:
        return await get_stock_img_v2(origin_stock_id, stock_id)
    elif mode == 3:
        return await get_stock_img_sina(origin_stock_id, stock_id)
    elif mode == 4:
        return await get_stock_img_netease(origin_stock_id, stock_id)
    elif mode == 5:
        return await get_stock_img_tencent(origin_stock_id, stock_id)
    elif mode == 6:
        return await get_stock_img_auto(origin_stock_id, stock_id)
    else:
        return await get_stock_img_sina(origin_stock_id, stock_id)


async def get_username(bot, group_id, user_id):
    user_name = await bot.get_group_member_info(group_id=group_id, user_id=user_id)
    return user_name["card"] or user_name["nickname"]
