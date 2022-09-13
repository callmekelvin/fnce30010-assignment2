"""
This is a template for Project 1, Task 1 (Induced demand-supply)
"""

from enum import Enum
from fmclient import Agent, OrderSide, Order, OrderType, Session
from typing import List
from datetime import datetime

# Student details
SUBMISSION = {"number": "1080783", "name": "Calvin Ho"}

# Fixed Profit Margin
PROFIT_MARGIN = 10


# Enum for the roles of the bot
class Role(Enum):
    BUYER = 0
    SELLER = 1


# Let us define another enumeration to deal with the type of bot
class BotType(Enum):
    PROACTIVE = 0
    REACTIVE = 1


class OrderStatus(Enum):
    SENT = 0
    ACCEPTED = 1
    TRADED = 2
    REJECTED = 3
    CANCELLED = 4


class DSBot(Agent):
    def __init__(self, account, email, password, marketplace_id, bot_type: BotType):
        super().__init__(account, email, password, marketplace_id, name="DSBot")
        self._public_market = None
        self._private_market = None

        self._role = None
        self._bot_type = bot_type

        self.order_pairs = OrderPairs()
        self._private_market_offer = None

        self._cash_available = None
        self._private_assets = None
        self._public_assets = None

        self.private_order_no = 0
        self.remaining_private_order_no = 0

    # getters and setters
    def get_private_order_no(self):
        return self.private_order_no

    def get_remaining_private_order_no(self):
        return self.remaining_private_order_no

    def set_remaining_private_order_no(self, num):
        self.remaining_private_order_no = num

    def role(self):
        """
        Returns and sets the order side the bot takes on the public market based off private incentive
        :return: Role(Enum)
        """

        if self._private_market_offer.order_side == OrderSide.BUY:
            self._role = Role(0)
        else:
            self._role = Role(1)

        return self._role

    def initialised(self):
        """
        Gets and sets the public and private market variables
        :return:
        """
        for market_id, market in self.markets.items():
            if market.private_market:
                self._private_market = market
            else:
                self._public_market = market

    def order_accepted(self, order: Order):
        if order.mine and order.ref == self.order_pairs.public_order.ref:
            self.order_pairs.public_order.order_status = OrderStatus(1)

        elif order.mine and order.ref == self.order_pairs.private_order.ref:
            self.order_pairs.private_order.order_status = OrderStatus(1)

    def order_rejected(self, info, order: Order):
        if order.mine and order.ref == self.order_pairs.public_order.ref:
            self.order_pairs.public_order.order_status = OrderStatus(3)

        elif order.mine and order.ref == self.order_pairs.private_order.ref:
            self.order_pairs.private_order.order_status = OrderStatus(3)

    def received_orders(self, orders: List[Order]):

        # updates the status of orders
        self._update_trade_status()

        # run code based off bot type
        if self._bot_type == BotType(1):
            # reactive bot code
            self._reactive_bot()
        else:
            # proactive bot code
            self._proactive_bot()

    def _print_trade_opportunity(self, other_order):
        self.inform(f"I am a {self.role()} with profitable order {other_order}")

    def received_holdings(self, holdings):
        # updates locally stored variables on cash and units available
        self._cash_available = holdings.cash_available

        for market_id, asset in holdings.assets.items():
            if self._private_market.fm_id == market_id:
                self._private_assets = asset.units_available
            else:
                self._public_assets = asset.units_available

    def received_session_info(self, session: Session):
        if session.is_open:
            # reset variables that change inbetween sessions

            self._role = None

            self.order_pairs = OrderPairs()
            self._private_market_offer = None

            self._cash_available = None
            self._private_assets = None
            self._public_assets = None

            self.private_order_no = 0
            self.remaining_private_order_no = 0

        elif session.is_closed:
            pass

    def pre_start_tasks(self):
        pass

    def _update_trade_status(self):
        """
        Update Status of Orders => Check to see if they have been accepted or cancelled
        It also checks if there is a new private incentive in the private market
        :return:
        """

        for order_id, order in Order.all().items():
            # update private market offer
            if order.is_pending and order.is_private and not order.mine:
                # only update market offer if the price and order side has changed
                offer_uid = f"Price-{order.price}-Order-Side{order.order_side}-Date-{order.date_created}"

                current_offer_uid = ""
                if self._private_market_offer is not None:
                    current_offer_uid = f"Price-{self._private_market_offer.price}-" \
                                        f"Order-Side{self._private_market_offer.order_side}" \
                                        f"-Date-{self._private_market_offer.date_created}"

                if offer_uid != current_offer_uid:
                    self._private_market_offer = order

                    self.private_order_no = order.units
                    self.remaining_private_order_no = order.units

                    self.role()

            # order cancelled - public order
            elif order.is_cancelled and order.mine and self.order_pairs.public_order is not None and \
                    order.ref == self.order_pairs.public_order.ref:
                self.order_pairs.public_order.order_status = OrderStatus(4)

            # order cancelled - private order
            elif order.is_cancelled and order.mine and self.order_pairs.private_order is not None and \
                    order.ref == self.order_pairs.private_order.ref:
                self.order_pairs.private_order.order_status = OrderStatus(4)

            # order traded - private order
            elif self.order_pairs.private_order is not None and \
                    order.traded_order is not None and order.mine and\
                    order.ref == self.order_pairs.private_order.ref:
                self.order_pairs.private_order.order_status = OrderStatus(2)

            # order traded - public order
            elif self.order_pairs.public_order is not None and \
                    order.traded_order is not None and \
                    order.mine and order.ref == self.order_pairs.public_order.ref:
                self.order_pairs.public_order.order_status = OrderStatus(2)

    def _is_reactive_order_profitable(self, order):
        """
        Based off an order in the public order book, determine if it is a profitable opportunity and if we can take
        this profitable opportunity
        :param order:
        :return:
        """

        # Buy from Public Market: Buy Low from Public Market, Sell High on Private Market
        if self._role == Role(0) and order.order_side == OrderSide.SELL:
            if order.price + PROFIT_MARGIN <= self._private_market_offer.price:
                self._print_trade_opportunity(order)

                if self._can_take_reactive_opportunity(order):
                    # take public opportunity
                    self.order_pairs.set_reactive_public_order(self._private_market_offer, order,
                                                               self._public_market, self)

        # Sell to Public Market: Buy Low from Private Market, Sell High on Public Market
        elif self._role == Role(1) and order.order_side == OrderSide.BUY:
            if order.price >= self._private_market_offer.price + PROFIT_MARGIN:
                self._print_trade_opportunity(order)

                if self._can_take_reactive_opportunity(order):
                    # take public opportunity
                    self.order_pairs.set_reactive_public_order(self._private_market_offer, order,
                                                               self._public_market, self)

    def _can_take_reactive_opportunity(self, order):
        """
        Can take advantage of the public order opportunity? - do we have sufficient cash/ units available
        :param order:
        :return:
        """

        # if there has not been a public order and if we have a private market incentive
        if self.order_pairs.public_order is None and self._private_market_offer is not None:
            if self.remaining_private_order_no <= 0:
                self.inform(f"No available units of private incentive to trade with")
                return False

            # check if we have sufficient funds to buy
            if order.order_side == OrderSide.SELL and self._cash_available <= order.price:
                self.inform(f"Insufficient funds to purchase public asset")
                return False

            # check if we have sufficient assets to sell
            elif order.order_side == OrderSide.BUY:
                if order.is_private and self._private_assets <= 0:
                    self.inform(f"Insufficient private units to sell")
                    return False

                elif not order.is_private and self._public_assets <= 0:
                    self.inform(f"Insufficient public assets to sell")
                    return False
                else:
                    return True
            else:
                return True
        else:
            return False

    def _can_take_proactive_opportunity(self):
        """
        Similar to _can_take_reactive_opportunity function
        However, as we proactively create orders, we need to consider upper and lower price bounds of the market
        :return:
        """

        # if there has not been a public order and if we have a private market incentive
        if self.order_pairs.public_order is None and self._private_market_offer is not None:

            # Sell to Public Market => Markup Buy Price from Private Market by Profit Margin
            # Sell High to Public Market, Buy Low from Private Market, Received Private Sell Order Incentive
            # Ensure we have sufficient assets and price of order we place is below max market price
            if self._private_market_offer.order_side == OrderSide.SELL and self._public_assets > 0 and \
                    PROFIT_MARGIN + self._private_market_offer.price <= self._public_market.max_price and \
                    self.remaining_private_order_no > 0:
                # create sell public order
                self.order_pairs.public_order = _CurrentOrder((PROFIT_MARGIN + self._private_market_offer.price), False,
                                                              OrderSide.SELL, self._public_market, self)

            # Buy from Public Market => Markdown Buy Price from Private Market by Profit Margin
            # Buy Low to Public Market, Sell High from Private Market, Received Private Buy Order Incentive
            # Ensure we have the cash to buy and price fo order we place is above min market price
            elif self._private_market_offer.order_side == OrderSide.BUY and \
                    (self._cash_available >= self._private_market_offer.price - PROFIT_MARGIN) and \
                    (self._private_market_offer.price - PROFIT_MARGIN >= self._public_market.min_price) and \
                    self.remaining_private_order_no > 0:
                # create buy public order
                self.order_pairs.public_order = _CurrentOrder((self._private_market_offer.price - PROFIT_MARGIN), False,
                                                              OrderSide.BUY, self._public_market, self)

    def _reactive_bot(self):
        """
        Reacts to public trade offers in the market
        :return:
        """

        # get all profitable opportunities from public market
        for order_id, order in Order.all().items():
            if not order.mine and order.is_pending and not order.is_private:
                # order profitable
                self._is_reactive_order_profitable(order)

        self.order_pairs.continue_order_pair(self._private_market_offer, self._private_market, self)

    def _proactive_bot(self):
        """
        Proactive creates trade offers in the market
        :return:
        """

        self._can_take_proactive_opportunity()

        self.order_pairs.continue_order_pair(self._private_market_offer, self._private_market, self)


class _CurrentOrder:
    """
    Wrapper class to store information about an Order and provides functionality to create new orders
    """
    def __init__(self, price, is_private, order_side, trade_market_id, bot):
        self.price = price
        self.is_private = is_private
        self.owner_or_target = "M000"
        self.order_side = order_side
        self.trade_market_id = trade_market_id
        self.order_status = None
        self.date_created = datetime.now()
        self.ref = f"PRIVATE-{self.is_private}-Price-{self.price}-OrderSide-{self.order_side}" \
                   f"-[{SUBMISSION['number']}]-{self.date_created}"

        bot.send_order(self._create_order())
        self.order_status = OrderStatus(0)

    def _create_order(self):

        # submit the order
        new_order = Order.create_new(self.trade_market_id)
        new_order.order_side = self.order_side
        new_order.order_type = OrderType.LIMIT
        new_order.price = self.price
        new_order.units = 1
        new_order.ref = self.ref

        if self.is_private:
            new_order.owner_or_target = self.owner_or_target

        return new_order

    def __repr__(self):
        return f"{self.ref}-Order-Status-{self.order_status}"


class OrderPairs:
    """
    Public and Private Order Trade Pair
    """
    def __init__(self):
        self.public_order = None
        self.private_order = None

    def set_reactive_public_order(self, private_offer, public_offer, public_market, bot):

        # if public order has not been placed
        if self.public_order is None and private_offer is not None:
            if private_offer.order_side == OrderSide.SELL:
                public_order_side = OrderSide.SELL
            else:
                public_order_side = OrderSide.BUY

            # submit public order
            self.public_order = _CurrentOrder(public_offer.price, False, public_order_side, public_market, bot)

    def continue_order_pair(self, private_offer, private_market, bot):
        # run check which stage of the order pair we are up to

        if self.public_order is not None:
            # if public order has been cancelled or rejected => start again
            if self.public_order.order_status == OrderStatus(3) or self.public_order.order_status == OrderStatus(4):
                self.public_order = None
                self.private_order = None

            # if public order has been traded but yet to put in private order trade
            elif self.public_order.order_status == OrderStatus(2) and self.private_order is None:
                if self.public_order.order_side == OrderSide.SELL:
                    private_order_side = OrderSide.BUY
                else:
                    private_order_side = OrderSide.SELL

                # submit private order
                self.private_order = _CurrentOrder(private_offer.price, True, private_order_side, private_market, bot)

            # public order traded but private order rejected/ cancelled
            elif self.public_order.order_status == OrderStatus(2) and self.private_order is not None and \
                    (self.private_order.order_status == OrderStatus(3)
                     or self.private_order.order_status == OrderStatus(4)):
                self.private_order = None

            # trade pair finished => restart
            elif self.private_order is not None and \
                    self.public_order.order_status == OrderStatus(2) \
                    and self.private_order.order_status == OrderStatus(2):
                self.public_order = None
                self.private_order = None

                bot.set_remaining_private_order_no(bot.get_remaining_private_order_no() - 1)

    def __repr__(self):
        if self.public_order is None:
            public_str = f"Public-Order:None"
        else:
            public_str = f"Public-Order:{self.public_order.ref}"

        if self.private_order is None:
            private_str = f"Private-Order:None"
        else:
            private_str = f"Private-Order:{self.private_order.ref}"

        return f"{public_str}===={private_str}"


if __name__ == "__main__":
    FM_ACCOUNT = "regular-idol"
    FM_EMAIL = "calvin1@student.unimelb.edu.au"
    FM_PASSWORD = "1080783"
    MARKETPLACE_ID = 1175

    # Change Bot Type Here
    # BotType(0) => PROACTIVE and BotType(1) => REACTIVE
    BOT_TYPE = BotType(1)

    ds_bot = DSBot(FM_ACCOUNT, FM_EMAIL, FM_PASSWORD, MARKETPLACE_ID, BOT_TYPE)
    ds_bot.run()
