"""
This script calculates the framecount of the video source.

Author: Alkl58
Date: 06.03.2021
"""
import re
import subprocess
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

class WorkerFramecount(QObject):
    """
    WorkerFramecount

    Signals
    ----------
    framecount : emits the framecount of the subprogress in the run function
    finished : emits if the run function is finished
    """
    framecount = pyqtSignal(int)
    finished = pyqtSignal()
    @pyqtSlot()
    def run(self, video_input):
        """
        Attributes
        ----------
        video_input : path to video input
        """
        cmd="ffmpeg -i " + '\u0022' + video_input + '\u0022' + " -hide_banner -loglevel 32 -map 0:v:0 -f null -"
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,universal_newlines=True, shell=True)
        temp = []
        for line in process.stdout:
            temp.append(line)
        lines = [line.strip() for line in temp]
        idx = [i for i, item in enumerate(lines) if item.startswith('frame')]
        temp = lines[idx[-1]]
        result = re.search('frame=(.+?)fps=', str(temp))
        self.framecount.emit(int(result.group(1)))
        self.finished.emit()
