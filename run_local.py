#!/usr/bin/env python3
"""
BingX Trading Bot - Local Development Runner
Easy-to-use script for running the bot locally with all components
"""

import os
import sys
import subprocess
import time
import signal
import asyncio
from pathlib import Path
from typing import List, Optional
import argparse


class Colors:
    """Terminal colors for pretty output"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class LocalRunner:
    def __init__(self):
        self.processes: List[subprocess.Popen] = []
        self.project_root = Path(__file__).parent
        self.env_file = self.project_root / ".env"
        self.running = False
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def print_banner(self):
        """Print startup banner"""
        banner = f"""
{Colors.HEADER}{Colors.BOLD}
╔══════════════════════════════════════════════════════════════╗
║                   🤖 BingX Trading Bot                       ║
║                    Local Development                         ║
╚══════════════════════════════════════════════════════════════╝
{Colors.ENDC}
"""
        print(banner)
    
    def log(self, message: str, level: str = "INFO"):
        """Colored logging"""
        colors = {
            "INFO": Colors.OKBLUE,
            "SUCCESS": Colors.OKGREEN,
            "WARNING": Colors.WARNING,
            "ERROR": Colors.FAIL,
            "HEADER": Colors.HEADER
        }
        color = colors.get(level, Colors.ENDC)
        timestamp = time.strftime("%H:%M:%S")
        print(f"{color}[{timestamp}] {level}: {message}{Colors.ENDC}")
    
    def check_requirements(self) -> bool:
        """Check if all requirements are met"""
        self.log("Checking requirements...", "INFO")
        
        # Check Python version
        if sys.version_info < (3, 11):
            self.log("Python 3.11+ required", "ERROR")
            return False
        
        # Check if .env exists
        if not self.env_file.exists():
            self.log("Creating .env from template...", "WARNING")
            self.create_env_file()
        
        # Check Docker
        try:
            result = subprocess.run(["docker", "--version"], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                self.log("Docker not found. Install Docker to use containers.", "WARNING")
        except FileNotFoundError:
            self.log("Docker not found. Will run without containers.", "WARNING")
        
        self.log("Requirements check completed", "SUCCESS")
        return True
    
    def create_env_file(self):
        """Create .env file from example"""
        example_file = self.project_root / ".env.example"
        if example_file.exists():
            # Copy example to .env with development defaults
            with open(example_file, 'r') as f:
                content = f.read()
            
            # Set development defaults
            content = content.replace("ENVIRONMENT=production", "ENVIRONMENT=development")
            content = content.replace("DEBUG=False", "DEBUG=True")
            content = content.replace("PAPER_TRADING=False", "PAPER_TRADING=True")
            content = content.replace("BINGX_TESTNET=False", "BINGX_TESTNET=True")
            content = content.replace("TRADING_ENABLED=True", "TRADING_ENABLED=False")
            
            with open(self.env_file, 'w') as f:
                f.write(content)
            
            self.log("Created .env file with development defaults", "SUCCESS")
            self.log("⚠️ IMPORTANT: Edit .env with your BingX API credentials!", "WARNING")
        else:
            self.log("No .env.example found", "ERROR")
    
    def install_dependencies(self):
        """Install Python dependencies"""
        self.log("Installing Python dependencies...", "INFO")
        try:
            subprocess.run([
                sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
            ], check=True, cwd=self.project_root)
            self.log("Dependencies installed successfully", "SUCCESS")
        except subprocess.CalledProcessError as e:
            self.log(f"Failed to install dependencies: {e}", "ERROR")
            sys.exit(1)
    
    def setup_database(self):
        """Setup database with Docker or show instructions"""
        self.log("Setting up database...", "INFO")
        
        try:
            # Check if Docker is available
            subprocess.run(["docker", "--version"], 
                          capture_output=True, check=True)
            
            # Start PostgreSQL with Docker
            self.log("Starting PostgreSQL with Docker...", "INFO")
            subprocess.run([
                "docker", "run", "-d",
                "--name", "bingx_postgres_dev",
                "-e", "POSTGRES_DB=bingx_trading",
                "-e", "POSTGRES_USER=trading_user", 
                "-e", "POSTGRES_PASSWORD=trading_password",
                "-p", "5432:5432",
                "--restart", "unless-stopped",
                "postgres:16-alpine"
            ], check=True)
            
            self.log("PostgreSQL container started", "SUCCESS")
            self.log("Waiting for database to be ready...", "INFO")
            time.sleep(10)
            
        except (FileNotFoundError, subprocess.CalledProcessError):
            self.log("Docker not available. Please install PostgreSQL manually:", "WARNING")
            self.log("1. Install PostgreSQL 16+", "INFO")
            self.log("2. Create database 'bingx_trading'", "INFO")
            self.log("3. Create user 'trading_user' with password 'trading_password'", "INFO")
            self.log("4. Update DATABASE_URL in .env file", "INFO")
    
    def run_migrations(self):
        """Database initialization (handled by application)"""
        self.log("Database initialization will be handled by the application...", "INFO")
        self.log("Skipping Alembic migrations (using SQLAlchemy create_tables)", "SUCCESS")
        try:
            # No migration needed - application handles table creation
            pass
        except Exception as e:
            self.log(f"Migration failed: {e}", "ERROR")
            self.log("You may need to setup the database first", "WARNING")
    
    def start_component(self, name: str, command: List[str], cwd: Optional[Path] = None) -> subprocess.Popen:
        """Start a component process"""
        self.log(f"Starting {name}...", "INFO")
        
        env = os.environ.copy()
        # Add project root to Python path
        env['PYTHONPATH'] = str(self.project_root)
        
        process = subprocess.Popen(
            command,
            cwd=cwd or self.project_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        self.processes.append(process)
        return process
    
    def start_web_interface(self):
        """Start the web interface"""
        return self.start_component(
            "Web Interface",
            [sys.executable, "-m", "uvicorn", "api.web_api:app", 
             "--host", "0.0.0.0", "--port", "8000", "--reload"]
        )
    
    def start_scanner_worker(self):
        """Start the scanner worker"""
        return self.start_component(
            "Scanner Worker",
            [sys.executable, "-m", "scanner.initial_scanner"]
        )
    
    def start_analysis_worker(self):
        """Start the analysis worker"""
        return self.start_component(
            "Analysis Worker", 
            [sys.executable, "-m", "analysis.worker"]
        )
    
    def start_trading_worker(self):
        """Start the trading worker"""
        return self.start_component(
            "Trading Worker",
            [sys.executable, "-m", "trading.worker"]
        )
    
    def monitor_processes(self):
        """Monitor all running processes"""
        self.log("All components started successfully!", "SUCCESS")
        self.log("🌐 Web Dashboard: http://localhost:8000", "HEADER")
        self.log("📊 API Docs: http://localhost:8000/docs", "HEADER")
        self.log("Press Ctrl+C to stop all components", "INFO")
        
        try:
            while self.running:
                # Check if any process has died
                for i, process in enumerate(self.processes):
                    if process.poll() is not None:
                        self.log(f"Process {i} has stopped", "WARNING")
                
                time.sleep(1)
                
        except KeyboardInterrupt:
            self.log("Shutdown signal received", "INFO")
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.log("Shutting down...", "WARNING")
        self.running = False
        self.cleanup()
    
    def cleanup(self):
        """Clean up all processes"""
        self.log("Stopping all components...", "INFO")
        
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        
        self.log("All components stopped", "SUCCESS")
        sys.exit(0)
    
    def run_minimal(self):
        """Run minimal setup (web interface only)"""
        self.log("Starting minimal setup (web interface only)...", "HEADER")
        
        # Start only web interface
        self.start_web_interface()
        self.running = True
        self.monitor_processes()
    
    def run_full(self):
        """Run full setup with all workers"""
        self.log("Starting full setup (all components)...", "HEADER")
        
        # Start all components
        self.start_web_interface()
        time.sleep(2)  # Give web interface time to start
        
        self.start_scanner_worker()
        time.sleep(1)
        
        self.start_analysis_worker()
        time.sleep(1)
        
        self.start_trading_worker()
        
        self.running = True
        self.monitor_processes()
    
    def run_docker(self):
        """Run with Docker Compose"""
        self.log("Starting with Docker Compose...", "HEADER")
        
        try:
            # Start services
            subprocess.run([
                "docker-compose", "up", "-d", "--build",
                "postgres", "redis"
            ], check=True, cwd=self.project_root)
            
            self.log("Database services started", "SUCCESS")
            self.log("Starting application...", "INFO")
            
            # Wait for services to be ready
            time.sleep(10)
            
            # Run migrations
            self.run_migrations()
            
            # Start application components
            self.run_full()
            
        except subprocess.CalledProcessError as e:
            self.log(f"Docker Compose failed: {e}", "ERROR")
            sys.exit(1)
    
    def test_api_connection(self):
        """Test API connection and configuration"""
        self.log("Testing API connection...", "INFO")
        
        try:
            import ccxt
            from config.settings import get_settings
            
            settings = get_settings()
            
            if not settings.BINGX_API_KEY or settings.BINGX_API_KEY == "your_bingx_api_key_here":
                self.log("❌ BingX API credentials not configured", "ERROR")
                self.log("Please edit .env file with your API credentials", "WARNING")
                return False
            
            # Test connection
            exchange = ccxt.bingx({
                'apiKey': settings.BINGX_API_KEY,
                'secret': settings.BINGX_SECRET_KEY,
                'sandbox': settings.BINGX_TESTNET,
                'enableRateLimit': True,
            })
            
            # Try fetching markets (this doesn't require authentication)
            markets = exchange.fetch_markets()
            self.log(f"✅ API connection successful! Found {len(markets)} markets", "SUCCESS")
            return True
            
        except Exception as e:
            self.log(f"❌ API connection failed: {e}", "ERROR")
            return False


def main():
    parser = argparse.ArgumentParser(description="BingX Trading Bot - Local Development")
    parser.add_argument("--mode", choices=["minimal", "full", "docker"], default="minimal",
                       help="Running mode (default: minimal)")
    parser.add_argument("--setup", action="store_true", 
                       help="Setup environment and dependencies")
    parser.add_argument("--test", action="store_true",
                       help="Test API connection")
    parser.add_argument("--install", action="store_true",
                       help="Install dependencies only")
    
    args = parser.parse_args()
    
    runner = LocalRunner()
    runner.print_banner()
    
    if not runner.check_requirements():
        sys.exit(1)
    
    if args.install:
        runner.install_dependencies()
        return
    
    if args.setup:
        runner.install_dependencies()
        runner.setup_database()
        runner.run_migrations()
        return
    
    if args.test:
        runner.test_api_connection()
        return
    
    # Install dependencies if needed
    runner.install_dependencies()
    
    # Run based on mode
    if args.mode == "minimal":
        runner.run_minimal()
    elif args.mode == "full":
        runner.run_full() 
    elif args.mode == "docker":
        runner.run_docker()


if __name__ == "__main__":
    main()