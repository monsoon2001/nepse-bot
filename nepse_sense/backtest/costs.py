from dataclasses import dataclass


@dataclass
class NepseCosts:
    """NEPSE trading cost configuration.
    
    IMPORTANT: All rates marked "verify current rates" — these are sensible 
    defaults for configuration only and must be verified against current 
    NEPSE/SEBON published rates before use.
    """

    broker_commission_rate: float = 0.004  # 0.4% - verify current rates
    sebon_fee_rate: float = 0.00015  # 0.015% - verify current rates
    dp_charge: float = 25.0  # flat NPR per transaction - verify current rates
    capital_gains_tax_rate: float = 0.05  # 5% on profits (if applicable) - verify current rates
    slippage_rate: float = 0.001  # 0.1% slippage assumption
    min_lot_size: int = 1  # NEPSE minimum lot - verify

    def buy_cost(self, price: float, quantity: int) -> float:
        trade_value = price * quantity
        commission = trade_value * self.broker_commission_rate
        sebon = trade_value * self.sebon_fee_rate
        dp = self.dp_charge
        slippage = trade_value * self.slippage_rate
        return trade_value + commission + sebon + dp + slippage

    def sell_proceeds(self, price: float, quantity: int, buy_price: float) -> float:
        trade_value = price * quantity
        commission = trade_value * self.broker_commission_rate
        sebon = trade_value * self.sebon_fee_rate
        dp = self.dp_charge
        slippage = trade_value * self.slippage_rate
        profit = trade_value - (buy_price * quantity)
        tax = 0.0
        if profit > 0:
            tax = profit * self.capital_gains_tax_rate
        return trade_value - commission - sebon - dp - slippage - tax


DEFAULT_COSTS = NepseCosts()
