"""
Aegis SMC Entry Algorithm - v3.1 (Safety Patch + Enhancements)

The "Triple Threat" Entry System:
1. HTF Bias Filter (H4 Break of Structure)
2. Liquidity Sweep (Stop Hunt Detection)
3. Displacement + FVG (The Entry Zone)

V3 Safety Features:
- Setup Fingerprint: Never trade the same setup twice
- Symbol Cooldown: 1-hour rest per symbol after trade closes
- Dynamic Risk Sizing: 1.5% of balance instead of fixed $
- Drawdown Circuit Breaker: Halt trading if daily loss > 5%

V3.1 Enhancements:
- Trading Session Filter: Only trade during London/NY power hours
- HTF Neutral Rejection: Skip trades when market is choppy
- Floating Point Fix: Round setup_id to prevent mismatches
- Lot Size Floor: Properly handle min 0.01 lots

Engineering Standard: O(n) complexity, Guard Clauses for early exit.
"""
import pandas as pd
import logging
import os
from datetime import timedelta
from dotenv import load_dotenv
from google import genai
from django.utils import timezone
from django.db.models import Sum

from app.utils.api.positions import get_positions
from app.nexus.models import Trade

from app.utils.arithmetics import (
    calculate_order_size_usd, calculate_commission, 
    get_price_at_pnl, convert_usd_to_lots
)
from app.utils.api.data import fetch_data_pos, symbol_info_tick, account_info
from app.utils.api.order import send_market_order
from app.utils.account import have_open_positions_in_symbol
from app.utils.market import is_market_open
from app.quant.indicators.mean_reversion import get_smc_setup
from app.quant.algorithms.mean_reversion.bias import get_market_bias, bias_confirms_signal
from app.quant.algorithms.mean_reversion.config import (
    PAIRS, MAIN_TIMEFRAME, SL_PNL_MULTIPLIER, TP_PNL_MULTIPLIER,
    LEVERAGE, DEVIATION, CAPITAL_PER_TRADE, AI_ENABLED, AI_MODEL,
    RISK_PERCENT_PER_TRADE, SYMBOL_COOLDOWN_HOURS, DAILY_DRAWDOWN_LIMIT_PERCENT,
    SESSION_FILTER_ENABLED, TRADING_SESSIONS, REJECT_NEUTRAL_BIAS,
    MIN_LOT_SIZE, MAX_RISK_PERCENT_OVERRIDE
)
from app.utils.db.create import create_trade
from app.utils.notifications import send_telegram_notification

# WAT Timezone (West Africa Time = UTC+1)
import pytz
WAT = pytz.timezone('Africa/Lagos')

load_dotenv()
logger = logging.getLogger(__name__)
ai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def get_ai_approval(
    pair: str, 
    order_type: str,
    setup_details: dict,
    current_spread: float = 0,
    atr_value: float = 0,
    price_distance: float = 0,
    data_snapshot: str = ""
) -> str:
    """
    The Skeptical AI Controller - Loss Protection Mode.
    
    Optimized for gemini-1.5-flash-8b with strict If/Then rules
    to maximize rejection rate and protect the $130 balance.
    """
    if not AI_ENABLED:
        logger.info(f"[AI] Bypass: Automatically approving {pair}")
        return "GO"

    try:
        # Loss-Protection System Instruction (8b optimized)
        system_instruction = (
            "Role: Institutional Liquidity & Risk Controller (SMC/ICT Specialist). "
            "Objective: Capital Preservation. Protect the $130 balance at all costs. "
            
            "Framework for Analysis (The 'Institutional Filter'): "
            "1. DISPLACEMENT: The move MUST be energetic. Look for large candle bodies "
            "(displacement) leaving the FVG. If candles are small or overlapping (choppy), respond STOP. "
            "2. LIQUIDITY: Verify the 'Sweep Level' is an obvious swing high/low. "
            "If the price is just 'floating' in the middle of a range, respond STOP. "
            "3. MITIGATION: If the price has already spent too much time inside the FVG "
            "(more than 3 candles), the setup is stale. Respond STOP. "
            "4. MOMENTUM: Only approve trades where the immediate 3-candle trend is aggressive. "
            
            "Decision Logic: "
            "- You are looking for 'Textbook' setups only. "
            "- 90% of setups should be REJECTED. "
            "- Bias: If the HTF Bias is not strictly BULLISH/BEARISH, be 2x more skeptical. "
            
            "Constraint: Output exactly ONE word: 'GO' or 'STOP'. No explanation."
        )
        
        # Loss-Protection Prompt with Context
        prompt = f"""
[MARKET CONTEXT]
Symbol: {pair} | Action: {order_type}
Current Spread: {current_spread:.1f} points
Recent Volatility (ATR): {atr_value:.5f}

[SETUP DETAILS]
SMC Setup: {setup_details.get('setup_type', 'UNKNOWN')}
FVG Midpoint: {setup_details.get('fvg_midpoint', 'N/A')}
Sweep Level: {setup_details.get('sweep_level', 'N/A')}
Stop Loss Distance: {price_distance:.5f} ({price_distance / atr_value:.1f}x ATR) 

[RULES - FOLLOW STRICTLY]
- If Stop Loss distance < 1.5x ATR, respond STOP (Too noisy, will get stopped out)
- If the move into FVG was slow/grindy, respond STOP (No displacement)
- If displacement candle is at least 2x size of previous 5 candles avg, consider GO
- Otherwise, default to STOP

[OHLC DATA (Recent Bars)]
{data_snapshot}

Analyze and decide: GO or STOP?"""
        
        response = ai_client.models.generate_content(
            model=AI_MODEL,
            contents=prompt,
            config=genai.types.GenerateContentConfig(system_instruction=system_instruction)
        )
        
        decision = response.text.strip().upper()
        # Sanitize response - default to STOP if unclear
        if "GO" in decision and "STOP" not in decision:
            decision = "GO"
        else:
            decision = "STOP"  # Default to safe option
        
        logger.info(f"[AI] {pair} Analysis -> {decision} (SL/ATR: {price_distance/atr_value:.1f}x)")
        return decision
        
    except Exception as e:
        logger.warning(f"[AI Error] {e} -> Safety Default: STOP")
        return "STOP"  # Changed: Default to STOP on error, not GO


def check_drawdown_circuit_breaker() -> bool:
    """
    V3 Safety: Drawdown Circuit Breaker
    
    If the bot has lost more than DAILY_DRAWDOWN_LIMIT_PERCENT of the starting balance TODAY,
    it will halt trading and send an SOS alert.
    
    Returns True if trading should be HALTED.
    """
    try:
        # Get current account info for starting reference
        acc = account_info()
        if acc is None:
            return False  # Can't check, allow trading
        
        current_balance = acc.get('balance', 0)
        
        # Get today's start (midnight UTC)
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Sum all realized losses TODAY (negative PnL trades)
        daily_losses = Trade.objects.filter(
            close_time__gte=today_start,
            pnl__lt=0
        ).aggregate(total_loss=Sum('pnl'))['total_loss'] or 0
        
        # Daily losses is negative, so take absolute value
        daily_loss_amount = abs(daily_losses)
        
        # Calculate what percentage of current balance this represents
        # Note: This is approximate. Ideally we'd use start-of-day balance.
        if current_balance > 0:
            loss_percent = (daily_loss_amount / current_balance) * 100
        else:
            loss_percent = 0
        
        if loss_percent >= DAILY_DRAWDOWN_LIMIT_PERCENT:
            logger.critical(f"🚨 CIRCUIT BREAKER TRIGGERED: Daily loss {loss_percent:.2f}% >= {DAILY_DRAWDOWN_LIMIT_PERCENT}% limit!")
            send_telegram_notification(
                f"🚨 *CIRCUIT BREAKER ACTIVATED*\n\n"
                f"Daily Loss: *${daily_loss_amount:.2f}* ({loss_percent:.2f}%)\n"
                f"Limit: {DAILY_DRAWDOWN_LIMIT_PERCENT}%\n\n"
                f"⛔ *Trading halted until tomorrow.*\n"
                f"Review your positions and strategy."
            )
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error in circuit breaker check: {e}")
        return False  # On error, allow trading but log it


def is_trading_session_active() -> bool:
    """
    V3.1: Trading Session Filter
    
    Only allows trading during London (8-12 WAT) and New York (13-17 WAT) sessions.
    Asian session (2 AM WAT) has too many fakeouts for SMC strategies.
    
    Returns True if current time is within an active trading session.
    """
    if not SESSION_FILTER_ENABLED:
        return True  # Filter disabled, allow all trades
    
    try:
        now_wat = timezone.now().astimezone(WAT)
        current_hour = now_wat.hour
        
        for session in TRADING_SESSIONS:
            if session['start_hour'] <= current_hour < session['end_hour']:
                return True
        
        return False
    except Exception as e:
        logger.warning(f"Session filter error: {e}. Allowing trade.")
        return True


def entry_algorithm():
    """
    Main entry algorithm implementing the "Triple Threat" SMC strategy.
    
    V3.1 Flow:
    0. Check Circuit Breaker (halt if daily loss > 5%)
    0.5 Check Trading Session (London/NY only)
    1. Skip if market closed or position exists.
    2. Check Symbol Cooldown (1-hour rest after last trade)
    3. Get HTF Bias (H4 BOS) - Reject NEUTRAL
    4. Fetch M15 data and run SMC setup detection.
    5. Check Setup Fingerprint (don't re-trade same setup)
    6. Validate against HTF bias + Inducement check.
    7. Get AI approval.
    8. Dynamic Risk Sizing (1.5% of balance) with lot size floor.
    9. Execute trade.
    """
    try:
        # =================================================================
        # V3 GUARD 0: Drawdown Circuit Breaker
        # =================================================================
        if check_drawdown_circuit_breaker():
            logger.warning("⛔ Trading halted by Circuit Breaker. Exiting entry loop.")
            return
        
        # =================================================================
        # V3.1 GUARD 0.5: Trading Session Filter
        # =================================================================
        if not is_trading_session_active():
            now_wat = timezone.now().astimezone(WAT)
            logger.info(f"[Entry] Outside trading hours ({now_wat.strftime('%H:%M')} WAT). Sessions: London 8-12, NY 13-17.")
            return
        
        # Fetch current positions once for exposure check
        all_positions = get_positions()
        exposed_currencies = set()
        
        if all_positions is not None and not all_positions.empty:
            for _, pos in all_positions.iterrows():
                sym = pos['symbol']
                # extract base/quote assuming standard 6 char (e.g. EURUSDm -> EUR, USD)
                if len(sym) >= 6:
                    exposed_currencies.add(sym[:3])
                    exposed_currencies.add(sym[3:6])

        # Get current account info for dynamic sizing
        acc = account_info()
        current_balance = acc.get('balance', 100) if acc else 100  # Fallback to $100

        for pair in PAIRS:
            # Guard Clause 1: Position or Market Check
            if have_open_positions_in_symbol(pair):
                continue
            if not is_market_open(pair):
                continue
            
            # =================================================================
            # V3 GUARD 1: Symbol Cooldown (1 Hour)
            # =================================================================
            cooldown_cutoff = timezone.now() - timedelta(hours=SYMBOL_COOLDOWN_HOURS)
            last_trade = Trade.objects.filter(symbol=pair).order_by('-entry_time').first()
            
            if last_trade and last_trade.entry_time and last_trade.entry_time > cooldown_cutoff:
                time_since = timezone.now() - last_trade.entry_time
                minutes_left = int((timedelta(hours=SYMBOL_COOLDOWN_HOURS) - time_since).total_seconds() / 60)
                logger.info(f"[Entry] {pair} Skipped: Cooldown active ({minutes_left} min remaining).")
                continue
            
            # Guard Clause 2: Margin Level Safety Check
            if acc is not None and acc.get('margin', 0) > 0 and acc.get('margin_level', 9999) < 500:
                logger.warning(f"⚠️ High Risk: Margin Level at {acc.get('margin_level', 0):.1f}%. Skipping {pair}.")
                continue

            # Guard Clause 3: Currency Exposure Check
            base_curr = pair[:3]
            quote_curr = pair[3:6]
            if base_curr in exposed_currencies or quote_curr in exposed_currencies:
                continue

            # Step 1: Get Higher Timeframe Bias
            htf_bias = get_market_bias(pair, htf_timeframe='H4', bars=100)
            logger.info(f"[Entry] {pair} HTF Bias: {htf_bias}")
            
            # =================================================================
            # V3.1 GUARD: Reject NEUTRAL HTF Bias
            # =================================================================
            if REJECT_NEUTRAL_BIAS and htf_bias == 'NEUTRAL':
                logger.info(f"[Entry] {pair} Skipped: HTF Bias is NEUTRAL (choppy market).")
                continue

            # Step 2: Fetch M15 Data (need more bars for sweep detection)
            df = fetch_data_pos(pair, MAIN_TIMEFRAME, 30)
            if df is None or df.empty:
                continue
            
            # Step 3: Run SMC Setup Detection
            setup = get_smc_setup(df, sweep_lookback=20, displacement_threshold=1.5)
            
            # Guard Clause: No valid setup found
            if setup is None:
                continue
            
            # =================================================================
            # V3 GUARD 2: Setup Fingerprint / Blacklist
            # V3.1 FIX: Round midpoint to prevent floating point mismatches
            # =================================================================
            fvg_midpoint_raw = setup.get('fvg_midpoint', 0)
            # V3.1 FIX: Always round to 5 decimals for forex consistency
            fvg_midpoint = round(fvg_midpoint_raw, 5)
            setup_id = f"{pair}_{fvg_midpoint}"
            
            if Trade.objects.filter(setup_id=setup_id).exists():
                logger.info(f"🚫 [Entry] {pair} Setup {setup_id} already traded. Skipping.")
                continue
            
            # Guard Clause 4: STRICT Inducement Check
            if not setup.get('inducement', {}).get('swept'):
                logger.info(f"[Entry] {pair} Skipped: Inducement not found (Trap avoided).")
                continue
            
            setup_type = setup['setup_type']  # 'BULLISH' or 'BEARISH'
            logger.info(f"[Entry] {pair} SMC Setup Detected: {setup_type}")
            
            # Step 4: Validate against HTF Bias
            if not bias_confirms_signal(htf_bias, setup_type):
                logger.info(f"[Entry] {pair} Skipped: {setup_type} signal conflicts with {htf_bias} bias.")
                continue
            
            # Step 5: Prepare for Position Sizing & AI Analysis
            # (AI call moved to after we have spread/ATR/distance context)
            order_type = 'BUY' if setup_type == 'BULLISH' else 'SELL'
            tick_info = symbol_info_tick(pair)
            
            if tick_info is None or tick_info.empty:
                continue

            last_tick_price = tick_info['ask'].iloc[0] if order_type == 'BUY' else tick_info['bid'].iloc[0]
            price_decimals = len(str(last_tick_price).split('.')[-1])
            
            # Get contract info for lot calculation
            point = tick_info.get('point', pd.Series([0.00001])).iloc[0] if isinstance(tick_info.get('point'), pd.Series) else tick_info.get('point', 0.00001)
            contract_size = tick_info.get('trade_contract_size', pd.Series([100000])).iloc[0] if isinstance(tick_info.get('trade_contract_size'), pd.Series) else tick_info.get('trade_contract_size', 100000)
            
            # =================================================================
            # V4: STRUCTURE-BASED POSITION SIZING
            # The "Professional SMC Formula"
            # =================================================================
            
            # 1. Calculate the Dollar Risk (1.5% of balance)
            risk_amount_usd = (current_balance * RISK_PERCENT_PER_TRADE) / 100
            
            # 2. Get the Structural Stop from the Setup
            # The SMC engine returns the 'sweep_level' (low for bullish, high for bearish)
            structure_sl = setup.get('sweep_level')
            
            if structure_sl is None:
                logger.warning(f"[Entry] {pair} Skipped: No sweep_level found in setup.")
                continue
            
            # 3. Add a "Noise Buffer" (20 points / 2 pips) to avoid stop hunts
            buffer = 20 * point
            if order_type == 'SELL':
                sl_price = structure_sl + buffer  # SL above the high for SELL
            else:  # BUY
                sl_price = structure_sl - buffer  # SL below the low for BUY
            
            # 4. Calculate Distance in Price (not pips)
            price_distance = abs(last_tick_price - sl_price)
            
            # Guard: Ensure minimum distance to avoid invalid stops
            ask = tick_info['ask'].iloc[0]
            bid = tick_info['bid'].iloc[0]
            current_spread = ask - bid
            min_dist = max(50 * point, current_spread * 2)
            
            if price_distance < min_dist:
                logger.info(f"[Entry] {pair} Skipped: SL distance {price_distance:.5f} < minimum {min_dist:.5f}.")
                continue
            
            # Calculate ATR for AI volatility awareness
            import pandas_ta as ta
            atr_series = ta.atr(df['high'], df['low'], df['close'], length=14)
            atr_value = atr_series.iloc[-1] if atr_series is not None and not atr_series.empty else price_distance
            
            # =================================================================
            # AI APPROVAL: The Skeptical Controller (moved here for context)
            # =================================================================
            ai_decision = get_ai_approval(
                pair=pair,
                order_type=order_type,
                setup_details=setup,
                current_spread=current_spread / point,  # Convert to points
                atr_value=atr_value,
                price_distance=price_distance,
                data_snapshot=df.tail(8).to_string()
            )
            
            if ai_decision != "GO":
                logger.info(f"[Entry] {pair} Skipped: AI Controller said STOP.")
                continue
            
            # 5. THE CRITICAL MATH: Position Sizing Formula
            # Lots = RiskAmount / (PriceDistance × ContractSize)
            # Example: $2.00 / (0.0020 distance * 100,000 contract) = 0.01 Lots
            order_volume_lots = risk_amount_usd / (price_distance * contract_size)
            
            # 6. Apply Min Lot Floor & Safety Override
            order_volume_lots = round(max(MIN_LOT_SIZE, order_volume_lots), 2)
            
            # Recalculate actual risk with final lot size
            actual_risk_usd = order_volume_lots * price_distance * contract_size
            actual_risk_percent = (actual_risk_usd / current_balance) * 100 if current_balance > 0 else 0
            
            if actual_risk_percent > MAX_RISK_PERCENT_OVERRIDE:
                logger.warning(f"[Entry] {pair} Skipped: Actual risk {actual_risk_percent:.1f}% > {MAX_RISK_PERCENT_OVERRIDE}% limit.")
                continue
            
            logger.info(f"[Entry] {pair} Position Sizing: ${risk_amount_usd:.2f} risk / ({price_distance:.5f} dist × {contract_size} contract) = {order_volume_lots} lots")
            
            # 7. Calculate TP using 3:1 Risk-Reward Ratio ("Power of 3")
            # Partial close at 40% (~1.2:1) locks profit, then let runner hit 3:1
            tp_distance = price_distance * 3  # Aiming for the 3:1 Sniper shot
            if order_type == 'BUY':
                tp_price = last_tick_price + tp_distance
            else:  # SELL
                tp_price = last_tick_price - tp_distance
            
            # Calculate position size in USD for record keeping
            order_size_usd = order_volume_lots * contract_size * last_tick_price
            order_capital = risk_amount_usd  # For DB: capital at risk
            commission = calculate_commission(order_size_usd, pair)

            order = send_market_order(
                symbol=pair, volume=order_volume_lots, order_type=order_type,
                sl=round(sl_price, price_decimals), tp=round(tp_price, price_decimals),
                deviation=DEVIATION, type_filling="ORDER_FILLING_FOK",
                position_size_usd=order_size_usd, commission=commission, 
                capital=order_capital, leverage=LEVERAGE
            )

            if order is not None:
                # TELEGRAM ALERT with full SMC v3 details
                inducement_status = "✅ SWEPT" if setup.get('inducement', {}).get('swept') else "⚠️ Not found"
                displacement_status = "✅ YES" if setup.get('displacement_found') else "⚠️ Weak"
                
                msg = (
                    f"🚀 *Aegis SMC v3.1 Trade Executed*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔹 *Pair:* `{pair}`\n"
                    f"🔹 *Action:* `{order_type}`\n"
                    f"🔹 *Lots:* `{order_volume_lots}`\n"
                    f"🔹 *Risk:* `${order_capital:.2f}` ({RISK_PERCENT_PER_TRADE}% of ${current_balance:.0f})\n"
                    f"🔹 *Entry:* `{last_tick_price}`\n"
                    f"🚩 *Stop Loss:* `{round(sl_price, price_decimals)}`\n"
                    f"🎯 *Take Profit:* `{round(tp_price, price_decimals)}`\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📊 *HTF Bias:* `{htf_bias}`\n"
                    f"🎯 *Sweep Level:* `{setup.get('sweep_level', 'N/A')}`\n"
                    f"🔥 *Displacement:* {displacement_status}\n"
                    f"🪤 *Inducement:* {inducement_status}\n"
                    f"📍 *Setup ID:* `{setup_id}`\n"
                    f"🤖 _AI Analysis: APPROVED_"
                )
                send_telegram_notification(msg)
                
                # Pass setup_id to create_trade
                create_trade(
                    order, pair, order_capital, order_size_usd, LEVERAGE, 
                    commission, order_type, 'Exness', 'FOREX', 'AEGIS_SMC_V3.1', 
                    MAIN_TIMEFRAME, order_volume_lots, sl_price, tp_price,
                    setup_id=setup_id  # V3: Store fingerprint
                )
                
                logger.info(f"[Entry] {pair} TRADE EXECUTED: {order_type} @ {last_tick_price} | Setup: {setup_id} | Inducement: {inducement_status}")

    except Exception as e:
        logger.error(f"Error in Aegis SMC v3.1 loop: {e}")