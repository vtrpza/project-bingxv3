# analysis/volume.py
"""Volume analysis for detecting trading opportunities."""

import logging
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from config.trading_config import TradingConfig
from utils.logger import get_logger
from utils.formatters import PriceFormatter

logger = get_logger(__name__)


class VolumeAnalysisError(Exception):
    """Exception for volume analysis errors."""
    pass


class VolumeAnalyzer:
    """Analyzes trading volume patterns and detects volume spikes."""
    
    def __init__(self):
        self.config = TradingConfig()
    
    def prepare_volume_dataframe(self, candles: List[Dict[str, Any]]) -> pd.DataFrame:
        """Prepare DataFrame for volume analysis."""
        if not candles:
            raise VolumeAnalysisError("No candle data provided")
        
        try:
            df = pd.DataFrame(candles)
            
            # Ensure required columns
            required_cols = ['timestamp', 'volume', 'close']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                raise VolumeAnalysisError(f"Missing required columns: {missing_cols}")
            
            # Convert to numeric
            df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
            df['close'] = pd.to_numeric(df['close'], errors='coerce')
            
            # Handle timestamp
            if df['timestamp'].dtype == 'object':
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            else:
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # Sort and clean
            df = df.sort_values('timestamp').reset_index(drop=True)
            df = df.dropna().reset_index(drop=True)
            
            if len(df) == 0:
                raise VolumeAnalysisError("No valid data after cleaning")
            
            return df
            
        except Exception as e:
            logger.error(f"Error preparing volume DataFrame: {e}")
            raise VolumeAnalysisError(f"Failed to prepare volume data: {e}")
    
    def calculate_volume_statistics(self, candles: List[Dict[str, Any]], 
                                   lookback_periods: int = 20) -> Dict[str, Decimal]:
        """Calculate volume statistics for analysis."""
        try:
            df = self.prepare_volume_dataframe(candles)
            
            if len(df) < lookback_periods:
                lookback_periods = len(df)
            
            # Get recent volume data
            recent_volumes = df['volume'].tail(lookback_periods)
            
            # Calculate statistics
            stats = {
                'current_volume': Decimal(str(df['volume'].iloc[-1])),
                'average_volume': Decimal(str(recent_volumes.mean())),
                'median_volume': Decimal(str(recent_volumes.median())),
                'max_volume': Decimal(str(recent_volumes.max())),
                'min_volume': Decimal(str(recent_volumes.min())),
                'std_volume': Decimal(str(recent_volumes.std())),
                'volume_20ma': Decimal(str(recent_volumes.mean())),
                'periods_analyzed': lookback_periods,
            }
            
            # Calculate derived metrics
            if stats['average_volume'] > 0:
                stats['volume_ratio'] = stats['current_volume'] / stats['average_volume']
                stats['volume_zscore'] = (stats['current_volume'] - stats['average_volume']) / stats['std_volume'] if stats['std_volume'] > 0 else Decimal('0')
            else:
                stats['volume_ratio'] = Decimal('0')
                stats['volume_zscore'] = Decimal('0')
            
            return stats
            
        except Exception as e:
            logger.error(f"Error calculating volume statistics: {e}")
            raise VolumeAnalysisError(f"Failed to calculate volume statistics: {e}")
    
    def detect_volume_spike(self, candles: List[Dict[str, Any]], 
                           threshold: Optional[Decimal] = None,
                           lookback_periods: int = 20) -> Dict[str, Any]:
        """Detect volume spikes based on historical average."""
        threshold = threshold or self.config.VOLUME_SPIKE_THRESHOLD
        
        try:
            stats = self.calculate_volume_statistics(candles, lookback_periods)
            
            # Determine if current volume is a spike
            is_spike = stats['volume_ratio'] >= threshold
            
            # Classify spike intensity
            spike_intensity = "NONE"
            if is_spike:
                ratio = float(stats['volume_ratio'])
                if ratio >= 5.0:
                    spike_intensity = "EXTREME"
                elif ratio >= 3.0:
                    spike_intensity = "HIGH"
                elif ratio >= 2.0:
                    spike_intensity = "MODERATE"
                else:
                    spike_intensity = "LOW"
            
            return {
                'is_spike': is_spike,
                'spike_intensity': spike_intensity,
                'volume_ratio': stats['volume_ratio'],
                'volume_zscore': stats['volume_zscore'],
                'current_volume': stats['current_volume'],
                'average_volume': stats['average_volume'],
                'threshold_used': threshold,
                'lookback_periods': lookback_periods,
                'confidence': min(float(stats['volume_ratio']), 5.0) / 5.0 if is_spike else 0.0,
            }
            
        except Exception as e:
            logger.error(f"Error detecting volume spike: {e}")
            return {
                'is_spike': False,
                'spike_intensity': "NONE",
                'volume_ratio': Decimal('0'),
                'volume_zscore': Decimal('0'),
                'current_volume': Decimal('0'),
                'average_volume': Decimal('0'),
                'threshold_used': threshold,
                'lookback_periods': lookback_periods,
                'confidence': 0.0,
                'error': str(e),
            }
    
    def analyze_volume_trend(self, candles: List[Dict[str, Any]], 
                           periods: int = 10) -> Dict[str, Any]:
        """Analyze volume trend over recent periods."""
        try:
            df = self.prepare_volume_dataframe(candles)
            
            if len(df) < periods:
                periods = len(df)
            
            # Get recent volume data
            recent_volumes = df['volume'].tail(periods).values
            
            # Calculate trend using linear regression
            x = np.arange(len(recent_volumes))
            coeffs = np.polyfit(x, recent_volumes, 1)
            slope = coeffs[0]
            
            # Determine trend direction
            avg_volume = np.mean(recent_volumes)
            relative_slope = slope / avg_volume if avg_volume > 0 else 0
            
            if relative_slope > 0.1:
                trend = "INCREASING"
            elif relative_slope < -0.1:
                trend = "DECREASING"
            else:
                trend = "STABLE"
            
            return {
                'trend': trend,
                'slope': Decimal(str(slope)),
                'relative_slope': Decimal(str(relative_slope)),
                'avg_volume': Decimal(str(avg_volume)),
                'periods_analyzed': periods,
                'trend_strength': min(abs(relative_slope) * 10, 1.0),
            }
            
        except Exception as e:
            logger.error(f"Error analyzing volume trend: {e}")
            return {
                'trend': "UNKNOWN",
                'slope': Decimal('0'),
                'relative_slope': Decimal('0'),
                'avg_volume': Decimal('0'),
                'periods_analyzed': 0,
                'trend_strength': 0.0,
                'error': str(e),
            }
    
    def calculate_volume_price_correlation(self, candles: List[Dict[str, Any]], 
                                         periods: int = 20) -> Dict[str, Any]:
        """Calculate correlation between volume and price movements."""
        try:
            df = self.prepare_volume_dataframe(candles)
            
            if len(df) < periods:
                periods = len(df)
            
            # Get recent data
            recent_data = df.tail(periods)
            
            # Calculate price changes
            price_changes = recent_data['close'].pct_change().dropna()
            volume_changes = recent_data['volume'].pct_change().dropna()
            
            # Align data
            min_length = min(len(price_changes), len(volume_changes))
            if min_length < 5 or price_changes.std() == 0 or volume_changes.std() == 0:
                raise VolumeAnalysisError("Insufficient or constant data for correlation analysis")
            
            price_changes = price_changes.tail(min_length)
            volume_changes = volume_changes.tail(min_length)
            
            # Calculate correlation
            correlation = price_changes.corr(volume_changes)
            
            # Interpret correlation
            if abs(correlation) > 0.7:
                correlation_strength = "STRONG"
            elif abs(correlation) > 0.4:
                correlation_strength = "MODERATE"
            elif abs(correlation) > 0.2:
                correlation_strength = "WEAK"
            else:
                correlation_strength = "NONE"
            
            correlation_direction = "POSITIVE" if correlation > 0 else "NEGATIVE"
            
            return {
                'correlation': Decimal(str(correlation)),
                'correlation_strength': correlation_strength,
                'correlation_direction': correlation_direction,
                'periods_analyzed': min_length,
                'is_significant': abs(correlation) > 0.4,
            }
            
        except Exception as e:
            logger.error(f"Error calculating volume-price correlation: {e}")
            return {
                'correlation': Decimal('0'),
                'correlation_strength': "NONE",
                'correlation_direction': "NEUTRAL",
                'periods_analyzed': 0,
                'is_significant': False,
                'error': str(e),
            }
    
    def detect_volume_breakout(self, candles: List[Dict[str, Any]], 
                              breakout_periods: int = 5) -> Dict[str, Any]:
        """Detect volume breakout patterns."""
        try:
            df = self.prepare_volume_dataframe(candles)
            
            if len(df) < breakout_periods + 10:
                raise VolumeAnalysisError("Insufficient data for breakout detection")
            
            # Calculate volume moving average
            df['volume_ma'] = df['volume'].rolling(window=20).mean()
            
            # Get recent periods
            recent_data = df.tail(breakout_periods)
            
            # Check if recent volumes are consistently above average
            volumes_above_ma = (recent_data['volume'] > recent_data['volume_ma']).sum()
            breakout_threshold = breakout_periods * 0.6  # 60% of periods must be above MA
            
            is_breakout = volumes_above_ma >= breakout_threshold
            
            # Calculate breakout strength
            if is_breakout:
                avg_ratio = (recent_data['volume'] / recent_data['volume_ma']).mean()
                breakout_strength = min(float(avg_ratio - 1), 2.0) / 2.0  # Normalize to 0-1
            else:
                breakout_strength = 0.0
            
            return {
                'is_breakout': is_breakout,
                'breakout_strength': breakout_strength,
                'periods_above_ma': int(volumes_above_ma),
                'total_periods_checked': breakout_periods,
                'breakout_threshold': breakout_threshold,
                'avg_volume_ratio': Decimal(str((recent_data['volume'] / recent_data['volume_ma']).mean())),
            }
            
        except Exception as e:
            logger.error(f"Error detecting volume breakout: {e}")
            return {
                'is_breakout': False,
                'breakout_strength': 0.0,
                'periods_above_ma': 0,
                'total_periods_checked': breakout_periods,
                'breakout_threshold': 0,
                'avg_volume_ratio': Decimal('0'),
                'error': str(e),
            }
    
    def comprehensive_volume_analysis(self, candles: List[Dict[str, Any]], 
                                    symbol: str, timeframe: str) -> Dict[str, Any]:
        """Perform comprehensive volume analysis."""
        try:
            analysis_start = datetime.utcnow()
            
            # Basic volume statistics
            volume_stats = self.calculate_volume_statistics(candles)
            
            # Volume spike detection
            spike_analysis = self.detect_volume_spike(candles)
            
            # Volume trend analysis
            trend_analysis = self.analyze_volume_trend(candles)
            
            # Volume-price correlation
            correlation_analysis = self.calculate_volume_price_correlation(candles)
            
            # Volume breakout detection
            breakout_analysis = self.detect_volume_breakout(candles)
            
            # Overall assessment
            volume_score = 0.0
            
            # Score based on spike
            if spike_analysis['is_spike']:
                volume_score += 0.4 * spike_analysis['confidence']
            
            # Score based on trend
            if trend_analysis['trend'] == "INCREASING":
                volume_score += 0.2 * trend_analysis['trend_strength']
            
            # Score based on correlation
            if correlation_analysis['is_significant']:
                volume_score += 0.2
            
            # Score based on breakout
            if breakout_analysis['is_breakout']:
                volume_score += 0.2 * breakout_analysis['breakout_strength']
            
            volume_score = min(volume_score, 1.0)  # Cap at 1.0
            
            # Determine overall volume condition
            if volume_score >= 0.7:
                volume_condition = "EXCEPTIONAL"
            elif volume_score >= 0.5:
                volume_condition = "HIGH"
            elif volume_score >= 0.3:
                volume_condition = "MODERATE"
            elif volume_score >= 0.1:
                volume_condition = "LOW"
            else:
                volume_condition = "MINIMAL"
            
            analysis_duration = (datetime.utcnow() - analysis_start).total_seconds()
            
            return {
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': datetime.utcnow().isoformat(),
                'analysis_duration_seconds': analysis_duration,
                'volume_condition': volume_condition,
                'volume_score': volume_score,
                'statistics': volume_stats,
                'spike_analysis': spike_analysis,
                'trend_analysis': trend_analysis,
                'correlation_analysis': correlation_analysis,
                'breakout_analysis': breakout_analysis,
                'trading_signals': {
                    'volume_supports_trade': volume_score >= 0.3,
                    'strong_volume_signal': volume_score >= 0.6,
                    'volume_spike_detected': spike_analysis['is_spike'],
                    'volume_trending_up': trend_analysis['trend'] == "INCREASING",
                    'volume_breakout': breakout_analysis['is_breakout'],
                },
            }
            
        except Exception as e:
            logger.error(f"Error in comprehensive volume analysis for {symbol}: {e}")
            return {
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': datetime.utcnow().isoformat(),
                'error': str(e),
                'volume_condition': "ERROR",
                'volume_score': 0.0,
                'trading_signals': {
                    'volume_supports_trade': False,
                    'strong_volume_signal': False,
                    'volume_spike_detected': False,
                    'volume_trending_up': False,
                    'volume_breakout': False,
                },
            }
    
    def format_volume_summary(self, analysis: Dict[str, Any]) -> str:
        """Format volume analysis into readable summary."""
        try:
            lines = [
                f"=== VOLUME ANALYSIS: {analysis['symbol']} ({analysis['timeframe']}) ===",
                f"Timestamp: {analysis['timestamp']}",
                f"Overall Condition: {analysis['volume_condition']}",
                f"Volume Score: {analysis['volume_score']:.2f}/1.00",
                "",
            ]
            
            # Volume statistics
            if 'statistics' in analysis:
                stats = analysis['statistics']
                lines.extend([
                    "=== VOLUME STATISTICS ===",
                    f"Current Volume: {PriceFormatter.format_volume(stats.get('current_volume', 0))}",
                    f"Average Volume: {PriceFormatter.format_volume(stats.get('average_volume', 0))}",
                    f"Volume Ratio: {stats.get('volume_ratio', 0):.2f}x",
                    "",
                ])
            
            # Spike analysis
            if 'spike_analysis' in analysis:
                spike = analysis['spike_analysis']
                lines.extend([
                    "=== VOLUME SPIKE ANALYSIS ===",
                    f"Spike Detected: {'YES' if spike.get('is_spike', False) else 'NO'}",
                    f"Spike Intensity: {spike.get('spike_intensity', 'NONE')}",
                    f"Confidence: {spike.get('confidence', 0):.1%}",
                    "",
                ])
            
            # Trading signals
            if 'trading_signals' in analysis:
                signals = analysis['trading_signals']
                lines.extend([
                    "=== TRADING SIGNALS ===",
                    f"Volume Supports Trade: {'YES' if signals.get('volume_supports_trade', False) else 'NO'}",
                    f"Strong Volume Signal: {'YES' if signals.get('strong_volume_signal', False) else 'NO'}",
                    f"Volume Spike: {'YES' if signals.get('volume_spike_detected', False) else 'NO'}",
                    f"Volume Trending Up: {'YES' if signals.get('volume_trending_up', False) else 'NO'}",
                    f"Volume Breakout: {'YES' if signals.get('volume_breakout', False) else 'NO'}",
                ])
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"Error formatting volume summary: {e}"


# Global volume analyzer instance
_volume_analyzer = None


def get_volume_analyzer() -> VolumeAnalyzer:
    """Get the global VolumeAnalyzer instance."""
    global _volume_analyzer
    if _volume_analyzer is None:
        _volume_analyzer = VolumeAnalyzer()
    return _volume_analyzer


# Convenience function for quick volume analysis
async def analyze_volume_for_symbol(symbol: str, timeframe: str, 
                                  candles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Perform volume analysis for a specific symbol and timeframe."""
    try:
        analyzer = get_volume_analyzer()
        return analyzer.comprehensive_volume_analysis(candles, symbol, timeframe)
    except Exception as e:
        logger.error(f"Error analyzing volume for {symbol} {timeframe}: {e}")
        return {
            'symbol': symbol,
            'timeframe': timeframe,
            'timestamp': datetime.utcnow().isoformat(),
            'error': str(e),
            'volume_condition': "ERROR",
            'volume_score': 0.0,
        }