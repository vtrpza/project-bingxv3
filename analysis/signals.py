# analysis/signals.py
"""Trading signal generation based on technical analysis."""

import logging
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from datetime import datetime
from enum import Enum

from config.trading_config import TradingConfig
from analysis.indicators import get_technical_indicators, IndicatorError
from analysis.volume import get_volume_analyzer, VolumeAnalysisError
from utils.logger import get_logger, trading_logger
from utils.formatters import PriceFormatter

logger = get_logger(__name__)


class SignalType(Enum):
    """Trading signal types."""
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"
    STRONG_BUY = "STRONG_BUY"
    STRONG_SELL = "STRONG_SELL"


class SignalRule(Enum):
    """Trading signal rules."""
    MA_CROSSOVER = "ma_crossover"
    MA_DISTANCE = "ma_distance"
    VOLUME_SPIKE = "volume_spike"
    RSI_CONFIRMATION = "rsi_confirmation"


class SignalStrength(Enum):
    """Signal strength levels."""
    WEAK = "WEAK"
    MODERATE = "MODERATE"
    STRONG = "STRONG"
    VERY_STRONG = "VERY_STRONG"


class TradingSignalError(Exception):
    """Exception for trading signal generation errors."""
    pass


class SignalGenerator:
    """Generates trading signals based on technical analysis and volume."""
    
    def __init__(self):
        self.config = TradingConfig()
        self.indicators = get_technical_indicators()
        self.volume_analyzer = get_volume_analyzer()
    
    def analyze_rule_1_crossover(self, candles_2h: List[Dict[str, Any]], 
                                candles_4h: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Rule 1: MA crossover with RSI confirmation."""
        try:
            results = {
                'rule_name': 'MA_CROSSOVER_RSI',
                'triggered': False,
                'signal_type': None,
                'confidence': 0.0,
                'details': {},
                'timeframes_analyzed': [],
            }
            
            timeframe_results = {}
            
            # Analyze 2h timeframe
            if len(candles_2h) >= max(self.config.MM1_PERIOD, self.config.CENTER_PERIOD) + 2:
                try:
                    # Calculate indicators
                    indicators_2h = self.indicators.calculate_all_indicators(candles_2h)
                    
                    # Detect crossover
                    crossover_2h = self.indicators.detect_ma_crossover(candles_2h)
                    
                    # Check RSI
                    rsi_valid = (indicators_2h.get('rsi') and 
                               self.config.is_rsi_in_range(indicators_2h['rsi']))
                    
                    timeframe_results['2h'] = {
                        'indicators': indicators_2h,
                        'crossover': crossover_2h,
                        'rsi_valid': rsi_valid,
                        'signal_valid': crossover_2h is not None and rsi_valid,
                    }
                    
                    results['timeframes_analyzed'].append('2h')
                    
                except Exception as e:
                    logger.warning(f"Error analyzing 2h timeframe for Rule 1: {e}")
                    timeframe_results['2h'] = {'error': str(e)}
            
            # Analyze 4h timeframe
            if len(candles_4h) >= max(self.config.MM1_PERIOD, self.config.CENTER_PERIOD) + 2:
                try:
                    # Calculate indicators
                    indicators_4h = self.indicators.calculate_all_indicators(candles_4h)
                    
                    # Detect crossover
                    crossover_4h = self.indicators.detect_ma_crossover(candles_4h)
                    
                    # Check RSI
                    rsi_valid = (indicators_4h.get('rsi') and 
                               self.config.is_rsi_in_range(indicators_4h['rsi']))
                    
                    timeframe_results['4h'] = {
                        'indicators': indicators_4h,
                        'crossover': crossover_4h,
                        'rsi_valid': rsi_valid,
                        'signal_valid': crossover_4h is not None and rsi_valid,
                    }
                    
                    results['timeframes_analyzed'].append('4h')
                    
                except Exception as e:
                    logger.warning(f"Error analyzing 4h timeframe for Rule 1: {e}")
                    timeframe_results['4h'] = {'error': str(e)}
            
            # Determine overall signal
            valid_signals = []
            for tf, data in timeframe_results.items():
                if data.get('signal_valid', False):
                    crossover = data.get('crossover')
                    if crossover == "BULLISH_CROSS":
                        valid_signals.append(('BUY', tf))
                    elif crossover == "BEARISH_CROSS":
                        valid_signals.append(('SELL', tf))
            
            if valid_signals:
                # Take the signal from the higher timeframe if multiple
                if any(signal[1] == '4h' for signal in valid_signals):
                    primary_signal = next(signal for signal in valid_signals if signal[1] == '4h')
                else:
                    primary_signal = valid_signals[0]
                
                results['triggered'] = True
                results['signal_type'] = primary_signal[0]
                results['confidence'] = 0.7 if primary_signal[1] == '4h' else 0.6
                results['primary_timeframe'] = primary_signal[1]
            
            results['details'] = timeframe_results
            return results
            
        except Exception as e:
            logger.error(f"Error in Rule 1 analysis: {e}")
            return {
                'rule_name': 'MA_CROSSOVER_RSI',
                'triggered': False,
                'signal_type': None,
                'confidence': 0.0,
                'error': str(e),
                'details': {},
                'timeframes_analyzed': [],
            }
    
    def analyze_rule_2_distance(self, candles_2h: List[Dict[str, Any]], 
                               candles_4h: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Rule 2: MA distance without RSI."""
        try:
            results = {
                'rule_name': 'MA_DISTANCE',
                'triggered': False,
                'signal_type': None,
                'confidence': 0.0,
                'details': {},
                'timeframes_analyzed': [],
            }
            
            timeframe_results = {}
            distance_signals = []
            
            # Analyze 2h timeframe
            if len(candles_2h) >= max(self.config.MM1_PERIOD, self.config.CENTER_PERIOD):
                try:
                    indicators_2h = self.indicators.calculate_all_indicators(candles_2h)
                    mm1 = indicators_2h.get('mm1')
                    center = indicators_2h.get('center')
                    
                    if mm1 and center:
                        distance = self.indicators.calculate_ma_distance(mm1, center)
                        is_significant = distance >= self.config.MA_DISTANCE_2H_PERCENT
                        
                        signal_type = None
                        if is_significant:
                            signal_type = "BUY" if mm1 > center else "SELL"
                        
                        timeframe_results['2h'] = {
                            'indicators': indicators_2h,
                            'distance': distance,
                            'threshold': self.config.MA_DISTANCE_2H_PERCENT,
                            'is_significant': is_significant,
                            'signal_type': signal_type,
                        }
                        
                        if is_significant:
                            distance_signals.append((signal_type, '2h', float(distance)))
                    
                    results['timeframes_analyzed'].append('2h')
                    
                except Exception as e:
                    logger.warning(f"Error analyzing 2h timeframe for Rule 2: {e}")
                    timeframe_results['2h'] = {'error': str(e)}
            
            # Analyze 4h timeframe
            if len(candles_4h) >= max(self.config.MM1_PERIOD, self.config.CENTER_PERIOD):
                try:
                    indicators_4h = self.indicators.calculate_all_indicators(candles_4h)
                    mm1 = indicators_4h.get('mm1')
                    center = indicators_4h.get('center')
                    
                    if mm1 and center:
                        distance = self.indicators.calculate_ma_distance(mm1, center)
                        is_significant = distance >= self.config.MA_DISTANCE_4H_PERCENT
                        
                        signal_type = None
                        if is_significant:
                            signal_type = "BUY" if mm1 > center else "SELL"
                        
                        timeframe_results['4h'] = {
                            'indicators': indicators_4h,
                            'distance': distance,
                            'threshold': self.config.MA_DISTANCE_4H_PERCENT,
                            'is_significant': is_significant,
                            'signal_type': signal_type,
                        }
                        
                        if is_significant:
                            distance_signals.append((signal_type, '4h', float(distance)))
                    
                    results['timeframes_analyzed'].append('4h')
                    
                except Exception as e:
                    logger.warning(f"Error analyzing 4h timeframe for Rule 2: {e}")
                    timeframe_results['4h'] = {'error': str(e)}
            
            # Determine overall signal
            if distance_signals:
                # Prioritize 4h timeframe or highest distance
                primary_signal = max(distance_signals, key=lambda x: (x[1] == '4h', x[2]))
                
                results['triggered'] = True
                results['signal_type'] = primary_signal[0]
                results['confidence'] = 0.6 if primary_signal[1] == '4h' else 0.5
                results['primary_timeframe'] = primary_signal[1]
                results['max_distance'] = primary_signal[2]
            
            results['details'] = timeframe_results
            return results
            
        except Exception as e:
            logger.error(f"Error in Rule 2 analysis: {e}")
            return {
                'rule_name': 'MA_DISTANCE',
                'triggered': False,
                'signal_type': None,
                'confidence': 0.0,
                'error': str(e),
                'details': {},
                'timeframes_analyzed': [],
            }
    
    def analyze_rule_3_volume(self, candles_spot: List[Dict[str, Any]], 
                             candles_2h: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Rule 3: Volume spike with MA direction."""
        try:
            results = {
                'rule_name': 'VOLUME_SPIKE',
                'triggered': False,
                'signal_type': None,
                'confidence': 0.0,
                'details': {},
                'timeframes_analyzed': [],
            }
            
            # Analyze volume spike
            volume_analysis = {}
            if len(candles_spot) >= 20:
                try:
                    volume_analysis = self.volume_analyzer.detect_volume_spike(candles_spot)
                    results['timeframes_analyzed'].append('spot')
                except Exception as e:
                    logger.warning(f"Error analyzing volume: {e}")
                    volume_analysis = {'error': str(e)}
            
            # Get MA direction from 2h timeframe
            ma_direction = None
            ma_indicators = {}
            if len(candles_2h) >= max(self.config.MM1_PERIOD, self.config.CENTER_PERIOD):
                try:
                    ma_indicators = self.indicators.calculate_all_indicators(candles_2h)
                    mm1 = ma_indicators.get('mm1')
                    center = ma_indicators.get('center')
                    
                    if mm1 and center:
                        ma_direction = "BUY" if mm1 > center else "SELL"
                    
                    results['timeframes_analyzed'].append('2h')
                    
                except Exception as e:
                    logger.warning(f"Error calculating MA direction: {e}")
                    ma_indicators = {'error': str(e)}
            
            # Determine signal
            volume_spike = volume_analysis.get('is_spike', False)
            if volume_spike and ma_direction:
                results['triggered'] = True
                results['signal_type'] = ma_direction
                results['confidence'] = volume_analysis.get('confidence', 0.5)
            
            results['details'] = {
                'volume_analysis': volume_analysis,
                'ma_indicators': ma_indicators,
                'ma_direction': ma_direction,
            }
            
            return results
            
        except Exception as e:
            logger.error(f"Error in Rule 3 analysis: {e}")
            return {
                'rule_name': 'VOLUME_SPIKE',
                'triggered': False,
                'signal_type': None,
                'confidence': 0.0,
                'error': str(e),
                'details': {},
                'timeframes_analyzed': [],
            }
    
    def generate_trading_signal(self, symbol: str, 
                               candles_spot: List[Dict[str, Any]],
                               candles_2h: List[Dict[str, Any]], 
                               candles_4h: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate comprehensive trading signal based on all rules."""
        try:
            signal_start = datetime.utcnow()
            
            # Analyze all rules
            rule_1_result = await self.analyze_rule_1_crossover(candles_2h, candles_4h)
            rule_2_result = await self.analyze_rule_2_distance(candles_2h, candles_4h)
            rule_3_result = await self.analyze_rule_3_volume(candles_spot, candles_2h)
            
            # Collect triggered rules
            triggered_rules = []
            buy_signals = []
            sell_signals = []
            
            for rule_result in [rule_1_result, rule_2_result, rule_3_result]:
                if rule_result.get('triggered', False):
                    rule_name = rule_result['rule_name']
                    signal_type = rule_result['signal_type']
                    confidence = rule_result['confidence']
                    
                    triggered_rules.append(rule_name)
                    
                    if signal_type == "BUY":
                        buy_signals.append((rule_name, confidence))
                    elif signal_type == "SELL":
                        sell_signals.append((rule_name, confidence))
            
            # Calculate overall signal
            overall_signal = SignalType.NEUTRAL
            overall_confidence = 0.0
            
            if buy_signals and not sell_signals:
                # Pure buy signals
                overall_signal = SignalType.BUY
                overall_confidence = sum(conf for _, conf in buy_signals) / len(buy_signals)
                
                if len(buy_signals) >= 2 or overall_confidence >= 0.7:
                    overall_signal = SignalType.STRONG_BUY
                    
            elif sell_signals and not buy_signals:
                # Pure sell signals
                overall_signal = SignalType.SELL
                overall_confidence = sum(conf for _, conf in sell_signals) / len(sell_signals)
                
                if len(sell_signals) >= 2 or overall_confidence >= 0.7:
                    overall_signal = SignalType.STRONG_SELL
                    
            elif buy_signals and sell_signals:
                # Conflicting signals - take the stronger one
                buy_strength = sum(conf for _, conf in buy_signals)
                sell_strength = sum(conf for _, conf in sell_signals)
                
                if buy_strength > sell_strength * 1.2:  # Buy must be 20% stronger
                    overall_signal = SignalType.BUY
                    overall_confidence = buy_strength / len(buy_signals)
                elif sell_strength > buy_strength * 1.2:  # Sell must be 20% stronger
                    overall_signal = SignalType.SELL
                    overall_confidence = sell_strength / len(sell_signals)
                else:
                    overall_signal = SignalType.NEUTRAL
                    overall_confidence = 0.0
            
            # Determine signal strength
            if overall_confidence >= 0.8:
                signal_strength = SignalStrength.VERY_STRONG
            elif overall_confidence >= 0.6:
                signal_strength = SignalStrength.STRONG
            elif overall_confidence >= 0.4:
                signal_strength = SignalStrength.MODERATE
            else:
                signal_strength = SignalStrength.WEAK
            
            # Calculate analysis duration
            analysis_duration = (datetime.utcnow() - signal_start).total_seconds()
            
            # Create final signal result
            signal_result = {
                'symbol': symbol,
                'timestamp': datetime.utcnow().isoformat(),
                'analysis_duration_seconds': analysis_duration,
                'signal_type': overall_signal.value,
                'signal_strength': signal_strength.value,
                'confidence': round(overall_confidence, 3),
                'rules_triggered': triggered_rules,
                'rules_analysis': {
                    'rule_1_crossover': rule_1_result,
                    'rule_2_distance': rule_2_result,
                    'rule_3_volume': rule_3_result,
                },
                'signal_breakdown': {
                    'buy_signals': buy_signals,
                    'sell_signals': sell_signals,
                    'total_rules_triggered': len(triggered_rules),
                },
                'trading_recommendation': {
                    'should_trade': overall_signal != SignalType.NEUTRAL and overall_confidence >= 0.4,
                    'trade_direction': overall_signal.value if overall_signal != SignalType.NEUTRAL else None,
                    'urgency': signal_strength.value,
                    'risk_level': 'HIGH' if overall_confidence < 0.5 else 'MEDIUM' if overall_confidence < 0.7 else 'LOW',
                },
            }
            
            # Log significant signals
            if overall_signal != SignalType.NEUTRAL and overall_confidence >= 0.5:
                trading_logger.signal_generated(
                    symbol=symbol,
                    signal_type=overall_signal.value,
                    strength=overall_confidence,
                    rules=triggered_rules,
                    indicators={
                        'rules_triggered': len(triggered_rules),
                        'confidence': overall_confidence,
                        'signal_strength': signal_strength.value,
                    }
                )
            
            return signal_result
            
        except Exception as e:
            logger.error(f"Error generating trading signal for {symbol}: {e}")
            return {
                'symbol': symbol,
                'timestamp': datetime.utcnow().isoformat(),
                'signal_type': SignalType.NEUTRAL.value,
                'signal_strength': SignalStrength.WEAK.value,
                'confidence': 0.0,
                'rules_triggered': [],
                'error': str(e),
                'trading_recommendation': {
                    'should_trade': False,
                    'trade_direction': None,
                    'urgency': 'NONE',
                    'risk_level': 'HIGH',
                },
            }
    
    def format_signal_summary(self, signal_result: Dict[str, Any]) -> str:
        """Format signal result into readable summary."""
        try:
            lines = [
                f"=== TRADING SIGNAL: {signal_result['symbol']} ===",
                f"Timestamp: {signal_result['timestamp']}",
                f"Signal: {signal_result['signal_type']} ({signal_result['signal_strength']})",
                f"Confidence: {signal_result['confidence']:.1%}",
                f"Rules Triggered: {', '.join(signal_result['rules_triggered']) if signal_result['rules_triggered'] else 'None'}",
                "",
            ]
            
            # Trading recommendation
            rec = signal_result.get('trading_recommendation', {})
            lines.extend([
                "=== TRADING RECOMMENDATION ===",
                f"Should Trade: {'YES' if rec.get('should_trade', False) else 'NO'}",
                f"Direction: {rec.get('trade_direction', 'N/A')}",
                f"Urgency: {rec.get('urgency', 'N/A')}",
                f"Risk Level: {rec.get('risk_level', 'N/A')}",
                "",
            ])
            
            # Rule breakdown
            if 'rules_analysis' in signal_result:
                lines.append("=== RULES ANALYSIS ===")
                
                for rule_name, rule_data in signal_result['rules_analysis'].items():
                    if rule_data.get('triggered', False):
                        lines.append(f"{rule_name}: TRIGGERED ({rule_data.get('confidence', 0):.1%} confidence)")
                    else:
                        lines.append(f"{rule_name}: Not triggered")
                
                lines.append("")
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"Error formatting signal summary: {e}"


# Global signal generator instance
_signal_generator = None


def get_signal_generator() -> SignalGenerator:
    """Get the global SignalGenerator instance."""
    global _signal_generator
    if _signal_generator is None:
        _signal_generator = SignalGenerator()
    return _signal_generator


# Convenience function for signal generation
async def generate_signal_for_symbol(symbol: str,
                                   candles_spot: List[Dict[str, Any]],
                                   candles_2h: List[Dict[str, Any]], 
                                   candles_4h: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate trading signal for a specific symbol."""
    try:
        generator = get_signal_generator()
        return generator.generate_trading_signal(symbol, candles_spot, candles_2h, candles_4h)
    except Exception as e:
        logger.error(f"Error generating signal for {symbol}: {e}")
        return {
            'symbol': symbol,
            'timestamp': datetime.utcnow().isoformat(),
            'signal_type': SignalType.NEUTRAL.value,
            'signal_strength': SignalStrength.WEAK.value,
            'confidence': 0.0,
            'rules_triggered': [],
            'error': str(e),
        }