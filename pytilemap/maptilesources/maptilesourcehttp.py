from __future__ import print_function, absolute_import

from qtpy.QtCore import Qt, Signal, Slot, QObject, QByteArray, QUrl, QThread
from qtpy.QtGui import QPixmap
from qtpy.QtNetwork import QNetworkRequest, QNetworkDiskCache, QNetworkAccessManager, \
    QNetworkReply

from .maptilesource import MapTileSource
from ..qtsupport import getQVariantValue, getCacheFolder

DEFAULT_CACHE_SIZE = 1024 * 1024 * 100


class MapTileHTTPLoader(QObject):

    tileLoaded = Signal(int, int, int, QByteArray)

    def __init__(self, cacheSize=DEFAULT_CACHE_SIZE, userAgent='(PyQt) TileMap 1.0', parent=None):
        QObject.__init__(self, parent=parent)
        self._manager = None
        self._cache = None
        self._cacheSize = cacheSize

        try:
            # Convert user agent to bytes
            userAgent = userAgent.encode()
        except:
            # no encode method exists. This hsould be the Python 2 case
            pass

        self._userAgent = userAgent
        self._tileInDownload = dict()

    @Slot(int, int, int, str)
    def loadTile(self, x, y, zoom, url):
        if self._manager is None:
            self._manager = QNetworkAccessManager(parent=self)
            self._manager.finished.connect(self.handleNetworkData)
            cache = QNetworkDiskCache()
            cacheDir = getCacheFolder()
            cache.setCacheDirectory(cacheDir)
            cache.setMaximumCacheSize(self._cacheSize)
            self._manager.setCache(cache)

        key = (x, y, zoom)
        url = QUrl(url)
        if key in self._tileInDownload:
            # Image is already in download... return
            return
        else:
            request = QNetworkRequest(url=url)
            request.setRawHeader(b'User-Agent', self._userAgent)
            request.setAttribute(QNetworkRequest.User, key)
            request.setAttribute(QNetworkRequest.CacheLoadControlAttribute, QNetworkRequest.PreferCache)
            self._tileInDownload[key] = self._manager.get(request)

        # print('In download:', len(self._tileInDownload))

    @Slot(QNetworkReply)
    def handleNetworkData(self, reply):
        tp = getQVariantValue(reply.request().attribute(QNetworkRequest.User))
        if tp in self._tileInDownload:
            del self._tileInDownload[tp]

        if not reply.error():
            data = reply.readAll()
            self.tileLoaded.emit(tp[0], tp[1], tp[2], data)
        reply.close()
        reply.deleteLater()

    @Slot()
    def abortRequest(self, x, y, zoom):
        p = (x, y, zoom)
        if p in self._tileInDownload:
            reply = self._tileInDownload[p]
            del self._tileInDownload[p]
            reply.close()
            reply.deleteLater()

    @Slot()
    def abortAllRequests(self):
        for x, y, zoom in list(self._tileInDownload.keys()):
            self.abortRequest(x, y, zoom)
        # print('In download:', len(self._tileInDownload))


class MapTileSourceHTTP(MapTileSource):

    requestTileLoading = Signal(int, int, int, str)
    abortTileLoading = Signal()

    def __init__(self, cacheSize=DEFAULT_CACHE_SIZE, userAgent='(PyQt) TileMap 1.2',
                 tileSize=256, minZoom=2, maxZoom=18, mapHttpLoader=None, parent=None):
        MapTileSource.__init__(self, tileSize=tileSize, minZoom=minZoom, maxZoom=maxZoom, parent=parent)

        self._thread = QThread(parent=self)

        if mapHttpLoader is not None:
            self._loader = mapHttpLoader
        else:
            self._loader = MapTileHTTPLoader(cacheSize=cacheSize, userAgent=userAgent)
        self._loader.moveToThread(self._thread)

        self.requestTileLoading.connect(self._loader.loadTile, Qt.QueuedConnection)
        self.abortTileLoading.connect(self._loader.abortAllRequests, Qt.QueuedConnection)
        self._loader.tileLoaded.connect(self.handleTileDataLoaded, Qt.QueuedConnection)

        self._thread.start()
        # self.destroyed.connect(self.close)

    @Slot()
    def close(self):
        self.abortTileLoading.emit()
        self._thread.terminate()

    def url(self, x, y, zoom):
        raise NotImplementedError()

    def requestTile(self, x, y, zoom):
        url = self.url(x, y, zoom)
        self.requestTileLoading.emit(x, y, zoom, url)
        return None

    @Slot(int, int, int, QByteArray)
    def handleTileDataLoaded(self, x, y, zoom, data):
        pix = QPixmap()
        pix.loadFromData(data)
        self.tileReceived.emit(x, y, zoom, pix)

    def abortAllRequests(self):
        self.abortTileLoading.emit()

    def imageFormat(self):
        return 'PNG'
