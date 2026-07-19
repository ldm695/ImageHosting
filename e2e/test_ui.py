"""Browser E2E tests for the key UI paths.

Black-box: drives the real page + real backend. No app.js changes needed.
"""
from playwright.sync_api import expect


def _upload(page, file_path):
    """Select a file and confirm the upload dialog."""
    page.set_input_files('#fileInput', file_path)
    page.locator('#uploadRenameDialog.active').wait_for()
    page.locator('#uploadRenameOk').click()


def test_page_loads_with_empty_state(page, live_server):
    page.goto(live_server)
    # Title chip + empty state visible, zero images.
    expect(page.locator('#emptyState')).to_be_visible()
    expect(page.locator('.md-card')).to_have_count(0)


def test_upload_shows_card(page, live_server, sample_png):
    page.goto(live_server)
    _upload(page, sample_png)
    expect(page.locator('.md-card')).to_have_count(1)
    expect(page.locator('.md-card__title')).to_contain_text('sample.png')


def test_upload_multiple_updates_count(page, live_server, make_named_png):
    page.goto(live_server)
    a = make_named_png('a.png')
    b = make_named_png('b.png', (200, 80, 80))
    page.set_input_files('#fileInput', [a, b])
    page.locator('#uploadRenameDialog.active').wait_for()
    page.locator('#uploadRenameOk').click()
    expect(page.locator('.md-card')).to_have_count(2)


def test_delete_removes_card(page, live_server, sample_png):
    page.goto(live_server)
    _upload(page, sample_png)
    expect(page.locator('.md-card')).to_have_count(1)

    # Reveal the card's action overlay, then delete.
    page.locator('.md-card').first.hover()
    page.locator('.md-card .md-icon-btn[data-action="delete"]').first.click()
    # Confirm dialog appears -> confirm.
    page.locator('#confirmDialog.active').wait_for()
    page.locator('#confirmOk').click()

    expect(page.locator('.md-card')).to_have_count(0)
    expect(page.locator('#emptyState')).to_be_visible()


def test_theme_switch_to_dark(page, live_server):
    page.goto(live_server)
    page.locator('#settingsBtn').click()
    page.locator('#settingsDialog.active').wait_for()
    # The real <input> is visually hidden (MD3 custom radio); click its label.
    page.locator('label.theme-radio:has(input[value="dark"])').click()
    page.locator('#settingsSave').click()
    # <html data-theme="dark"> after save.
    expect(page.locator('html')).to_have_attribute('data-theme', 'dark')
