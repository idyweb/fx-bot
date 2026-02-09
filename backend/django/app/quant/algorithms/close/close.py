import traceback
import logging
from datetime import datetime
from time import sleep

import pandas as pd

from app.utils.api.positions import get_positions
from app.utils.api.ticket import get_order_from_ticket, get_deal_from_ticket
from app.utils.constants import TIMEZONE
from app.utils.db.close import close_trade

logger = logging.getLogger(__name__)

import traceback
import logging
from datetime import datetime
from time import sleep

import pandas as pd

from app.utils.api.positions import get_positions
from app.utils.api.ticket import get_order_from_ticket, get_deal_from_ticket
from app.utils.constants import TIMEZONE
from app.utils.db.close import close_trade
from app.nexus.models import Trade

logger = logging.getLogger(__name__)

def close_algorithm():
    """
    Continuously monitors open trades, detects closed trades by comparing 
    Database state (Source of Truth) vs MT5 Terminal state (Open Positions).
    """
    try:
        current_time = datetime.now(TIMEZONE).replace(microsecond=0)

        # 1. Fetch current open positions from MT5
        positions = get_positions()
        
        # Get set of currently open tickets in MT5 (as strings for consistent comparison)
        if positions is not None and not positions.empty:
            # Ensure 'ticket' column is treated as string
            mt5_open_tickets = set(positions['ticket'].astype(str).values)
        else:
            mt5_open_tickets = set()

        # 2. Fetch all trades that the Database thinks are still OPEN
        # We assume 'close_time' being NULL means it's open.
        # We cast transaction_broker_id to string to be safe, though it's CharField.
        db_open_trades = Trade.objects.filter(close_time__isnull=True)
        
        # 3. Identify Discrepancies
        # If a trade is OPEN in DB, but NOT in MT5 positions -> It must have closed.
        
        for trade in db_open_trades:
            ticket_id = str(trade.transaction_broker_id)
            
            if ticket_id not in mt5_open_tickets:
                # This trade is closed in MT5 but open in DB. 
                # We need to fetch its closing details from history.
                
                logger.info(f"Detecting closure for Trade {ticket_id} (Symbol: {trade.symbol})...")
                
                try:
                    # Define usage of 'from_date' to search history. 
                    # Use entry_time (aware) if available, or fall back to recent past.
                    if trade.entry_time:
                        from_date = trade.entry_time - pd.Timedelta(minutes=5)
                    else:
                        from_date = current_time - pd.Timedelta(hours=24)
                        
                    to_date = current_time + pd.Timedelta(minutes=5)

                    # Retrieve the closed order/deal details
                    # closed_order = get_order_from_ticket(ticket_id) # Might not needed if deal has everything
                    closed_deal = get_deal_from_ticket(ticket_id, from_date=from_date, to_date=to_date)

                    if closed_deal is None:
                        # Sometimes deal takes a moment to appear in history or history is partitioned.
                        # However, if it's not in Open Positions, and not in History, where is it?
                        # It might be in the very process of closing.
                        logger.warning(f"Trade {ticket_id} is missing from Open Positions but Deal not found in History yet.")
                        continue

                    # Extract closing details from the Deal
                    # Deal time is usually epoch or datetime. get_deal_from_ticket usually returns dictionary.
                    deal_time = closed_deal.get('time')
                    if isinstance(deal_time, (int, float)):
                        close_time = pd.to_datetime(deal_time, unit='s', utc=True)
                    else:
                        close_time = deal_time if deal_time else current_time
                        
                    close_price = closed_deal.get('price', 0.0)
                    pnl = closed_deal.get('profit', 0.0)
                    commission = closed_deal.get('commission', 0.0)
                    swap = closed_deal.get('swap', 0.0)
                    # total PnL usually includes commission/swap in some views, but 'profit' field is usually raw gross or net depending on broker.
                    # Usually: Profit + Commission + Swap = Net Result. 
                    # Our model has 'pnl' and 'pnl_excluding_commission'.
                    
                    # Let's assume 'profit' from MT5 deal is Gross Profit (price diff * volume).
                    # Actually in MT5 'profit' field usually accounts for price difference.
                    
                    pnl_gross = pnl
                    pnl_net = pnl + commission + swap
                    
                    closing_reason = closed_deal.get('reason', 'CLOSED_BY_SCRIPT')
                    
                    # Update DB
                    closed_trade_record = close_trade(
                        ticket=ticket_id,
                        close_time=close_time,
                        close_price=close_price,
                        pnl=pnl_net, # We likely want Net PnL in the main PnL field? 
                        # Looking at model: pnl and pnl_excluding_commission.
                        # Let's map PnL -> Net, and Excluding -> Gross.
                        pnl_excluding_commission=pnl_gross,
                        closing_reason=str(closing_reason), # Ensure string
                        closed_deal=closed_deal
                    )
                    
                    if closed_trade_record:
                        logger.info(f"Successfully synced close for Trade {ticket_id}. PnL: {pnl_net}")
                    
                except Exception as inner_e:
                    logger.error(f"Error syncing trade {ticket_id}: {inner_e}")
                    # continue to next trade

    except Exception as e:
        error_msg = f"Exception in close_algorithm: {e}\n{traceback.format_exc()}"
        logger.error({"error": error_msg})