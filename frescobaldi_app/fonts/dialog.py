# This file is part of the Frescobaldi project, http://www.frescobaldi.org/
#
# Copyright (c) 2008 - 2014 by Wilbert Berendsen
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
# See http://www.gnu.org/licenses/ for more information.


"""
Show a dialog with available text and music fonts.
"""

from PyQt5.QtCore import (
    QSettings,
    QSize,
    Qt,
)
from PyQt5.QtWidgets import (
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import app
import documentinfo
import log
import qutil
import widgets.dialog
import fonts

from . import (
    textfonts,
    musicfonts,
    fontcommand,
    preview
)


def show_fonts_dialog(mainwin):
    """
    Display a dialog with the available fonts of LilyPond specified by info.
    """
    dlg = FontsDialog(mainwin)
    qutil.saveDialogSize(
        dlg, "engrave/tools/available-fonts/dialog/size", QSize(640, 400)
    )
    dlg.show()


class FontsDialog(widgets.dialog.Dialog):
    """Dialog to show available fonts"""

    selected_fonts = {
        'music': 'emmentaler',
        'brace': 'emmentaler',
        # TODO: Make these configurable, for now
        # simply write in LilyPond's default fonts.
        'roman': 'TeXGyre Schola',
        'sans': 'TeXGyre Heros',
        'typewriter': 'TeXGyre Cursor'
    }

    def __init__(self, parent):
        super(FontsDialog, self).__init__(
            parent,
            buttons=('restoredefaults', 'close',),
        )

        # Info about the current document's LilyPond version
        self.info = documentinfo.lilyinfo(parent.currentDocument())
        self.available_fonts = fonts.available(self.info)

        # Notation fonts (and preview) are limited to LilyPond >= 2.19.12
        self.show_music = self.info.version() >= (2, 19, 12)

        self.reloadButton = self._buttonBox.button(
            QDialogButtonBox.RestoreDefaults)
        self.reloadButton.setEnabled(False)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowModality(Qt.NonModal)

        self.tabWidget = QTabWidget(self)
        self.preview_pane = preview.FontsPreviewWidget(self)
        self.preview_pane.starting_up = True

        self.splitter = QSplitter()
        self.splitter.setOrientation(Qt.Horizontal)
        self.splitter.addWidget(self.tabWidget)
        if self.show_music:
            self.splitter.addWidget(self.preview_pane)
        self.setMainWidget(self.splitter)

        app.qApp.setOverrideCursor(Qt.WaitCursor)
        self.createTabs()

        app.translateUI(self)
        self.loadSettings()

        self.connectSignals()
        if self.available_fonts.text_fonts().is_loaded():
            self.populate_widgets()
        else:
            self.tabWidget.insertTab(0, self.logTab, _("LilyPond output"))
            self.tabWidget.setCurrentIndex(0)
            self.font_tree_tab.display_waiting()
            self.available_fonts.text_fonts().load_fonts(self.logWidget)
        app.qApp.restoreOverrideCursor()
        self.preview_pane.starting_up = False
        self.preview_pane.show_sample()

    def createTabs(self):

        def create_log():
            # Show original log
            self.logTab = QWidget()
            self.logWidget = log.Log(self.logTab)
            self.logLabel = QLabel()
            logLayout = QVBoxLayout()
            logLayout.addWidget(self.logLabel)
            logLayout.addWidget(self.logWidget)
            self.logTab.setLayout(logLayout)

        create_log()
        # Show Text Font results
        # (Initially don't actually show it, only after compilation)
        self.font_tree_tab = textfonts.TextFontsWidget(self.available_fonts)

        if self.show_music:
            # Show installed notation fonts
            self.music_tree_tab = (
                musicfonts.MusicFontsWidget(self.available_fonts, self)
            )
            self.tabWidget.addTab(self.music_tree_tab, _("Music Fonts"))

        # Configure the resulting font command
        self.font_command_tab = fontcommand.FontCommandWidget(self)
        self.font_command_tab.invalidate_command()
        self.tabWidget.addTab(self.font_command_tab, _("Font Command"))

        # Show various fontconfig information
        self.misc_tree_tab = textfonts.MiscFontsInfoWidget(self.available_fonts)
        self.tabWidget.addTab(self.misc_tree_tab, _("Miscellaneous"))

    def connectSignals(self):
        self.available_fonts.text_fonts().loaded.connect(self.text_fonts_loaded)
        self.finished.connect(self.saveSettings)
        self.finished.connect(self.preview_pane.musicFontPreview.cleanup)
        self.reloadButton.clicked.connect(self.reload)
        if self.show_music:
            mtt = self.music_tree_tab
            mtt.button_install.clicked.connect(
                self.install_music_fonts)

    def translateUI(self):
        self.setWindowTitle(app.caption(_("Document Fonts")))
        self.reloadButton.setText(_("&Reload"))
        self.logLabel.setText(_("LilyPond output of -dshow-available-options"))

    def loadSettings(self):
        s = QSettings()
        s.beginGroup('available-fonts-dialog')

        # Text font tab
        self.load_font_tree_column_width(s)

        # Preview
        if self.show_music:
            self.preview_pane.loadSettings()

        # Music font tab
        # TODO: The following doesn't work so we can't restore
        # the layout of the splitter yet.
#        self.musicFontsSplitter.restoreState(
#            s.value('music-font-splitter-sizes').toByteArray()
#        )

    def saveSettings(self):
        s = QSettings()
        s.beginGroup('available-fonts-dialog')

        # Text font tab
        s.setValue('col-width', self.font_tree_tab.tree_view.columnWidth(0))

        # Preview
        if self.show_music:
            self.preview_pane.saveSettings()

        # Dialog layout
        s.setValue('music-fonts-splitter-sizes', self.splitter.saveState())

    def font_cmd(self, approach=None):
        """Return the font setting command as shown in the Font Command tab."""
        approach = approach or self.font_command_tab.approach
        return self.font_command_tab.command(approach)

    def font_full_cmd(self, approach=None):
        """Return the "full" command with all properties/fonts."""
        approach = approach or self.font_command_tab.approach
        return self.font_command_tab.full_cmd(approach)

    def install_music_fonts(self):
        """'Install' music fonts from a directory (structure) by
        linking fonts into the LilyPond installation's font
        directories (otf and svg)."""

        dlg = QFileDialog(self)
        dlg.setFileMode(QFileDialog.Directory)
        if not dlg.exec():
            return

        installed = self.available_fonts.music_fonts()
        root_dir = dlg.selectedFiles()[0]
        from . import musicfonts
        repo = musicfonts.MusicFontRepo(root_dir)
        repo.flag_for_install(installed)

        # QUESTION: Do we need a message dialog to confirm/cancel installation?
        # repo.installable_fonts.item_model() is an item model like the one
        # we use for the music font display, but contains only the installable
        # font entries.

        try:
            repo.install_flagged(installed)
        except musicfonts.MusicFontPermissionException as e:
            msg_box = QMessageBox()
            msg_box.setText(_("Fonts could not be installed!"))
            msg_box.setInformativeText(
            _("Installing fonts in the LilyPond installation " +
              "appears to require administrator privileges on " +
              "your system and can unfortunately not be handled " +
              "by Frescobaldi,"))
            msg_box.setDetailedText("{}".format(e))
            msg_box.exec()

    def load_font_tree_column_width(self, s):
        """Load column widths for fontTreeView,
        factored out because it has to be done upon reload too."""
        self.font_tree_tab.tree_view.setColumnWidth(0, int(s.value('col-width', 200)))

    def populate_widgets(self):
        """Populate widgets."""
        self.tabWidget.insertTab(0, self.font_tree_tab, _("Text Fonts"))
        self.tabWidget.setCurrentIndex(0)
        self.load_font_tree_column_width(QSettings())
        self.font_tree_tab.display_count()
        self.font_tree_tab.refresh_filter_edit()
        self.font_tree_tab.filter_edit.setFocus()
        self.reloadButton.setEnabled(True)

    def reload(self):
        """Refresh font list by running LilyPond"""
        self.tabWidget.removeTab(0)
        self.tabWidget.insertTab(0, self.logTab, _("LilyPond output"))
        self.tabWidget.setCurrentIndex(0)
        self.logWidget.clear()
        # We're connected to the 'loaded' signal
        self.available_fonts.text_fonts().load_fonts(self.logWidget)

    def text_fonts_loaded(self):
        """We don't want to keep the LilyPond log open."""
        self.tabWidget.removeTab(0)
        self.populate_widgets()