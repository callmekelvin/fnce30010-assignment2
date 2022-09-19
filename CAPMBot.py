"""
This is a template bot for  the CAPM Task.
"""
from typing import List
from fmclient import Agent, Session
from fmclient import Order, OrderSide, OrderType

from enum import Enum
import numpy as np
from itertools import permutations, combinations
from datetime import datetime
import math

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

    def __init__(self, account, email, password, marketplace_id, risk_penalty=0.001, session_time=20):
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

        # refers to current portfolio performance => including pending trades
        self.current_performance = None

        # refers to self.current_performance + proposed_trade
        self.potential_performance = None

        # sent order dictionary
        self.sent_order_dict = {}

        # pending orders dictionary
        self.pending_order_dict = {}

        # traded orders dictionary
        self.traded_order_dict = {}

    def initialised(self):
        # Extract payoff distribution for each security
        # Extract information about each market
        for market_id, market_info in self.markets.items():
            security = market_info.item
            description = market_info.description
            self._payoffs[security] = [int(a) for a in description.split(",")]
            self._market_ids[market_id] = market_info

        self.inform(f"Payoffs: {self._payoffs}")
        self.inform(f"Market Information: {self._market_ids}")
        self.inform("Bot initialised, I have the payoffs for the states.")

    def _calculate_performance(self, units, cash):
        # Expected Payoff and Payoff Variance
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

        # self.inform(f"Expected Payoff: {expected_payoff}")
        # self.inform(f"Payoff Variance: {payoff_variance}")
        # self.inform(f"Performance: {performance}")

        return performance

    def _calculate_current_performance(self, potential_order=None):
        """
        Calculates the performance => when there is a potential order and when there isn't
        :param potential_order:
        :return:
        """

        # calculate current portfolio performance => including pending trades

        # start with settled holdings and settled cash
        current_performance_cash = (self.cash * CONVERT_TO_DOLLARS)
        current_performance_holdings = self.units_holdings.copy()

        # Include pending trades => make changes based off pending cash transactions and units
        # As we expect these pending orders to be traded
        # for order in self.pending_order_dict.values():
        #     if order.order_side == OrderSide.SELL:
        #         current_performance_cash += (order.price * CONVERT_TO_DOLLARS)
        #         current_performance_holdings[order.trade_market_id.item] = \
        #             current_performance_holdings[order.trade_market_id.item] - 1
        #
        #     elif order.order_side == OrderSide.BUY:
        #         current_performance_cash -= (order.price * CONVERT_TO_DOLLARS)
        #         current_performance_holdings[order.trade_market_id.item] = \
        #             current_performance_holdings[order.trade_market_id.item] + 1
        #
        # self.inform(f"Current Performance Holdings (after pending): {current_performance_holdings}")


        # if we are calculating the potential performance => include the effects of the potential order
        # On next test, remove the safeguards:
        # Remove: current_performance_cash >= potential_order.price * CONVERT_TO_DOLLARS:
        # Remove: current_performance_holdings[potential_order.market.item] > 0:
        if potential_order:
            # if the order from the market is sell => our order will be to buy
            if potential_order.order_side == OrderSide.SELL and \
                    current_performance_cash >= potential_order.price * CONVERT_TO_DOLLARS:
                current_performance_cash -= (potential_order.price * CONVERT_TO_DOLLARS)
                current_performance_holdings[potential_order.market.item] = \
                    current_performance_holdings[potential_order.market.item] + 1

            # if the order from the market is buy => our order will be to sell
            elif potential_order.order_side == OrderSide.BUY and \
                    current_performance_holdings[potential_order.market.item] > 0:
                current_performance_cash += (potential_order.price * CONVERT_TO_DOLLARS)
                current_performance_holdings[potential_order.market.item] = \
                    current_performance_holdings[potential_order.market.item] - 1

            else:
                self.inform(f"Can't trade this potential order")

        if potential_order:
            self.inform(f"Current Performance Holdings: {current_performance_holdings}")
            self.inform(f"Current Performance Holdings (with potential order): {current_performance_holdings}")

        # calculate performance
        current_performance = self._calculate_performance(current_performance_holdings, current_performance_cash)

        return current_performance

    def get_potential_performance(self, orders):
        """
        Returns the portfolio performance if the given list of orders is executed.
        The performance as per the following formula:
        Performance = ExpectedPayoff - b * PayoffVariance, where b is the penalty for risk.
        :param orders: list of orders
        :return:
        """

        potential_performance = self._calculate_current_performance(orders)

        return potential_performance

    def is_portfolio_optimal(self):
        """
        Returns true if the current holdings are optimal (as per the performance formula), false otherwise.
        :return:
        """
        pass

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

    def _take_performance_improvement(self, order):
        # Perform a check to ensure outstanding units pending in a market is less than maximum units you can put through
        # This applies to both order sides in a single market

        no_outstanding_orders = 0
        for pending_order in self.pending_order_dict.values():
            if pending_order.trade_market_id == order.market:
                no_outstanding_orders += 1

        for sent_order in self.sent_order_dict.values():
            if sent_order.trade_market_id == order.market:
                no_outstanding_orders += 1

        if no_outstanding_orders >= order.market.max_units:
            return

        # NEED TO REVIEW USE OF CASH_AVAILABLE AND UNITS HOLDING AVAILABLE
        if order.order_side == OrderSide.SELL:
            if self.cash_available >= order.price:
                new_order = _CurrentOrder(order.price, OrderSide.BUY, order.market, self)
                self.sent_order_dict[new_order.ref] = new_order
            else:
                self.inform(f"Insufficient funds to take performance improvement")

        elif order.order_side == OrderSide.BUY:
            if self.units_available_holdings[order.market.item] >= 0:
                new_order = _CurrentOrder(order.price, OrderSide.SELL, order.market, self)
                self.sent_order_dict[new_order.ref] = new_order
            else:
                self.inform(f"Insufficient units of "
                            f"{order.market.item} to take performance improvement")

    def received_orders(self, orders: List[Order]):
        # is_portfolio_optimal function logic => bot in reactive mode

        # portfolio_optimal_flag = True

        # calculate current_performance => current asset holdings + pending orders
        self._print_my_orders()

        for order_id, order in Order.all().items():
            # update my order statuses
            self._update_trade_status(order)

            # if the public order is pending and not our order
            if order.is_pending and not order.mine:
                # potential performance => current asset holdings + potential order
                potential_performance = self.get_potential_performance(order)
                self.current_performance = self._calculate_current_performance()

                self.inform(f"Current Order: {order}; Current Performance: {self.current_performance},"
                            f" Potential Performance: {potential_performance}")
                self.inform(" ")

                # if the potential order improves performance => trade it
                # this also means that the current portfolio is not optimal
                if potential_performance > self.current_performance:

                    self._take_performance_improvement(order)
                    # portfolio_optimal_flag = False
                    break

        # if there is no cash and only asset holding is notes => sell notes to get cash (MIGHT ALSO BE HANDLED?)

        # if portfolio is optimal => switch bot to proactive mode (create its own performance improving orders)
        # if portfolio_optimal_flag:
        #     # randomly pick an asset market

    def _print_my_orders(self):
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
            self.inform("Market is open")

            # reset all variables between sessions
            # DO RESET HERE => NOT ALL VARIABLES ARE HERE YET
            self.cash_available = None
            self.cash = None
            self.units_available_holdings = {}
            self.units_holdings = {}

            self.current_performance = None
            self.sent_order_dict = {}
            self.pending_order_dict = {}
            self.traded_order_dict = {}

            # If payoffs have changed while market was closed => recalculate
            recalculation_required = False

            for market_id, market_info in self.markets.items():
                security = market_info.item
                description = market_info.description
                new_payoffs = [int(a) for a in description.split(",")]

                if np.array_equal(self._payoffs[security], new_payoffs):
                    recalculation_required = True

            if recalculation_required:
                self._pre_calculate_payoffs_and_variance()

            self.inform("Bot initialised, I have the payoffs for the states.")

        elif session.is_closed:
            self.inform("Market is closed")
            # pass

    def _pre_calculate_payoffs_and_variance(self):
        """Asset Variances, Covariances and Unit Asset Payoffs can be computed as soon as payoffs in different
        states is known. Hence, we can pre-compute these values to speed up calculation of portfolio performance."""
        self.unit_asset_payoffs = {}
        self.asset_variances = {}
        self.asset_covariances = {}

        # Convert Payoffs into Dollars
        payoff_dollars = {}
        for security, payoff in self._payoffs.items():
            payoff_dollars[security] = (np.array(payoff) * CONVERT_TO_DOLLARS).tolist()
        # self.inform(f"Payoff in Dollars: {payoff_dollars}")

        # Pre-Calculate Unit Asset Payoffs and Asset Variance
        for security in self._payoffs.keys():
            self.unit_asset_payoffs[security] = np.sum(payoff_dollars[security]) * STATE_PROBABILITY
            self.asset_variances[security] = np.var(payoff_dollars[security])

        # Pre-Calculate Co-Variances
        all_cov_comb = permutations(payoff_dollars.keys(), 2)

        for security_comb in all_cov_comb:
            cov_pair = np.cov(payoff_dollars[security_comb[0]], payoff_dollars[security_comb[1]], bias=True)[0][1]
            self.asset_covariances[security_comb] = cov_pair
            # self.inform(f"Covariance for {security_comb} = {cov_pair}")

        # Print Unit Asset Payoffs, Asset Variance and Asset Covariances
        self.inform(f"Unit Asset Payoffs: {self.unit_asset_payoffs}")
        self.inform(f"Asset Variance: {self.asset_variances}")
        self.inform(f"Asset Covariance: {self.asset_covariances}")

    def pre_start_tasks(self):
        self._pre_calculate_payoffs_and_variance()
        # pass

    def received_holdings(self, holdings):
        self.cash = holdings.cash
        self.cash_available = holdings.cash_available

        for market_id, asset in holdings.assets.items():
            self.units_available_holdings[market_id.item] = asset.units_available
            self.units_holdings[market_id.item] = asset.units

        self.inform(" ")
        self.inform(f"Received Holdings:")
        self.inform(f"Cash Available: {self.cash_available}; Cash: {self.cash}")
        self.inform(f"Unit Holdings: {self.units_holdings}")
        self.inform(f"Unit Available Holdings {self.units_available_holdings}")


class _CurrentOrder:
    """
    STILL NEED TO REWORK FOR USE IN TASK 2

    Adapted Project 1 - Task 1 Code
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
        # bot.inform(f"Order Sent: {self.ref}")

    def _create_order(self):
        # self.inform(f"Created-Order: {self.ref}")

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
