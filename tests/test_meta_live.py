"""Explicit read-only Meta preflight. This module never publishes content."""
import os

import pytest

from fb_news_autopilot.facebook.auth import run_preflight


pytestmark = pytest.mark.meta_live


@pytest.mark.skipif(os.getenv('META_LIVE_TESTS') != '1',
                    reason='set META_LIVE_TESTS=1 for read-only Meta preflight')
def test_live_meta_preflight_is_read_only_and_configured():
    result = run_preflight()
    assert result.ok, result.error_category
