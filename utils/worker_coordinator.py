#!/usr/bin/env python3
"""
Worker coordination system to prevent rate limiting conflicts
"""

import asyncio
import time
from typing import Dict, Set, Optional
from dataclasses import dataclass
from utils.logger import get_logger

logger = get_logger(__name__)

@dataclass
class WorkerPriority:
    """Worker priority configuration"""
    HIGH = 1    # Critical operations (trading)
    MEDIUM = 2  # Scanner operations  
    LOW = 3     # Analysis/background tasks

class WorkerCoordinator:
    """Coordinates API requests between multiple workers to prevent rate limiting conflicts"""
    
    def __init__(self):
        self.active_workers: Dict[str, Dict] = {}
        self.request_queue = asyncio.Queue()
        self.coordination_lock = asyncio.Lock()
        
        # Worker priorities
        self.worker_priorities = {
            'trading': WorkerPriority.HIGH,
            'scanner': WorkerPriority.MEDIUM,
            'analysis': WorkerPriority.LOW,
        }
        
        # Resource allocation per worker type
        self.resource_allocation = {
            'trading': 0.4,    # 40% of rate limit budget
            'scanner': 0.4,    # 40% of rate limit budget  
            'analysis': 0.2,   # 20% of rate limit budget
        }
        
        self.last_request_times = {}
        
    async def register_worker(self, worker_id: str, worker_type: str):
        """Register a worker with the coordinator"""
        async with self.coordination_lock:
            self.active_workers[worker_id] = {
                'type': worker_type,
                'priority': self.worker_priorities.get(worker_type, WorkerPriority.LOW),
                'requests_made': 0,
                'last_request': None,
                'allocated_budget': self.resource_allocation.get(worker_type, 0.1)
            }
            logger.info(f"Registered worker {worker_id} of type {worker_type}")
    
    async def unregister_worker(self, worker_id: str):
        """Unregister a worker"""
        async with self.coordination_lock:
            if worker_id in self.active_workers:
                del self.active_workers[worker_id]
                logger.info(f"Unregistered worker {worker_id}")
    
    async def request_api_permission(self, worker_id: str, endpoint_category: str = 'market_data') -> bool:
        """Request permission to make an API call"""
        if worker_id not in self.active_workers:
            logger.warning(f"Unknown worker {worker_id} requesting API permission")
            return True  # Allow unknown workers for backwards compatibility
        
        worker_info = self.active_workers[worker_id]
        current_time = time.time()
        
        # Check if worker is within its allocated budget
        if await self._is_within_budget(worker_id, current_time):
            # Update request tracking
            worker_info['requests_made'] += 1
            worker_info['last_request'] = current_time
            return True
        
        # Worker exceeded budget, implement intelligent backoff
        wait_time = await self._calculate_backoff_time(worker_id)
        if wait_time > 0:
            logger.debug(f"Worker {worker_id} waiting {wait_time:.2f}s due to budget limits")
            await asyncio.sleep(wait_time)
        
        return True
    
    async def _is_within_budget(self, worker_id: str, current_time: float) -> bool:
        """Check if worker is within its allocated budget"""
        worker_info = self.active_workers[worker_id]
        window_start = current_time - 10  # 10-second window
        
        # Count recent requests
        recent_requests = 0
        if worker_info['last_request'] and worker_info['last_request'] > window_start:
            recent_requests = worker_info['requests_made']
        
        # Calculate allowed requests for this worker
        max_requests = int(85 * worker_info['allocated_budget'])  # 85 req/10s total budget
        
        return recent_requests < max_requests
    
    async def _calculate_backoff_time(self, worker_id: str) -> float:
        """Calculate intelligent backoff time based on worker priority"""
        worker_info = self.active_workers[worker_id]
        priority = worker_info['priority']
        
        # Higher priority workers get shorter backoffs
        base_backoff = {
            WorkerPriority.HIGH: 0.1,    # 100ms
            WorkerPriority.MEDIUM: 0.2,  # 200ms  
            WorkerPriority.LOW: 0.5,     # 500ms
        }.get(priority, 0.5)
        
        # Add some jitter to prevent thundering herd
        import random
        jitter = random.uniform(0.8, 1.2)
        
        return base_backoff * jitter
    
    async def get_coordinator_stats(self) -> Dict:
        """Get coordination statistics"""
        async with self.coordination_lock:
            return {
                'active_workers': len(self.active_workers),
                'workers': {
                    worker_id: {
                        'type': info['type'],
                        'priority': info['priority'],
                        'requests_made': info['requests_made'],
                        'allocated_budget': info['allocated_budget']
                    }
                    for worker_id, info in self.active_workers.items()
                },
                'total_requests': sum(info['requests_made'] for info in self.active_workers.values())
            }

# Global coordinator instance
_coordinator = None

def get_coordinator() -> WorkerCoordinator:
    """Get the global worker coordinator instance"""
    global _coordinator
    if _coordinator is None:
        _coordinator = WorkerCoordinator()
    return _coordinator

# Decorator for coordinated API calls
def coordinated_request(worker_type: str = 'unknown'):
    """Decorator to coordinate API requests"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            coordinator = get_coordinator()
            worker_id = f"{worker_type}_{id(func)}"
            
            # Register worker if not already registered
            if worker_id not in coordinator.active_workers:
                await coordinator.register_worker(worker_id, worker_type)
            
            # Request permission
            await coordinator.request_api_permission(worker_id)
            
            # Execute the function
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator