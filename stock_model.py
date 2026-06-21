from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from tortoise import fields

from zhenxun.services.db_context import Model
from zhenxun.services.log import logger


def build_stock_account_key(user_id: str | int) -> str:
    return str(user_id)


def parse_stock_account_key(uid: str) -> tuple[int, int | None]:
    user_id, _, group_id = uid.partition(":")
    return int(user_id), int(group_id) if group_id else None


class StockDB(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    uid = fields.CharField(max_length=255, null=False)
    stock_id = fields.CharField(max_length=255, null=False)
    number = fields.DecimalField(max_digits=20, decimal_places=3, null=True)
    buy_time = fields.DatetimeField(auto_now_add=True)
    gearing = fields.DecimalField(max_digits=10, decimal_places=3, null=True, default=1)
    cost = fields.DecimalField(max_digits=20, decimal_places=3, null=True)

    class Meta(Model.Meta):
        table = "stock_game"
        table_description = "股海风云·股票表"

    @staticmethod
    def _run_script():
        """迁移 number 和 cost 列从 NUMERIC(10,3) 到 NUMERIC(20,3)"""
        return [
            """ALTER TABLE stock_game ALTER COLUMN number TYPE NUMERIC(20, 3);""",
            """ALTER TABLE stock_game ALTER COLUMN cost TYPE NUMERIC(20, 3);""",
        ]

    # @classmethod
    # async def get_stock_by_uid_and_stock_id(cls, uid, stock_id):
    #     async with in_transaction() as conn:
    #         return await cls.filter(uid=uid, stock_id=stock_id).with_for_update().first()

    @classmethod
    async def merge_legacy_user_stocks(cls, user_id: str | int) -> None:
        user_uid = build_stock_account_key(user_id)
        legacy_stocks = [
            stock
            for stock in await cls.filter(uid__startswith=f"{user_uid}:").all()
            if stock.uid.partition(":")[0] == user_uid
        ]
        for legacy_stock in legacy_stocks:
            target_stock = await cls.filter(
                uid=user_uid, stock_id=legacy_stock.stock_id
            ).first()
            if not target_stock:
                legacy_stock.uid = user_uid
                await legacy_stock.save()
                continue
            should_keep_gearing = legacy_stock.cost > target_stock.cost
            target_stock.number += legacy_stock.number
            target_stock.cost += legacy_stock.cost
            if should_keep_gearing:
                target_stock.gearing = legacy_stock.gearing
            await target_stock.save()
            await legacy_stock.delete()

    @classmethod
    async def buy_stock(
        cls, uid: str, stock_id: str, gearing: float, number: Decimal, cost: Decimal
    ) -> "StockDB | None":
        try:
            query = await cls.filter(uid=uid, stock_id=stock_id).first()
            if not query:
                logger.info("第一次买")
                await cls.create(
                    uid=uid,
                    stock_id=stock_id,
                    gearing=gearing,
                    number=number,
                    cost=cost,
                )
            else:
                logger.info("已经买过了")
                query.number = number + query.number
                query.cost = cost + query.cost
                await query.save()
            return await cls.filter(uid=uid, stock_id=stock_id).first()
        except Exception as e:
            logger.info(f"购买股票数据库问题 {type(e)}: {e}")
            raise e

    @classmethod
    async def sell_stock(cls, uid: str, stock_id: str, percent: float) -> None:
        try:
            query = await cls.filter(uid=uid, stock_id=stock_id).first()
            if not query:
                logger.error("错误 这个股票不存在")
            else:
                logger.info("正在卖股票")
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
    async def get_stock(cls, uid: str, stock_id: str) -> "StockDB | None":
        try:
            return await cls.filter(uid=uid, stock_id=stock_id).first()
        except Exception as e:
            logger.info(f"单个查询股票数据库问题 {type(e)}: {e}")
            raise e

    @classmethod
    async def get_my_stock(
        cls,
        uid: str,
    ) -> Sequence["StockDB"]:
        try:
            return await cls.filter(uid=uid).all()
        except Exception as e:
            logger.info(f"单个查询股票数据库问题 {type(e)}: {e}")
            raise e

    @classmethod
    async def clear_stock_by_id(cls, uid: str, stock_id: str) -> None:
        try:
            await cls.filter(uid=uid, stock_id=stock_id).delete()
        except Exception as e:
            logger.info(f"删除指定股票问题 {type(e)}: {e}")
            raise e

    @classmethod
    async def get_stocks_by_uid(
        cls,
        uid: str,
    ) -> Sequence["StockDB"]:
        try:
            return await cls.filter(uid=uid).all()
        except Exception as e:
            logger.info(f"批量查询股票数据库问题 {type(e)}: {e}")
            raise e


class StockOrderDB(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    uid = fields.CharField(max_length=255, null=False)
    group_id = fields.IntField(null=True)
    stock_id = fields.CharField(max_length=255, null=False)
    type = fields.CharField(max_length=10, null=False)  # buy 或 sell
    gearing = fields.DecimalField(max_digits=20, decimal_places=3, null=True, default=1)
    cost = fields.DecimalField(max_digits=20, decimal_places=3, null=True)
    percent = fields.DecimalField(
        max_digits=10, decimal_places=3, null=True
    )  # 卖出时使用
    create_time = fields.DatetimeField(auto_now_add=True)
    execute_time = fields.DatetimeField(null=False)
    status = fields.CharField(
        max_length=10, null=False, default="pending"
    )  # pending, executed, cancelled, failed

    class Meta(Model.Meta):
        table = "stock_order"
        table_description = "股海风云·委托单表"

    @staticmethod
    def _run_script():
        """迁移 cost 列从 NUMERIC(10,3) 到 NUMERIC(20,3)"""
        return [
            """ALTER TABLE stock_order ALTER COLUMN cost TYPE NUMERIC(20, 3);""",
        ]

    @classmethod
    async def migrate_legacy_user_orders(cls, user_id: str | int) -> None:
        user_uid = build_stock_account_key(user_id)
        legacy_orders = [
            order
            for order in await cls.filter(uid__startswith=f"{user_uid}:").all()
            if order.uid.partition(":")[0] == user_uid
        ]
        for order in legacy_orders:
            _, old_group_id = parse_stock_account_key(order.uid)
            if old_group_id is not None and order.group_id is None:
                order.group_id = old_group_id
            order.uid = user_uid
            await order.save()

    @classmethod
    async def migrate_all_legacy_group_ids(cls) -> None:
        """启动时全量迁移：将旧 uid 中含群号的委托单提取群号到 group_id 字段"""
        orders = await cls.filter(group_id=None).all()
        for order in orders:
            _, gid = parse_stock_account_key(order.uid)
            if gid is not None:
                order.group_id = gid
                await order.save()

    @classmethod
    async def create_order(
        cls,
        uid: str,
        stock_id: str,
        order_type: str,
        gearing: float,
        cost: float,
        percent: float,
        execute_time: datetime,
        group_id: int | None = None,
    ) -> "StockOrderDB":
        try:
            order = await cls.create(
                uid=uid,
                group_id=group_id,
                stock_id=stock_id,
                type=order_type,
                gearing=gearing,
                cost=cost,
                percent=percent,
                execute_time=execute_time,
                status="pending",
            )
            return order
        except Exception as e:
            logger.info(f"创建委托单数据库问题 {type(e)}: {e}")
            raise e

    @classmethod
    async def get_pending_orders(
        cls, current_time: datetime
    ) -> Sequence["StockOrderDB"]:
        try:
            return await cls.filter(
                status="pending", execute_time__lte=current_time
            ).all()
        except Exception as e:
            logger.info(f"获取待执行委托单数据库问题 {type(e)}: {e}")
            raise e

    @classmethod
    async def get_user_orders(cls, uid: str) -> Sequence["StockOrderDB"]:
        try:
            return await cls.filter(uid=uid, status="pending").all()
        except Exception as e:
            logger.info(f"获取用户委托单数据库问题 {type(e)}: {e}")
            raise e

    @classmethod
    async def execute_order(cls, order_id: int) -> None:
        try:
            order = await cls.get(id=order_id)
            order.status = "executed"
            await order.save()
        except Exception as e:
            logger.info(f"执行委托单数据库问题 {type(e)}: {e}")
            raise e

    @classmethod
    async def fail_order(cls, order_id: int) -> "StockOrderDB | None":
        try:
            order = await cls.get(id=order_id)
            order.status = "failed"
            await order.save()
            return order
        except Exception as e:
            logger.info(f"标记委托单失败数据库问题 {type(e)}: {e}")
            raise e

    @classmethod
    async def get_timeout_failed_orders(
        cls, current_time: datetime, timeout_hours: int = 3
    ) -> Sequence["StockOrderDB"]:
        try:
            from datetime import timedelta

            timeout_threshold = current_time - timedelta(hours=timeout_hours)
            return await cls.filter(
                status="failed", execute_time__lte=timeout_threshold
            ).all()
        except Exception as e:
            logger.info(f"获取超时失败委托单数据库问题 {type(e)}: {e}")
            raise e

    @classmethod
    async def cancel_user_orders(cls, uid: str) -> tuple[int, float]:
        """取消用户的所有待执行委托单，返还金钱
        返回: (取消的委托单数量, 返还的总金额)
        """
        try:
            orders = await cls.filter(uid=uid, status="pending").all()
            if not orders:
                return 0, 0.0

            total_refund = 0.0
            count = 0
            for order in orders:
                if order.type == "buy" and order.cost:
                    total_refund += float(order.cost)
                order.status = "cancelled"
                await order.save()
                count += 1

            return count, total_refund
        except Exception as e:
            logger.info(f"取消委托单数据库问题 {type(e)}: {e}")
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
