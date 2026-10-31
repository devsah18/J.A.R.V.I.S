"""Browser automation tool using Selenium WebDriver.

Provides programmatic control over Chrome (or Firefox) for:
- Navigation and page loading
- Content extraction (text, links, tables, specific elements)
- Form filling and interaction (click, type, select)
- Screenshots
- JavaScript execution
- Cookie/storage management
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from tools.base import ParamSpec, Risk, Tool, ToolResult

logger = logging.getLogger(__name__)

# Selenium imports are optional - tool degrades gracefully
try:
    from selenium import webdriver
    from selenium.common.exceptions import (
        NoSuchElementException,
        TimeoutException,
        WebDriverException,
    )
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.remote.webdriver import WebDriver
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        HAS_WDM = True
    except ImportError:
        HAS_WDM = False
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    webdriver = None
    WebDriver = None
    ChromeOptions = None
    ChromeService = None
    By = None
    Keys = None
    WebDriverWait = None
    EC = None
    NoSuchElementException = Exception
    TimeoutException = Exception
    WebDriverException = Exception
    ChromeDriverManager = None
    HAS_WDM = False


DEFAULT_TIMEOUT = 15
DEFAULT_IMPLICIT_WAIT = 3


class BrowserAutomationTool(Tool):
    name = "browser_auto"
    description = "Control a web browser: navigate, extract content, click, type, screenshot, run JavaScript."
    risk = Risk.MEDIUM
    params = (
        ParamSpec("action", "Action: navigate|extract|click|type|screenshot|execute_js|wait|close"),
        ParamSpec("url", "URL to navigate to (for navigate action)", required=False),
        ParamSpec("selector", "CSS/XPath selector for element actions", required=False),
        ParamSpec("text", "Text to type (for type action)", required=False),
        ParamSpec("script", "JavaScript to execute (for execute_js action)", required=False),
        ParamSpec("timeout", "Seconds to wait (default 15)", required=False),
        ParamSpec("attribute", "Attribute to extract (for extract action, default: text)", required=False),
        ParamSpec("path", "File path to save screenshot (for screenshot action)", required=False),
    )

    def __init__(self):
        self._driver: Optional[WebDriver] = None
        self._base_profile_dir: Optional[Path] = None

    def _ensure_driver(self) -> WebDriver:
        if not SELENIUM_AVAILABLE:
            raise RuntimeError(
                "Selenium not installed. Run: pip install selenium webdriver-manager"
            )
        if self._driver is None:
            self._driver = self._create_driver()
        return self._driver

    def _create_driver(self) -> WebDriver:
        options = ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1366,768")
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 VARSHA/1.0")
        # Uncomment for headless: options.add_argument("--headless=new")
        
        # Use persistent profile for session persistence
        if self._base_profile_dir is None:
            self._base_profile_dir = Path.home() / ".varsha" / "chrome_profile"
        self._base_profile_dir.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={self._base_profile_dir}")
        options.add_argument("--profile-directory=Default")

        service = None
        if HAS_WDM:
            try:
                service = ChromeService(ChromeDriverManager().install())
            except Exception as e:
                logger.warning("webdriver-manager failed, using system chromedriver: %s", e)
        
        driver = webdriver.Chrome(service=service, options=options)
        driver.implicitly_wait(DEFAULT_IMPLICIT_WAIT)
        driver.set_page_load_timeout(DEFAULT_TIMEOUT)
        return driver

    def run(
        self,
        action: str = "",
        url: str = "",
        selector: str = "",
        text: str = "",
        script: str = "",
        timeout: int = DEFAULT_TIMEOUT,
        attribute: str = "text",
        path: str = "",
        **kwargs,
    ) -> ToolResult:
        action = (action or "").strip().lower()
        
        if action == "navigate":
            return self._navigate(url, timeout)
        elif action == "extract":
            return self._extract(selector, attribute)
        elif action == "click":
            return self._click(selector, timeout)
        elif action == "type":
            return self._type(selector, text, timeout)
        elif action == "screenshot":
            return self._screenshot(path)
        elif action == "execute_js":
            return self._execute_js(script)
        elif action == "wait":
            return self._wait(selector, timeout)
        elif action == "close":
            return self._close()
        elif action == "get_cookies":
            return self._get_cookies()
        elif action == "set_cookies":
            return self._set_cookies(selector)  # selector = JSON string
        elif action == "get_title":
            return self._get_title()
        elif action == "get_url":
            return self._get_url()
        elif action == "back":
            return self._back()
        elif action == "forward":
            return self._forward()
        elif action == "refresh":
            return self._refresh()
        else:
            return ToolResult.failure(
                f"Unknown action '{action}'. Valid: navigate, extract, click, type, "
                "screenshot, execute_js, wait, close, get_cookies, set_cookies, "
                "get_title, get_url, back, forward, refresh"
            )

    def _navigate(self, url: str, timeout: int) -> ToolResult:
        if not url:
            return ToolResult.failure("URL required for navigate action")
        try:
            driver = self._ensure_driver()
            driver.set_page_load_timeout(timeout)
            driver.get(url)
            # Wait for page to be interactive
            WebDriverWait(driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            title = driver.title
            return ToolResult.success(
                f"Navigated to {url}. Title: {title}",
                url=url,
                title=title,
            )
        except TimeoutException:
            return ToolResult.failure(f"Page load timed out after {timeout}s: {url}")
        except WebDriverException as e:
            return ToolResult.failure(f"Navigation failed: {e}")

    def _extract(self, selector: str, attribute: str) -> ToolResult:
        if not selector:
            return ToolResult.failure("Selector required for extract action")
        try:
            driver = self._ensure_driver()
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if not elements:
                # Try XPath
                elements = driver.find_elements(By.XPATH, selector)
            if not elements:
                return ToolResult.failure(f"No elements found for selector: {selector}")
            
            results = []
            for el in elements:
                if attribute == "text":
                    val = el.text
                elif attribute == "html":
                    val = el.get_attribute("outerHTML")
                elif attribute == "href":
                    val = el.get_attribute("href")
                elif attribute == "src":
                    val = el.get_attribute("src")
                else:
                    val = el.get_attribute(attribute)
                if val:
                    results.append(val.strip())
            
            if not results:
                return ToolResult.failure("Elements found but no content extracted")
            
            return ToolResult.success(
                f"Extracted {len(results)} result(s)",
                results=results,
                count=len(results),
            )
        except Exception as e:
            return ToolResult.failure(f"Extraction failed: {e}")

    def _click(self, selector: str, timeout: int) -> ToolResult:
        if not selector:
            return ToolResult.failure("Selector required for click action")
        try:
            driver = self._ensure_driver()
            wait = WebDriverWait(driver, timeout)
            element = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
            element.click()
            return ToolResult.success(f"Clicked element: {selector}")
        except TimeoutException:
            return ToolResult.failure(f"Element not clickable within {timeout}s: {selector}")
        except NoSuchElementException:
            return ToolResult.failure(f"Element not found: {selector}")
        except Exception as e:
            return ToolResult.failure(f"Click failed: {e}")

    def _type(self, selector: str, text: str, timeout: int) -> ToolResult:
        if not selector:
            return ToolResult.failure("Selector required for type action")
        if text is None:
            text = ""
        try:
            driver = self._ensure_driver()
            wait = WebDriverWait(driver, timeout)
            element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, selector)))
            element.clear()
            element.send_keys(text)
            return ToolResult.success(f"Typed into {selector}", text=text)
        except TimeoutException:
            return ToolResult.failure(f"Element not visible within {timeout}s: {selector}")
        except NoSuchElementException:
            return ToolResult.failure(f"Element not found: {selector}")
        except Exception as e:
            return ToolResult.failure(f"Type failed: {e}")

    def _screenshot(self, path: str) -> ToolResult:
        try:
            driver = self._ensure_driver()
            if not path:
                path = str(Path.cwd() / "screenshot.png")
            driver.save_screenshot(path)
            return ToolResult.success(
                f"Screenshot saved to {path}",
                path=path,
            )
        except Exception as e:
            return ToolResult.failure(f"Screenshot failed: {e}")

    def _execute_js(self, script: str) -> ToolResult:
        if not script:
            return ToolResult.failure("Script required for execute_js action")
        try:
            driver = self._ensure_driver()
            result = driver.execute_script(script)
            return ToolResult.success(
                "JavaScript executed",
                result=result,
            )
        except Exception as e:
            return ToolResult.failure(f"JavaScript execution failed: {e}")

    def _wait(self, selector: str, timeout: int) -> ToolResult:
        if not selector:
            return ToolResult.failure("Selector required for wait action")
        try:
            driver = self._ensure_driver()
            wait = WebDriverWait(driver, timeout)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
            return ToolResult.success(f"Element appeared: {selector}")
        except TimeoutException:
            return ToolResult.failure(f"Element did not appear within {timeout}s: {selector}")

    def _close(self) -> ToolResult:
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None
        return ToolResult.success("Browser closed")

    def _get_cookies(self) -> ToolResult:
        try:
            driver = self._ensure_driver()
            cookies = driver.get_cookies()
            return ToolResult.success(f"Retrieved {len(cookies)} cookies", cookies=cookies)
        except Exception as e:
            return ToolResult.failure(f"Get cookies failed: {e}")

    def _set_cookies(self, cookies_json: str) -> ToolResult:
        try:
            driver = self._ensure_driver()
            cookies = json.loads(cookies_json)
            for cookie in cookies:
                driver.add_cookie(cookie)
            return ToolResult.success(f"Set {len(cookies)} cookies")
        except json.JSONDecodeError:
            return ToolResult.failure("Invalid JSON for cookies")
        except Exception as e:
            return ToolResult.failure(f"Set cookies failed: {e}")

    def _get_title(self) -> ToolResult:
        try:
            driver = self._ensure_driver()
            return ToolResult.success("Page title", title=driver.title)
        except Exception as e:
            return ToolResult.failure(f"Get title failed: {e}")

    def _get_url(self) -> ToolResult:
        try:
            driver = self._ensure_driver()
            return ToolResult.success("Current URL", url=driver.current_url)
        except Exception as e:
            return ToolResult.failure(f"Get URL failed: {e}")

    def _back(self) -> ToolResult:
        try:
            driver = self._ensure_driver()
            driver.back()
            return ToolResult.success("Navigated back")
        except Exception as e:
            return ToolResult.failure(f"Back failed: {e}")

    def _forward(self) -> ToolResult:
        try:
            driver = self._ensure_driver()
            driver.forward()
            return ToolResult.success("Navigated forward")
        except Exception as e:
            return ToolResult.failure(f"Forward failed: {e}")

    def _refresh(self) -> ToolResult:
        try:
            driver = self._ensure_driver()
            driver.refresh()
            return ToolResult.success("Page refreshed")
        except Exception as e:
            return ToolResult.failure(f"Refresh failed: {e}")

    def risk_for(self, **kwargs) -> Risk:
        action = (kwargs.get("action") or "").strip().lower()
        if action in ("click", "type", "execute_js", "set_cookies"):
            return Risk.HIGH
        if action in ("navigate", "screenshot", "extract", "close"):
            return Risk.MEDIUM
        return Risk.LOW