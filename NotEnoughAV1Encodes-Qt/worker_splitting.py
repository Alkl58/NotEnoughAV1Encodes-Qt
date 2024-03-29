"""
This script splits the video into n-seconds long chunks.

Author: Alkl58
Date: 05.03.2021
"""
import subprocess
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot


class WorkerSplitting(QObject):
    """
    WorkerSplitting Class

    Signals
    ----------
    finished : emit a signal if work is finished
    """
    finished = pyqtSignal()
    @pyqtSlot()
    def run(self, video_input, video_codec, seg_time, splitting_output, ffmpeg_path):
        """
        Attributes
        ----------
        video_input : string - path of the video input file
        video_codec : string - video codec for reencoding while splitting (x264, utvideo, ffv1)
        seg_time : int as string - chunk length in seconds
        splitting_output : string - path of the chunked video output
        ffmpeg_path : path to ffmpeg
        """
        cmd = "\"" + ffmpeg_path + "\"" + " -i " + "\"" + video_input + "\"" + " -hide_banner -loglevel 32 -map_metadata -1 -c:v " + video_codec + " -f segment -segment_time " + seg_time + " \"" + splitting_output + "\""
        subprocess.call(cmd, shell=True)
        self.finished.emit()
