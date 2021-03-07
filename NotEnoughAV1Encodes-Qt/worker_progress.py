"""
This script reads the progress of all ffmpeg instances.

Author: Alkl58
Date: 06.03.2021
"""
import os
import time
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

class WorkerProgress(QObject):
    """
    WorkerProgress

    Signals
    ----------
    progress : emits the progress of the subprogress in the run function
    finished : emits if the run function is finished
    """
    progress = pyqtSignal(int)
    finished = pyqtSignal()
    @pyqtSlot()
    def run(self, progress_path, mux_path):
        """
        Attributes
        ----------
        progress_path : path to where the log files are located
        """
        mux_file_not_written = True
        while mux_file_not_written:
            # Pulls the framecount every 2 seconds
            time.sleep(2)
            total_encoded_frames = 0

            for filename in os.listdir(progress_path):
                if filename.endswith(".log"):
                    try:
                        with open(os.path.join(progress_path, filename), 'r') as file_log:
                            lines = [line.rstrip() for line in file_log]
                        idx = [i for i, item in enumerate(lines) if item.startswith('frame')]
                        total_encoded_frames += int(lines[idx[-1]][6:])
                    except:
                        pass
            if os.path.isfile(mux_path):
                mux_file_not_written = False
            self.progress.emit(total_encoded_frames)
        self.finished.emit()

