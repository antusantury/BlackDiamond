import logging
from datetime import datetime
from typing import Optional, Dict, List
from shared.database import db

logger = logging.getLogger(__name__)

class DisputeManager:
    """Centralized dispute management functionality"""
    
    @staticmethod
    def get_all_disputes(status: str = None, limit: int = 50, offset: int = 0) -> List[Dict]:
        """Get all disputes, optionally filtered by status"""
        try:
            with db._get_connection() as conn:
                cursor = conn.cursor()
                
                base_query = '''
                    SELECT d.*, 
                           ub.username as buyer_username, ub.first_name as buyer_name,
                           us.username as seller_username, us.first_name as seller_name
                    FROM disputes d
                    LEFT JOIN users ub ON d.buyer_id = ub.user_id
                    LEFT JOIN users us ON d.seller_id = us.user_id
                '''
                
                if status and status != 'all':
                    query = base_query + ' WHERE d.status = ? ORDER BY d.created_at DESC LIMIT ? OFFSET ?'
                    cursor.execute(query, (status, limit, offset))
                else:
                    query = base_query + ' ORDER BY d.created_at DESC LIMIT ? OFFSET ?'
                    cursor.execute(query, (limit, offset))
                
                return [dict(row) for row in cursor.fetchall()]
        
        except Exception as e:
            logger.error(f"Error getting disputes: {e}")
            return []
    
    @staticmethod
    def get_dispute_by_id(dispute_id: int) -> Optional[Dict]:
        """Get dispute details by ID"""
        try:
            with db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT d.*, 
                           ub.username as buyer_username, ub.first_name as buyer_name,
                           us.username as seller_username, us.first_name as seller_name
                    FROM disputes d
                    LEFT JOIN users ub ON d.buyer_id = ub.user_id
                    LEFT JOIN users us ON d.seller_id = us.user_id
                    WHERE d.dispute_id = ?
                ''', (dispute_id,))
                
                row = cursor.fetchone()
                return dict(row) if row else None
        
        except Exception as e:
            logger.error(f"Error getting dispute {dispute_id}: {e}")
            return None
    
    @staticmethod
    def update_dispute_status(dispute_id: int, status: str) -> bool:
        """Update dispute status"""
        try:
            with db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE disputes SET status = ? WHERE dispute_id = ?', (status, dispute_id))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating dispute {dispute_id} status: {e}")
            return False
    
    @staticmethod
    def add_dispute_response(dispute_id: int, admin_id: int, response_text: str) -> bool:
        """Add admin response to dispute"""
        try:
            with db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE disputes 
                    SET resolution = ?, resolved_at = ? 
                    WHERE dispute_id = ?
                ''', (response_text, datetime.now().isoformat(), dispute_id))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error adding response to dispute {dispute_id}: {e}")
            return False
    
    @staticmethod
    def get_dispute_count_by_status() -> Dict[str, int]:
        """Get count of disputes by status"""
        try:
            with db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT status, COUNT(*) as count 
                    FROM disputes 
                    GROUP BY status
                ''')
                
                result = {}
                for row in cursor.fetchall():
                    result[row[0]] = row[1]
                
                return result
        except Exception as e:
            logger.error(f"Error getting dispute counts: {e}")
            return {}

    @staticmethod
    def get_disputes_count(status: str = None) -> int:
        """Get total count of disputes, optionally filtered by status"""
        try:
            with db._get_connection() as conn:
                cursor = conn.cursor()
                if status and status != 'all':
                    cursor.execute('SELECT COUNT(*) FROM disputes WHERE status = ?', (status,))
                else:
                    cursor.execute('SELECT COUNT(*) FROM disputes')
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Error getting disputes count: {e}")
            return 0
    
    @staticmethod
    def get_buyer_disputes(buyer_id: int) -> List[Dict]:
        """Get all disputes for a buyer"""
        try:
            with db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT d.*, us.username as seller_username, us.first_name as seller_name
                    FROM disputes d
                    LEFT JOIN users us ON d.seller_id = us.user_id
                    WHERE d.buyer_id = ?
                    ORDER BY d.created_at DESC
                ''', (buyer_id,))
                
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting buyer disputes for {buyer_id}: {e}")
            return []
    
    @staticmethod
    def get_seller_disputes(seller_id: int) -> List[Dict]:
        """Get all disputes for a seller"""
        try:
            with db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT d.*, ub.username as buyer_username, ub.first_name as buyer_name
                    FROM disputes d
                    LEFT JOIN users ub ON d.buyer_id = ub.user_id
                    WHERE d.seller_id = ?
                    ORDER BY d.created_at DESC
                ''', (seller_id,))
                
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting seller disputes for {seller_id}: {e}")
            return []

# Global dispute manager instance
dispute_manager = DisputeManager()
