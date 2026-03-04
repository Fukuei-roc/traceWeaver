#!/usr/bin/env python3
"""
Advanced Playwright Network Recorder - Manual Control Version

A manually controlled browser recorder for HTTP replay and AI-assisted debugging.
Allows human-operated browser with selective network activity recording.

Usage:
    pip install playwright
    playwright install
    python advanced_record_manual.py

Commands:
    start   - Enable recording
    stop    - Disable recording
    save    - Save storage_state.json
    mark    - Insert timestamped marker (e.g., "mark Login clicked")
    quit    - Save everything and exit
"""

import json
import os
import sys
import platform
import uuid
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from playwright.sync_api import (
    sync_playwright,
    Browser,
    BrowserContext,
    Page,
    Request,
    Response,
)

# ============================================================================
# Configuration
# ============================================================================

# All resource types to record (empty = all types)
# Options: "xhr", "fetch", "document", "stylesheet", "image", "script", "font", "websocket", "other"
RECORD_RESOURCE_TYPES = ()  # Empty tuple = record all types

# Maximum response body size to capture inline (bytes)
MAX_INLINE_BODY_SIZE = 512 * 1024  # 512KB

# ============================================================================
# Artifact Collector
# ============================================================================

class ArtifactCollector:
    """Collects and saves debugging artifacts during browser session."""
    
    def __init__(self, artifacts_dir: Path):
        self.artifacts_dir = artifacts_dir
        self.run_dir = artifacts_dir / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        self.screenshots_dir = self.run_dir / "screenshots"
        self.dom_dir = self.run_dir / "dom"
        
        # File handles for JSONL logging
        self.network_log_file: Optional[Any] = None
        self.console_log_file: Optional[Any] = None
        self.pageerror_log_file: Optional[Any] = None
        self.requestfailed_log_file: Optional[Any] = None
        
        # Markers for timeline
        self.markers: list = []
        
        # Thread lock for file writing
        self._lock = threading.Lock()
        
    def setup(self) -> None:
        """Create directory structure and open file handles."""
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.dom_dir.mkdir(parents=True, exist_ok=True)
        
        # Open JSONL files for streaming logs
        self.network_log_file = open(
            self.run_dir / "network_log.jsonl", "w", encoding="utf-8"
        )
        self.console_log_file = open(
            self.run_dir / "console.jsonl", "w", encoding="utf-8"
        )
        self.pageerror_log_file = open(
            self.run_dir / "pageerror.jsonl", "w", encoding="utf-8"
        )
        self.requestfailed_log_file = open(
            self.run_dir / "requestfailed.jsonl", "w", encoding="utf-8"
        )
        
    def close(self) -> None:
        """Close all file handles."""
        for f in [
            self.network_log_file,
            self.console_log_file,
            self.pageerror_log_file,
            self.requestfailed_log_file,
        ]:
            if f:
                try:
                    f.close()
                except Exception:
                    pass
                
    def get_run_dir(self) -> Path:
        """Return the run directory path."""
        return self.run_dir
    
    # ------------------------------------------------------------------------
    # Network Logging
    # ------------------------------------------------------------------------
    
    def log_network(self, request: Request, response: Optional[Response]) -> None:
        """Log a network request/response pair."""
        if not self.network_log_file:
            return
            
        try:
            # Build request data
            req_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "url": request.url,
                "method": request.method,
                "resource_type": request.resource_type,
                "headers": dict(request.headers),
            }
            
            # Add post data if present
            if request.post_data:
                try:
                    req_data["post_data"] = request.post_data.decode("utf-8")
                except Exception:
                    req_data["post_data"] = "<binary or decode failed>"
                    
            # Build response data
            if response:
                res_data = {
                    "status": response.status,
                    "status_text": response.status_text,
                    "headers": dict(response.headers),
                }
                
                # Try to capture response body
                try:
                    body = response.body()
                    if body and len(body) <= MAX_INLINE_BODY_SIZE:
                        # Try to decode as text/json
                        try:
                            res_data["body"] = body.decode("utf-8")
                            res_data["body_size"] = len(body)
                        except UnicodeDecodeError:
                            res_data["body"] = "<binary data>"
                            res_data["body_size"] = len(body)
                            # Save binary body to file
                            body_file = self.run_dir / "response_bodies" / f"{uuid.uuid4().hex}.bin"
                            body_file.parent.mkdir(exist_ok=True)
                            body_file.write_bytes(body)
                            res_data["body_file"] = str(body_file)
                    else:
                        res_data["body_size"] = len(body) if body else 0
                        res_data["body"] = "<too large to capture>" if body else "<empty>"
                except Exception as e:
                    res_data["body_error"] = str(e)
                    
                req_data["response"] = res_data
            else:
                req_data["response"] = None
                
            # Write to JSONL (thread-safe)
            with self._lock:
                self.network_log_file.write(json.dumps(req_data, ensure_ascii=False) + "\n")
                self.network_log_file.flush()
            
        except Exception as e:
            print(f"[ERROR] Failed to log network: {e}", file=sys.stderr)
            
    # ------------------------------------------------------------------------
    # Console Logging
    # ------------------------------------------------------------------------
    
    def log_console(self, msg) -> None:
        """Log console message."""
        if not self.console_log_file:
            return
            
        try:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": msg.type,
                "text": msg.text,
                "location": f"{msg.location.get('url', '')}:{msg.location.get('lineNumber', 0)}",
            }
            with self._lock:
                self.console_log_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
                self.console_log_file.flush()
        except Exception as e:
            print(f"[ERROR] Failed to log console: {e}", file=sys.stderr)
            
    # ------------------------------------------------------------------------
    # Page Error Logging
    # ------------------------------------------------------------------------
    
    def log_pageerror(self, error: Exception) -> None:
        """Log uncaught exception."""
        if not self.pageerror_log_file:
            return
            
        try:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(error),
                "type": type(error).__name__,
            }
            with self._lock:
                self.pageerror_log_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
                self.pageerror_log_file.flush()
        except Exception as e:
            print(f"[ERROR] Failed to log pageerror: {e}", file=sys.stderr)
            
    # ------------------------------------------------------------------------
    # Failed Request Logging
    # ------------------------------------------------------------------------
    
    def log_requestfailed(self, request: Request) -> None:
        """Log failed request."""
        if not self.requestfailed_log_file:
            return
            
        try:
            failure = request.failure
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "url": request.url,
                "method": request.method,
                "resource_type": request.resource_type,
                "failure": failure.error_text if failure else "Unknown",
            }
            with self._lock:
                self.requestfailed_log_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
                self.requestfailed_log_file.flush()
        except Exception as e:
            print(f"[ERROR] Failed to log requestfailed: {e}", file=sys.stderr)
            
    # ------------------------------------------------------------------------
    # Markers
    # ------------------------------------------------------------------------
    
    def add_marker(self, message: str) -> None:
        """Add a timestamped marker."""
        marker = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": message,
        }
        self.markers.append(marker)
        print(f"[MARKER] {marker['timestamp']}: {message}")
        
    # ------------------------------------------------------------------------
    # Screenshots
    # ------------------------------------------------------------------------
    
    def screenshot(self, name: str, page: Page) -> None:
        """Capture screenshot."""
        try:
            path = self.screenshots_dir / f"{name}.png"
            page.screenshot(path=path, full_page=False)
            print(f"[SCREENSHOT] Saved: {path}")
        except Exception as e:
            print(f"[ERROR] Failed to capture screenshot: {e}", file=sys.stderr)
            
    # ------------------------------------------------------------------------
    # DOM Snapshot
    # ------------------------------------------------------------------------
    
    def save_dom(self, page: Page) -> None:
        """Save full page HTML."""
        try:
            html = page.content()
            path = self.dom_dir / "page.html"
            path.write_text(html, encoding="utf-8")
            print(f"[DOM] Saved: {path}")
        except Exception as e:
            print(f"[ERROR] Failed to save DOM: {e}", file=sys.stderr)
            
    # ------------------------------------------------------------------------
    # Storage State
    # ------------------------------------------------------------------------
    
    def save_storage_state(self, context: BrowserContext) -> Optional[Path]:
        """Save browser storage state."""
        try:
            path = self.run_dir / "storage_state.json"
            context.storage_state(path=path)
            print(f"[STORAGE] Saved: {path}")
            return path
        except Exception as e:
            print(f"[ERROR] Failed to save storage state: {e}", file=sys.stderr)
            return None
            
    # ------------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------------
    
    def save_metadata(
        self,
        browser: Browser,
        playwright_version: str,
        viewport: dict,
    ) -> None:
        """Save run metadata."""
        try:
            # Get browser version
            browser_version = browser.version
            
            meta = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "run_id": self.run_dir.name,
                "os": platform.system(),
                "os_version": platform.version(),
                "python_version": platform.python_version(),
                "playwright_version": playwright_version,
                "browser": browser.browser_type.name,
                "browser_version": browser_version,
                "viewport": viewport,
                "headless": False,  # Always visible for manual control
                "timezone": str(datetime.now(timezone.utc).astimezone().tzinfo),
                "locale": "en-US",
                "markers": self.markers,
            }
            
            path = self.run_dir / "run_meta.json"
            path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"[META] Saved: {path}")
            
        except Exception as e:
            print(f"[ERROR] Failed to save metadata: {e}", file=sys.stderr)


# ============================================================================
# Network Recorder
# ============================================================================

class NetworkRecorder:
    """Manually controlled network recorder with rich artifact collection."""
    
    def __init__(self, artifacts_dir: str = "artifacts"):
        self.artifacts_dir = Path(artifacts_dir)
        self.collector: Optional[ArtifactCollector] = None
        
        # Playwright objects
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        
        # Recording state
        self.is_recording = False
        
        # Paths for trace and HAR
        self.trace_path: Optional[Path] = None
        self.har_path: Optional[Path] = None
        
    def start(self) -> None:
        """Initialize Playwright and launch browser."""
        print("[INIT] Starting Playwright Network Recorder...")
        
        # Setup collector
        self.collector = ArtifactCollector(self.artifacts_dir)
        self.collector.setup()
        
        # Launch Playwright
        self.playwright = sync_playwright().start()
        
        # Get Playwright version
        try:
            from importlib.metadata import version
            pw_version = version("playwright")
        except Exception:
            pw_version = "unknown"
        print(f"[INFO] Playwright version: {pw_version}")
        
        # Setup paths
        self.trace_path = self.collector.get_run_dir() / "trace.zip"
        self.har_path = self.collector.get_run_dir() / "trace.har"
        
        # Launch browser
        self.browser = self.playwright.chromium.launch(
            headless=False,  # Visible browser for manual control
            args=["--disable-popup-blocking"],
        )
        
        # Get viewport from default context
        default_context = self.browser.new_context()
        default_page = default_context.new_page()
        viewport = default_page.viewport_size or {"width": 1280, "height": 720}
        default_page.close()
        default_context.close()
        
        # Create context with HAR recording
        self.context = self.browser.new_context(
            viewport=viewport,
            record_har_path=str(self.har_path),
            record_har_content="attach",
        )
        
        # Create page
        self.page = self.context.new_page()
        
        # Setup event handlers
        self._setup_event_handlers()
        
        # Note: Tracing will start when 'start' command is issued
        
        # Save initial metadata
        self.collector.save_metadata(self.browser, pw_version, viewport)
        
        # Take initial screenshot
        self.collector.screenshot("initial", self.page)
        
        print(f"[INIT] Browser launched. Run directory: {self.collector.get_run_dir()}")
        print("[READY] Use 'start' to begin recording, 'stop' to stop.")
        print("[READY] Commands: start, stop, save, mark <msg>, quit")
        
    def _setup_event_handlers(self) -> None:
        """Setup page event handlers for network, console, errors."""
        
        # Console messages
        self.page.on("console", lambda msg: self._handle_console(msg))
        
        # Page errors
        self.page.on("pageerror", lambda err: self._handle_pageerror(err))
        
        # Request failures
        self.page.on("requestfailed", lambda req: self._handle_requestfailed(req))
        
        # Network responses (for recording)
        self.page.on("response", lambda res: self._handle_response(res))
        
    def _handle_console(self, msg) -> None:
        """Handle console message."""
        if self.collector:
            self.collector.log_console(msg)
            
    def _handle_pageerror(self, error: Exception) -> None:
        """Handle page error."""
        if self.collector:
            self.collector.log_pageerror(error)
            # Take error screenshot if recording
            if self.is_recording and self.page:
                self.collector.screenshot("error", self.page)
                
    def _handle_requestfailed(self, request: Request) -> None:
        """Handle failed request."""
        if self.collector:
            self.collector.log_requestfailed(request)
            
    def _handle_response(self, response: Response) -> None:
        """Handle network response - record if recording."""
        if not self.is_recording:
            return
            
        # Check if this is a high-value resource type (if configured)
        resource_type = response.request.resource_type
        if RECORD_RESOURCE_TYPES and resource_type not in RECORD_RESOURCE_TYPES:
            return
            
        # Get the request object
        request = response.request
        
        # Log the network interaction
        if self.collector:
            self.collector.log_network(request, response)
            
    # ------------------------------------------------------------------------
    # Recording Control
    # ------------------------------------------------------------------------
    
    def start_recording(self) -> None:
        """Enable recording mode."""
        if self.is_recording:
            print("[WARN] Already recording!")
            return
            
        self.is_recording = True
        
        # Start tracing with full capture
        try:
            self.context.tracing.stop()
        except Exception:
            pass  # Tracing not started yet, ignore
        
        self.context.tracing.start(
            screenshots=True,
            snapshots=True,
            sources=True,
        )
        
        # Screenshot on start
        if self.page and self.collector:
            self.collector.screenshot("start", self.page)
            
        print("[RECORDING] Started network recording")
        
    def stop_recording(self) -> None:
        """Disable recording mode."""
        if not self.is_recording:
            print("[WARN] Not recording!")
            return
            
        self.is_recording = False
        
        # Stop tracing and save
        if self.trace_path:
            try:
                self.context.tracing.stop(path=str(self.trace_path))
                print(f"[TRACE] Saved: {self.trace_path}")
            except Exception as e:
                print(f"[WARN] Could not save trace: {e}")
        
        # Screenshot on stop
        if self.page and self.collector:
            self.collector.screenshot("stop", self.page)
            self.collector.save_dom(self.page)
            
        print("[RECORDING] Stopped network recording")
        
    def save_storage(self) -> None:
        """Save storage state."""
        if self.context and self.collector:
            self.collector.save_storage_state(self.context)
            
    def mark(self, message: str) -> None:
        """Add a marker."""
        if self.collector:
            self.collector.add_marker(message)
            
    # ------------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------------
    
    def cleanup(self) -> None:
        """Cleanup resources."""
        print("[CLEANUP] Saving final state...")
        
        # Final storage save
        self.save_storage()
        
        # Update metadata with final markers
        if self.collector:
            meta_path = self.collector.get_run_dir() / "run_meta.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                meta["markers"] = self.collector.markers
                meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        
        # Close collector
        if self.collector:
            self.collector.close()
            
        # Close Playwright
        if self.playwright:
            self.playwright.stop()
            
        print("[CLEANUP] Done")


# ============================================================================
# CLI Interface
# ============================================================================

class CLI:
    """Interactive CLI for manual control."""
    
    def __init__(self, recorder: NetworkRecorder):
        self.recorder = recorder
        
    def run(self) -> None:
        """Run the CLI loop."""
        print("\n" + "=" * 60)
        print("  Playwright Network Recorder - Manual Control")
        print("=" * 60)
        print("\nCommands:")
        print("  start        - Begin recording network requests")
        print("  stop         - Stop recording and capture artifacts")
        print("  save         - Save storage state immediately")
        print("  mark <msg>   - Add timestamped marker")
        print("  quit         - Save everything and exit")
        print("=" * 60 + "\n")
        
        while True:
            try:
                # Get input
                cmd = input("> ").strip()
                
                if not cmd:
                    continue
                    
                # Parse command
                parts = cmd.split(None, 1)
                command = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""
                
                # Handle command
                if command == "start":
                    self.recorder.start_recording()
                    
                elif command == "stop":
                    self.recorder.stop_recording()
                    
                elif command == "save":
                    self.recorder.save_storage()
                    
                elif command == "mark":
                    if args:
                        self.recorder.mark(args)
                    else:
                        print("[ERROR] Usage: mark <message>")
                        
                elif command in ("quit", "exit", "q"):
                    self.recorder.cleanup()
                    print("\n[EXIT] Artifacts saved. Goodbye!")
                    break
                    
                else:
                    print(f"[ERROR] Unknown command: {command}")
                    print("Valid commands: start, stop, save, mark <msg>, quit")
                    
            except KeyboardInterrupt:
                print("\n[INTERRUPT] Use 'quit' to exit properly")
                self.recorder.cleanup()
                break
                
            except EOFError:
                break
                
        # Ensure cleanup
        self.recorder.cleanup()


# ============================================================================
# Main Entry Point
# ============================================================================

def main() -> None:
    """Main entry point."""
    # Create recorder
    recorder = NetworkRecorder(artifacts_dir="artifacts")
    
    try:
        # Start browser
        recorder.start()
        
        # Run CLI
        cli = CLI(recorder)
        cli.run()
        
    except Exception as e:
        print(f"[FATAL] {e}", file=sys.stderr)
        recorder.cleanup()
        raise


if __name__ == "__main__":
    main()
