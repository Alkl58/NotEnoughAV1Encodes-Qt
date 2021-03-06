"""
This script is the main encoding worker class
which runs n-workers async in the threading model of qt.

Author: Alkl58
Date: 05.03.2021
"""
from multiprocessing.dummy import Pool
from functools import partial
from subprocess import call
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

class Worker(QObject):
    """
    Worker Class

    Signals
    ----------
    finished : returns if all work is finished
    """
    finished = pyqtSignal()
    @pyqtSlot()
    def run(self, pool_size, queue_first, queue_second):
        """
        Attributes
        ----------
        pool_size : sets the amount of workers
        queue_first : first pass queue list
        queue_second : second pass queue list
        """
        pool = Pool(pool_size)
        for i, _ in enumerate(pool.imap(partial(call, shell=True), queue_first)):  # Multi Threaded Encoding
            print("Finished Worker: " + str(i))
        for i, _ in enumerate(pool.imap(partial(call, shell=True), queue_second)):  # Multi Threaded Encoding
            print("Finished Worker: " + str(i))
        self.finished.emit()
