from services.log import logger
from services.db_context import db
from datetime import datetime
from typing import List


class StockLogDB(db.Model):
    __tablename__ = "stock_game_log"

    id = db.Column(db.Integer(), primary_key=True)
    # 角色ID
    uid = db.Column(db.String(), nullable=False)
    # 股票ID
    stock_id = db.Column(db.String(), nullable=False)
    # 股数
    number = db.Column(db.Numeric(scale=3, asdecimal=False))
    # 操作(0-卖 1-买)
    action = db.Column(db.Integer(), nullable=False)
    # 买入价格
    price = db.Column(db.Numeric(scale=3, asdecimal=False), nullable=True)
    # 买入成本
    cost = db.Column(db.Numeric(scale=3, asdecimal=False), nullable=True)
    # 购买时间
    action_time = db.Column(db.DateTime(), default=datetime.now)
    # 杠杆倍率（默认1，负数为做空）
    gearing = db.Column(db.Numeric(scale=3, asdecimal=False), nullable=True)
    # 卖出价格
    sell_price = db.Column(db.Numeric(scale=3, asdecimal=False), nullable=True)
    # 卖出成本
    get = db.Column(db.Numeric(scale=3, asdecimal=False), nullable=True)
    # 净利润（仅限于卖使用）
    profit = db.Column(db.Numeric(scale=3, asdecimal=False), nullable=True)

    @classmethod
    async def buy_stock_log(
            cls,
            uid: str,
            stock_id: str,
            gearing: float,
            number: float,
            price: float,
            cost: float,
            buy_time: datetime
    ) -> None:
        try:
            async with db.transaction():
                await cls.create(
                    uid=uid, stock_id=stock_id, gearing=gearing, number=number, cost=cost, action=1, price=price,
                    action_time=buy_time
                )
        except Exception as e:
            logger.info(f"购买日志股票数据库问题 {type(e)}: {e}")

    @classmethod
    async def sell_stock_log(
            cls,
            uid: str,
            stock_id: str,
            number: float,
            price: float,
            get: float,
            profit: float,
    ) -> None:
        try:
            async with db.transaction():
                await cls.create(
                    uid=uid, stock_id=stock_id, number=number, get=get,
                    sell_price=price, action=0, profit=profit
                )
        except Exception as e:
            logger.info(f"卖日志股票数据库问题 {type(e)}: {e}")
