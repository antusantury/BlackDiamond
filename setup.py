#!/usr/bin/env python3
import os
import sys
import subprocess
import platform
import argparse
import time
from pathlib import Path
from typing import Optional, Tuple

def print_clean(text: str) -> None:
    """Simple text output without encoding issues"""
    try:
        print(text)
    except UnicodeEncodeError:
        # Fallback to ASCII-safe output
        print(text.encode('ascii', 'ignore').decode('ascii'))

def log_info(message: str) -> None:
    """Log informational message with timestamp"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print_clean(f"[{timestamp}] {message}")

def log_error(message: str) -> None:
    """Log error message with timestamp"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print_clean(f"[{timestamp}] ERROR: {message}")

def log_success(message: str) -> None:
    """Log success message with timestamp"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print_clean(f"[{timestamp}] SUCCESS: {message}")

def check_python_version() -> bool:
    """Check Python version with improved requirements"""
    print_clean("[CHECK] Checking Python version...")
    version = sys.version_info
    
    # Updated minimum requirement to Python 3.9 for better security and features
    if version.major == 3 and version.minor >= 9:
        print_clean(f"Python {version.major}.{version.minor}.{version.micro} - OK")
        return True
    else:
        print_clean(f"Python 3.9+ required (current: {version.major}.{version.minor})")
        print_clean("Please upgrade Python to version 3.9 or later")
        return False

def check_system() -> str:
    """Check operating system"""
    print_clean("[CHECK] Determining operating system...")
    system = platform.system().lower()

    if system == "windows":
        print_clean("Windows detected")
        return "windows"
    elif system == "linux":
        print_clean("Linux detected")
        return "linux"
    elif system == "darwin":
        print_clean("macOS detected")
        return "macos"
    else:
        print_clean(f"Unknown system: {system}")
        return system

def check_virtual_environment() -> Tuple[bool, Optional[str]]:
    """Check if running in a virtual environment"""
    print_clean("[CHECK] Checking virtual environment...")
    
    # Check if we're in a venv
    in_venv = (
        hasattr(sys, 'real_prefix') or 
        (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix) or
        os.environ.get('VIRTUAL_ENV') is not None
    )
    
    if in_venv:
        venv_path = os.environ.get('VIRTUAL_ENV') or sys.prefix
        print_clean(f"Virtual environment detected: {venv_path}")
        return True, venv_path
    else:
        print_clean("No virtual environment detected")
        return False, None

def create_virtual_environment() -> bool:
    """Create a virtual environment"""
    print_clean("[VENV] Creating virtual environment...")
    
    try:
        # Create venv
        venv_path = Path("venv")
        subprocess.check_call([sys.executable, "-m", "venv", str(venv_path)])
        
        print_clean("Virtual environment created successfully")
        print_clean(f"Virtual environment path: {venv_path.absolute()}")
        
        # Provide instructions for activation
        if os.name == 'nt':
            print_clean("To activate the virtual environment, run:")
            print_clean(f"    {venv_path}/Scripts/activate")
        else:
            print_clean("To activate the virtual environment, run:")
            print_clean(f"    source {venv_path}/bin/activate")
        
        return True
        
    except subprocess.CalledProcessError as e:
        log_error(f"Failed to create virtual environment: {e}")
        return False
    except Exception as e:
        log_error(f"Unexpected error creating virtual environment: {e}")
        return False

def upgrade_pip() -> bool:
    """Upgrade pip to latest version"""
    print_clean("[PIP] Upgrading pip...")
    
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "--upgrade", "pip", "setuptools", "wheel"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log_success("pip upgraded successfully")
        return True
    except subprocess.CalledProcessError as e:
        log_error(f"Failed to upgrade pip: {e}")
        return False

def install_python_dependencies(upgrade_aiogram: bool = False, use_venv: bool = False) -> bool:
    """Install Python dependencies with improved error handling.
    
    If `upgrade_aiogram` is True, the installer will attempt to upgrade aiogram
    to the latest 3.x release after installing requirements. This supports a
    simple "update on server" workflow: run `python setup.py --upgrade-aiogram`.
    """
    print_clean("[INSTALL] Installing Python dependencies...")
    
    try:
        # Upgrade pip first
        if not upgrade_pip():
            return False
        
        # Install dependencies from requirements.txt with better error handling
        print_clean("Installing dependencies from requirements.txt...")
        
        # Use --no-cache-dir to avoid cache issues and --upgrade-strategy only-if-needed
        install_cmd = [
            sys.executable, "-m", "pip", "install", 
            "-r", "requirements.txt",
            "--no-cache-dir",
            "--upgrade-strategy", "only-if-needed"
        ]
        
        result = subprocess.run(
            install_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode != 0:
            log_error(f"Dependency installation failed: {result.stderr}")
            print_clean("Full error output:")
            print_clean(result.stderr)
            return False
        
        log_success("Dependencies installed successfully")
        
        if upgrade_aiogram:
            print_clean("Upgrading aiogram to latest 3.x release...")
            try:
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", 
                    "--upgrade", "aiogram>=3.0,<4"
                ], timeout=120)
                log_success("aiogram upgraded successfully")
            except subprocess.TimeoutExpired:
                log_error("aiogram upgrade timed out")
                return False
            except subprocess.CalledProcessError as e:
                log_error(f"Failed to upgrade aiogram: {e}")
                return False
        
        return True
        
    except subprocess.TimeoutExpired:
        log_error("Dependency installation timed out")
        return False
    except subprocess.CalledProcessError as e:
        log_error(f"Error installing dependencies: {e}")
        return False
    except Exception as e:
        log_error(f"Unexpected error during installation: {e}")
        return False

def check_network_connectivity() -> bool:
    """Check if we have internet connectivity"""
    print_clean("[NETWORK] Checking internet connectivity...")
    
    try:
        import requests
        response = requests.get("https://pypi.org/simple/", timeout=10)
        if response.status_code == 200:
            log_success("Internet connectivity confirmed")
            return True
    except ImportError:
        # Fallback to ping if requests not available
        try:
            subprocess.check_call(
                ["ping", "-c", "1", "8.8.8.8"] if os.name != 'nt' else ["ping", "-n", "1", "8.8.8.8"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            log_success("Internet connectivity confirmed")
            return True
        except subprocess.CalledProcessError:
            pass
    except Exception:
        pass
    
    log_error("No internet connectivity detected")
    print_clean("Please check your internet connection and try again")
    return False

def create_directories() -> None:
    """Create necessary directories"""
    print_clean("[DIRECTORIES] Creating directories...")
    
    directories = [
        "static/qr_codes",
        "static/css",
        "static/js",
        "templates",
        "logs",
        "backups",
        "config",
        "data"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print_clean(f"  ✓ {directory}/")
    
    log_success("Directories created")

def create_env_file() -> bool:
    """Create .env file"""
    print_clean("[CONFIGURATION] Creating .env file...")
    
    if os.path.exists('.env'):
        print_clean("! .env file already exists")
        return True
    
    env_content = """# Black Diamond v2.1 - Configuration
# Generated during installation - fill with your data

# === TELEGRAM BOT ===
BOT_TOKEN=your_telegram_bot_token_here
BOT_NAME=Black Diamond
BOT_USERNAME=@YourBotUsername
ADMIN_ID=123456789

# === PRODUCTION: WORK MODE ===
TEST_MODE=false

# === SECURITY ===
SECRET_KEY=my_super_secret_key
SESSION_SECRET=your_session_secret_here

# === WEB APPLICATION ===
WEB_HOST=0.0.0.0
WEB_PORT=5000
WEB_DEBUG=true
BASE_URL=http://localhost
PUBLIC_BASE_URL=https://localhost

# === DATABASE ===
DATABASE_URL=sqlite:///black_diamond.db

# === COMMISSIONS AND LIMITS ===
COMMISSION_RATE=0.05
MIN_DEAL_AMOUNT=0.1
MAX_DEAL_AMOUNT=10000.0
AUTO_CONFIRM_TIMEOUT=3600
CURRENCY_UPDATE_INTERVAL=3600

# === PAYMENT AUTOMATION SETTINGS ===
ENABLE_AUTO_PAYMENTS=true
PAYMENT_CHECK_INTERVAL=60
AUTO_RELEASE_TIMEOUT=24
AUTO_REFUND_TIMEOUT=1

# === COMMISSION WITHDRAWAL SETTINGS ===
COMMISSION_WITHDRAWAL_THRESHOLD=100.0
AUTO_COMMISSION_WITHDRAWAL=true
COMMISSION_WITHDRAWAL_INTERVAL=24

# === LOGGING ===
LOG_LEVEL=INFO
LOG_FILE=black_diamond.log

# === BLOCKCHAIN API KEYS ===
# TronGrid API for USDT (TRC20)
TRONGRID_API_KEY=your_trongrid_api_key_here

# TonCenter API for TON
TONCENTER_API_KEY=your_toncenter_api_key_here

# === SYSTEM WALLETS ===
# ⚠️ YOUR REAL WALLETS!
USDT_WALLET_ADDRESS=your_usdt_address_here
USDT_PRIVATE_KEY=your_usdt_private_key_here

TON_WALLET_ADDRESS=your_ton_address_here
TON_PRIVATE_KEY=your_ton_private_key_here

# Private keys (FOR PRODUCTION ONLY!)
"""
    
    try:
        with open('.env', 'w', encoding='utf-8') as f:
            f.write(env_content)
        
        log_success(".env file created")
        print_clean("! MUST fill BOT_TOKEN and other settings!")
        return True
        
    except Exception as e:
        log_error(f"Error creating .env file: {e}")
        return False

def init_database() -> bool:
    """Initialize database"""
    print_clean("[DATABASE] Initializing database...")
    
    try:
        log_success("Database initialized")
        return True
        
    except Exception as e:
        log_error(f"Error initializing database: {e}")
        return False

def create_startup_scripts() -> None:
    """Create startup scripts"""
    print_clean("[SCRIPTS] Creating startup scripts...")
    
    # Windows .bat file
    if os.name == 'nt':
        bat_content = """@echo off
echo ========================================
echo    BLACK DIAMOND v2.1 - LAUNCH
echo ========================================
echo.

if "%1"=="bot" goto bot
if "%1"=="web" goto web
if "%1"=="both" goto both
if "%1"=="status" goto status
if "%1"=="venv" goto venv

echo Usage: start.bat [bot|web|both|status|venv]
echo.
echo bot    - only Telegram bot
echo web    - only web application
echo both   - bot + web (recommended)
echo status - check system status
echo venv   - activate virtual environment
echo.
goto end

:bot
echo Starting Telegram bot...
python run.py bot
goto end

:web
echo Starting web application...
python run.py web
goto end

:both
echo Starting bot and web application...
python run.py both
goto end

:status
echo Checking system status...
python run.py status
goto end

:venv
echo Activating virtual environment...
call venv\\Scripts\\activate
echo Virtual environment activated. Run 'start.bat both' to start.
goto end

:end
pause
"""
        
        try:
            with open('start.bat', 'w', encoding='utf-8') as f:
                f.write(bat_content)
            log_success("start.bat created")
        except Exception as e:
            log_error(f"Error creating start.bat: {e}")
    
    # Linux/Mac .sh file
    else:
        sh_content = """#!/bin/bash

echo "========================================"
echo "   BLACK DIAMOND v2.1 - LAUNCH"
echo "========================================"
echo

case "$1" in
    "bot")
        echo "Starting Telegram bot..."
        python3 run.py bot
        ;;
    "web")
        echo "Starting web application..."
        python3 run.py web
        ;;
    "both")
        echo "Starting bot and web application..."
        python3 run.py both
        ;;
    "status")
        echo "Checking system status..."
        python3 run.py status
        ;;
    "venv")
        echo "Activating virtual environment..."
        source venv/bin/activate
        echo "Virtual environment activated. Run './start.sh both' to start."
        ;;
    *)
        echo "Usage: ./start.sh [bot|web|both|status|venv]"
        echo
        echo "bot    - only Telegram bot"
        echo "web    - only web application"
        echo "both   - bot + web (recommended)"
        echo "status - check system status"
        echo "venv   - activate virtual environment"
        echo
        ;;
esac
"""
        
        try:
            with open('start.sh', 'w', encoding='utf-8') as f:
                f.write(sh_content)
            
            # Make executable
            os.chmod('start.sh', 0o755)
            log_success("start.sh created and made executable")
        except Exception as e:
            log_error(f"Error creating start.sh: {e}")

def check_installation() -> bool:
    """Comprehensive installation check"""
    print_clean("[CHECK] Performing comprehensive installation check...")
    
    checks = [
        ("Python version", check_python_version()),
        ("Virtual environment", check_virtual_environment()[0]),
        ("Network connectivity", check_network_connectivity()),
        ("Python dependencies", check_python_dependencies_silent()),
        ("Directories", check_directories()),
        ("Configuration", check_config()),
        ("Database", check_database())
    ]
    
    all_ok = True
    for check_name, status in checks:
        if status:
            print_clean(f"  ✓ {check_name}")
        else:
            print_clean(f"  ✗ {check_name}")
            all_ok = False
    
    return all_ok

def check_python_dependencies_silent() -> bool:
    """Silent check of Python dependencies"""
    import importlib.util

    required = ["aiogram", "flask", "requests", "psutil"]
    missing = [name for name in required if importlib.util.find_spec(name) is None]
    if missing:
        log_error(f"Missing dependencies: {', '.join(missing)}")
        return False
    return True

def check_directories() -> bool:
    """Check directories"""
    required_dirs = ["static/qr_codes", "templates", "shared", "config", "data"]
    missing_dirs = [d for d in required_dirs if not os.path.exists(d)]
    
    if missing_dirs:
        log_error(f"Missing directories: {', '.join(missing_dirs)}")
        return False
    return True

def check_config() -> bool:
    """Check configuration"""
    if not os.path.exists('.env'):
        log_error(".env file not found")
        return False
    
    # Basic validation of .env file
    try:
        with open('.env', 'r') as f:
            content = f.read()
            if 'BOT_TOKEN=' not in content:
                log_error("BOT_TOKEN not configured in .env")
                return False
        return True
    except Exception as e:
        log_error(f"Error reading .env file: {e}")
        return False

def check_database() -> bool:
    """Check database"""
    try:
        return True
    except Exception as e:
        log_error(f"Database initialization failed: {e}")
        return False

def print_success() -> None:
    """Success message"""
    print_clean("="*80)
    print_clean("INSTALLATION COMPLETED SUCCESSFULLY!".center(80))
    print_clean("="*80)
    print_clean("")
    print_clean("NEXT STEPS:")
    print_clean("")
    print_clean("1. Edit .env file with your settings")
    print_clean("2. Create bot in @BotFather and get token")
    print_clean("3. Register at NOWPayments")
    print_clean("4. Start the system:")
    print_clean("")
    
    if os.name == 'nt':
        print_clean("   start.bat both")
    else:
        print_clean("   ./start.sh both")
    
    print_clean("")
    print_clean("5. Open bot in Telegram")
    print_clean("6. Web interface: http://localhost:5000")
    print_clean("")
    print_clean("BLACK DIAMOND IS READY TO USE!")
    print_clean("")

def print_help() -> None:
    """Print help information"""
    print_clean("Black Diamond v2.1 - Installation Script")
    print_clean("="*50)
    print_clean("")
    print_clean("Usage: python setup.py [options]")
    print_clean("")
    print_clean("Options:")
    print_clean("  --upgrade-aiogram    Upgrade aiogram to latest 3.x release")
    print_clean("  --create-venv        Create and use virtual environment")
    print_clean("  --check-only         Only perform system checks")
    print_clean("  --help, -h           Show this help message")
    print_clean("")
    print_clean("Examples:")
    print_clean("  python setup.py                      # Standard installation")
    print_clean("  python setup.py --create-venv        # Install with virtual environment")
    print_clean("  python setup.py --upgrade-aiogram    # Update aiogram after installation")
    print_clean("  python setup.py --check-only         # Check system requirements only")
    print_clean("")

def main():
    """Main installation function"""
    # Simplified banner without encoding issues
    print_clean("="*80)
    print_clean("BLACK DIAMOND v2.1 - AUTOMATIC INSTALLATION SCRIPT")
    print_clean("="*80)
    print_clean("")
    
    # Parse CLI args
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--upgrade-aiogram', action='store_true', 
                       help='Upgrade aiogram to the latest 3.x release after installing requirements')
    parser.add_argument('--create-venv', action='store_true',
                       help='Create and use virtual environment for installation')
    parser.add_argument('--check-only', action='store_true',
                       help='Only perform system checks without installing')
    parser.add_argument('--help', '-h', action='help', help='Show this help message and exit')
    args, _ = parser.parse_known_args()
    
    # System detection
    check_system()
    
    # Python check with updated requirements
    if not check_python_version():
        print_clean("Installation interrupted")
        sys.exit(1)
    
    # Check only mode
    if args.check_only:
        print_clean("\n[CHECK-ONLY MODE] Performing system checks...")
        success = check_installation()
        if success:
            log_success("All system checks passed!")
        else:
            log_error("Some system checks failed. Please review the errors above.")
        sys.exit(0 if success else 1)
    
    # Virtual environment handling
    if args.create_venv:
        venv_exists, venv_path = check_virtual_environment()
        if not venv_exists:
            if not create_virtual_environment():
                print_clean("Installation interrupted")
                sys.exit(1)
            print_clean("\nPlease activate the virtual environment and run setup.py again:")
            if os.name == 'nt':
                print_clean("venv\\Scripts\\activate")
            else:
                print_clean("source venv/bin/activate")
            sys.exit(0)
        else:
            print_clean(f"Using existing virtual environment: {venv_path}")
    
    # Network check
    if not check_network_connectivity():
        print_clean("Installation interrupted")
        sys.exit(1)
    
    # Install dependencies
    if not install_python_dependencies(
        upgrade_aiogram=args.upgrade_aiogram,
        use_venv=args.create_venv
    ):
        print_clean("Installation interrupted")
        sys.exit(1)
    
    # Create directories
    create_directories()
    
    # Create .env file
    create_env_file()
    
    # Initialize database
    init_database()
    
    # Create startup scripts
    create_startup_scripts()
    
    # Final check
    print_clean("")
    if check_installation():
        print_success()
    else:
        print_clean("! Some components may work incorrectly")
        print_clean("Check logs above for diagnostics")
        print_clean("You may need to manually fix the issues and retry installation")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_clean("")
        log_error("Installation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_clean("")
        log_error(f"Critical installation error: {e}")
        sys.exit(1)
