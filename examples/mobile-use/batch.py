#!/usr/bin/env python3
"""
Mobile Sandbox Batch Operations Script (Async High-Concurrency Version)

Features:
1. Uses AsyncSandbox for truly concurrent creation of N sandboxes
2. Each sandbox independently completes: create -> operate -> destroy (fully async)
3. Sandboxes don't wait for each other, fully parallel execution
4. Aggregates data from all sandboxes at the end

Configuration (.env file):
    E2B_API_KEY=xxx                # Required, API key
    E2B_DOMAIN=xxx                 # Required, service domain (e.g., ap-guangzhou.tencentags.com)
    SANDBOX_TEMPLATE=mobile-v1     # Required, sandbox template
    SANDBOX_TIMEOUT=300            # Optional, sandbox timeout in seconds, default 300
    SANDBOX_COUNT=2                # Optional, total sandbox count, default 2
    PROCESS_COUNT=2                # Optional, process count, default 2
    THREAD_POOL_SIZE=5             # Optional, thread pool size per process, default 5
    USE_MOUNTED_APK=false          # Optional, default false (upload APK from local)
                                   #   Set to true to install from mounted path, requires COS disk mounted to sandbox

Usage:
    python batch.py
"""

from __future__ import annotations

import os

# =============================================================================
# IMPORTANT: Set HTTP connection pool size BEFORE importing e2b
# e2b SDK defaults to max_keepalive_connections=20, which causes concurrency bottleneck
# =============================================================================
os.environ.setdefault("E2B_MAX_KEEPALIVE_CONNECTIONS", "1000")
os.environ.setdefault("E2B_MAX_CONNECTIONS", "2000")

import sys
import time
import json
import random
import signal
import asyncio
import hashlib
import logging
import statistics
import traceback
import multiprocessing
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from types import FrameType
from typing import List, Optional, Dict, Any, Tuple, TextIO, Callable, Union
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import requests

# =============================================================================
# Logging Configuration
# =============================================================================
def setup_logging(level: Optional[str] = None) -> logging.Logger:
    """
    Configure logging system.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               If not specified, reads from LOG_LEVEL environment variable,
               defaults to INFO.
    """
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO")
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Create formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Add console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    return logging.getLogger(__name__)


# Lazy-initialized logger
logger: Optional[logging.Logger] = None

# Lazy imports
AsyncSandbox = None


# =============================================================================
# Constants
# =============================================================================
APK_DOWNLOAD_BASE_URL = "https://agentsandbox-1251707795.cos.ap-guangzhou.myqcloud.com/repo/apk"

DEFAULT_CONFIG = {
    'E2B_DOMAIN': '',              # Required
    'E2B_API_KEY': '',             # Required
    'SANDBOX_TEMPLATE': '',        # Required
    'SANDBOX_TIMEOUT': 300,
    'SANDBOX_COUNT': 2,
    'PROCESS_COUNT': 2,
    'THREAD_POOL_SIZE': 5,
    'USE_MOUNTED_APK': False,      # Default: upload APK from local; set to True after mounting COS disk
}

# Mount path prefix (for mounted APK mode)
MOUNT_PATH_PREFIX = '/data/local/tmp/mnt'

# Error message truncation length
MAX_ERROR_MSG_LENGTH = 200

# App configurations for testing
# This is an example configuration. Users can customize by adding their own apps.
# Required fields: name, package, activity, apk_name, remote_path, mounted_path, permissions
APP_CONFIGS = {
    'meituan': {
        'name': 'Meituan',
        'package': 'com.sankuai.meituan',
        'activity': '.activity.MainActivity',
        'apk_name': '125_c86eb843c958b405143024ba12d9175a.apk',
        'remote_path': '/data/local/tmp/meituan.apk',  # Path for upload mode
        'mounted_path': f'{MOUNT_PATH_PREFIX}/125_c86eb843c958b405143024ba12d9175a.apk',  # Path for mounted mode
        'permissions': [
            'android.permission.ACCESS_FINE_LOCATION',
            'android.permission.ACCESS_COARSE_LOCATION',
            'android.permission.READ_EXTERNAL_STORAGE',
            'android.permission.CAMERA',
            'android.permission.RECORD_AUDIO',
            'android.permission.READ_CONTACTS',
        ]
    },
}

# Operation definitions: (key, display_name)
OPERATIONS = [
    ('upload_apk', 'Upload APK'),
    ('install_apk', 'Install APK'),
    ('launch_apk', 'Launch APK'),
    ('screenshot_1', 'Screenshot (1)'),
    ('tap_random_1', 'Tap Random (1)'),
    ('get_page_xml', 'Get Page XML'),
    ('get_device_info', 'Get Device Info'),
    ('open_browser', 'Open Browser'),
    ('tap_random_2', 'Tap Random (2)'),
    ('screenshot_2', 'Screenshot (2)'),
    ('get_logs', 'Get Logs'),
]


# =============================================================================
# Exceptions
# =============================================================================
class ConfigurationError(Exception):
    """Configuration error"""
    pass


# =============================================================================
# Configuration Management
# =============================================================================
def _load_env_file() -> None:
    """Load .env file"""
    try:
        from dotenv import load_dotenv
        script_dir = Path(__file__).parent.absolute()
        load_dotenv(script_dir / ".env")
    except ImportError:
        script_dir = Path(__file__).parent.absolute()
        env_file = script_dir / ".env"
        if env_file.exists():
            try:
                with open(env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            os.environ[key.strip()] = value.strip()
            except IOError as e:
                print(f"Warning: Failed to read .env file: {e}", file=sys.stderr)


def load_config() -> Dict[str, Any]:
    """Load and validate configuration"""
    _load_env_file()
    
    def _parse_bool(key: str, default: bool = False) -> bool:
        raw = os.getenv(key, "")
        if raw == "":
            return default
        return raw.lower() in ('true', '1', 'yes')
    
    def _parse_optional_int(key: str) -> Optional[int]:
        raw = os.getenv(key, "").strip()
        if raw == "":
            return None
        return int(raw)

    sandbox_count = int(os.getenv("SANDBOX_COUNT", str(DEFAULT_CONFIG['SANDBOX_COUNT'])))

    config = {
        'E2B_DOMAIN': os.getenv("E2B_DOMAIN", DEFAULT_CONFIG['E2B_DOMAIN']),
        'E2B_API_KEY': os.getenv("E2B_API_KEY", DEFAULT_CONFIG['E2B_API_KEY']),
        'SANDBOX_TEMPLATE': os.getenv("SANDBOX_TEMPLATE", DEFAULT_CONFIG['SANDBOX_TEMPLATE']),
        'SANDBOX_TIMEOUT': int(os.getenv("SANDBOX_TIMEOUT", str(DEFAULT_CONFIG['SANDBOX_TIMEOUT']))),
        'SANDBOX_COUNT': sandbox_count,
        'PROCESS_COUNT': int(os.getenv("PROCESS_COUNT", str(DEFAULT_CONFIG['PROCESS_COUNT']))),
        'THREAD_POOL_SIZE': int(os.getenv("THREAD_POOL_SIZE", str(DEFAULT_CONFIG['THREAD_POOL_SIZE']))),
        'USE_MOUNTED_APK': _parse_bool("USE_MOUNTED_APK", DEFAULT_CONFIG['USE_MOUNTED_APK']),
    }
    
    _validate_config(config)
    return config


def _validate_config(config: Dict[str, Any]) -> None:
    """Validate configuration parameters"""
    errors = []

    # Required fields validation
    if not config['E2B_API_KEY']:
        errors.append("E2B_API_KEY not set, please configure in .env file")

    if not config['E2B_DOMAIN']:
        errors.append("E2B_DOMAIN not set, please configure in .env file (e.g., ap-guangzhou.tencentags.com)")

    if not config['SANDBOX_TEMPLATE']:
        errors.append("SANDBOX_TEMPLATE not set, please configure in .env file (e.g., mobile-v1)")

    # Numeric range validation
    if config['SANDBOX_COUNT'] < 1:
        errors.append(f"SANDBOX_COUNT must be >= 1, current value: {config['SANDBOX_COUNT']}")

    if config['PROCESS_COUNT'] < 1:
        errors.append(f"PROCESS_COUNT must be >= 1, current value: {config['PROCESS_COUNT']}")

    if config['SANDBOX_TIMEOUT'] < 60:
        errors.append(f"SANDBOX_TIMEOUT must be >= 60 seconds, current value: {config['SANDBOX_TIMEOUT']}")

    if config['THREAD_POOL_SIZE'] < 1:
        errors.append(f"THREAD_POOL_SIZE must be >= 1, current value: {config['THREAD_POOL_SIZE']}")

    if errors:
        raise ConfigurationError("\n".join(errors))

    # Warnings
    if config['SANDBOX_COUNT'] > 100:
        print(f"Warning: SANDBOX_COUNT={config['SANDBOX_COUNT']} is large, may exceed quota limits", file=sys.stderr)

    if config.get('PROCESS_COUNT', 1) > 1 and config['SANDBOX_COUNT'] < config.get('PROCESS_COUNT', 1):
        print("Warning: PROCESS_COUNT > SANDBOX_COUNT, will only start SANDBOX_COUNT processes", file=sys.stderr)


# =============================================================================
# Utility Functions
# =============================================================================
def format_timestamp() -> str:
    """Format timestamp"""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def extract_error_details(e: Exception) -> str:
    """Extract detailed error information from exception"""
    error_parts = []

    # Basic error type and message
    error_type = type(e).__name__
    error_msg = str(e).strip()
    
    if error_msg:
        error_parts.append(f"{error_type}: {error_msg}")
    else:
        error_parts.append(error_type)

    # Try to extract HTTP response details (for httpx/requests library exceptions)
    # Check if response attribute exists
    response = getattr(e, 'response', None)
    if response is not None:
        status_code = getattr(response, 'status_code', None)
        if status_code:
            error_parts.append(f"HTTP {status_code}")

        # Try to get response body
        try:
            if hasattr(response, 'text'):
                body = response.text[:MAX_ERROR_MSG_LENGTH] if response.text else ''
                if body:
                    error_parts.append(f"Body: {body}")
            elif hasattr(response, 'content'):
                body = response.content[:MAX_ERROR_MSG_LENGTH].decode('utf-8', errors='ignore') if response.content else ''
                if body:
                    error_parts.append(f"Body: {body}")
        except Exception:
            pass

        # Try to get response headers
        try:
            headers = getattr(response, 'headers', None)
            if headers:
                # Extract some useful header info
                useful_headers = ['X-Request-Id', 'X-Trace-Id', 'Retry-After', 'X-RateLimit-Remaining']
                header_info = []
                for h in useful_headers:
                    val = headers.get(h)
                    if val:
                        header_info.append(f"{h}={val}")
                if header_info:
                    error_parts.append(f"Headers: {', '.join(header_info)}")
        except Exception:
            pass

    # Check if request attribute exists (request info)
    request = getattr(e, 'request', None)
    if request is not None:
        try:
            method = getattr(request, 'method', '')
            url = getattr(request, 'url', '')
            if method and url:
                error_parts.append(f"Request: {method} {url}")
        except Exception:
            pass

    # Check for chained exception
    cause = getattr(e, '__cause__', None)
    if cause and cause is not e:
        cause_msg = str(cause).strip()
        if cause_msg:
            error_parts.append(f"Caused by: {type(cause).__name__}: {cause_msg[:MAX_ERROR_MSG_LENGTH]}")

    return " | ".join(error_parts)


@contextmanager
def timer():
    """Timer context manager"""
    start = time.perf_counter()
    result = {'elapsed_ms': 0.0}
    try:
        yield result
    finally:
        result['elapsed_ms'] = (time.perf_counter() - start) * 1000


def create_operation_metrics() -> Dict[str, OperationMetrics]:
    """Create operation metrics dictionary"""
    return {
        key: OperationMetrics(name=f'{i}. {name}')
        for i, (key, name) in enumerate(OPERATIONS, 1)
    }


# =============================================================================
# APK Management
# =============================================================================
def download_apk(apk_name: str, save_path: Path) -> bool:
    """Download APK file"""
    from urllib.parse import quote
    remote_name = apk_name.replace('.apk', '.ap')
    encoded_name = quote(remote_name)
    download_url = f"{APK_DOWNLOAD_BASE_URL}/{encoded_name}"

    print(f"  - Downloading APK: {download_url}")
    try:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(download_url, stream=True, timeout=300)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        print(f"  - Download complete: {save_path}")
        return True
    except requests.exceptions.RequestException as e:
        if logger:
            logger.error(f"Failed to download APK: {e}")
        if save_path.exists():
            save_path.unlink()
        return False


def ensure_apk_ready(app_name: str = 'meituan') -> bool:
    """Ensure APK file is ready (pre-download)"""
    config = APP_CONFIGS.get(app_name.lower())
    if not config:
        if logger:
            logger.error(f"Unknown app name: {app_name}")
        return False

    apk_dir = Path(__file__).parent / "apk"
    apk_path = apk_dir / config['apk_name']

    if apk_path.exists():
        file_size_mb = apk_path.stat().st_size / (1024 * 1024)
        print(f"APK exists: {apk_path} ({file_size_mb:.1f}MB)")
        return True

    print(f"APK not found, starting download: {config['apk_name']}")
    print("(Download time not included in batch operation time)")

    if download_apk(config['apk_name'], apk_path):
        file_size_mb = apk_path.stat().st_size / (1024 * 1024)
        print(f"APK download complete: {apk_path} ({file_size_mb:.1f}MB)")
        return True
    return False


# =============================================================================
# Logging Output Class
# =============================================================================
class TeeLogger:
    """Logger that outputs to both terminal and file (supports context manager)"""

    def __init__(self, log_file: Path, mirror_to_terminal: bool = True):
        self._terminal = sys.stdout
        self._log_file = log_file
        self._mirror_to_terminal = mirror_to_terminal
        self._file: Optional[TextIO] = None
        self._original_stdout: Optional[TextIO] = None

    def __enter__(self) -> 'TeeLogger':
        self._original_stdout = sys.stdout
        # Line buffering: avoid forced flush on every write, reduce I/O overhead in high-concurrency scenarios
        self._file = open(self._log_file, 'w', encoding='utf-8', buffering=1)
        sys.stdout = self
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        sys.stdout = self._original_stdout or self._terminal
        if self._file:
            self._file.close()
            self._file = None
    
    def write(self, message: str) -> None:
        if self._mirror_to_terminal:
            self._terminal.write(message)
        if self._file:
            self._file.write(message)
    
    def flush(self) -> None:
        if self._mirror_to_terminal:
            self._terminal.flush()
        if self._file:
            self._file.flush()


# =============================================================================
# Data Classes
# =============================================================================
@dataclass
class OperationMetrics:
    """Metrics for a single operation type"""
    name: str
    total_runs: int = 0
    success_count: int = 0
    failure_count: int = 0
    latencies_ms: List[float] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    # Retry statistics
    retry_triggered: int = 0  # Number of retries triggered
    retry_success: int = 0    # Successful after retry
    retry_failed: int = 0     # Still failed after retry
    
    @property
    def success_rate(self) -> float:
        return (self.success_count / self.total_runs * 100) if self.total_runs else 0.0
    
    @property
    def avg_latency_ms(self) -> float:
        return statistics.mean(self.latencies_ms) if self.latencies_ms else 0.0
    
    @property
    def p95_latency_ms(self) -> float:
        if len(self.latencies_ms) < 2:
            return self.latencies_ms[0] if self.latencies_ms else 0.0
        sorted_lat = sorted(self.latencies_ms)
        idx = min(int(len(sorted_lat) * 0.95), len(sorted_lat) - 1)
        return sorted_lat[idx]
    
    @property
    def max_latency_ms(self) -> float:
        return max(self.latencies_ms) if self.latencies_ms else 0.0
    
    @property
    def min_latency_ms(self) -> float:
        return min(self.latencies_ms) if self.latencies_ms else 0.0
    
    def record_success(self, latency_ms: float, retried: bool = False) -> None:
        """Record successful operation"""
        self.total_runs += 1
        self.success_count += 1
        self.latencies_ms.append(latency_ms)
        if retried:
            self.retry_triggered += 1
            self.retry_success += 1

    def record_failure(self, error: str, latency_ms: float = 0.0, retried: bool = False) -> None:
        """Record failed operation"""
        self.total_runs += 1
        self.failure_count += 1
        self.errors.append(error[:MAX_ERROR_MSG_LENGTH])
        if latency_ms > 0:
            self.latencies_ms.append(latency_ms)
        if retried:
            self.retry_triggered += 1
            self.retry_failed += 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'name': self.name,
            'total_runs': self.total_runs,
            'success_count': self.success_count,
            'failure_count': self.failure_count,
            'success_rate': f"{self.success_rate:.2f}%",
            'avg_latency_ms': f"{self.avg_latency_ms:.2f}",
            'p95_latency_ms': f"{self.p95_latency_ms:.2f}",
            'max_latency_ms': f"{self.max_latency_ms:.2f}",
            'min_latency_ms': f"{self.min_latency_ms:.2f}",
            'retry_triggered': self.retry_triggered,
            'retry_success': self.retry_success,
            'retry_failed': self.retry_failed,
        }
    
    def to_detail_dict(self) -> Dict[str, Any]:
        """Convert to detail dictionary (for details.json, includes raw samples)"""
        return {
            'name': self.name,
            'total_runs': self.total_runs,
            'success_count': self.success_count,
            'failure_count': self.failure_count,
            'latencies_ms': self.latencies_ms,
            'errors': self.errors,
            'retry_triggered': self.retry_triggered,
            'retry_success': self.retry_success,
            'retry_failed': self.retry_failed,
        }
    
    @classmethod
    def from_detail_dict(cls, data: Dict[str, Any]) -> 'OperationMetrics':
        """Restore OperationMetrics from details.json structure"""
        m = cls(name=str(data.get('name', '')))
        m.total_runs = int(data.get('total_runs', 0) or 0)
        m.success_count = int(data.get('success_count', 0) or 0)
        m.failure_count = int(data.get('failure_count', 0) or 0)
        m.latencies_ms = [float(x) for x in (data.get('latencies_ms') or [])]
        m.errors = [str(x) for x in (data.get('errors') or [])]
        m.retry_triggered = int(data.get('retry_triggered', 0) or 0)
        m.retry_success = int(data.get('retry_success', 0) or 0)
        m.retry_failed = int(data.get('retry_failed', 0) or 0)
        return m
    
    def merge(self, other: 'OperationMetrics') -> None:
        """Merge another metrics object"""
        self.total_runs += other.total_runs
        self.success_count += other.success_count
        self.failure_count += other.failure_count
        self.latencies_ms.extend(other.latencies_ms)
        self.errors.extend(other.errors)
        self.retry_triggered += other.retry_triggered
        self.retry_success += other.retry_success
        self.retry_failed += other.retry_failed


@dataclass
class SandboxTestResult:
    """Complete test result for a single sandbox"""
    sandbox_id: int
    worker_id: int = 0
    success: bool = False
    error: str = ""

    create_latency_ms: float = 0.0
    connect_latency_ms: float = 0.0
    total_latency_ms: float = 0.0

    create_success: bool = False
    connect_success: bool = False
    operations_success: bool = False
    destroy_success: bool = False

    # Retry related
    create_retry_count: int = 0  # Retry count (0 means success on first try)
    create_retried: bool = False  # Whether retry was triggered

    # Timestamps (for debugging)
    start_time: str = ""           # Test start time
    end_time: str = ""             # Test end time
    create_start_time: str = ""    # Create start time
    create_end_time: str = ""      # Create end time
    destroy_start_time: str = ""   # Destroy start time
    destroy_end_time: str = ""     # Destroy end time
    real_sandbox_id: str = ""      # Actual sandbox ID returned by E2B

    operation_metrics: Dict[str, OperationMetrics] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'sandbox_id': self.sandbox_id,
            'worker_id': self.worker_id,
            'real_sandbox_id': self.real_sandbox_id,
            'success': self.success,
            'error': self.error,
            'create_success': self.create_success,
            'connect_success': self.connect_success,
            'operations_success': self.operations_success,
            'create_latency_ms': self.create_latency_ms,
            'connect_latency_ms': self.connect_latency_ms,
            'total_latency_ms': self.total_latency_ms,
            'create_retry_count': self.create_retry_count,
            'create_retried': self.create_retried,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'create_start_time': self.create_start_time,
            'create_end_time': self.create_end_time,
            'destroy_start_time': self.destroy_start_time,
            'destroy_end_time': self.destroy_end_time,
            'operations': {k: v.to_dict() for k, v in self.operation_metrics.items()},
            'operations_detail': {k: v.to_detail_dict() for k, v in self.operation_metrics.items()},
        }


def _sandbox_test_result_from_detail_dict(data: Dict[str, Any]) -> SandboxTestResult:
    """Restore SandboxTestResult from details.json structure (for multi-process aggregation)"""
    r = SandboxTestResult(sandbox_id=int(data.get('sandbox_id', 0) or 0))
    r.worker_id = int(data.get('worker_id', 0) or 0)
    r.real_sandbox_id = str(data.get('real_sandbox_id', '') or '')
    r.success = bool(data.get('success', False))
    r.error = str(data.get('error', '') or '')
    
    r.create_success = bool(data.get('create_success', False))
    r.connect_success = bool(data.get('connect_success', False))
    r.operations_success = bool(data.get('operations_success', False))
    r.destroy_success = bool(data.get('destroy_success', False))
    
    r.create_latency_ms = float(data.get('create_latency_ms', 0.0) or 0.0)
    r.connect_latency_ms = float(data.get('connect_latency_ms', 0.0) or 0.0)
    r.total_latency_ms = float(data.get('total_latency_ms', 0.0) or 0.0)
    
    r.create_retry_count = int(data.get('create_retry_count', 0) or 0)
    r.create_retried = bool(data.get('create_retried', False))
    
    r.start_time = str(data.get('start_time', '') or '')
    r.end_time = str(data.get('end_time', '') or '')
    r.create_start_time = str(data.get('create_start_time', '') or '')
    r.create_end_time = str(data.get('create_end_time', '') or '')
    r.destroy_start_time = str(data.get('destroy_start_time', '') or '')
    r.destroy_end_time = str(data.get('destroy_end_time', '') or '')
    
    ops_detail = data.get('operations_detail')
    ops_summary = data.get('operations')
    ops: Dict[str, Any] = ops_detail if isinstance(ops_detail, dict) else (ops_summary if isinstance(ops_summary, dict) else {})
    
    if isinstance(ops_detail, dict):
        r.operation_metrics = {k: OperationMetrics.from_detail_dict(v) for k, v in ops_detail.items() if isinstance(v, dict)}
    elif isinstance(ops_summary, dict):
        # Compatible with old format: cannot restore samples, fallback to count only (not included in global P95/avg calculation)
        metrics: Dict[str, OperationMetrics] = {}
        for k, v in ops_summary.items():
            if not isinstance(v, dict):
                continue
            m = OperationMetrics(name=str(v.get('name', '')))
            m.total_runs = int(v.get('total_runs', 0) or 0)
            m.success_count = int(v.get('success_count', 0) or 0)
            m.failure_count = int(v.get('failure_count', 0) or 0)
            m.retry_triggered = int(v.get('retry_triggered', 0) or 0)
            m.retry_success = int(v.get('retry_success', 0) or 0)
            m.retry_failed = int(v.get('retry_failed', 0) or 0)
            metrics[k] = m
        r.operation_metrics = metrics
    
    return r


# =============================================================================
# Resource Manager
# =============================================================================
class ResourceManager:
    """Manage sandbox and driver resources (thread-safe)"""
    
    def __init__(self):
        self._sandboxes: Dict[int, Any] = {}
        self._drivers: Dict[int, Any] = {}
        self._cleanup_done = False
        self._lock = asyncio.Lock()
    
    async def register_sandbox(self, sandbox_id: int, sandbox: Any) -> None:
        async with self._lock:
            self._sandboxes[sandbox_id] = sandbox
    
    async def register_driver(self, sandbox_id: int, driver: Any) -> None:
        async with self._lock:
            self._drivers[sandbox_id] = driver
    
    async def unregister(self, sandbox_id: int) -> None:
        async with self._lock:
            self._sandboxes.pop(sandbox_id, None)
            self._drivers.pop(sandbox_id, None)
    
    async def cleanup_all(self) -> None:
        """Async cleanup of all resources"""
        async with self._lock:
            if self._cleanup_done:
                return
            self._cleanup_done = True

            sandbox_count = len(self._sandboxes)
            driver_count = len(self._drivers)

            if sandbox_count == 0 and driver_count == 0:
                return

            print(f"\nCleaning up resources... (sandboxes: {sandbox_count}, drivers: {driver_count})")

            # Clean up drivers
            loop = asyncio.get_running_loop()
            for driver in list(self._drivers.values()):
                try:
                    await loop.run_in_executor(None, driver.quit)
                except Exception as e:
                    if logger:
                        logger.debug(f"Failed to cleanup driver: {e}")

            # Clean up sandboxes
            async def kill_sandbox(sandbox: Any) -> None:
                try:
                    await sandbox.kill()
                except Exception as e:
                    if logger:
                        logger.debug(f"Failed to cleanup sandbox: {e}")

            await asyncio.gather(
                *[kill_sandbox(s) for s in self._sandboxes.values()],
                return_exceptions=True
            )

            self._sandboxes.clear()
            self._drivers.clear()
            print("Resource cleanup complete")


# =============================================================================
# SDK Helper Functions
# =============================================================================
def get_async_sandbox_class() -> type:
    """Lazy-load AsyncSandbox class"""
    global AsyncSandbox
    if AsyncSandbox is None:
        from e2b import AsyncSandbox as _AsyncSandbox
        AsyncSandbox = _AsyncSandbox

    return AsyncSandbox


async def warmup_connection_pool() -> None:
    """Warm up HTTP connection pool"""
    print("\nWarming up connection pool: calling list API...")
    start = time.perf_counter()
    try:
        SandboxClass = get_async_sandbox_class()
        paginator = SandboxClass.list(limit=1)
        await paginator.next_items()
        elapsed_ms = (time.perf_counter() - start) * 1000
        print(f"Warmup complete, elapsed: {elapsed_ms:.0f}ms")
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        print(f"Warmup complete (with exception, not affecting): {elapsed_ms:.0f}ms, {e}")


def create_appium_connection_class(access_token: str) -> type:
    """Create isolated AppiumConnection subclass for each sandbox"""
    from appium.webdriver.appium_connection import AppiumConnection

    class IsolatedConnection(AppiumConnection):
        extra_headers = {'X-Access-Token': access_token}

    return IsolatedConnection


def create_appium_driver(sandbox: Any, sandbox_id: int = -1, max_retries: int = 5) -> Any:
    """Create Appium driver connection"""
    from appium import webdriver
    from appium.options.android import UiAutomator2Options
    from appium.webdriver.client_config import AppiumClientConfig

    def _log(msg: str) -> None:
        print(f"  [{format_timestamp()}] [Sandbox {sandbox_id:2d}]   {msg}")
    
    access_token = sandbox._envd_access_token
    health_url = f"https://{sandbox.get_host(8080)}/healthz"
    headers = {'X-Access-Token': access_token}
    last_error: Optional[Exception] = None
    
    for attempt in range(max_retries + 1):
        if attempt > 0:
            _log(f"Retry {attempt}/{max_retries}, health check first...")
            for _ in range(10):
                try:
                    resp = requests.get(health_url, headers=headers, timeout=5)
                    if resp.status_code == 200:
                        _log("Health check passed")
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.1)  # 100ms interval, max 1 second
            else:
                _log("Health check timeout, continue trying to connect")
        
        try:
            with timer() as t1:
                options = UiAutomator2Options()
                options.platform_name = 'Android'
                options.automation_name = 'UiAutomator2'
                options.new_command_timeout = 0
                
                ConnectionClass = create_appium_connection_class(access_token)
                appium_url = f"https://{sandbox.get_host(4723)}"
                client_config = AppiumClientConfig(
                    remote_server_addr=appium_url,
                    timeout=300,
                )
                executor = ConnectionClass(client_config=client_config)
            
            with timer() as t2:
                driver = webdriver.Remote(
                    command_executor=executor,
                    options=options,
                )
            
            _log(f"Config: {t1['elapsed_ms']:.0f}ms, Session create: {t2['elapsed_ms']:.0f}ms")

            if driver and hasattr(driver, 'get_window_size'):
                _ = driver.session_id
                return driver
            raise RuntimeError("Invalid driver object")

        except Exception as e:
            last_error = e
            _log(f"Connection failed: {str(e)[:60]}")
            continue

    raise RuntimeError(f"Appium connection failed (retried {max_retries} times): {last_error}")


# =============================================================================
# Sandbox Tester
# =============================================================================
class AsyncSandboxTester:
    """Async sandbox tester"""
    
    def __init__(self, sandbox_id: int, config: Dict[str, Any], output_dir: Path,
                 executor: ThreadPoolExecutor, resource_manager: ResourceManager):
        self.sandbox_id = sandbox_id
        self.worker_id = int(config.get('_WORKER_ID', 0) or 0)
        self.config = config
        self.output_dir = output_dir
        self.executor = executor
        self.resource_manager = resource_manager
        
        self.sandbox: Optional[Any] = None
        self.driver: Optional[Any] = None
        self.screen_width = 720
        self.screen_height = 1280
        
        self.sandbox_output_dir = output_dir / f"sandbox_{sandbox_id}"
        self.sandbox_output_dir.mkdir(parents=True, exist_ok=True)
        
        self.metrics = create_operation_metrics()
    
    def _log(self, msg: str) -> None:
        print(f"  [{format_timestamp()}] [Sandbox {self.sandbox_id:2d}] {msg}")

    async def run(self) -> SandboxTestResult:
        """Run complete test flow"""
        result = SandboxTestResult(sandbox_id=self.sandbox_id)
        result.worker_id = self.worker_id
        result.start_time = format_timestamp()

        with timer() as total_timer:
            # 1. Create sandbox
            created = await self._create_sandbox(result)
            if created:
                # 2. Connect Appium
                connected = await self._connect_appium(result)
                if not connected:
                    result.destroy_start_time = format_timestamp()
                    await self._cleanup()
                    result.destroy_end_time = format_timestamp()
                else:
                    # 3. Execute operations
                    await self._run_operations(result)

                    # 4. Cleanup
                    result.destroy_start_time = format_timestamp()
                    self._log("Destroying sandbox...")
                    result.destroy_success = await self._cleanup()
                    result.destroy_end_time = format_timestamp()
                    self._log("Sandbox destroyed")

        result.end_time = format_timestamp()
        result.total_latency_ms = total_timer['elapsed_ms']
        result.success = result.create_success and result.connect_success and result.operations_success
        return result

    async def _create_sandbox(self, result: SandboxTestResult, max_retries: int = 1, retry_delay_ms: int = 100) -> bool:
        """Create sandbox (with retry support)"""
        SandboxClass = get_async_sandbox_class()
        last_error = None
        total_start = time.perf_counter()
        result.create_start_time = format_timestamp()
        
        for attempt in range(max_retries + 1):
            if attempt > 0:
                result.create_retried = True
                result.create_retry_count = attempt
                self._log(f"Retry create sandbox ({attempt}/{max_retries})...")
                await asyncio.sleep(retry_delay_ms / 1000)

            start = time.perf_counter()
            try:
                self._log(f"Preparing to create sandbox ts={time.time():.3f}")
                self.sandbox = await SandboxClass.create(
                    template=self.config['SANDBOX_TEMPLATE'],
                    timeout=self.config['SANDBOX_TIMEOUT']
                )

                result.create_latency_ms = (time.perf_counter() - total_start) * 1000
                result.create_success = True
                result.create_end_time = format_timestamp()
                result.real_sandbox_id = self.sandbox.sandbox_id

                await self.resource_manager.register_sandbox(self.sandbox_id, self.sandbox)
                if attempt > 0:
                    self._log(f"Sandbox created (after {attempt} retries, {result.create_latency_ms:.0f}ms) sandbox_id={self.sandbox.sandbox_id}")
                else:
                    self._log(f"Sandbox created ({result.create_latency_ms:.0f}ms) sandbox_id={self.sandbox.sandbox_id}")
                return True

            except Exception as e:
                elapsed_ms = (time.perf_counter() - start) * 1000
                last_error = extract_error_details(e)
                self._log(f"Sandbox creation failed: {last_error[:MAX_ERROR_MSG_LENGTH]} ({elapsed_ms:.0f}ms)")

        # All retries failed
        result.create_latency_ms = (time.perf_counter() - total_start) * 1000
        result.error = f"Sandbox creation failed (retried {max_retries} times): {last_error[:MAX_ERROR_MSG_LENGTH]}"
        self._log(f"{result.error} (total: {result.create_latency_ms:.0f}ms)")
        return False

    async def _connect_appium(self, result: SandboxTestResult) -> bool:
        """Connect Appium"""
        self._log("Connecting Appium...")
        start = time.perf_counter()
        try:
            loop = asyncio.get_running_loop()
            import functools
            self.driver = await loop.run_in_executor(
                self.executor,
                functools.partial(create_appium_driver, self.sandbox, self.sandbox_id)
            )
            
            result.connect_latency_ms = (time.perf_counter() - start) * 1000
            result.connect_success = True
            await self.resource_manager.register_driver(self.sandbox_id, self.driver)
            
            window_size = await loop.run_in_executor(self.executor, self.driver.get_window_size)
            self.screen_width = window_size['width']
            self.screen_height = window_size['height']
            self._log(f"Appium connected ({result.connect_latency_ms:.0f}ms)")
            return True

        except Exception as e:
            result.connect_latency_ms = (time.perf_counter() - start) * 1000
            error_msg = extract_error_details(e)
            result.error = f"Appium connection failed: {error_msg[:MAX_ERROR_MSG_LENGTH]}"
            self._log(f"{result.error} ({result.connect_latency_ms:.0f}ms)")
            return False

    async def _run_operations(self, result: SandboxTestResult) -> None:
        """Execute operation tests"""
        try:
            self._log("Executing operation tests...")
            loop = asyncio.get_running_loop()
            result.operations_success = await loop.run_in_executor(
                self.executor, self._execute_operations
            )
            result.operation_metrics = self.metrics
            status = "all passed" if result.operations_success else "partial failed"
            self._log(f"Operation tests complete ({status})")

        except Exception as e:
            error_msg = str(e).strip() if str(e).strip() else f"{type(e).__name__}"
            result.error = f"Operation test exception: {error_msg[:MAX_ERROR_MSG_LENGTH]}"
            self._log(result.error)
            result.operation_metrics = self.metrics

    async def _cleanup(self) -> bool:
        """Cleanup resources"""
        success = True
        loop = asyncio.get_running_loop()

        if self.driver:
            try:
                await loop.run_in_executor(self.executor, self.driver.quit)
            except Exception as e:
                if logger:
                    logger.debug(f"Failed to cleanup driver: {e}")
                success = False
            self.driver = None

        if self.sandbox:
            try:
                await self.sandbox.kill()
            except Exception as e:
                if logger:
                    logger.debug(f"Failed to cleanup sandbox: {e}")
                success = False
            self.sandbox = None

        await self.resource_manager.unregister(self.sandbox_id)
        return success

    def _execute_operations(self) -> bool:
        """Execute all operations (sync method, called in thread pool)"""
        all_success = True

        # Operation mapping
        operation_funcs: Dict[str, Tuple[Callable, tuple]] = {
            'upload_apk': (self._upload_app, ('meituan',)),
            'install_apk': (self._install_and_grant, ('meituan',)),
            'launch_apk': (self._launch_app, ('meituan',)),
            'screenshot_1': (self._take_screenshot, ('screenshot_1.png',)),
            'tap_random_1': (self._tap_random, ()),
            'get_page_xml': (self._get_page_xml, ('page_1.xml',)),
            'get_device_info': (self._get_device_info, ('device_info.json',)),
            'open_browser': (self._open_browser, ()),
            'tap_random_2': (self._tap_random, ()),
            'screenshot_2': (self._take_screenshot, ('screenshot_2.png',)),
            'get_logs': (self._get_device_logs, ('logcat.txt',)),
        }

        for i, (key, name) in enumerate(OPERATIONS, 1):
            func, args = operation_funcs[key]
            success, latency = self._measure_operation(key, func, *args)
            self._log(f"[{i}/{len(OPERATIONS)}] {name}: {'success' if success else 'failed'} ({latency:.0f}ms)")
            all_success &= success

        return all_success

    def _measure_operation(self, key: str, func: Callable, *args,
                           max_retries: int = 1, retry_delay_ms: int = 100) -> Tuple[bool, float]:
        """Measure single operation (with retry support)"""
        metrics = self.metrics[key]
        last_error = None
        total_start = time.perf_counter()
        retried = False
        
        for attempt in range(max_retries + 1):
            if attempt > 0:
                retried = True
                self._log(f"  Retry {key} ({attempt}/{max_retries})...")
                time.sleep(retry_delay_ms / 1000)

            start = time.perf_counter()
            try:
                result = func(*args)
                elapsed_ms = (time.perf_counter() - start) * 1000
                success = result is not None and result is not False

                if success:
                    total_elapsed_ms = (time.perf_counter() - total_start) * 1000
                    metrics.record_success(total_elapsed_ms, retried=retried)
                    return True, total_elapsed_ms
                else:
                    last_error = f"Operation returned: {result}"

            except Exception as e:
                last_error = extract_error_details(e)

        # All retries failed
        total_elapsed_ms = (time.perf_counter() - total_start) * 1000
        metrics.record_failure(last_error, total_elapsed_ms, retried=retried)
        return False, total_elapsed_ms

    # ========== Operation Implementations ==========

    def _tap_random(self) -> bool:
        """Tap random position"""
        x = random.randint(100, self.screen_width - 100)
        y = random.randint(200, self.screen_height - 200)
        return self._execute_shell('input', ['tap', str(x), str(y)])
    
    def _install_and_grant(self, app_name: str) -> bool:
        if not self._install_app(app_name):
            return False
        self._grant_permissions(app_name)
        return True
    
    def _upload_app(self, app_name: str) -> bool:
        """Upload APK (skip if using mounted mode)"""
        # If using mounted APK, return success directly (no need to upload)
        if self.config.get('USE_MOUNTED_APK', True):
            return True

        config = APP_CONFIGS.get(app_name.lower())
        if not config:
            return False

        apk_dir = Path(__file__).parent / "apk"
        apk_path = apk_dir / config['apk_name']

        if not apk_path.exists():
            self._log("Local APK not found, starting download...")
            if not download_apk(config['apk_name'], apk_path):
                return False

        CHUNK_SIZE = 20 * 1024 * 1024
        file_size = apk_path.stat().st_size
        total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE

        temp_dir = '/data/local/tmp/chunks'
        remote_path = config['remote_path']

        try:
            import base64

            # Clean and prepare directory
            self._execute_shell('rm', ['-rf', temp_dir])
            self._execute_shell('mkdir', ['-p', temp_dir])
            self._execute_shell('rm', ['-f', remote_path])

            # Chunked upload
            with open(apk_path, 'rb') as f:
                for i in range(total_chunks):
                    chunk_data = f.read(CHUNK_SIZE)
                    chunk_b64 = base64.b64encode(chunk_data).decode('utf-8')
                    chunk_path = f"{temp_dir}/chunk_{i:04d}"
                    self.driver.push_file(chunk_path, chunk_b64)

            # Merge chunks
            for i in range(total_chunks):
                chunk_path = f"{temp_dir}/chunk_{i:04d}"
                if i == 0:
                    self._execute_shell('cp', [chunk_path, remote_path])
                else:
                    self._execute_shell('cat', [chunk_path, '>>', remote_path])
                self._execute_shell('rm', ['-f', chunk_path])

            # Clean temp directory
            self._execute_shell('rm', ['-rf', temp_dir])

            # Verify MD5
            local_md5 = hashlib.md5(apk_path.read_bytes()).hexdigest()
            md5_result = self._execute_shell('md5sum', [remote_path], return_result=True)
            remote_md5 = md5_result.strip().split()[0] if md5_result else ''

            return remote_md5.lower() == local_md5.lower()

        except Exception as e:
            if logger:
                logger.debug(f"Upload APK exception: {e}")
            return False

    def _install_app(self, app_name: str) -> bool:
        """Install APK (select mounted path or upload path based on config)"""
        config = APP_CONFIGS.get(app_name.lower())
        if not config:
            return False

        # Select APK path based on config
        use_mounted = self.config.get('USE_MOUNTED_APK', True)
        apk_path = config['mounted_path'] if use_mounted else config['remote_path']

        try:
            state = self.driver.query_app_state(config['package'])
            if state != 0:
                return True

            result = self.driver.execute_script('mobile: shell', {
                'command': 'pm',
                'args': ['install', '-r', '-g', apk_path],
                'timeout': 120000
            })

            if result and 'Success' in str(result):
                return True

            state = self.driver.query_app_state(config['package'])
            return state != 0
        except Exception as e:
            if logger:
                logger.debug(f"Install APK failed: {e}")
            return False

    def _grant_permissions(self, app_name: str) -> bool:
        """Grant permissions"""
        config = APP_CONFIGS.get(app_name.lower())
        if not config:
            return False
        
        package = config['package']
        for permission in config.get('permissions', []):
            try:
                self._execute_shell('pm', ['grant', package, permission])
            except Exception as e:
                if logger:
                    logger.debug(f"Grant {permission} failed: {e}")
        return True

    def _launch_app(self, app_name: str) -> bool:
        """Launch app"""
        config = APP_CONFIGS.get(app_name.lower())
        if not config:
            return False

        try:
            self.driver.activate_app(config['package'])
            time.sleep(2)
            state = self.driver.query_app_state(config['package'])
            return state == 4
        except Exception as e:
            if logger:
                logger.debug(f"Launch app failed: {e}")
            return False

    def _take_screenshot(self, filename: str) -> bool:
        try:
            filepath = self.sandbox_output_dir / filename
            # save_screenshot returns True on success, False or exception on failure
            result = self.driver.save_screenshot(str(filepath))
            if result:
                return True
            # If returns False, check if file exists (compatible with different Appium client versions)
            return filepath.exists() and filepath.stat().st_size > 0
        except Exception as e:
            if logger:
                logger.debug(f"Screenshot failed: {e}")
            return False

    def _get_page_xml(self, filename: str) -> Optional[str]:
        try:
            page_source = self.driver.page_source
            if page_source:
                filepath = self.sandbox_output_dir / filename
                filepath.write_text(page_source, encoding='utf-8')
            return page_source
        except Exception as e:
            if logger:
                logger.debug(f"Get page XML failed: {e}")
            return None

    def _get_device_info(self, filename: str) -> Optional[Dict]:
        try:
            model = self._execute_shell('getprop', ['ro.product.model'], return_result=True)
            info = {'model': model.strip() if model else 'N/A'}

            filepath = self.sandbox_output_dir / filename
            filepath.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding='utf-8')
            return info
        except Exception as e:
            if logger:
                logger.debug(f"Get device info failed: {e}")
            return None

    def _open_browser(self, url: str = "https://www.tencent.com/zh-cn/") -> bool:
        try:
            self._execute_shell('am', ['start', '-a', 'android.intent.action.VIEW', '-d', url])
            time.sleep(2)
            return True
        except Exception as e:
            if logger:
                logger.debug(f"Open browser failed: {e}")
            return False

    def _get_device_logs(self, filename: str) -> Optional[str]:
        try:
            logs = self._execute_shell('logcat', ['-d'], return_result=True)
            if logs:
                filepath = self.sandbox_output_dir / filename
                filepath.write_text(logs, encoding='utf-8')
            return logs
        except Exception as e:
            if logger:
                logger.debug(f"Get logs failed: {e}")
            return None

    def _execute_shell(self, command: str, args: List[str], return_result: bool = False) -> Union[str, bool, None]:
        """
        Generic method for executing shell commands.

        Args:
            command: Shell command to execute
            args: Command arguments
            return_result: If True, returns command output; if False, returns True on success

        Returns:
            Command output string if return_result=True, otherwise True on success
        """
        result = self.driver.execute_script('mobile: shell', {
            'command': command,
            'args': args
        })
        return result if return_result else True


# =============================================================================
# Result Reporting
# =============================================================================
class ResultReporter:
    """Result report generator"""

    def __init__(self, sandbox_count: int):
        self.sandbox_count = sandbox_count

    def aggregate(self, results: List[SandboxTestResult],
                  start_time: datetime, end_time: datetime,
                  config: Dict[str, Any]) -> Dict[str, Any]:
        """Aggregate test results"""
        duration = (end_time - start_time).total_seconds()

        create_metrics = OperationMetrics(name='Sandbox Create')
        connect_metrics = OperationMetrics(name='Appium Connect')
        operation_metrics = create_operation_metrics()

        success_count = 0

        # Retry statistics
        retry_triggered = 0  # Number of retries triggered
        retry_success = 0    # Successful after retry
        retry_failed = 0     # Still failed after retry

        for r in results:
            # Aggregate create metrics
            if r.create_success:
                create_metrics.record_success(r.create_latency_ms)
            else:
                create_metrics.record_failure(r.error, r.create_latency_ms)

            # Aggregate retry stats
            if r.create_retried:
                retry_triggered += 1
                if r.create_success:
                    retry_success += 1
                else:
                    retry_failed += 1

            # Aggregate connect metrics
            if r.create_success:
                if r.connect_success:
                    connect_metrics.record_success(r.connect_latency_ms)
                else:
                    connect_metrics.record_failure(r.error, r.connect_latency_ms)

            # Merge operation metrics
            for key, metrics in r.operation_metrics.items():
                if key in operation_metrics:
                    operation_metrics[key].merge(metrics)
            
            if r.success:
                success_count += 1
        
        data: Dict[str, Any] = {
            'config': {
                'sandbox_count': self.sandbox_count,
                'process_count': int(config.get('PROCESS_COUNT', 2) or 2),
                'use_mounted_apk': bool(config.get('USE_MOUNTED_APK', False)),
                'thread_pool_size': config.get('THREAD_POOL_SIZE', 5),
            },
            'summary': {
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'duration_seconds': duration,
                'total_sandboxes': self.sandbox_count,
                'successful_sandboxes': success_count,
                'success_rate': f"{success_count / self.sandbox_count * 100:.2f}%",
            },
            'retry': {
                'sandbox_create': {
                    'triggered': retry_triggered,
                    'success': retry_success,
                    'failed': retry_failed,
                },
            },
            'sandbox_create': create_metrics.to_dict(),
            'appium_connect': connect_metrics.to_dict(),
            'operations': {k: v.to_dict() for k, v in operation_metrics.items()},
        }

        return data
    
    def print_summary(self, summary: Dict[str, Any]) -> None:
        """Print summary report"""
        print(f"\n{'='*80}")
        print("Test Results Summary")
        print(f"{'='*80}")
        print(f"Total duration: {summary['summary']['duration_seconds']:.2f} seconds")
        print(f"Successful sandboxes: {summary['summary']['successful_sandboxes']}/{summary['summary']['total_sandboxes']} "
              f"({summary['summary']['success_rate']})")

        print(f"\n{'-'*80}")
        print(f"{'Operation':<28} {'Success%':<12} {'Avg(ms)':<12} {'P95(ms)':<12} {'Max(ms)':<12}")
        print(f"{'-'*80}")

        idx = 1

        # Print sandbox create metrics
        self._print_metric_row(idx, 'Sandbox Create', summary['sandbox_create'])
        idx += 1

        self._print_metric_row(idx, 'Appium Connect', summary['appium_connect'])
        idx += 1

        # Print operation metrics (skip Upload APK if using mounted mode)
        use_mounted = summary.get('config', {}).get('use_mounted_apk', False)
        for key, name in OPERATIONS:
            # Skip Upload APK if using mounted mode
            if use_mounted and key == 'upload_apk':
                continue

            if key in summary['operations']:
                self._print_metric_row(idx, name, summary['operations'][key])
                idx += 1

        print(f"{'='*80}")

        # Print retry statistics
        self._print_retry_summary(summary)

    def _print_metric_row(self, idx: int, name: str, metrics: Dict[str, Any]) -> None:
        """Print single metric row"""
        print(f"{f'{idx}. {name}':<28} {metrics['success_rate']:<12} "
              f"{metrics['avg_latency_ms']:<12} {metrics['p95_latency_ms']:<12} "
              f"{metrics['max_latency_ms']:<12}")

    def _print_retry_summary(self, summary: Dict[str, Any]) -> None:
        """Print retry statistics"""
        retry_items = []

        # Sandbox create retries
        sandbox_retry = summary.get('retry', {}).get('sandbox_create', {})
        if sandbox_retry.get('triggered', 0) > 0:
            retry_items.append(('Sandbox Create', sandbox_retry))

        # Operation retries
        for key, name in OPERATIONS:
            op = summary.get('operations', {}).get(key, {})
            if op.get('retry_triggered', 0) > 0:
                retry_items.append((name, {
                    'triggered': op['retry_triggered'],
                    'success': op['retry_success'],
                    'failed': op['retry_failed'],
                }))

        if retry_items:
            print(f"\nRetry Statistics:")
            print(f"{'-'*60}")
            print(f"{'Operation':<20} {'Triggered':<12} {'Success':<12} {'Failed':<12}")
            print(f"{'-'*60}")
            for name, retry in retry_items:
                print(f"{name:<20} {retry['triggered']:<12} {retry['success']:<12} {retry['failed']:<12}")
            print(f"{'-'*60}")

    def save(self, summary: Dict[str, Any], results: List[SandboxTestResult],
             task_dir: Path) -> None:
        """Save results to files"""
        # Save summary
        summary_file = task_dir / "summary.json"
        summary_file.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )

        # Save details
        details = [r.to_dict() for r in results]
        details_file = task_dir / "details.json"
        details_file.write_text(
            json.dumps(details, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )

        print(f"\nResults saved to: {task_dir}")


# =============================================================================
# Batch Operation Runner
# =============================================================================
class BatchRunner:
    """Batch operation runner"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.sandbox_count = config['SANDBOX_COUNT']
        self.executor: Optional[ThreadPoolExecutor] = None
        self.resource_manager = ResourceManager()
        self.reporter = ResultReporter(self.sandbox_count)
        self._sandbox_id_offset = 0

    async def run(self, task_dir: Optional[Path] = None, sandbox_id_offset: int = 0) -> Dict[str, Any]:
        """Run batch operations"""
        self._sandbox_id_offset = int(sandbox_id_offset)
        
        if task_dir is None:
            output_dir = Path(__file__).parent / "output" / "batch_output"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            task_dir = output_dir / f"{self.sandbox_count}_{timestamp}"
            task_dir.mkdir(parents=True, exist_ok=True)
        else:
            task_dir.mkdir(parents=True, exist_ok=True)
        
        # Thread pool size: Appium connections/operations are sync blocking, need thread pool for concurrency
        # Default=SANDBOX_COUNT (consistent with old behavior), can override with THREAD_POOL_SIZE; max 1000
        override_workers = self.config.get('THREAD_POOL_SIZE')
        max_workers = min(int(override_workers), 1000) if override_workers else min(self.sandbox_count, 1000)
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        print(f"Thread pool size: {max_workers}")

        log_file = task_dir / "console.log"
        # Main process output (including summary) always outputs to terminal
        mirror_to_terminal = True
        with TeeLogger(log_file, mirror_to_terminal=mirror_to_terminal):
            try:
                return await self._run_tests(task_dir)
            finally:
                if self.executor:
                    self.executor.shutdown(wait=False)
                    self.executor = None
    
    async def _run_tests(self, task_dir: Path) -> Dict[str, Any]:
        """Execute tests"""
        self._print_header(task_dir)

        # Warmup connection pool (not counted in batch operation time)
        await warmup_connection_pool()

        print(f"\nStarting concurrent test of {self.sandbox_count} sandboxes...")

        # Record batch operation start time
        start_time = datetime.now()

        # Execute tests concurrently
        sandbox_ids = [self._sandbox_id_offset + i for i in range(self.sandbox_count)]
        tasks = [self._run_single_test(sandbox_id, task_dir) for sandbox_id in sandbox_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Record batch operation end time (before result processing)
        end_time = datetime.now()

        # Process results (not counted in batch operation total time)
        valid_results = self._process_results(sandbox_ids, results)

        # Generate report
        summary = self.reporter.aggregate(valid_results, start_time, end_time, self.config)

        # In multi-process mode, worker processes only save results without printing summary (avoid duplicate output)
        # Final summary is printed by parent process
        is_worker = self.config.get('_WORKER_ID') is not None
        actual_process_count = int(self.config.get('_ACTUAL_PROCESS_COUNT', 1))
        is_multiprocess_worker = is_worker and actual_process_count > 1

        if not is_multiprocess_worker:
            # Single process mode or single process scenario: print summary
            self.reporter.print_summary(summary)

        self.reporter.save(summary, valid_results, task_dir)

        return summary

    def _print_header(self, task_dir: Path) -> None:
        """Print test header info"""
        print(f"\n{'='*80}")
        print("Batch Concurrent Operations (Async Version)")
        print(f"{'='*80}")
        print(f"Concurrency: {self.sandbox_count}")
        print(f"Task directory: {task_dir}")
        print(f"{'='*80}")

    async def _run_single_test(self, sandbox_id: int, task_dir: Path) -> SandboxTestResult:
        """Run single sandbox test"""
        tester = AsyncSandboxTester(
            sandbox_id, self.config, task_dir,
            self.executor, self.resource_manager
        )
        return await tester.run()

    def _process_results(self, sandbox_ids: List[int], results: List[Any]) -> List[SandboxTestResult]:
        """Process test results"""
        valid_results = []
        for sandbox_id, r in zip(sandbox_ids, results):
            if isinstance(r, Exception):
                print(f"  [Sandbox {sandbox_id}] Exception: {str(r)[:50]}")
                err_result = SandboxTestResult(sandbox_id=sandbox_id, error=str(r)[:MAX_ERROR_MSG_LENGTH])
                err_result.worker_id = int(self.config.get('_WORKER_ID', 0) or 0)
                valid_results.append(err_result)
            else:
                valid_results.append(r)
                status = "success" if r.success else "failed"
                # Detailed output: sandbox ID, real ID, start/end time, create time, destroy time
                print(f"  [Done] Sandbox {r.sandbox_id} ({r.real_sandbox_id}) {status} | "
                      f"start: {r.start_time} end: {r.end_time} | "
                      f"create: {r.create_start_time}~{r.create_end_time} ({r.create_latency_ms:.0f}ms) | "
                      f"destroy: {r.destroy_start_time}~{r.destroy_end_time} | "
                      f"total: {r.total_latency_ms:.0f}ms")
        return valid_results

    async def cleanup(self) -> None:
        """Cleanup resources"""
        await self.resource_manager.cleanup_all()


def _split_sandbox_counts(total: int, process_count: int) -> List[int]:
    """Split total sandbox count across processes, distribute evenly"""
    total = int(total)
    process_count = int(process_count)
    if total <= 0:
        return []
    process_count = max(1, min(process_count, total))
    base, rem = divmod(total, process_count)
    return [base + (1 if i < rem else 0) for i in range(process_count)]


def _worker_process_entry(worker_id: int, sandbox_count: int, sandbox_id_offset: int, task_dir_str: str,
                          base_config: Dict[str, Any]) -> None:
    """Worker process entry: each worker has independent event loop + thread pool"""
    global logger, _runner, _cleanup_done
    _cleanup_done = False

    config = dict(base_config)
    config['SANDBOX_COUNT'] = int(sandbox_count)
    config['PROCESS_COUNT'] = 1  # Prevent worker from recursively splitting
    config['_WORKER_ID'] = int(worker_id)

    logger = setup_logging()

    os.environ["E2B_DOMAIN"] = config['E2B_DOMAIN']
    os.environ["E2B_API_KEY"] = config['E2B_API_KEY']

    def signal_handler(signum: int, frame: Optional[FrameType]) -> None:
        sig_name = signal.Signals(signum).name
        print(f"\n[worker {worker_id}] Received {sig_name} signal, exiting...")
        _sync_cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    import atexit
    atexit.register(_sync_cleanup)

    runner = BatchRunner(config)
    _runner = runner

    try:
        asyncio.run(runner.run(task_dir=Path(task_dir_str), sandbox_id_offset=int(sandbox_id_offset)))
    except KeyboardInterrupt:
        print("\n\nTest interrupted")
        _sync_cleanup()
    except Exception as e:
        print(f"Test failed: {e}")
        traceback.print_exc()
        _sync_cleanup()


def _run_multiprocess(config: Dict[str, Any]) -> None:
    """Multi-process mode: parent process splits tasks and aggregates results"""
    global _worker_processes
    
    total = int(config['SANDBOX_COUNT'])
    process_count = int(config.get('PROCESS_COUNT', 1) or 1)
    counts = _split_sandbox_counts(total, process_count)
    process_count = len(counts)
    
    output_dir = Path(__file__).parent / "output" / "batch_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    task_dir = output_dir / f"{total}_p{process_count}_{timestamp}"
    task_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = task_dir / "console.log"
    # Parent process summary always outputs to terminal (most important info for user)
    mirror_to_terminal = True
    with TeeLogger(log_file, mirror_to_terminal=mirror_to_terminal):
        print(f"\n{'='*80}")
        print("Batch Concurrent Operations (Multi-process + Thread Pool)")
        print(f"{'='*80}")
        print(f"Total sandboxes: {total}")
        print(f"Process count: {process_count}")
        print(f"Per-process allocation: {counts}")
        print(f"Task directory: {task_dir}")
        print(f"{'='*80}")

        # Write split plan for debugging
        plan = []
        offset = 0
        for wid, c in enumerate(counts):
            plan.append({'worker_id': wid, 'sandbox_count': c, 'sandbox_id_offset': offset})
            offset += c
        (task_dir / "workers.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding='utf-8')
        
        ctx = multiprocessing.get_context("spawn")
        processes: List[multiprocessing.Process] = []
        
        offset = 0
        for wid, c in enumerate(counts):
            worker_dir = task_dir / f"worker_{wid:02d}"
            worker_dir.mkdir(parents=True, exist_ok=True)

            # Pass actual process count so workers know whether to output to terminal
            worker_config = dict(config)
            worker_config['_ACTUAL_PROCESS_COUNT'] = process_count

            p = ctx.Process(
                target=_worker_process_entry,
                args=(wid, c, offset, str(worker_dir), worker_config),
                name=f"batch-worker-{wid}",
            )
            processes.append(p)
            offset += c
        
        _worker_processes = processes
        for p in processes:
            p.start()
        
        for p in processes:
            p.join()
        
        exit_codes = {p.name: p.exitcode for p in processes}
        failed = {k: v for k, v in exit_codes.items() if v not in (0, None)}
        if failed:
            print(f"Warning: Some worker processes exited abnormally: {failed}")

        _worker_processes.clear()

        # Aggregate results
        worker_summaries: List[Dict[str, Any]] = []
        all_results: List[SandboxTestResult] = []

        for item in plan:
            wid = item['worker_id']
            worker_dir = task_dir / f"worker_{wid:02d}"
            summary_path = worker_dir / "summary.json"
            details_path = worker_dir / "details.json"
            if not summary_path.exists() or not details_path.exists():
                print(f"Warning: worker_{wid:02d} missing result files, skipping aggregation")
                continue
            
            worker_summaries.append(json.loads(summary_path.read_text(encoding='utf-8')))
            details = json.loads(details_path.read_text(encoding='utf-8'))
            if isinstance(details, list):
                all_results.extend(_sandbox_test_result_from_detail_dict(d) for d in details if isinstance(d, dict))

        # Use worker's actual start/end times to calculate overall interval
        start_times = []
        end_times = []
        for s in worker_summaries:
            try:
                st = s.get('summary', {}).get('start_time')
                et = s.get('summary', {}).get('end_time')
                if st:
                    start_times.append(datetime.fromisoformat(st))
                if et:
                    end_times.append(datetime.fromisoformat(et))
            except Exception:
                continue
        overall_start = min(start_times) if start_times else datetime.now()
        overall_end = max(end_times) if end_times else datetime.now()
        
        reporter = ResultReporter(total)
        summary = reporter.aggregate(all_results, overall_start, overall_end, config)
        reporter.print_summary(summary)
        reporter.save(summary, all_results, task_dir)

        print(f"\nMulti-process batch operation complete: {task_dir}")


# =============================================================================
# Main Function
# =============================================================================
async def main_async() -> None:
    """Async main function"""
    global logger

    try:
        config = load_config()
    except ConfigurationError as e:
        print(f"Configuration error: {e}")
        sys.exit(1)

    # Initialize logging
    logger = setup_logging()

    os.environ["E2B_DOMAIN"] = config['E2B_DOMAIN']
    os.environ["E2B_API_KEY"] = config['E2B_API_KEY']

    # Print configuration
    from e2b.api import limits
    print("=" * 80)
    print("Mobile Sandbox Batch Operations")
    print("=" * 80)
    print(f"E2B_DOMAIN: {config['E2B_DOMAIN']}")
    print(f"SANDBOX_TEMPLATE: {config['SANDBOX_TEMPLATE']}")
    print(f"SANDBOX_COUNT: {config['SANDBOX_COUNT']}")
    print(f"PROCESS_COUNT: {config['PROCESS_COUNT']}")
    print(f"USE_MOUNTED_APK: {config['USE_MOUNTED_APK']}")
    print(f"THREAD_POOL_SIZE: {config['THREAD_POOL_SIZE']}")
    print(f"HTTP pool: max_keepalive={limits.max_keepalive_connections}, max_conn={limits.max_connections}")

    # Pre-check APK (only in local upload mode)
    if config['USE_MOUNTED_APK']:
        print(f"\nUsing mounted APK (path: {MOUNT_PATH_PREFIX})")
    else:
        print("\nChecking APK file...")
        if not ensure_apk_ready('meituan'):
            print("\nError: APK preparation failed, cannot continue")
            sys.exit(1)
    print("")

    # Multi-process mode: parent process splits and aggregates
    if int(config.get('PROCESS_COUNT', 1) or 1) > 1:
        _run_multiprocess(config)
        return

    # Single process mode
    global _runner
    runner = BatchRunner(config)
    _runner = runner  # Set global variable for cleanup function

    try:
        await runner.run()
    except KeyboardInterrupt:
        print("\n\nTest interrupted")
        await runner.cleanup()
    except Exception as e:
        logger.error(f"Test failed: {e}")
        traceback.print_exc()
        await runner.cleanup()

    print("\nDone.")


# Global variables for cleanup
_runner: Optional[BatchRunner] = None
_cleanup_done = False
_worker_processes: List[multiprocessing.Process] = []


def _sync_cleanup() -> None:
    """Synchronous cleanup function (for atexit and signal handlers)"""
    global _runner, _cleanup_done, _worker_processes

    if _cleanup_done:
        return
    _cleanup_done = True

    # Multi-process mode: try graceful shutdown of child processes first to avoid orphan sandbox resources
    if _worker_processes:
        print("\nStopping child processes...")
        for p in list(_worker_processes):
            try:
                if p.is_alive() and p.pid:
                    os.kill(p.pid, signal.SIGINT)
            except Exception:
                pass
        
        deadline = time.time() + 8
        for p in list(_worker_processes):
            remaining = max(0.0, deadline - time.time())
            try:
                p.join(timeout=remaining)
            except Exception:
                pass
        
        for p in list(_worker_processes):
            try:
                if p.is_alive():
                    p.terminate()
            except Exception:
                pass
        
        for p in list(_worker_processes):
            try:
                p.join(timeout=2)
            except Exception:
                pass
        
        _worker_processes.clear()
        print("Child processes stopped")

    if _runner is None:
        return

    print("\nCleaning up resources...")

    # Run async cleanup in sync context
    try:
        # Try to get current event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # If event loop is running, create task
            asyncio.ensure_future(_runner.cleanup())
        else:
            # Otherwise create new event loop for cleanup
            asyncio.run(_runner.cleanup())
    except Exception as e:
        print(f"Error during cleanup: {e}")
        # Try synchronous cleanup
        try:
            rm = _runner.resource_manager
            for sandbox in list(rm._sandboxes.values()):
                try:
                    sandbox.kill()
                except Exception:
                    pass
        except Exception:
            pass

    print("Resource cleanup complete")


def main() -> None:
    """Entry function"""
    global _runner

    def signal_handler(signum: int, frame: Optional[FrameType]) -> None:
        sig_name = signal.Signals(signum).name
        print(f"\nReceived {sig_name} signal, exiting...")
        _sync_cleanup()
        sys.exit(0)

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Register atexit handler (called on normal exit)
    import atexit
    atexit.register(_sync_cleanup)

    asyncio.run(main_async())


if __name__ == "__main__":
    main()
