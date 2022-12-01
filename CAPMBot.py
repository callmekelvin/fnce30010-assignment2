"""
This is a template bot for the CAPM Task.
"""
from typing import List
from fmclient import Agent, Session
from fmclient import Order, OrderSide, OrderType

from enum import Enum
import numpy as np
from itertools import permutations, combinations
from datetime import datetime
import math
import random

# Submission details
SUBMISSION = {"student_number": "1080783", "name": "Calvin Ho"}

FM_ACCOUNT = "regular-idol"
FM_EMAIL = "calvin1@student.unimelb.edu.au"
FM_PASSWORD = "1080783"
MARKETPLACE_ID = 1185  # replace this with the marketplace id

CONVERT_TO_DOLLARS = 1/100
STATE_PROBABILITY = 1/4


class OrderStatus(Enum):
    SENT = 0
    ACCEPTED = 1
    TRADED = 2
    REJECTED = 3
    CANCELLED = 4


class CAPMBot(Agent):

    def __init__(self, account, email, password, marketplace_id, risk_penalty=0.007, session_time=20):
        """
        Constructor for the Bot
        :param account: Account name
        :param email: Email id
        :param password: password
        :param marketplace_id: id of the marketplace
        :param risk_penalty: Penalty for risk
        :param session_time: Total trading time for one session
        """
        super().__init__(account, email, password, marketplace_id, name="CAPM Bot")
        self._payoffs = {}
        self._risk_penalty = risk_penalty
        self._session_time = session_time
        self._market_ids = {}

        self.cash_available = None
        self.cash = None
        self.units_available_holdings = {}
        self.units_holdings = {}

        self.unit_asset_payoffs = None
        self.asset_variances = None
        self.asset_covariances = None

        self.current_performance = None
        self.potential_performance = None

        self.sent_order_dict = {}
        self.pending_order_dict = {}
        self.traded_order_dict = {}

    def initialised(self):
        """
        Extract payoff distribution for each security and extract information about each market
        """
        for market_id, market_info in self.markets.items():
            security = market_info.item
            description = market_info.description
            self._payoffs[security] = [int(a) for a in description.split(",")]
            self._market_ids[market_id] = market_info

        self.inform("Bot initialised, I have the payoffs for the states.")

    def _calculate_performance(self, units, cash):
        """
        Raw Calculation of Performance by calculating Expected Payoff and Payoff Variance
        :param units:
        :param cash:
        :return:
        """
        expected_payoff = cash
        payoff_variance = 0

        for unit in units.keys():
            expected_payoff += units[unit] * (self.unit_asset_payoffs[unit])
            payoff_variance += math.pow(units[unit], 2) * self.asset_variances[unit]

        all_cov_comb = combinations(units.keys(), 2)

        for security_comb in all_cov_comb:
            payoff_variance += \
                2 * units[security_comb[0]] * units[security_comb[1]] * self.asset_covariances[security_comb]

        performance = expected_payoff - (self._risk_penalty * payoff_variance)

        return performance

    def _calculate_current_performance(self, potential_order=None, order_item=None, order_price=None, order_side=None):
        """
        Calculates the performance - Based off Settled Cash/ Holdings
        Note: Does not include the impact of pending orders
        :param potential_order:
        :return:
        """

        # Get settled holdings and settled cash
        current_performance_cash = (self.cash * CONVERT_TO_DOLLARS)
        current_performance_holdings = self.units_holdings.copy()

        # if we are calculating the potential performance by trading an order => adjust holdings and cash
        if potential_order:
            # if the order is to buy
            if order_side == OrderSide.BUY:
                current_performance_cash -= (order_price * CONVERT_TO_DOLLARS)
                current_performance_holdings[order_item] = \
                    current_performance_holdings[order_item] + 1

            # if the order is to sell
            elif order_side == OrderSide.SELL:
                current_performance_cash += (order_price * CONVERT_TO_DOLLARS)
                current_performance_holdings[order_item] = \
                    current_performance_holdings[order_item] - 1

        # calculate performance
        current_performance = self._calculate_performance(current_performance_holdings, current_performance_cash)

        return current_performance

    def get_potential_performance(self, orders):
        """
        Returns the portfolio performance if the given list of orders is executed.
        The performance as per the following formula:
        Performance = ExpectedPayoff - b * PayoffVariance, where b is the penalty for risk
        :param orders: list of orders
        :return:
        """

        # Gets Potential Performance if Current Orders from the Market are Traded
        # Ex. If the order from the market is to buy => our order would be to sell to the market and vice versa
        if orders.order_side == OrderSide.BUY:
            potential_performance = \
                self._calculate_current_performance(orders, orders.market.item, orders.price, OrderSide.SELL)
        else:
            potential_performance = \
                self._calculate_current_performance(orders, orders.market.item, orders.price, OrderSide.BUY)

        return potential_performance

    def is_portfolio_optimal(self):
        """
        Returns true if the current holdings are optimal (as per the performance formula), false otherwise.
        :return:
        """

        # Assumes that the current portfolio is optimal, unless proven otherwise
        portfolio_optimal_flag = True

        for order_id, order in Order.all().items():
            # update my order statuses
            self._update_trade_status(order)

            # If the order is pending and not our order
            if order.is_pending and not order.mine:

                # calculate the potential performance if we traded this public order
                potential_performance = self.get_potential_performance(order)

                # calculate current performance based off settled holdings/ cash
                self.current_performance = self._calculate_current_performance()

                # if trading the public order improves performance => trade it if we can
                if potential_performance > self.current_performance:

                    # Note: Our trade will take the opposite order side of the market trade
                    if order.order_side == OrderSide.BUY:
                        self._take_performance_improvement(order.market, OrderSide.SELL, order.price)
                    elif order.order_side == OrderSide.SELL:
                        self._take_performance_improvement(order.market, OrderSide.BUY, order.price)

                    # as there exists a public order that would improve our performance, our portfolio is not optimal
                    portfolio_optimal_flag = False
                    break

        return portfolio_optimal_flag

    def order_accepted(self, order):
        for order_ref, sent_order in self.sent_order_dict.items():
            if order.ref == order_ref:
                # remove from sent list, add to pending list
                self.sent_order_dict[order_ref].order_status = OrderStatus(1)

                self.pending_order_dict[order_ref] = self.sent_order_dict[order_ref]
                self.sent_order_dict.pop(order_ref)
                break

    def order_rejected(self, info, order):
        for order_ref, sent_order in self.sent_order_dict.items():
            if order.ref == order_ref:
                # remove from sent list

                self.sent_order_dict[order_ref].order_status = OrderStatus(3)
                self.sent_order_dict.pop(order.ref)
                break

    def _take_performance_improvement(self, order_market, order_side, order_price):
        """
        Check if we can make the performance improving order and if we can, do so
        :param order_market:
        :param order_side:
        :param order_price:
        :return:
        """

        # Ensure that pending units in orders do not exceed maximum units in orders allowed in a single market
        no_outstanding_orders = 0
        for pending_order in self.pending_order_dict.values():
            if pending_order.trade_market_id == order_market:
                no_outstanding_orders += 1

        for sent_order in self.sent_order_dict.values():
            if sent_order.trade_market_id == order_market:
                no_outstanding_orders += 1

        if no_outstanding_orders >= order_market.max_units:
            return

        # check if submit the order and if we can submit the order, do so
        if order_market.min_price <= order_price <= order_market.max_price:
            if order_side == OrderSide.BUY:
                if self.cash_available >= order_price:
                    new_order = _CurrentOrder(order_price, OrderSide.BUY, order_market, self)
                    self.sent_order_dict[new_order.ref] = new_order
                else:
                    self.inform(f"Insufficient funds to take performance improvement")

            elif order_side == OrderSide.SELL:
                if self.units_available_holdings[order_market.item] >= 0:
                    new_order = _CurrentOrder(order_price, OrderSide.SELL, order_market, self)
                    self.sent_order_dict[new_order.ref] = new_order
                else:
                    self.inform(f"Insufficient units of "
                                f"{order_market.item} to take performance improvement")
        else:
            self.inform(f"Order Price out of Market Price Ranges")

    def received_orders(self, orders: List[Order]):
        # Bot in Reactive Mode
        portfolio_optimal_flag = self.is_portfolio_optimal()

        # Bot in Proactive Mode
        if portfolio_optimal_flag:
            self._proactive_mode()

    def _proactive_mode(self):
        """
        If portfolio is optimal => Switch bot to Proactive Mode (find our own performance improving orders)
        Code is only run when there are no reactive performance improving opportunities
        """

        # Randomly pick an asset market
        random_asset_market = random.choice(list(self._market_ids.keys()))
        random_asset_item = self._market_ids[random_asset_market].item

        # Get best bid and ask prices for that random asset market
        best_prices = self._get_best_bid_ask_price(random_asset_market, random_asset_item)

        # Determine the Order Side of Trade
        # If we are running low on Cash => Try to sell/ short sell asset to gain funds
        if self.cash_available < best_prices["best_ask"]:
            order_direction = OrderSide.SELL

        # Otherwise, pick a random order side
        else:
            order_direction = random.choice(list([OrderSide.BUY, OrderSide.SELL]))

        # Run gradient price search
        self._gradient_price_search(random_asset_market, best_prices, order_direction)

    def _gradient_price_search(self, market_id, best_price, order_side):
        """
        Search for an order price in a given market and order side that would improve portfolio performance
        :param market_id:
        :param best_price:
        :param order_side:
        :return:
        """

        # Get market max, min price and gradient ascent/ descent price step
        max_price = self._market_ids[market_id].max_price
        min_price = self._market_ids[market_id].min_price
        price_step = self._market_ids[market_id].price_tick

        self.current_performance = self._calculate_current_performance()

        # Based off order side => determine if it is price ascent/ descent search and where to start price search
        if order_side == OrderSide.BUY:
            price_movement = -1
            price = best_price["best_bid"]
        else:
            price_movement = 1
            price = best_price["best_ask"]

        # ensure price search occurs within max and min price
        while min_price <= price <= max_price:

            potential_performance = self._calculate_current_performance(True, self._market_ids[market_id].item, price,
                                                                        order_side)

            # if this price improves performance, trade this order at this price
            if potential_performance > self.current_performance:

                self._take_performance_improvement(self._market_ids[market_id], order_side, price)
                break

            # increment/ decrement price
            price = price + (price_movement * price_step)

    def _get_best_bid_ask_price(self, asset_market, asset_item):
        """
        Get best bid and ask price for a certain asset market to determine where to start price search
        :param asset_market:
        :param asset_item:
        :return:
        """

        # Assume best bid and ask price are maximum and minimum price
        best_ask = self._market_ids[asset_market].max_price
        best_bid = self._market_ids[asset_market].min_price

        midpoint_price = int((self._market_ids[asset_market].max_price - self._market_ids[asset_market].min_price) / 2)

        best_prices = {"best_bid": best_bid, "best_ask": best_ask}

        # Get best bid and ask prices
        for order_id, order in Order.all().items():
            if order.is_pending and order.market.item == asset_item:
                if order.order_side == OrderSide.BUY and order.price > best_prices["best_bid"]:
                    best_prices["best_bid"] = order.price
                elif order.order_side == OrderSide.SELL and order.price < best_prices["best_ask"]:
                    best_prices["best_ask"] = order.price

        # If there is no existing bids for the order side => return midpoint price
        if best_prices["best_bid"] == self._market_ids[asset_market].min_price:
            best_prices["best_bid"] = midpoint_price

        if best_prices["best_ask"] == self._market_ids[asset_market].max_price:
            best_prices["best_ask"] = midpoint_price

        return best_prices

    def _print_my_orders(self):
        """
        Debug function to log the status of all orders
        :return:
        """
        self.inform(" ")
        self.inform(f"Log Order Process:")
        self.inform(f"Sent Order Dict: {self.sent_order_dict}")
        self.inform(f"Pending Order Dict: {self.pending_order_dict}")
        self.inform(f"Traded Order Dict: {self.traded_order_dict}")

    def _update_trade_status(self, order):
        """
        Code Adapted from Project 1: Task 1
        Update Status of Orders => Check to see if they have been accepted or cancelled

        Update the trade status order of pending orders => remove orders that are accepted/ cancelled
        :return:
        """

        # update pending order dictionary
        for order_ref, pending_order in self.pending_order_dict.items():
            # order cancelled
            if order.ref == order_ref and order.is_cancelled and order.mine:
                # remove from pending list

                self.pending_order_dict[order_ref].order_status = OrderStatus(4)
                self.pending_order_dict.pop(order.ref)
                break

            # order traded
            elif order.ref == order_ref and order.traded_order is not None and order.mine:
                # remove from pending list and transfer to traded list

                self.pending_order_dict[order_ref].order_status = OrderStatus(2)
                self.traded_order_dict[order.ref] = self.pending_order_dict[order_ref]
                self.pending_order_dict.pop(order.ref)
                break

    def received_session_info(self, session: Session):
        if session.is_open:
            # self.inform("Market is open")

            # reset all variables between sessions
            self.cash_available = None
            self.cash = None
            self.units_available_holdings = {}
            self.units_holdings = {}

            self.current_performance = None
            self.potential_performance = None

            self.sent_order_dict = {}
            self.pending_order_dict = {}
            self.traded_order_dict = {}

            # If payoffs have changed while market was closed => recalculate variance/ payoffs
            recalculation_required = False

            for market_id, market_info in self.markets.items():
                security = market_info.item
                description = market_info.description
                new_payoffs = [int(a) for a in description.split(",")]

                if not np.array_equal(self._payoffs[security], new_payoffs):
                    self._payoffs[security] = new_payoffs
                    recalculation_required = True

            if recalculation_required:
                self._pre_calculate_payoffs_and_variance()
                self.inform("Bot reinitialised, I have the payoffs for the states.")

        elif session.is_closed:
            # self.inform("Market is closed")
            pass

    def _pre_calculate_payoffs_and_variance(self):
        """
        Asset Variances, Covariances and Unit Asset Payoffs can be computed as soon as payoffs in different
        states is known. Hence, we can pre-compute these values to speed up calculation of portfolio performance.
        """
        self.unit_asset_payoffs = {}
        self.asset_variances = {}
        self.asset_covariances = {}

        # Convert Payoffs into Dollars
        payoff_dollars = {}
        for security, payoff in self._payoffs.items():
            payoff_dollars[security] = (np.array(payoff) * CONVERT_TO_DOLLARS).tolist()

        # Pre-Calculate Unit Asset Payoffs and Asset Variance
        for security in self._payoffs.keys():
            self.unit_asset_payoffs[security] = np.sum(payoff_dollars[security]) * STATE_PROBABILITY
            self.asset_variances[security] = np.var(payoff_dollars[security])

        # Pre-Calculate Co-Variances
        all_cov_comb = permutations(payoff_dollars.keys(), 2)

        for security_comb in all_cov_comb:
            cov_pair = np.cov(payoff_dollars[security_comb[0]], payoff_dollars[security_comb[1]], bias=True)[0][1]
            self.asset_covariances[security_comb] = cov_pair

        # Print Unit Asset Payoffs, Asset Variance and Asset Covariances
        # self.inform(f"Unit Asset Payoffs: {self.unit_asset_payoffs}")
        # self.inform(f"Asset Variance: {self.asset_variances}")
        # self.inform(f"Asset Covariance: {self.asset_covariances}")

    def pre_start_tasks(self):
        self._pre_calculate_payoffs_and_variance()

    def received_holdings(self, holdings):
        self.cash = holdings.cash
        self.cash_available = holdings.cash_available

        for market_id, asset in holdings.assets.items():
            self.units_available_holdings[market_id.item] = asset.units_available
            self.units_holdings[market_id.item] = asset.units


class _CurrentOrder:
    """
    Adapted from Project 1 - Task 1 Code
    Wrapper class to store information about an Order and provides functionality to create new orders
    """
    def __init__(self, price, order_side, trade_market_id, capm_bot):
        self.price = price
        self.order_side = order_side
        self.trade_market_id = trade_market_id
        self.order_status = None
        self.date_created = datetime.now()
        self.ref = f"Asset-{self.trade_market_id.item}-Price-{self.price}-OrderSide-{self.order_side}" \
                   f"-[{SUBMISSION['student_number']}]-{self.date_created}"

        capm_bot.send_order(self._create_order())
        self.order_status = OrderStatus(0)

    def _create_order(self):
        # submit the order
        new_order = Order.create_new(self.trade_market_id)
        new_order.order_side = self.order_side
        new_order.order_type = OrderType.LIMIT
        new_order.price = self.price
        new_order.units = 1
        new_order.ref = self.ref

        # return new_order
        return new_order

    def __repr__(self):
        return f"{self.ref}-Order-Status-{self.order_status}"


if __name__ == "__main__":
    bot = CAPMBot(FM_ACCOUNT, FM_EMAIL, FM_PASSWORD, MARKETPLACE_ID)
    bot.run()
