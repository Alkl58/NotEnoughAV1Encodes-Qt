"""
This script uses ffmpeg to encode audio.

Author: Alkl58
Date: 05.03.2021
"""
import subprocess
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot


class WorkerAudio(QObject):
    """
    WorkerAudio Class

    Signals
    ----------
    finished : emit a signal if work is finished
    """
    finished = pyqtSignal()
    @pyqtSlot()
    def run(self, video_input, audio_codec, audio_output, ffmpeg_path):
        """
        Attributes
        ----------
        video_input : string - path of the video input file
        audio_codec : list - audio encoding parameters
        audio_output : string - path of the audio output
        ffmpeg_path : path to ffmpeg
        """
        cmd = "\"" + ffmpeg_path + "\" -i \"" + video_input + "\" -map_metadata -1 -vn -sn " + audio_codec + " \"" + audio_output + "\""
        _ = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,universal_newlines=True, shell=True)

        self.finished.emit()
