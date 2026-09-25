"""
help_dialog.py
=============
The shared cheat-sheet popup - used by both the Config Editor's Help button and the main
module's Help section. Content lives in Resources/Html/<file>.html (static, extensible without
code); this file is only the window: a section-jump combo, a text search bar and the
read-only, copyable QTextBrowser.
"""

import os

import qt

from Resources.paths import HTML_DIR


def read_html_resource(filename):
    """Read one bundled HTML resource file (Resources/Html/<filename>) as text, or a short inline error message if it can't be read."""
    path = os.path.join(HTML_DIR, filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"<p>Could not load {filename}: {e}</p>"


def show_cheatsheet_dialog(parent, title, filename, sections):
    """Open Resources/Html/<filename> in a read-only, scrollable, copyable QTextBrowser popup, with a section-jump combo and a text search bar on top - jumping straight to a section or searching beats scrolling through a long page. `sections` is a list of (label, anchor) pairs; anchors match the <a name="..."> tags in the HTML file."""
    popup = qt.QDialog(parent)
    popup.setWindowTitle(title)
    popup.resize(700, 620)
    layout = qt.QVBoxLayout(popup)

    browser = qt.QTextBrowser()
    browser.setOpenExternalLinks(False)
    browser.setHtml(read_html_resource(filename))

    navRow = qt.QHBoxLayout()
    navRow.addWidget(qt.QLabel("Jump to:"))
    sectionCombo = qt.QComboBox()
    for label, _anchor in sections:
        sectionCombo.addItem(label)
    sectionCombo.connect(
        'currentIndexChanged(int)',
        lambda i: browser.scrollToAnchor(sections[i][1]) if 0 <= i < len(sections) else None)
    navRow.addWidget(sectionCombo)
    navRow.addStretch(1)
    layout.addLayout(navRow)

    findRow = qt.QHBoxLayout()
    findRow.addWidget(qt.QLabel("Find:"))
    findEdit = qt.QLineEdit()
    findEdit.setPlaceholderText("search this page...")

    def do_find(_checked=False):
        text = findEdit.text.strip()
        if text and not browser.find(text):
            browser.moveCursor(qt.QTextCursor.Start)   # wrap around to the top
            browser.find(text)

    findEdit.connect('returnPressed()', do_find)
    findRow.addWidget(findEdit)
    findNextBtn = qt.QPushButton("Find next")
    findNextBtn.setToolTip("Repeats the search, wrapping to the top once it reaches the end.")
    findNextBtn.connect('clicked(bool)', do_find)
    findRow.addWidget(findNextBtn)
    layout.addLayout(findRow)

    layout.addWidget(browser)
    closeBtn = qt.QPushButton("Close")
    closeBtn.connect('clicked(bool)', lambda checked=False: popup.close())
    layout.addWidget(closeBtn)
    popup.exec_()
