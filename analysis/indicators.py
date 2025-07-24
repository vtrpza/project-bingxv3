# analysis/indicators.py
"""Technical indicators calculation for trading analysis."""

import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from datetime import datetime

from config.trading_config import TradingConfig
from utils.logger import get_logger
from utils.validators import Validator, ValidationError
from utils.formatters import PriceFormatter

logger = get_logger(__name__)


class IndicatorError(Exception):
    """Exception for indicator calculation errors."""
    pass


class TechnicalIndicators:
    """Technical indicators calculator using pandas and numpy."""
    
    def __init__(self):
        self.config = TradingConfig()
    
    def prepare_dataframe(self, candles: List[Dict[str, Any]]) -> pd.DataFrame:
        """Convert candle data to pandas DataFrame for analysis."""
        if not candles:
            raise IndicatorError("No candle data provided")
        
        try:
            # Convert to DataFrame
            df = pd.DataFrame(candles)
            
            # Ensure required columns exist
            required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                raise IndicatorError(f"Missing required columns: {missing_cols}")
            
            # Convert price columns to float
            price_cols = ['open', 'high', 'low', 'close', 'volume']
            for col in price_cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Handle timestamp
            if df['timestamp'].dtype == 'object':
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            else:
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Sort by timestamp
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            # Remove any rows with NaN values
            df = df.dropna().reset_index(drop=True)
            
            if len(df) == 0:
                raise IndicatorError("No valid data after cleaning")
            
            return df
            
        except Exception as e:
            logger.error(f"Error preparing DataFrame: {e}")
            raise IndicatorError(f"Failed to prepare data: {e}")
    
    def calculate_ema(self, data: pd.Series, period: int) -> pd.Series:
        """Calculate Exponential Moving Average (EMA)."""
        if len(data) < period:
            raise IndicatorError(f"Insufficient data for EMA calculation: {len(data)} < {period}")
        
        try:
            return data.ewm(span=period, adjust=False).mean()
        except Exception as e:
            raise IndicatorError(f"Error calculating EMA: {e}")
    
    def calculate_sma(self, data: pd.Series, period: int) -> pd.Series:
        """Calculate Simple Moving Average (SMA)."""
        if len(data) < period:
            raise IndicatorError(f"Insufficient data for SMA calculation: {len(data)} < {period}")
        
        try:
            return data.rolling(window=period).mean()
        except Exception as e:
            raise IndicatorError(f"Error calculating SMA: {e}")
    
    def calculate_rsi(self, data: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Relative Strength Index (RSI)."""
        if len(data) < period + 1:
            raise IndicatorError(f"Insufficient data for RSI calculation: {len(data)} < {period + 1}")
        
        try:
            delta = data.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            
            # Handle division by zero to prevent NaN
            rs = gain / loss.replace(0, np.finfo(float).eps)  # Replace 0 with small epsilon
            rsi = 100 - (100 / (1 + rs))
            
            # Ensure RSI values are within valid range and handle any remaining NaN
            rsi = rsi.fillna(50)  # Fill NaN with neutral RSI value
            rsi = rsi.clip(0, 100)  # Ensure RSI is between 0-100
            
            return rsi
        except Exception as e:
            raise IndicatorError(f"Error calculating RSI: {e}")
    
    def calculate_mm1(self, candles: List[Dict[str, Any]], period: Optional[int] = None) -> Decimal:
        """Calculate MM1 (fast EMA) - latest value only."""
        period = period or self.config.MM1_PERIOD
        
        try:
            df = self.prepare_dataframe(candles)
            ema = self.calculate_ema(df['close'], period)
            latest_value = ema.iloc[-1]
            
            if pd.isna(latest_value):
                raise IndicatorError("MM1 calculation resulted in NaN")
            
            return Decimal(str(round(latest_value, 8)))
            
        except Exception as e:
            logger.error(f"Error calculating MM1: {e}")
            raise IndicatorError(f"Failed to calculate MM1: {e}")
    
    def calculate_center(self, candles: List[Dict[str, Any]], period: Optional[int] = None) -> Decimal:
        """Calculate Center (slow EMA) - latest value only."""
        period = period or self.config.CENTER_PERIOD
        
        try:
            df = self.prepare_dataframe(candles)
            ema = self.calculate_ema(df['close'], period)
            latest_value = ema.iloc[-1]
            
            if pd.isna(latest_value):
                raise IndicatorError("Center calculation resulted in NaN")
            
            return Decimal(str(round(latest_value, 8)))
            
        except Exception as e:
            logger.error(f"Error calculating Center: {e}")
            raise IndicatorError(f"Failed to calculate Center: {e}")
    
    def calculate_rsi_value(self, candles: List[Dict[str, Any]], period: Optional[int] = None) -> Decimal:
        """Calculate RSI - latest value only."""
        period = period or self.config.RSI_PERIOD
        
        try:
            df = self.prepare_dataframe(candles)
            rsi = self.calculate_rsi(df['close'], period)
            latest_value = rsi.iloc[-1]
            
            if pd.isna(latest_value):
                raise IndicatorError("RSI calculation resulted in NaN")
            
            # Ensure RSI is within valid range (0-100)
            latest_value = max(0, min(100, latest_value))
            
            return Decimal(str(round(latest_value, 2)))
            
        except Exception as e:
            logger.error(f"Error calculating RSI: {e}")
            raise IndicatorError(f"Failed to calculate RSI: {e}")
    
    def calculate_volume_sma(self, candles: List[Dict[str, Any]], period: Optional[int] = None) -> Decimal:
        """Calculate Volume Simple Moving Average."""
        period = period or self.config.VOLUME_SMA_PERIOD
        
        try:
            df = self.prepare_dataframe(candles)
            volume_sma = self.calculate_sma(df['volume'], period)
            latest_value = volume_sma.iloc[-1]
            
            if pd.isna(latest_value):
                raise IndicatorError("Volume SMA calculation resulted in NaN")
            
            return Decimal(str(round(latest_value, 8)))
            
        except Exception as e:
            logger.error(f"Error calculating Volume SMA: {e}")
            raise IndicatorError(f"Failed to calculate Volume SMA: {e}")
    
    def calculate_all_indicators(self, candles: List[Dict[str, Any]]) -> Dict[str, Decimal]:
        """Calculate all indicators for given candle data."""
        try:
            if not candles:
                raise IndicatorError("No candle data provided")
            
            results = {}
            
            # Calculate MM1 (Fast EMA)
            try:
                results['mm1'] = self.calculate_mm1(candles)
            except IndicatorError as e:
                logger.warning(f"Failed to calculate MM1: {e}")
                results['mm1'] = None
            
            # Calculate Center (Slow EMA)
            try:
                results['center'] = self.calculate_center(candles)
            except IndicatorError as e:
                logger.warning(f"Failed to calculate Center: {e}")
                results['center'] = None
            
            # Calculate RSI
            try:
                results['rsi'] = self.calculate_rsi_value(candles)
            except IndicatorError as e:
                logger.warning(f"Failed to calculate RSI: {e}")
                results['rsi'] = None
            
            # Calculate Volume SMA
            try:
                results['volume_sma'] = self.calculate_volume_sma(candles)
            except IndicatorError as e:
                logger.warning(f"Failed to calculate Volume SMA: {e}")
                results['volume_sma'] = None
            
            return results
            
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            raise IndicatorError(f"Failed to calculate indicators: {e}")
    
    def detect_ma_crossover(self, candles: List[Dict[str, Any]], 
                           min_periods: int = 2) -> Optional[str]:
        """Detect moving average crossover (bullish or bearish)."""
        try:
            if len(candles) < max(self.config.MM1_PERIOD, self.config.CENTER_PERIOD) + min_periods:
                return None
            
            df = self.prepare_dataframe(candles)
            
            # Calculate both MAs for recent periods
            mm1 = self.calculate_ema(df['close'], self.config.MM1_PERIOD)
            center = self.calculate_ema(df['close'], self.config.CENTER_PERIOD)
            
            # Check for crossover in last few periods
            if len(mm1) < min_periods or len(center) < min_periods:
                return None
            
            # Current and previous values
            mm1_curr = mm1.iloc[-1]
            mm1_prev = mm1.iloc[-2]
            center_curr = center.iloc[-1]
            center_prev = center.iloc[-2]
            
            # Check for crossover
            if mm1_prev <= center_prev and mm1_curr > center_curr:
                return "BULLISH_CROSS"
            elif mm1_prev >= center_prev and mm1_curr < center_curr:
                return "BEARISH_CROSS"
            
            return None
            
        except Exception as e:
            logger.error(f"Error detecting MA crossover: {e}")
            return None
    
    def calculate_ma_distance(self, mm1: Decimal, center: Decimal) -> Decimal:
        """Calculate percentage distance between moving averages."""
        try:
            if not mm1 or not center or center == 0:
                return Decimal('0')
            
            # Use Decimal arithmetic throughout to avoid type mixing
            distance = abs(mm1 - center) / center
            # Round using Decimal quantize to avoid float conversion
            return distance.quantize(Decimal('0.000001'))
            
        except Exception as e:
            logger.error(f"Error calculating MA distance: {e}")
            return Decimal('0')
    
    def is_ma_distance_significant(self, mm1: Decimal, center: Decimal, 
                                  timeframe: str) -> bool:
        """Check if MA distance is significant for trading signal."""
        try:
            distance = self.calculate_ma_distance(mm1, center)
            threshold = self.config.get_ma_distance_threshold(timeframe)
            
            return distance >= threshold
            
        except Exception as e:
            logger.error(f"Error checking MA distance significance: {e}")
            return False
    
    def validate_indicators(self, indicators: Dict[str, Decimal]) -> Dict[str, bool]:
        """Validate calculated indicators are within expected ranges."""
        validation_results = {}
        
        # Validate MM1
        mm1 = indicators.get('mm1')
        validation_results['mm1_valid'] = (
            mm1 is not None and 
            mm1 > 0 and 
            mm1 < Decimal('1000000')  # Reasonable upper bound
        )
        
        # Validate Center
        center = indicators.get('center')
        validation_results['center_valid'] = (
            center is not None and 
            center > 0 and 
            center < Decimal('1000000')  # Reasonable upper bound
        )
        
        # Validate RSI
        rsi = indicators.get('rsi')
        validation_results['rsi_valid'] = (
            rsi is not None and 
            Decimal('0') <= rsi <= Decimal('100')
        )
        
        # Validate Volume SMA
        volume_sma = indicators.get('volume_sma')
        validation_results['volume_sma_valid'] = (
            volume_sma is not None and 
            volume_sma >= 0
        )
        
        # Cross-validate MA relationship
        if mm1 is not None and center is not None:
            # Distance should be reasonable (not more than 50% difference)
            distance = self.calculate_ma_distance(mm1, center)
            validation_results['ma_distance_reasonable'] = distance <= Decimal('0.5')
        else:
            validation_results['ma_distance_reasonable'] = False
        
        return validation_results
    
    def get_indicator_summary(self, indicators: Dict[str, Decimal], 
                            timeframe: str) -> Dict[str, Any]:
        """Get formatted summary of indicators."""
        try:
            mm1 = indicators.get('mm1')
            center = indicators.get('center')
            rsi = indicators.get('rsi')
            volume_sma = indicators.get('volume_sma')
            
            # Calculate derived metrics
            ma_distance = None
            ma_direction = None
            ma_distance_significant = False
            
            if mm1 and center:
                ma_distance = self.calculate_ma_distance(mm1, center)
                ma_direction = "ABOVE" if mm1 > center else "BELOW"
                ma_distance_significant = self.is_ma_distance_significant(mm1, center, timeframe)
            
            # RSI analysis
            rsi_condition = None
            if rsi:
                if rsi <= self.config.RSI_MIN:
                    rsi_condition = "OVERSOLD"
                elif rsi >= self.config.RSI_MAX:
                    rsi_condition = "OVERBOUGHT"
                elif self.config.is_rsi_in_range(rsi):
                    rsi_condition = "NEUTRAL"
                else:
                    rsi_condition = "OUT_OF_RANGE"
            
            return {
                'timeframe': timeframe,
                'timestamp': datetime.utcnow().isoformat(),
                'indicators': {
                    'mm1': PriceFormatter.format_price(mm1) if mm1 else None,
                    'center': PriceFormatter.format_price(center) if center else None,
                    'rsi': PriceFormatter.format_price(rsi, 2) if rsi else None,
                    'volume_sma': PriceFormatter.format_volume(volume_sma) if volume_sma else None,
                },
                'analysis': {
                    'ma_distance': PriceFormatter.format_percentage(ma_distance * 100) if ma_distance else None,
                    'ma_direction': ma_direction,
                    'ma_distance_significant': ma_distance_significant,
                    'rsi_condition': rsi_condition,
                    'rsi_in_trading_range': self.config.is_rsi_in_range(rsi) if rsi else False,
                },
                'validation': self.validate_indicators(indicators),
            }
            
        except Exception as e:
            logger.error(f"Error creating indicator summary: {e}")
            return {
                'timeframe': timeframe,
                'timestamp': datetime.utcnow().isoformat(),
                'error': str(e),
                'indicators': {},
                'analysis': {},
                'validation': {},
            }


# Global technical indicators instance
_technical_indicators = None


def get_technical_indicators() -> TechnicalIndicators:
    """Get the global TechnicalIndicators instance."""
    global _technical_indicators
    if _technical_indicators is None:
        _technical_indicators = TechnicalIndicators()
    return _technical_indicators


# Convenience functions for direct calculation
async def calculate_indicators_for_symbol(symbol: str, timeframe: str, 
                                        candles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate indicators for a specific symbol and timeframe."""
    try:
        indicators = get_technical_indicators()
        
        # Calculate all indicators
        results = indicators.calculate_all_indicators(candles)
        
        # Get summary with analysis
        summary = indicators.get_indicator_summary(results, timeframe)
        
        # Add symbol information
        summary['symbol'] = symbol
        summary['candles_analyzed'] = len(candles)
        
        return summary
        
    except Exception as e:
        logger.error(f"Error calculating indicators for {symbol} {timeframe}: {e}")
        return {
            'symbol': symbol,
            'timeframe': timeframe,
            'timestamp': datetime.utcnow().isoformat(),
            'error': str(e),
            'indicators': {},
            'analysis': {},
            'validation': {},
        }