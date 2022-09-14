"""
This is a template bot for  the CAPM Task.
"""
from typing import List
from fmclient import Agent, Session
from fmclient import Order, OrderSide, OrderType

from enum import Enum
import numpy as np
from itertools import permutations
from datetime import datetime

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

        # each market should have its own dictionary to store orders

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

    def get_potential_performance(self, orders):
        """
        Returns the portfolio performance if the given list of orders is executed.
        The performance as per the following formula:
        Performance = ExpectedPayoff - b * PayoffVariance, where b is the penalty for risk.
        :param orders: list of orders
        :return:
        """
        pass

    def is_portfolio_optimal(self):
        """
        Returns true if the current holdings are optimal (as per the performance formula), false otherwise.
        :return:
        """
        pass

    def order_accepted(self, order):
        pass

    def order_rejected(self, info, order):
        pass

    def received_orders(self, orders: List[Order]):
        # get all outstanding orders within the order book
        # run each order against the get_potential_performance() function to get potential performance
        # if potential performance > current performance => trade this order

        # if there was an instance where potential performance > current performance
        # is_portfolio_optimal should return False

        pass

    def received_session_info(self, session: Session):
        if session.is_open:
            self.inform("Market is open")

            # reset all variables between sessions
            # DO RESET HERE
            pass

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

        self.inform(f"Cash Available: {self.cash_available}; Cash: {self.cash}")
        self.inform(self.units_holdings)
        self.inform(self.units_available_holdings)


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
        self.ref = f"Market-{self.trade_market_id}-Price-{self.price}-OrderSide-{self.order_side}" \
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
