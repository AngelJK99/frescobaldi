# This file is part of the qpopplerview package.
#
# Copyright (c) 2010, 2011 by Wilbert Berendsen
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
Caching of generated pixmaps.
"""

import time
import weakref
import popplerqt4

from PyQt4.QtCore import QThread
from PyQt4.QtGui import QPixmap

from . import render
from . import rectangles


__all__ = ['maxsize', 'setmaxsize', 'pixmap', 'generate', 'clear', 'links', 'wait', 'options']


_cache = weakref.WeakKeyDictionary()
_schedulers = weakref.WeakKeyDictionary()
_options = weakref.WeakKeyDictionary()
_links = weakref.WeakKeyDictionary()


# cache size
_maxsize = 104857600 # 100M
_currentsize = 0

_globaloptions = None


def setmaxsize(maxsize):
    """Sets the maximum cache size in Megabytes."""
    global _maxsize
    _maxsize = maxsize * 1048576
    purge()
    

def maxsize():
    """Returns the maximum cache size in Megabytes."""
    return _maxsize / 1048576


def clear(document=None):
    """Clears the whole cache or the cache for the given Poppler.Document."""
    if document:
        try:
            del _cache[document]
        except KeyError:
            pass
    else:
        _cache.clear()
        global _currentsize
        _currentsize = 0


def pixmap(page, exact=True):
    """Returns a rendered pixmap for given Page if in cache.
    
    If exact is True (default), the function returns None if the exact size was
    not in the cache. If exact is False, the function may return a temporary
    rendering of the page of a different size, if that was available.
    
    """
    document = page.document()
    pageKey = (page.pageNumber(), page.rotation())
    sizeKey = (page.width(), page.height())
    
    if exact:
        try:
            entry = _cache[document][pageKey][sizeKey]
        except KeyError:
            return
        else:
            entry[1] = time.time()
            return entry[0]
    try:
        sizes = _cache[document][pageKey].keys()
    except KeyError:
        return
    # find the closest size (assuming aspect ratio has not changed)
    if sizes:
        sizes.sort(key=lambda s: abs(1 - s[0] / float(page.width())))
        return _cache[document][pageKey][sizes[0]][0]


def generate(page):
    """Schedule a pixmap to be generated for the cache."""
    # Poppler-Qt4 crashes when different pages from a Document are rendered at the same time,
    # so we schedule them to be run in sequence.
    document = page.document()
    try:
        scheduler = _schedulers[document]
    except KeyError:
        scheduler = _schedulers[document] = Scheduler()
    scheduler.schedulejob(page)


def add(pixmap, document, pageNumber, rotation, width, height):
    """(Internal) Adds a pixmap to the cache."""
    pageKey = (pageNumber, rotation)
    sizeKey = (width, height)
    byteCount = width * height * pixmap.depth() / 8
    _cache.setdefault(document, {}).setdefault(pageKey, {})[sizeKey] = [pixmap, time.time(), byteCount]
    
    # maintain cache size
    global _maxsize, _currentsize
    _currentsize += byteCount
    if _currentsize > _maxsize:
        purge()


def purge():
    """Removes old pixmaps from the cache to limit the space used.
    
    (Not necessary to call, as the cache will monitor its size automatically.)
    
    """
    # make a list of the images, sorted on time, newest first
    pixmaps = iter(sorted((
        (time, document, pageKey, sizeKey, byteCount)
            for document, pageKeys in _cache.items()
            for pageKey, sizeKeys in pageKeys.items()
            for sizeKey, (pixmap, time, byteCount) in sizeKeys.items()),
                reverse=True))

    # sum the size of the newest images
    global _maxsize, _currentsize
    byteCount = 0
    for item in pixmaps:
        byteCount += item[4]
        if byteCount > _maxsize:
            break
    _currentsize = byteCount
    # delete the other images
    for time, document, pageKey, sizeKey, byteCount in pixmaps:
        del _cache[document][pageKey][sizeKey]


def links(page):
    """Returns a position-searchable list of the links in the page."""
    document, pageNumber = page.document(), page.pageNumber()
    try:
        return _links[document][pageNumber]
    except KeyError:
        wait(document)
        links = rectangles.Rectangles(document.page(pageNumber).links(),
                                      lambda link: link.linkArea().normalized().getCoords())
        _links.setdefault(document, {})[pageNumber] = links
        return links


def wait(document, msec=None):
    """Blocks if a thread is rendering an image from the given Poppler.Document.
    
    Returns immediately if no thread is running.
    Returns false if msec milliseconds have elapsed and the thread is still running.
    
    Use this if you are calling certain things like rendering or requesting the links of a
    Poppler.Page. This is needed to avoid crashes in Poppler.
    
    """
    try:
        thread = _schedulers[document]._running
    except KeyError:
        return True
    if thread:
        return thread.wait(msec) if msec is not None else thread.wait()
    return True


def options(document=None):
    """Returns a RenderOptions object for a document or the global one if no document is given."""
    global _globaloptions, _options
    if document:
        try:
            return _options[document]
        except KeyError:
            result = _options[document] = render.RenderOptions()
            return result
    if not _globaloptions:
        _globaloptions = render.RenderOptions()
        # enable antialiasing by default
        _globaloptions.setRenderHint(popplerqt4.Poppler.Document.Antialiasing |
                                     popplerqt4.Poppler.Document.TextAntialiasing)
    return _globaloptions


def setoptions(options, document=None):
    """Sets a RenderOptions instance for the given document or as the global one if no document is given.
    
    Use None for the options to unset (delete) the options.
    
    """
    global _globaloptions, _options
    if not document:
        _globaloptions = options
    elif options:
        _options[document] = options
    else:
        try:
            del _options[document]
        except KeyError:
            pass


class Scheduler(object):
    """Manages running rendering jobs in sequence for a Document."""
    def __init__(self):
        self._schedule = []     # order
        self._jobs = {}         # jobs on key
        self._running = None
        
    def schedulejob(self, page):
        """Creates or retriggers an existing Job.
        
        The page's update() method will be called when the Job has completed.
        
        """
        # uniquely identify the image to be generated
        key = (page.pageNumber(), page.rotation(), page.width(), page.height())
        try:
            job = self._jobs[key]
        except KeyError:
            job = self._jobs[key] = Job(page)
            job.key = key
        else:
            self._schedule.remove(job)
            job.notify(page)
        self._schedule.append(job)
        self.checkStart()
        
    def checkStart(self):
        """Starts a job if none is running and at least one is waiting."""
        if self._schedule and not self._running:
            job = self._schedule[-1]
            document = job.document()
            if document:
                self._running = Runner(self, document, job)
            else:
                self.done(job)
            
    def done(self, job):
        """Called when the job has completed."""
        del self._jobs[job.key]
        self._schedule.remove(job)
        self._running = None
        for page in job.pages():
            page.update()
        self.checkStart()


class Job(object):
    """Simply contains data needed to create an image later."""
    def __init__(self, page):
        self._pages = []
        self.document = weakref.ref(page.document())
        self.pageNumber = page.pageNumber()
        self.rotation = page.rotation()
        self.width = page.width()
        self.height = page.height()
        self.notify(page)
        
    def notify(self, page):
        """Add a Page to the list to be notified when the job has completed."""
        pageref = weakref.ref(page)
        if pageref not in self._pages:
            self._pages.append(pageref)
        
    def pages(self):
        """Yields the pages that want to update() when this Job is done."""
        for pageref in self._pages:
            page = pageref()
            if page:
                yield page


class Runner(QThread):
    """Immediately runs a Job in a background thread."""
    def __init__(self, scheduler, document, job):
        super(Runner, self).__init__()
        self.scheduler = scheduler
        self.job = job
        self.document = document # keep reference now so that it does not die during this thread
        self.finished.connect(self.slotFinished)
        self.start()
        
    def run(self):
        """Main method of this thread, called by Qt on start()."""
        page = self.document.page(self.job.pageNumber)
        pageSize = page.pageSize()
        if self.job.rotation & 1:
            pageSize.transpose()
        xres = 72.0 * self.job.width / pageSize.width()
        yres = 72.0 * self.job.height / pageSize.height()
        options().write(self.document)
        options(self.document).write(self.document)
        self.image = page.renderToImage(xres, yres, 0, 0, self.job.width, self.job.height, self.job.rotation)
        
    def slotFinished(self):
        """Called when the thread has completed."""
        pixmap = QPixmap.fromImage(self.image)
        add(pixmap, self.document, self.job.pageNumber, self.job.rotation, self.job.width, self.job.height)
        self.scheduler.done(self.job)


