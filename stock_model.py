import traceback

from pydantic.types import Decimal

from services import Model
from services.log import logger
from datetime import datetime
from typing import List
from tortoise import fields

from tortoise.contrib.pydantic import pydantic_model_creator
from tortoise.transactions import in_transaction


class StockDB(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    uid = fields.CharField(max_length=255, null=False)
    stock_id = fields.CharField(max_length=255, null=False)
    number = fields.DecimalField(max_digits=10,decimal_places=3, null=True)
    buy_time = fields.DatetimeField(auto_now_add=True)
    gearing = fields.DecimalField(max_digits=10,  decimal_places=3,null=True, default=1)
    cost = fields.DecimalField(max_digits=10, decimal_places=3,null=True)

    class Meta:
        table = "stock_game"
        table_description = "股海风云·股票表"

    # @classmethod
    # async def get_stock_by_uid_and_stock_id(cls, uid, stock_id):
    #     async with in_transaction() as conn:
    #         return await cls.filter(uid=uid, stock_id=stock_id).with_for_update().first()

    @classmethod
    async def buy_stock(
            cls,
            uid: str,
            stock_id: str,
            gearing: float,
            number: Decimal,
            cost: Decimal
    ) -> "StockDB":
        try:
            query = await cls.filter(uid=uid, stock_id=stock_id).first()
            if not query:
                logger.info(f"第一次买")
                await cls.create(
                    uid=uid, stock_id=stock_id, gearing=gearing, number=number, cost=cost
                )
            else:
                logger.info(f"已经买过了")
                query.number = number + query.number
                query.cost = cost + query.cost
                await query.save()
            return await cls.filter(uid=uid, stock_id=stock_id).first()
        except Exception as e:
            logger.info(f"购买股票数据库问题 {type(e)}: {e}")
            raise e

    @classmethod
    async def sell_stock(
            cls,
            uid: str,
            stock_id: str,
            percent: float
    ) -> None:
        try:
            query = await cls.filter(uid=uid, stock_id=stock_id).first()
            if not query:
                logger.error(f"错误 这个股票不存在")
            else:
                logger.info(f"正在卖股票")
                if percent != 10:
                    query.number = query.number * (1 - Decimal(percent) / 10)
                    query.cost = query.cost * (1 - Decimal(percent) / 10)
                    await query.save()
                else:
                    await query.delete()
        except Exception as e:
            # do something with the traceback string
            logger.info(f"销售股票数据库问题 {type(e)}: {e}")
            raise e


    @classmethod
    async def get_stock(
            cls,
            uid: str,
            stock_id: str
    ) -> "StockDB":
        try:
            return await cls.filter(uid=uid, stock_id=stock_id).first()
        except Exception as e:
            logger.info(f"单个查询股票数据库问题 {type(e)}: {e}")
            raise e

    @classmethod
    async def get_my_stock(
            cls,
            uid: str,
    ) -> List["StockDB"]:
        try:
            return await cls.filter(uid=uid).all()
        except Exception as e:
            logger.info(f"单个查询股票数据库问题 {type(e)}: {e}")
            raise e


    @classmethod
    async def clear_stock_by_id(
            cls,
            uid: str,
            stock_id: str
    ) -> None:
        try:
            await cls.filter(uid=uid, stock_id=stock_id).delete()
        except Exception as e:
            logger.info(f"删除指定股票问题 {type(e)}: {e}")
            raise e

    @classmethod
    async def get_stocks_by_uid(
            cls,
            uid: str,
    ) -> List["StockDB"]:
        try:
            return await cls.filter(uid=uid).all()
        except Exception as e:
            logger.info(f"批量查询股票数据库问题 {type(e)}: {e}")
            raise e

# StockDB_Pydantic = pydantic_model_creator(StockDB, name="StockDB")
#
# class StockDB(db.Model):
#     __tablename__ = "stock_game"
#
#     id = db.Column(db.Integer(), primary_key=True)
#     # 角色ID
#     uid = db.Column(db.String(), nullable=False)
#     # 股票ID
#     stock_id = db.Column(db.String(), nullable=False)
#     # 股数
#     number = db.Column(db.Numeric(scale=3, asdecimal=False))
#     # 购买时间
#     buy_time = db.Column(db.DateTime(), default=datetime.now)
#     # 杠杆倍率（默认1，负数为做空）
#     gearing = db.Column(db.Numeric(scale=3, asdecimal=False), default=1)
#     # 成本
#     cost = db.Column(db.Numeric(scale=3, asdecimal=False))
#
#     @classmethod
#     async def get_stock_by_uid_and_stock_id(cls, uid, stock_id):
#         return await StockDB.query.where(StockDB.uid == uid and StockDB.stock_id == stock_id) \
#             .with_for_update().gino.first()
#
#     @classmethod
#     async def buy_stock(
#             cls,
#             uid: str,
#             stock_id: str,
#             gearing: float,
#             number: float,
#             cost: float
#     ) -> "StockDB":
#         try:
#             async with db.transaction():
#                 query = await StockDB.query.where(StockDB.uid == uid).where(StockDB.stock_id == stock_id) \
#                     .with_for_update().gino.first()
#                 if not query:
#                     logger.info(f"第一次买")
#                     await cls.create(
#                         uid=uid, stock_id=stock_id, gearing=gearing, number=number, cost=cost
#                     )
#                 else:
#                     logger.info(f"已经买过了")
#                     await query.update(
#                         number=number + query.number, cost=cost + query.cost
#                     ).apply()
#                 return await StockDB.query.where(StockDB.uid == uid).where(StockDB.stock_id == stock_id) \
#                     .gino.first()
#         except Exception as e:
#             logger.info(f"购买股票数据库问题 {type(e)}: {e}")
#
#     @classmethod
#     async def sell_stock(
#             cls,
#             uid: str,
#             stock_id: str,
#             percent: float
#     ) -> None:
#         try:
#             async with db.transaction():
#                 query = await StockDB.query.where(StockDB.uid == uid).where(StockDB.stock_id == stock_id) \
#                     .with_for_update().gino.first()
#                 if not query:
#                     logger.error(f"错误 这个股票不存在")
#                 else:
#                     logger.info(f"正在卖股票")
#                     if percent != 10:
#                         number = query.number * (1 - percent / 10)
#                         cost = query.cost * (1 - percent / 10)
#                         await query.update(
#                             number=number, cost=cost
#                         ).apply()
#                     else:
#                         await query.delete()
#         except Exception as e:
#             logger.info(f"销售股票数据库问题 {type(e)}: {e}")
#
#     # 查股票 只能查不能修改哦
#     @classmethod
#     async def get_stock(
#             cls,
#             uid: str,
#             stock_id: str
#     ) -> "StockDB":
#         try:
#             async with db.transaction():
#                 return await StockDB.query.where(StockDB.uid == uid).where(StockDB.stock_id == stock_id).gino.first()
#         except Exception as e:
#             logger.info(f"单个查询股票数据库问题 {type(e)}: {e}")
#
#     @classmethod
#     async def get_my_stock(
#             cls,
#             uid: str,
#     ) -> List["StockDB"]:
#         try:
#             async with db.transaction():
#                 return await StockDB.query.where(StockDB.uid == uid).gino.all()
#         except Exception as e:
#             logger.info(f"单个查询股票数据库问题 {type(e)}: {e}")
#
#
#     @classmethod
#     async def clear_stock_by_id(
#             cls,
#             uid: str,
#             stock_id: str
#     ) -> None:
#         try:
#             async with db.transaction():
#                 return await StockDB.delete.where((StockDB.uid == uid) & (StockDB.stock_id == stock_id)).gino.status()
#         except Exception as e:
#             logger.info(f"删除指定股票问题 {type(e)}: {e}")
#
#
#     @classmethod
#     async def get_stocks_by_uid(
#             cls,
#             uid: str,
#     ) -> List["StockDB"]:
#         try:
#             async with db.transaction():
#                 return await StockDB.query.where(StockDB.uid == uid).gino.all()
#         except Exception as e:
#             logger.info(f"批量查询股票数据库问题 {type(e)}: {e}")
#
