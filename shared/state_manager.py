import asyncio
import logging
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

from shared.database import db
from shared.platform_sync import cross_platform_sync

logger = logging.getLogger(__name__)


class ConflictResolutionStrategy(Enum):
    """Strategies for resolving concurrent modifications"""
    LATEST_WINS = "latest_wins"
    MERGE = "merge"
    MANUAL = "manual"
    ABORT = "abort"


@dataclass
class DealState:
    """Represents the current state of a deal"""
    deal_code: str
    status: str
    buyer_id: int
    seller_id: Optional[int]
    amount: float
    currency: str
    last_modified: datetime
    version: int = 1
    pending_changes: Dict[str, Any] = field(default_factory=dict)
    locked_by: Optional[str] = None  # session_id that has lock
    lock_expires: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'deal_code': self.deal_code,
            'status': self.status,
            'buyer_id': self.buyer_id,
            'seller_id': self.seller_id,
            'amount': self.amount,
            'currency': self.currency,
            'last_modified': self.last_modified.isoformat(),
            'version': self.version,
            'pending_changes': self.pending_changes,
            'locked_by': self.locked_by,
            'lock_expires': self.lock_expires.isoformat() if self.lock_expires else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DealState':
        return cls(
            deal_code=data['deal_code'],
            status=data['status'],
            buyer_id=data['buyer_id'],
            seller_id=data.get('seller_id'),
            amount=data['amount'],
            currency=data['currency'],
            last_modified=datetime.fromisoformat(data['last_modified']),
            version=data.get('version', 1),
            pending_changes=data.get('pending_changes', {}),
            locked_by=data.get('locked_by'),
            lock_expires=datetime.fromisoformat(data['lock_expires']) if data.get('lock_expires') else None
        )


class DealStateManager:
    """
    Manages deal state consistency across platforms with conflict resolution
    """

    def __init__(self):
        self._deal_states: Dict[str, DealState] = {}
        self._state_locks: Dict[str, asyncio.Lock] = {}
        self._conflict_resolution_strategy = ConflictResolutionStrategy.LATEST_WINS

    async def get_deal_state(self, deal_code: str) -> Optional[DealState]:
        """Get current deal state, loading from DB if necessary"""
        deal_code = deal_code.upper()

        # Check cache first
        if deal_code in self._deal_states:
            state = self._deal_states[deal_code]
            # Check if state is stale (older than 30 seconds)
            if datetime.now() - state.last_modified > timedelta(seconds=30):
                await self._refresh_deal_state(deal_code)
            return self._deal_states[deal_code]

        # Load from database
        return await self._load_deal_state(deal_code)

    async def _load_deal_state(self, deal_code: str) -> Optional[DealState]:
        """Load deal state from database"""
        try:
            deal = db.get_deal(deal_code)
            if not deal:
                return None

            state = DealState(
                deal_code=deal['deal_code'],
                status=deal['status'],
                buyer_id=deal['buyer_id'],
                seller_id=deal.get('seller_id'),
                amount=float(deal['amount']),
                currency=deal['currency'],
                last_modified=deal.get('updated_at', deal['created_at'])
            )

            self._deal_states[deal_code] = state
            return state

        except Exception as e:
            logger.error(f"Error loading deal state for {deal_code}: {e}")
            return None

    async def _refresh_deal_state(self, deal_code: str):
        """Refresh deal state from database"""
        try:
            deal = db.get_deal(deal_code)
            if deal:
                self._deal_states[deal_code].status = deal['status']
                self._deal_states[deal_code].seller_id = deal.get('seller_id')
                self._deal_states[deal_code].last_modified = deal.get('updated_at', deal['created_at'])
                self._deal_states[deal_code].version += 1
        except Exception as e:
            logger.error(f"Error refreshing deal state for {deal_code}: {e}")

    async def update_deal_state(self, deal_code: str, updates: Dict[str, Any],
                               session_id: str, platform: str) -> bool:
        """Update deal state with conflict resolution"""
        deal_code = deal_code.upper()

        # Get or create lock for this deal
        if deal_code not in self._state_locks:
            self._state_locks[deal_code] = asyncio.Lock()

        async with self._state_locks[deal_code]:
            # Get current state
            current_state = await self.get_deal_state(deal_code)
            if not current_state:
                logger.error(f"Deal {deal_code} not found for state update")
                return False

            # Check for conflicts
            conflict = await self._detect_conflict(current_state, updates, session_id)
            if conflict:
                resolved = await self._resolve_conflict(current_state, updates, conflict, session_id, platform)
                if not resolved:
                    logger.warning(f"Conflict resolution failed for deal {deal_code}")
                    return False

            # Apply updates
            success = await self._apply_state_updates(deal_code, updates, session_id, platform)
            if success:
                # Update cached state
                current_state.last_modified = datetime.now()
                current_state.version += 1

                # Notify subscribers
                await self._notify_state_change(deal_code, updates, platform)

            return success

    async def _detect_conflict(self, current_state: DealState, updates: Dict[str, Any],
                              session_id: str) -> Optional[Dict[str, Any]]:
        """Detect conflicts in state updates"""
        conflicts = {}

        # Check if deal is locked by another session
        if (current_state.locked_by and
            current_state.locked_by != session_id and
            current_state.lock_expires and
            datetime.now() < current_state.lock_expires):
            conflicts['locked'] = {
                'locked_by': current_state.locked_by,
                'expires': current_state.lock_expires
            }

        # Check for concurrent status changes
        if 'status' in updates:
            # Get fresh status from DB to check for concurrent changes
            fresh_deal = db.get_deal(current_state.deal_code)
            if fresh_deal and fresh_deal['status'] != current_state.status:
                conflicts['status_change'] = {
                    'expected': current_state.status,
                    'actual': fresh_deal['status']
                }

        return conflicts if conflicts else None

    async def _resolve_conflict(self, current_state: DealState, updates: Dict[str, Any],
                               conflict: Dict[str, Any], session_id: str, platform: str) -> bool:
        """Resolve conflicts based on strategy"""
        strategy = self._conflict_resolution_strategy

        if strategy == ConflictResolutionStrategy.LATEST_WINS:
            # Always accept the latest change
            logger.info(f"Resolving conflict with LATEST_WINS strategy for deal {current_state.deal_code}")
            return True

        elif strategy == ConflictResolutionStrategy.MERGE:
            # Try to merge changes
            return await self._merge_changes(current_state, updates, conflict)

        elif strategy == ConflictResolutionStrategy.MANUAL:
            # Notify user about conflict and require manual resolution
            await self._notify_conflict(current_state, updates, conflict, session_id, platform)
            return False

        elif strategy == ConflictResolutionStrategy.ABORT:
            # Abort the conflicting operation
            logger.warning(f"Aborting conflicting operation for deal {current_state.deal_code}")
            return False

        return False

    async def _merge_changes(self, current_state: DealState, updates: Dict[str, Any],
                           conflict: Dict[str, Any]) -> bool:
        """Attempt to merge conflicting changes"""
        try:
            # For now, simple merge strategy: non-conflicting fields can be merged
            merged_updates = {}

            # Get fresh data
            fresh_deal = db.get_deal(current_state.deal_code)
            if not fresh_deal:
                return False

            # Merge non-conflicting updates
            for key, value in updates.items():
                if key not in conflict.get('fields', []):
                    merged_updates[key] = value

            # Update with merged changes
            if merged_updates:
                updates.clear()
                updates.update(merged_updates)

            return True

        except Exception as e:
            logger.error(f"Error merging changes for deal {current_state.deal_code}: {e}")
            return False

    async def _notify_conflict(self, current_state: DealState, updates: Dict[str, Any],
                             conflict: Dict[str, Any], session_id: str, platform: str):
        """Notify about conflicts requiring manual resolution"""
        try:
            # Notify the user about the conflict
            conflict_info = {
                'deal_code': current_state.deal_code,
                'conflict_type': list(conflict.keys())[0],
                'attempted_changes': updates,
                'current_state': current_state.to_dict()
            }

            # Send notification
            await cross_platform_sync.publish_event({
                'event_type': 'conflict_detected',
                'deal_code': current_state.deal_code,
                'user_id': current_state.buyer_id,  # Notify buyer
                'platform': platform,
                'timestamp': datetime.now(),
                'data': conflict_info,
                'event_id': f"conflict_{current_state.deal_code}_{int(datetime.now().timestamp())}"
            })

        except Exception as e:
            logger.error(f"Error notifying conflict for deal {current_state.deal_code}: {e}")

    async def _apply_state_updates(self, deal_code: str, updates: Dict[str, Any],
                                 session_id: str, platform: str) -> bool:
        """Apply state updates to database"""
        try:
            # Map updates to database fields
            db_updates = {}
            for key, value in updates.items():
                if key == 'status':
                    db_updates['status'] = value
                elif key == 'seller_id':
                    db_updates['seller_id'] = value
                # Add other mappable fields as needed

            if db_updates:
                success = db.update_deal_status(deal_code, updates.get('status', 'active'))
                if not success:
                    return False

            # Update cached state
            if deal_code in self._deal_states:
                state = self._deal_states[deal_code]
                for key, value in updates.items():
                    if hasattr(state, key):
                        setattr(state, key, value)
                state.last_modified = datetime.now()
                state.version += 1

            return True

        except Exception as e:
            logger.error(f"Error applying state updates for deal {deal_code}: {e}")
            return False

    async def _notify_state_change(self, deal_code: str, updates: Dict[str, Any], platform: str):
        """Notify subscribers about state changes"""
        try:
            # Publish cross-platform event
            event = {
                'event_type': 'deal_state_changed',
                'deal_code': deal_code,
                'platform': platform,
                'timestamp': datetime.now(),
                'data': updates,
                'event_id': f"state_change_{deal_code}_{int(datetime.now().timestamp())}"
            }

            await cross_platform_sync.publish_event(event)

        except Exception as e:
            logger.error(f"Error notifying state change for deal {deal_code}: {e}")

    async def lock_deal(self, deal_code: str, session_id: str, duration_seconds: int = 300) -> bool:
        """Lock deal for exclusive access"""
        deal_code = deal_code.upper()

        state = await self.get_deal_state(deal_code)
        if not state:
            return False

        # Check if already locked
        if (state.locked_by and state.locked_by != session_id and
            state.lock_expires and datetime.now() < state.lock_expires):
            return False

        # Acquire lock
        state.locked_by = session_id
        state.lock_expires = datetime.now() + timedelta(seconds=duration_seconds)

        logger.info(f"Deal {deal_code} locked by session {session_id}")
        return True

    async def unlock_deal(self, deal_code: str, session_id: str) -> bool:
        """Unlock deal"""
        deal_code = deal_code.upper()

        state = await self.get_deal_state(deal_code)
        if not state or state.locked_by != session_id:
            return False

        state.locked_by = None
        state.lock_expires = None

        logger.info(f"Deal {deal_code} unlocked by session {session_id}")
        return True

    def set_conflict_resolution_strategy(self, strategy: ConflictResolutionStrategy):
        """Set conflict resolution strategy"""
        self._conflict_resolution_strategy = strategy
        logger.info(f"Conflict resolution strategy set to: {strategy.value}")

    async def cleanup_expired_locks(self):
        """Clean up expired locks"""
        now = datetime.now()
        expired_deals = []

        for deal_code, state in self._deal_states.items():
            if (state.locked_by and state.lock_expires and
                now > state.lock_expires):
                state.locked_by = None
                state.lock_expires = None
                expired_deals.append(deal_code)

        if expired_deals:
            logger.info(f"Cleaned up expired locks for deals: {expired_deals}")

        return len(expired_deals)

    def get_deal_stats(self, deal_code: str) -> Optional[Dict[str, Any]]:
        """Get statistics for a deal"""
        state = self._deal_states.get(deal_code.upper())
        if not state:
            return None

        return {
            'deal_code': state.deal_code,
            'version': state.version,
            'last_modified': state.last_modified.isoformat(),
            'is_locked': state.locked_by is not None,
            'lock_expires': state.lock_expires.isoformat() if state.lock_expires else None,
            'subscribers': len(cross_platform_sync.get_deal_subscriptions(state.deal_code))
        }


# Global instance
deal_state_manager = DealStateManager()


# Integration functions

async def ensure_deal_state_consistency(deal_code: str) -> bool:
    """Ensure deal state is consistent across platforms"""
    try:
        state = await deal_state_manager.get_deal_state(deal_code)
        if not state:
            return False

        # Compare with database state
        db_deal = db.get_deal(deal_code)
        if not db_deal:
            return False

        # Check for inconsistencies
        if (state.status != db_deal['status'] or
            state.seller_id != db_deal.get('seller_id')):

            logger.warning(f"State inconsistency detected for deal {deal_code}, refreshing...")
            await deal_state_manager._refresh_deal_state(deal_code)
            return False

        return True

    except Exception as e:
        logger.error(f"Error checking deal state consistency for {deal_code}: {e}")
        return False


async def validate_state_transition(deal_code: str, new_status: str,
                                  user_id: int, platform: str) -> bool:
    """Validate if a state transition is allowed"""
    try:
        state = await deal_state_manager.get_deal_state(deal_code)
        if not state:
            return False

        # Check user permissions
        is_buyer = state.buyer_id == user_id
        is_seller = state.seller_id == user_id

        # Define allowed transitions
        allowed_transitions = {
            'pending': ['active', 'cancelled'],
            'active': ['completed', 'cancelled', 'dispute_open'],
            'completed': [],  # Terminal state
            'cancelled': [],  # Terminal state
            'dispute_open': ['completed', 'cancelled']
        }

        current_transitions = allowed_transitions.get(state.status, [])
        if new_status not in current_transitions:
            logger.warning(f"Invalid state transition {state.status} -> {new_status} for deal {deal_code}")
            return False

        # Check role permissions
        if new_status == 'cancelled' and not is_buyer:
            return False

        if new_status == 'completed' and not is_seller:
            return False

        return True

    except Exception as e:
        logger.error(f"Error validating state transition for deal {deal_code}: {e}")
        return False