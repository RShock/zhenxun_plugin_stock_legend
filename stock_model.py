from services.log import logger
from services.db_context import db
from datetime import datetime
from typing import List


class StockDB(db.Model):
    __tablename__ = "stock_game"

    id = db.Column(db.Integer(), primary_key=True)
    # 角色ID
    uid = db.Column(db.String(), nullable=False)
    # 股票ID
    stock_id = db.Column(db.String(), nullable=False)
    # 股数
    number = db.Column(db.Numeric(scale=3, asdecimal=False))
    # 购买时间
    buy_time = db.Column(db.DateTime(), default=datetime.now)
    # 杠杆倍率（默认1，负数为做空）
    gearing = db.Column(db.Numeric(scale=3, asdecimal=False), default=1)
    # 成本
    cost = db.Column(db.Numeric(scale=3, asdecimal=False))

    @classmethod
    async def get_stock_by_uid_and_stock_id(cls, uid, stock_id):
        return await StockDB.query.where(StockDB.uid == uid and StockDB.stock_id == stock_id) \
            .with_for_update().gino.first()

    @classmethod
    async def buy_stock(
            cls,
            uid: str,
            stock_id: str,
            gearing: float,
            number: float,
            cost: float
    ) -> "StockDB":
        try:
            async with db.transaction():
                query = await StockDB.query.where(StockDB.uid == uid).where(StockDB.stock_id == stock_id) \
                    .with_for_update().gino.first()
                if not query:
                    logger.info(f"第一次买")
                    await cls.create(
                        uid=uid, stock_id=stock_id, gearing=gearing, number=number, cost=cost
                    )
                else:
                    logger.info(f"已经买过了")
                    await query.update(
                        number=number + query.number, cost=cost + query.cost
                    ).apply()
                return await StockDB.query.where(StockDB.uid == uid).where(StockDB.stock_id == stock_id) \
                    .gino.first()
        except Exception as e:
            logger.info(f"购买股票数据库问题 {type(e)}: {e}")

    @classmethod
    async def sell_stock(
            cls,
            uid: str,
            stock_id: str,
            percent: float
    ) -> None:
        try:
            async with db.transaction():
                query = await StockDB.query.where(StockDB.uid == uid).where(StockDB.stock_id == stock_id) \
                    .with_for_update().gino.first()
                if not query:
                    logger.error(f"错误 这个股票不存在")
                else:
                    logger.info(f"正在卖股票")
                    if percent != 10:
                        number = query.number * (1 - percent / 10)
                        cost = query.cost * (1 - percent / 10)
                        await query.update(
                            number=number, cost=cost
                        ).apply()
                    else:
                        await query.delete()
        except Exception as e:
            logger.info(f"销售股票数据库问题 {type(e)}: {e}")

    # 查股票 只能查不能修改哦
    @classmethod
    async def get_stock(
            cls,
            uid: str,
            stock_id: str
    ) -> "StockDB":
        try:
            async with db.transaction():
                return await StockDB.query.where(StockDB.uid == uid).where(StockDB.stock_id == stock_id).gino.first()
        except Exception as e:
            logger.info(f"单个查询股票数据库问题 {type(e)}: {e}")

    @classmethod
    async def get_my_stock(
            cls,
            uid: str,
    ) -> List["StockDB"]:
        try:
            async with db.transaction():
                return await StockDB.query.where(StockDB.uid == uid).gino.all()
        except Exception as e:
            logger.info(f"单个查询股票数据库问题 {type(e)}: {e}")


    # 返回值是应该给的钱
    @classmethod
    async def clear_stock_by_id(
            cls,
            uid: str,
    ) -> None:
        return None


    # 返回值是应该给的钱
    @classmethod
    async def get_stocks_by_uid(
            cls,
            uid: str,
    ) -> List["StockDB"]:
        try:
            async with db.transaction():
                return await StockDB.query.where(StockDB.uid == uid).gino.all()
        except Exception as e:
            logger.info(f"批量查询股票数据库问题 {type(e)}: {e}")

