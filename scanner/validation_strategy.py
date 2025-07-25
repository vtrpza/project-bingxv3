# scanner/validation_strategy.py
"""Strategy pattern implementation for different validation approaches."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
import asyncio
import logging
from datetime import datetime
from contextlib import AsyncExitStack
from concurrent.futures import ThreadPoolExecutor
import weakref
import gc

from utils.datetime_utils import utc_now
from scanner.scanner_config import get_scanner_config

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Standardized validation result container."""
    
    symbol: str
    is_valid: bool
    reason: Optional[str] = None
    validation_data: Dict[str, Any] = None
    validation_timestamp: datetime = None
    validation_duration_seconds: float = 0.0
    retry_count: int = 0
    error: Optional[Exception] = None
    
    def __post_init__(self):
        if self.validation_timestamp is None:
            self.validation_timestamp = utc_now()
        if self.validation_data is None:
            self.validation_data = {}


class ValidationStrategy(ABC):
    """Abstract base class for validation strategies."""
    
    @abstractmethod
    async def validate_symbols(self, symbols: List[str], validator, **kwargs) -> List[ValidationResult]:
        """Validate a list of symbols and return results."""
        pass
    
    @abstractmethod
    def get_strategy_name(self) -> str:
        """Get the name of this validation strategy."""
        pass


class SequentialValidationStrategy(ValidationStrategy):
    """Sequential validation strategy - processes symbols one by one."""
    
    def get_strategy_name(self) -> str:
        return "sequential"
    
    async def validate_symbols(self, symbols: List[str], validator, **kwargs) -> List[ValidationResult]:
        """Validate symbols sequentially."""
        results = []
        config = get_scanner_config()
        
        logger.info(f"Starting sequential validation of {len(symbols)} symbols")
        
        for i, symbol in enumerate(symbols):
            try:
                start_time = utc_now()
                
                # Validate with timeout
                validation_data = await asyncio.wait_for(
                    validator.validate_asset(symbol),
                    timeout=config.validation_timeout_seconds
                )
                
                duration = (utc_now() - start_time).total_seconds()
                
                result = ValidationResult(
                    symbol=symbol,
                    is_valid=validation_data.get('is_valid', False),
                    reason=validation_data.get('reason'),
                    validation_data=validation_data,
                    validation_duration_seconds=duration
                )
                
                results.append(result)
                
                # Optional delay to prevent overwhelming the API
                if i < len(symbols) - 1:
                    await asyncio.sleep(0.01)  # 10ms delay
                    
            except asyncio.TimeoutError:
                logger.warning(f"Validation timeout for {symbol}")
                results.append(ValidationResult(
                    symbol=symbol,
                    is_valid=False,
                    reason="Validation timeout",
                    error=asyncio.TimeoutError("Validation timeout")
                ))
            except Exception as e:
                logger.error(f"Error validating {symbol}: {e}")
                results.append(ValidationResult(
                    symbol=symbol,
                    is_valid=False,
                    reason=f"Validation error: {str(e)}",
                    error=e
                ))
        
        return results


class ConcurrentValidationStrategy(ValidationStrategy):
    """Concurrent validation strategy - processes symbols in parallel batches."""
    
    def get_strategy_name(self) -> str:
        return "concurrent"
    
    async def validate_symbols(self, symbols: List[str], validator, **kwargs) -> List[ValidationResult]:
        """Validate symbols concurrently in batches with performance optimizations."""
        config = get_scanner_config()
        results = []
        
        logger.info(f"Starting optimized concurrent validation of {len(symbols)} symbols "
                   f"(max_concurrent: {config.max_concurrent_validations})")
        
        # Use eager task factory for performance optimization
        # This executes coroutines synchronously during task construction when possible
        original_factory = None
        loop = asyncio.get_running_loop()
        if hasattr(asyncio, 'eager_task_factory'):
            original_factory = loop.get_task_factory()
            loop.set_task_factory(asyncio.eager_task_factory)
            logger.debug("Enabled eager task factory for validation")
        
        try:
            # Process in optimized batches with adaptive sizing
            batch_size = min(config.batch_size, max(10, len(symbols) // 4))  # Adaptive batch sizing
            
            for i in range(0, len(symbols), batch_size):
                batch = symbols[i:i + batch_size]
                batch_results = await self._validate_batch_concurrent_optimized(batch, validator, config)
                results.extend(batch_results)
                
                # Reduced delay with adaptive timing
                if i + batch_size < len(symbols):
                    # Smaller delay for better throughput, adaptive based on batch size
                    delay = max(0.01, 0.1 * (batch_size / config.batch_size))
                    await asyncio.sleep(delay)
                    
                    # Periodic garbage collection for memory optimization
                    if i % (batch_size * 4) == 0:
                        gc.collect()
        
        finally:
            # Restore original task factory
            if original_factory is not None:
                loop.set_task_factory(original_factory)
        
        return results
    
    async def _validate_batch_concurrent_optimized(self, batch: List[str], validator, config) -> List[ValidationResult]:
        """Validate a batch of symbols concurrently with performance optimizations."""
        # Use BoundedSemaphore for better performance than regular Semaphore
        semaphore = asyncio.BoundedSemaphore(config.max_concurrent_validations)
        
        async def validate_single_optimized(symbol: str) -> ValidationResult:
            # Use async with for cleaner resource management
            async with semaphore:
                return await self._validate_single_with_retry_optimized(symbol, validator, config)
        
        # Create tasks with better memory management using weak references
        tasks = []
        for symbol in batch:
            task = asyncio.create_task(validate_single_optimized(symbol))
            # Set task name for better debugging
            task.set_name(f"validate_{symbol}")
            tasks.append(task)
        
        try:
            # Use asyncio.gather with optimized settings
            # return_exceptions=False for better error propagation
            results = await asyncio.gather(*tasks, return_exceptions=False)
            return results
        except Exception as e:
            # Cancel remaining tasks if one fails
            for task in tasks:
                if not task.done():
                    task.cancel()
            # Wait for cancellation to complete
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
    
    async def _validate_single_with_retry_optimized(self, symbol: str, validator, config) -> ValidationResult:
        """Validate a single symbol with optimized retry logic and memory management."""
        last_error = None
        
        for attempt in range(config.max_retries + 1):
            try:
                start_time = utc_now()
                
                # Use asyncio.wait_for with optimized timeout handling
                try:
                    validation_data = await asyncio.wait_for(
                        validator.validate_asset(symbol),
                        timeout=config.validation_timeout_seconds
                    )
                except asyncio.TimeoutError:
                    # Handle timeout more efficiently
                    raise asyncio.TimeoutError(f"Validation timeout for {symbol} after {config.validation_timeout_seconds}s")
                
                duration = (utc_now() - start_time).total_seconds()
                
                # Optimized result creation with better memory usage
                result = ValidationResult(
                    symbol=symbol,
                    is_valid=validation_data.get('is_valid', False),
                    reason=validation_data.get('reason'),
                    validation_data=validation_data,
                    validation_duration_seconds=duration,
                    retry_count=attempt
                )
                
                # Clear validation_data reference to help with memory management
                validation_data = None
                return result
                
            except asyncio.TimeoutError as e:
                last_error = e
                logger.warning(f"Validation timeout for {symbol} (attempt {attempt + 1}/{config.max_retries + 1})")
                if attempt < config.max_retries:
                    # Optimized exponential backoff with jitter
                    base_delay = config.retry_delay * (1.5 ** attempt)  # More aggressive backoff
                    jitter = base_delay * 0.1  # Add 10% jitter
                    await asyncio.sleep(base_delay + jitter)
                    
            except Exception as e:
                last_error = e
                logger.error(f"Error validating {symbol} (attempt {attempt + 1}/{config.max_retries + 1}): {e}")
                if attempt < config.max_retries:
                    # Optimized exponential backoff with jitter
                    base_delay = config.retry_delay * (1.5 ** attempt)
                    jitter = base_delay * 0.1
                    await asyncio.sleep(base_delay + jitter)
        
        # All retries failed - create error result
        return ValidationResult(
            symbol=symbol,
            is_valid=False,
            reason=f"Validation failed after {config.max_retries + 1} attempts: {str(last_error)}",
            error=last_error,
            retry_count=config.max_retries + 1
        )


class PriorityValidationStrategy(ValidationStrategy):
    """Priority validation strategy - processes priority symbols first."""
    
    def get_strategy_name(self) -> str:
        return "priority"
    
    async def validate_symbols(self, symbols: List[str], validator, **kwargs) -> List[ValidationResult]:
        """Validate symbols with priority processing."""
        config = get_scanner_config()
        
        if not config.enable_priority_processing:
            # Fall back to concurrent strategy if priority processing is disabled
            concurrent_strategy = ConcurrentValidationStrategy()
            return await concurrent_strategy.validate_symbols(symbols, validator, **kwargs)
        
        # Separate priority and regular symbols
        priority_symbols = []
        regular_symbols = []
        
        for symbol in symbols:
            if hasattr(validator, 'criteria') and hasattr(validator.criteria, 'PRIORITY_SYMBOLS'):
                if symbol in validator.criteria.PRIORITY_SYMBOLS:
                    priority_symbols.append(symbol)
                else:
                    regular_symbols.append(symbol)
            else:
                regular_symbols.append(symbol)
        
        logger.info(f"Processing {len(priority_symbols)} priority symbols first, "
                   f"then {len(regular_symbols)} regular symbols")
        
        results = []
        
        # Process priority symbols first
        if priority_symbols:
            concurrent_strategy = ConcurrentValidationStrategy()
            priority_results = await concurrent_strategy.validate_symbols(
                priority_symbols, validator, **kwargs
            )
            results.extend(priority_results)
        
        # Process regular symbols
        if regular_symbols:
            concurrent_strategy = ConcurrentValidationStrategy()
            regular_results = await concurrent_strategy.validate_symbols(
                regular_symbols, validator, **kwargs
            )
            results.extend(regular_results)
        
        return results


class AdaptiveValidationStrategy(ValidationStrategy):
    """Adaptive validation strategy - chooses strategy based on conditions with performance optimization."""
    
    def get_strategy_name(self) -> str:
        return "adaptive"
    
    async def validate_symbols(self, symbols: List[str], validator, **kwargs) -> List[ValidationResult]:
        """Choose validation strategy based on current conditions with system resource awareness."""
        symbol_count = len(symbols)
        config = get_scanner_config()
        
        # Enhanced adaptive logic with system resource awareness
        import psutil
        
        try:
            # Get system resource usage
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory_percent = psutil.virtual_memory().percent
            
            logger.debug(f"System resources: CPU {cpu_percent}%, Memory {memory_percent}%")
            
            # Choose strategy based on symbol count, system load, and available resources
            if symbol_count <= 5 or cpu_percent > 80 or memory_percent > 85:
                # Few symbols or high system load - use sequential for stability
                strategy = SequentialValidationStrategy()
                logger.info(f"Using sequential strategy for {symbol_count} symbols (CPU: {cpu_percent}%, MEM: {memory_percent}%)")
            elif symbol_count <= 50 and cpu_percent < 60 and memory_percent < 70:
                # Medium number with good resources - use optimized concurrent
                strategy = ConcurrentValidationStrategy()
                logger.info(f"Using optimized concurrent strategy for {symbol_count} symbols")
            elif symbol_count > 50:
                # Many symbols - use priority processing with resource management
                strategy = PriorityValidationStrategy()
                logger.info(f"Using priority strategy for {symbol_count} symbols")
            else:
                # Fallback to concurrent with conservative settings
                strategy = ConcurrentValidationStrategy()
                logger.info(f"Using fallback concurrent strategy for {symbol_count} symbols")
                
        except ImportError:
            # psutil not available, use basic adaptive logic
            logger.warning("psutil not available, using basic adaptive strategy")
            if symbol_count <= 10:
                strategy = SequentialValidationStrategy()
                logger.info(f"Using sequential strategy for {symbol_count} symbols")
            elif symbol_count <= 100:
                strategy = ConcurrentValidationStrategy()
                logger.info(f"Using concurrent strategy for {symbol_count} symbols")
            else:
                strategy = PriorityValidationStrategy()
                logger.info(f"Using priority strategy for {symbol_count} symbols")
        
        return await strategy.validate_symbols(symbols, validator, **kwargs)


class HighPerformanceValidationStrategy(ValidationStrategy):
    """High-performance validation strategy optimized for maximum throughput."""
    
    def get_strategy_name(self) -> str:
        return "high_performance"
    
    async def validate_symbols(self, symbols: List[str], validator, **kwargs) -> List[ValidationResult]:
        """Ultra-optimized validation with maximum performance techniques."""
        config = get_scanner_config()
        
        logger.info(f"Starting high-performance validation of {len(symbols)} symbols")
        
        # Set up eager task factory for maximum performance
        loop = asyncio.get_running_loop()
        original_factory = None
        if hasattr(asyncio, 'eager_task_factory'):
            original_factory = loop.get_task_factory()
            loop.set_task_factory(asyncio.eager_task_factory)
        
        try:
            # Use asyncio.TaskGroup for better performance and error handling (Python 3.11+)
            if hasattr(asyncio, 'TaskGroup'):
                return await self._validate_with_task_group(symbols, validator, config)
            else:
                # Fallback to optimized gather for older Python versions
                return await self._validate_with_optimized_gather(symbols, validator, config)
        finally:
            if original_factory is not None:
                loop.set_task_factory(original_factory)
    
    async def _validate_with_task_group(self, symbols: List[str], validator, config) -> List[ValidationResult]:
        """Use TaskGroup for optimal performance (Python 3.11+)."""
        results = []
        semaphore = asyncio.BoundedSemaphore(config.max_concurrent_validations * 2)  # Higher concurrency
        
        # Process in optimized chunks
        chunk_size = min(50, max(10, len(symbols) // 8))  # Dynamic chunk sizing
        
        for i in range(0, len(symbols), chunk_size):
            chunk = symbols[i:i + chunk_size]
            
            async with asyncio.TaskGroup() as tg:
                chunk_tasks = []
                for symbol in chunk:
                    task = tg.create_task(self._validate_single_optimized(symbol, validator, config, semaphore))
                    task.set_name(f"hp_validate_{symbol}")
                    chunk_tasks.append(task)
            
            # Collect results from completed tasks
            chunk_results = [task.result() for task in chunk_tasks]
            results.extend(chunk_results)
            
            # Minimal delay with memory cleanup
            if i + chunk_size < len(symbols):
                await asyncio.sleep(0.001)  # 1ms delay
                if i % (chunk_size * 8) == 0:
                    gc.collect()  # Periodic cleanup
        
        return results
    
    async def _validate_with_optimized_gather(self, symbols: List[str], validator, config) -> List[ValidationResult]:
        """Optimized gather fallback for Python < 3.11."""
        semaphore = asyncio.BoundedSemaphore(config.max_concurrent_validations * 2)
        
        # Create all tasks at once for maximum parallelism
        tasks = [
            asyncio.create_task(self._validate_single_optimized(symbol, validator, config, semaphore))
            for symbol in symbols
        ]
        
        # Set task names for debugging
        for i, task in enumerate(tasks):
            task.set_name(f"hp_validate_{symbols[i]}")
        
        try:
            # Use gather with return_exceptions=False for better error handling
            results = await asyncio.gather(*tasks, return_exceptions=False)
            return results
        except Exception:
            # Cancel remaining tasks
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
    
    async def _validate_single_optimized(self, symbol: str, validator, config, semaphore) -> ValidationResult:
        """Ultra-optimized single validation with minimal overhead."""
        async with semaphore:
            try:
                start_time = utc_now()
                
                # Direct validation call with optimized timeout
                validation_data = await asyncio.wait_for(
                    validator.validate_asset(symbol),
                    timeout=config.validation_timeout_seconds * 0.8  # Tighter timeout for performance
                )
                
                duration = (utc_now() - start_time).total_seconds()
                
                result = ValidationResult(
                    symbol=symbol,
                    is_valid=validation_data.get('is_valid', False),
                    reason=validation_data.get('reason'),
                    validation_data=validation_data,
                    validation_duration_seconds=duration,
                    retry_count=0
                )
                
                return result
                
            except Exception as e:
                return ValidationResult(
                    symbol=symbol,
                    is_valid=False,
                    reason=f"High-performance validation failed: {str(e)}",
                    error=e,
                    retry_count=0
                )


# Strategy factory
class ValidationStrategyFactory:
    """Factory for creating validation strategies."""
    
    _strategies = {
        'sequential': SequentialValidationStrategy,
        'concurrent': ConcurrentValidationStrategy,
        'priority': PriorityValidationStrategy,
        'adaptive': AdaptiveValidationStrategy,
        'high_performance': HighPerformanceValidationStrategy,
    }
    
    @classmethod
    def create_strategy(cls, strategy_name: str) -> ValidationStrategy:
        """Create a validation strategy by name."""
        if strategy_name not in cls._strategies:
            raise ValueError(f"Unknown validation strategy: {strategy_name}. "
                           f"Available strategies: {list(cls._strategies.keys())}")
        
        return cls._strategies[strategy_name]()
    
    @classmethod
    def get_available_strategies(cls) -> List[str]:
        """Get list of available strategy names."""
        return list(cls._strategies.keys())
    
    @classmethod
    def get_default_strategy(cls) -> ValidationStrategy:
        """Get the default validation strategy with performance optimization."""
        # Use high_performance strategy by default for better throughput
        try:
            return cls.create_strategy('high_performance')
        except Exception:
            # Fallback to adaptive if high_performance fails
            logger.warning("High-performance strategy not available, falling back to adaptive")
            return cls.create_strategy('adaptive')