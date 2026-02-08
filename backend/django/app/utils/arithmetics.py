import traceback
import logging
import pandas as pd

from app.utils.constants import MT5Timeframe, METALS, OILS, CURRENCY_PAIRS, CRYPTOCURRENCIES
from app.utils.api.data import symbol_info

logger = logging.getLogger(__name__)

def get_price_at_pnl(desired_pnl: float, entry_price: float, order_size_usd: float, leverage: float, type: str, commission: float) -> tuple:
    """
    Calculate the price at which the desired PnL is achieved, with and without commission.

    :param desired_pnl: The desired profit or loss in USD.
    :param entry_price: The entry price of the trade.
    :param order_size_usd: The size of the position in USD.
    :param leverage: The leverage used for the trade.
    :param type: The type of position, either 'long' or 'short'.
    :param commission: The commission in USD.
    :return: A tuple containing two prices:
             - Price with commission
             - Price without commission
    :raises ValueError: If an unknown trade type is provided.
    """
    if type == 'BUY':
        price_including_commission = entry_price * (1 + (desired_pnl + commission) / order_size_usd)
        price_excluding_commission = entry_price * (1 + desired_pnl / order_size_usd)
    elif type == 'SELL':
        price_including_commission = entry_price * (1 - (desired_pnl + commission) / order_size_usd)
        price_excluding_commission = entry_price * (1 - desired_pnl / order_size_usd)
    else:
        raise ValueError(f"Unknown trade type: {type}")

    return price_including_commission, price_excluding_commission

def get_pnl_at_price(current_price: float, entry_price: float, order_size_usd: float, leverage: float, type: str, commission: float) -> tuple:
    if type == 'BUY':
        price_change = (current_price - entry_price) / entry_price
    elif type == 'SELL':
        price_change = (entry_price - current_price) / entry_price
    else:
        raise ValueError(f"Unknown trade type: {type}")
    
    # Calculate gross PNL
    pnl_including_commission = order_size_usd * price_change

    # Subtract commissions
    pnl_excluding_commission = pnl_including_commission - commission
    return pnl_including_commission, pnl_excluding_commission

def calculate_order_size_usd(capital: float, leverage: float) -> float:
    return capital * leverage

def calculate_price_with_spread(price: float, spread_multiplier: float, increase: bool) -> float:
    if increase:
        return price * (1 + spread_multiplier)
    else:
        return price * (1 - spread_multiplier)
    
def calculate_liquidation_price(entry_price: float, leverage: float, type: str) -> float:
    if type == 'BUY':
        liq_p = entry_price * (1 - (1 / leverage))
    elif type == 'SELL':
        liq_p = entry_price * (1 + (1 / leverage))
    else:
        raise ValueError(f"Unknown position type: {type}")
    
    return liq_p


def calculate_trade_volume(open_price: float, current_price: float, current_pnl: float, leverage: float) -> float:
    """
    Calculate the trade volume given the open price, current price, current PNL, and leverage.

    :param open_price: The opening price of the trade
    :param current_price: The current price of the asset
    :param current_pnl: The current profit/loss of the trade in USD
    :param leverage: The leverage used for the trade
    :return: The volume of the trade in USD
    """
    price_change = abs(current_price - open_price) / open_price
    trade_volume = abs(current_pnl / (price_change * leverage))
    return trade_volume

def calculate_order_capital(symbol, volume_lots, leverage, price_open):
    order_size_usd = convert_lots_to_usd(symbol, volume_lots, price_open)
    capital_used = order_size_usd / leverage
    return capital_used

def convert_lots_to_usd(symbol, lots, price_open):
    """
    Convert volume size from lots to USD amount.
    
    :param symbol: The trading symbol (e.g., 'BITCOIN', 'ETHEREUM')
    :param lots: The volume size in lots
    :return: The equivalent USD amount
    """
    # Get the contract size for the symbol
    symbol_info_data = symbol_info(symbol)
    if symbol_info_data is None:
        raise ValueError(f"Symbol {symbol} not found in MetaTrader 5")
    
    contract_size = symbol_info_data.get('trade_contract_size', 100000)
    
    # Calculate the USD amount using the opening price
    usd_amount = lots * contract_size * price_open
    
    return usd_amount

def convert_usd_to_lots(symbol: str, usd_amount: float, type: str) -> float:
    """
    Convert USD amount to lots for a given symbol.

    :param symbol: The trading symbol (e.g., 'BITCOIN', 'ETHEREUM')
    :param usd_amount: The amount in USD to convert
    :param type: The type of order ('BUY' or 'SELL')
    :return: The equivalent amount in lots
    """
    try:
        # Get the symbol information
        symbol_info_data = symbol_info(symbol)
        if symbol_info_data is None:
            raise ValueError(f"Symbol {symbol} not found in MetaTrader 5")
        
        # Ensure that 'ask' and 'bid' are scalar values
        ask_price = symbol_info_data.ask.iloc[0] if isinstance(symbol_info_data.ask, pd.Series) else symbol_info_data.ask
        bid_price = symbol_info_data.bid.iloc[0] if isinstance(symbol_info_data.bid, pd.Series) else symbol_info_data.bid
        
        ask_price = float(ask_price)
        bid_price = float(bid_price)
        
        price_dict = {
            'BUY': ask_price,
            'SELL': bid_price
        }
        
        # Get the contract size and calculate lots
        contract_size = symbol_info_data.get('trade_contract_size', 100000)
        lots = usd_amount / (contract_size * price_dict[type])
        
        # Round to the nearest lot step
        lot_step = symbol_info_data.get('volume_step', 0.01)
        lots = round(lots / lot_step) * lot_step
        
        symbol_info_dict = {
            'ask': ask_price,
            'bid': bid_price,
            'spread': float(symbol_info_data.spread.iloc[0]) if hasattr(symbol_info_data.spread, 'iloc') else float(symbol_info_data.spread),
            'volume': float(symbol_info_data.volume.iloc[0]) if hasattr(symbol_info_data.volume, 'iloc') else float(symbol_info_data.volume),
            'trade_contract_size': contract_size,
            'volume_step': lot_step
        }

        logger.info({
            'message': 'Lots converted from USD to lots',
            'symbol': symbol,
            'symbol_info': symbol_info_dict,
            'usd_amount': usd_amount,
            'type': type,
            'lots': float(lots)  # Convert to float for proper JSON serialization
        })

        return lots
    except Exception as e:
        error_msg = f"Exception in convert_usd_to_lots: {e}\n{traceback.format_exc()}"
        logger.error(error_msg)
        return 0.0  # Return a default value or handle accordingly

def calculate_commission(order_size_usd: float, pair: str) -> float:
    """
    Calculate the total commission for a trade based on the notional value.
    :param order_size_usd: The notional value of the position in USD.
    :return: The total commission for opening and closing the trade.
    """
    try:
        pair_upper = pair.upper()

        # Crypto (0.05%)
        # Check for common crypto tickers
        if any(c in pair_upper for c in ['BTC', 'ETH', 'BNB', 'SOL', 'HBAR', 'DOGE', 'LTC', 'XRP', 'ADA', 'DOT', 'MATIC', 'UNI', 'AVAX', 'LINK', 'ATOM', 'AXS']):
             commission_rate = 0.0005 

        # Commodities / Metals / Oils (0.025%)
        elif any(c in pair_upper for c in ['XAU', 'XAG', 'OIL', 'NG', 'WTI', 'BRN']):
             commission_rate = 0.00025

        # Forex (0.025%) - Fallback for currency pairs
        # Checks if it looks like a currency pair (contains major currencies)
        elif any(c in pair_upper for c in ['USD', 'EUR', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD', 'NZD']):
             commission_rate = 0.00025
        
        else:
            # Fallback for unknown pairs, assume Forex/Metal rate or log warning
            logger.warning(f"Unknown pair type for commission: {pair}. Defaulting to 0.025%")
            commission_rate = 0.00025

        commission = order_size_usd * commission_rate # Total commission for both open and close
        return commission
    except Exception as e:
        error_msg = f"Exception in calculate_commission: {e}\n{traceback.format_exc()}"
        logger.error(error_msg)
