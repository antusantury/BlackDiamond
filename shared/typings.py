from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import (
    Dict, List, Optional, Union, Any, Tuple, Generic, TypeVar,
    Protocol, Literal
)


# === CORE ENUMS ===

class LanguageCode(Enum):
    """Supported language codes"""
    ENGLISH = "en"
    UKRAINIAN = "ua"
    CHINESE = "zh"


class DealStatus(Enum):
    """Deal lifecycle statuses"""
    PENDING = "pending"
    ACTIVE = "active"
    FUNDED = "funded"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    DISPUTED = "dispute_open"


class PaymentStatus(Enum):
    """Payment statuses"""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REFUNDED = "refunded"


class Currency(Enum):
    """Supported cryptocurrencies"""
    USDT = "USDT"
    TON = "TON"
    ETH = "ETH"


class NotificationType(Enum):
    """Notification types"""
    PAYMENT = "payment"
    DEAL = "deal"
    SYSTEM = "system"
    SECURITY = "security"


class UserRole(Enum):
    """User roles and permissions"""
    USER = "user"
    ADMIN = "admin"
    MODERATOR = "moderator"


class ErrorSeverity(Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class PaymentMethod(Enum):
    """Payment methods"""
    BLOCKCHAIN = "blockchain"
    BALANCE = "balance"
    ESCROW = "escrow"


class QRFormat(Enum):
    """QR code formats"""
    STANDARD = "standard"
    BRANDED = "branded"
    MINI = "mini"
    BASE64 = "base64"


# === CORE DATACLASSES ===

@dataclass
class User:
    """User entity with complete profile information"""
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    language: LanguageCode = LanguageCode.ENGLISH
    avatar_url: Optional[str] = None
    registered_date: datetime = field(default_factory=datetime.now)
    deals_count: int = 0
    total_deal_amount: Decimal = Decimal("0.00")
    is_banned: bool = False
    balance: Decimal = Decimal("0.00")
    role: UserRole = UserRole.USER
    last_activity: Optional[datetime] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    verification_level: int = 0  # 0 = none, 1 = basic, 2 = verified


@dataclass
class Deal:
    """Deal entity with complete transaction information"""
    deal_code: str
    buyer_id: int
    seller_id: Optional[int] = None
    amount: Decimal = Decimal("0.00")
    currency: Currency = Currency.USDT
    status: DealStatus = DealStatus.ACTIVE
    description: Optional[str] = None
    product_link: Optional[str] = None
    image_link: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    seller_joined_at: Optional[datetime] = None
    payment_confirmed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None
    commission_amount: Decimal = Decimal("0.00")
    seller_amount: Decimal = Decimal("0.00")
    payout_method: Optional[str] = None
    escrow_address: Optional[str] = None
    payment_tx_hash: Optional[str] = None
    is_automatic: bool = False


@dataclass
class Payment:
    """Payment entity with blockchain transaction details"""
    payment_id: str
    checkout_id: str
    tx_hash: Optional[str] = None
    amount: Decimal = Decimal("0.00")
    currency: Currency = Currency.USDT
    status: PaymentStatus = PaymentStatus.PENDING
    confirmations: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    confirmed_at: Optional[datetime] = None
    escrow_address: Optional[str] = None
    payment_memo: Optional[str] = None
    expires_at: Optional[datetime] = None
    gas_fee: Optional[Decimal] = None
    network_fee: Optional[Decimal] = None


@dataclass
class Notification:
    """Notification entity for user communications"""
    id: Optional[int] = None
    user_id: int = 0
    type: NotificationType = NotificationType.SYSTEM
    title: str = ""
    message: str = ""
    action_url: Optional[str] = None
    read: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    priority: int = 0  # 0 = low, 1 = normal, 2 = high
    metadata: Dict[str, Any] = field(default_factory=dict)




@dataclass
class Settings:
    """Application settings"""
    id: int = 1
    commission_rate: Decimal = Decimal("0.02")  # 2%
    min_deal_amount: Decimal = Decimal("1.00")
    max_deal_amount: Decimal = Decimal("10000.00")
    auto_confirm_timeout: int = 3600  # 1 hour in seconds
    currency_update_interval: int = 300  # 5 minutes
    maintenance_mode: bool = False
    max_daily_deals: int = 50
    verification_required: bool = True
    supported_currencies: List[Currency] = field(default_factory=lambda: [Currency.USDT, Currency.TON])


@dataclass
class QRCode:
    """QR code generation result"""
    checkout_id: str
    format: QRFormat
    url: str
    base64_data: Optional[str] = None
    file_path: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None


@dataclass
class RateLimit:
    """Rate limiting configuration"""
    key: str
    count: int = 0
    window_start: int = 0
    window_seconds: int = 3600
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class ErrorContext:
    """Error handling context"""
    service: str
    operation: str
    correlation_id: Optional[str] = None
    user_id: Optional[int] = None
    request_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


# === GENERIC TYPES ===

T = TypeVar('T')
Result = Union[T, Exception]


class SuccessResult(Generic[T]):
    """Generic success result wrapper"""
    def __init__(self, data: T, message: Optional[str] = None):
        self.data = data
        self.message = message or "Success"
        self.success = True
    
    @classmethod
    def from_data(cls, data: T) -> 'SuccessResult[T]':
        return cls(data)


class ErrorResult:
    """Generic error result wrapper"""
    def __init__(self, error: Union[str, Exception], code: Optional[int] = None):
        self.error = error if isinstance(error, str) else str(error)
        self.code = code
        self.success = False


class PaginatedResult(Generic[T]):
    """Generic paginated result"""
    def __init__(
        self, 
        items: List[T], 
        total: int, 
        page: int, 
        per_page: int,
        has_next: bool = False,
        has_prev: bool = False
    ):
        self.items = items
        self.total = total
        self.page = page
        self.per_page = per_page
        self.pages = (total + per_page - 1) // per_page
        self.has_next = has_next
        self.has_prev = has_prev


# === API TYPES ===

@dataclass
class APIResponse:
    """Standard API response format"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    message: Optional[str] = None
    code: Optional[int] = None
    correlation_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CreateDealRequest:
    """Create deal API request"""
    amount: Decimal
    currency: Currency
    description: Optional[str] = None
    product_link: Optional[str] = None
    image_link: Optional[str] = None
    is_automatic: bool = False


@dataclass
class CreatePaymentRequest:
    """Create payment API request"""
    deal_code: str
    amount: Decimal
    currency: Currency
    payment_method: PaymentMethod = PaymentMethod.BLOCKCHAIN


@dataclass
class CheckoutResponse:
    """Payment checkout response"""
    checkout_id: str
    deal_code: str
    escrow_address: str
    amount: Decimal
    currency: Currency
    commission_amount: Decimal
    seller_amount: Decimal
    qr_codes: Dict[str, str]
    expires_at: datetime
    status: PaymentStatus
    payment_memo: Optional[str] = None
    qr_code_base64: Optional[str] = None
    blockchain_tx: Optional[str] = None


# === CONFIGURATION TYPES ===

@dataclass
class DatabaseConfig:
    """Database configuration"""
    path: str
    pool_min_size: int = 5
    pool_max_size: int = 20
    connection_timeout: int = 30
    wal_mode: bool = True
    foreign_keys: bool = True
    cache_size: int = 10000
    temp_store: str = "memory"


@dataclass
class BlockchainConfig:
    """Blockchain configuration"""
    tron_api_key: Optional[str] = None
    ton_api_key: Optional[str] = None
    tron_explorer_url: str = "https://tronscan.org"
    ton_explorer_url: str = "https://tonscan.org"
    tron_api_url: str = "https://api.trongrid.io"
    ton_api_url: str = "https://toncenter.com/api/v2"
    min_confirmations: int = 1
    usdt_contract: str = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"


@dataclass
class AppConfig:
    """Application configuration"""
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 5000
    secret_key: str = ""
    session_timeout: int = 3600
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    timezone: str = "UTC"
    log_level: str = "INFO"
    maintenance_mode: bool = False
    admin_ids: List[int] = field(default_factory=list)


# === UTILITY TYPES ===

@dataclass
class HealthStatus:
    """Health check status"""
    status: Literal["healthy", "degraded", "unhealthy"]
    timestamp: datetime = field(default_factory=datetime.now)
    services: Dict[str, str] = field(default_factory=dict)
    version: Optional[str] = None
    uptime: Optional[float] = None


@dataclass
class CircuitStatus:
    """Circuit breaker status"""
    name: str
    state: CircuitState
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    next_attempt_time: Optional[datetime] = None
    success_count: int = 0


# === PROTOCOLS ===

class DatabaseProtocol(Protocol):
    """Database interface protocol"""
    def get_user(self, user_id: int) -> Optional[User]: ...
    def create_user(self, user_data: Dict[str, Any]) -> bool: ...
    def get_deal(self, deal_code: str) -> Optional[Deal]: ...
    def create_deal(self, deal_data: Dict[str, Any]) -> bool: ...
    def update_deal_status(self, deal_code: str, status: DealStatus) -> bool: ...
    def get_payment(self, payment_id: str) -> Optional[Payment]: ...
    def create_payment(self, payment_data: Dict[str, Any]) -> bool: ...


class PaymentProcessorProtocol(Protocol):
    """Payment processor interface protocol"""
    def create_payment(self, deal_code: str, amount: Decimal, currency: Currency) -> Optional[CheckoutResponse]: ...
    def check_payment_status(self, checkout_id: str) -> Tuple[bool, str]: ...
    def process_deal_payment(self, deal_code: str, amount: Decimal, currency: Currency) -> Optional[CheckoutResponse]: ...


class LocalizationProtocol(Protocol):
    """Localization service interface protocol"""
    def get_text(self, key: str, language: LanguageCode, **kwargs) -> str: ...
    
    @property
    def languages(self) -> List[LanguageCode]:
        """Supported languages list"""
        ...
    
    @property
    def default_language(self) -> LanguageCode:
        """Default language"""
        ...


# === TYPE ALIASES ===

UserID = int
DealCode = str
PaymentID = str
Amount = Decimal
Timestamp = datetime
CurrencyCode = str

# Common collection types
UserList = List[User]
DealList = List[Deal]
PaymentList = List[Payment]
NotificationList = List[Notification]


# Configuration dictionaries
ConfigDict = Dict[str, Any]
EnvironmentVars = Dict[str, str]
MetadataDict = Dict[str, Any]

# Database result types
DBResult = Optional[Union[User, Deal, Payment, Notification]]
DBResults = List[Union[User, Deal, Payment, Notification]]

# API request/response types
APIRequest = Dict[str, Any]
APIResponseData = Dict[str, Any]

# Validation types
ValidationResult = Tuple[bool, Union[T, Any]]  # (is_valid, value_or_error)
ValidationErrors = List[str]


# === FACTORY FUNCTIONS ===

def create_user_dict(user: User) -> Dict[str, Any]:
    """Convert User dataclass to dictionary"""
    return {
        'user_id': user.user_id,
        'username': user.username,
        'first_name': user.first_name,
        'language': user.language.value if user.language else None,
        'avatar_url': user.avatar_url,
        'registered_date': user.registered_date.isoformat() if user.registered_date else None,
        'deals_count': user.deals_count,
        'total_deal_amount': str(user.total_deal_amount),
        'is_banned': user.is_banned,
        'balance': str(user.balance),
        'role': user.role.value if user.role else None,
    }


def create_deal_dict(deal: Deal) -> Dict[str, Any]:
    """Convert Deal dataclass to dictionary"""
    return {
        'deal_code': deal.deal_code,
        'buyer_id': deal.buyer_id,
        'seller_id': deal.seller_id,
        'amount': str(deal.amount),
        'currency': deal.currency.value if deal.currency else None,
        'status': deal.status.value if deal.status else None,
        'description': deal.description,
        'product_link': deal.product_link,
        'image_link': deal.image_link,
        'created_at': deal.created_at.isoformat() if deal.created_at else None,
        'updated_at': deal.updated_at.isoformat() if deal.updated_at else None,
        'commission_amount': str(deal.commission_amount),
        'seller_amount': str(deal.seller_amount),
        'is_automatic': deal.is_automatic,
    }


# === TYPE GUARDS ===

def is_user(obj: Any) -> bool:
    """Type guard for User objects"""
    return isinstance(obj, User)


def is_deal(obj: Any) -> bool:
    """Type guard for Deal objects"""
    return isinstance(obj, Deal)


def is_payment(obj: Any) -> bool:
    """Type guard for Payment objects"""
    return isinstance(obj, Payment)


def is_valid_currency(currency: str) -> bool:
    """Type guard for valid currency codes"""
    try:
        return Currency(currency) in [Currency.USDT, Currency.TON, Currency.ETH]
    except ValueError:
        return False


def is_valid_deal_status(status: str) -> bool:
    """Type guard for valid deal statuses"""
    try:
        return DealStatus(status) in [
            DealStatus.PENDING, DealStatus.ACTIVE, DealStatus.FUNDED,
            DealStatus.COMPLETED, DealStatus.CANCELLED, DealStatus.EXPIRED, DealStatus.DISPUTED
        ]
    except ValueError:
        return False
